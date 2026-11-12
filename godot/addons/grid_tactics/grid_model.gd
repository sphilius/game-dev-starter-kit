# GridModel: the whole battle board as plain data. Every rule (move, attack, ability) lives here.
class_name GridModel
extends RefCounted
## "Pure data" means no nodes and no drawing: you can run a full battle in a test or a bot
## thousands of times a second. Presenters (2D or 3D) listen to the signals below and animate.
##
## Rules in short:
##   • Cells are Vector2i; (0,0) is the top-left. Walls and units block movement.
##   • A unit moves up to move_range steps along a free path (4 directions, no diagonals).
##   • A basic attack hits one unit whose distance is within attack_range_min..max.
##   • An ability is aimed at a cell within cast_range and hits every unit in its shape.
##   • Telegraphed attacks (GridUnit.intent) hit their cells later; see TacticsAI.

## A unit was placed on the board.
signal unit_added(unit: GridUnit)
## `path` lists every cell walked, start to end, so a presenter can animate step by step.
signal unit_moved(unit: GridUnit, path: Array[Vector2i])
## HP changed. amount > 0 is damage, < 0 is healing. `source` may be null.
signal unit_damaged(unit: GridUnit, amount: int, source: GridUnit)
signal unit_died(unit: GridUnit)
## A basic attack or ability was used on these cells (for swing/explosion effects).
signal action_used(unit: GridUnit, cells: Array[Vector2i], ability: AbilityData)
## A unit's telegraphed attack was set or cleared (redraw the danger markers).
signal intent_changed(unit: GridUnit)

var size := Vector2i(8, 8)
var units: Array[GridUnit] = []
var _blocked := {}                 # Vector2i -> true for wall cells
var _astar := AStarGrid2D.new()    # Godot's built-in grid pathfinder


## GridModel.new(Vector2i(8, 6)) makes an empty 8×6 board.
func _init(p_size := Vector2i(8, 8)) -> void:
	size = p_size
	_astar.region = Rect2i(Vector2i.ZERO, size)
	_astar.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_NEVER      # tactics grids move in 4 directions
	_astar.default_compute_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	_astar.default_estimate_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	_astar.update()                                             # must be called after changing region


# --- Board --------------------------------------------------------------------------------

## True when the cell is on the board.
func in_bounds(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < size.x and cell.y < size.y


## Marks a cell as a wall (or clears it).
func set_blocked(cell: Vector2i, blocked := true) -> void:
	if not in_bounds(cell):
		return
	if blocked:
		_blocked[cell] = true
	else:
		_blocked.erase(cell)
	_astar.set_point_solid(cell, blocked)


## True for wall cells (set with set_blocked). Units are not walls: see is_free().
func is_blocked(cell: Vector2i) -> bool:
	return _blocked.has(cell)


## The living unit standing on `cell`, or null.
func unit_at(cell: Vector2i) -> GridUnit:
	for u in units:
		if u.is_alive() and u.cell == cell:
			return u
	return null


## True if a unit could stand here: on the board, not a wall, not occupied.
func is_free(cell: Vector2i) -> bool:
	return in_bounds(cell) and not is_blocked(cell) and unit_at(cell) == null


## Places a new unit. Returns null (and adds nothing) if the cell is not free.
func add_unit(data: UnitData, team: int, cell: Vector2i) -> GridUnit:
	if not is_free(cell):
		return null
	var unit := GridUnit.new(data, team, cell)
	units.append(unit)
	unit_added.emit(unit)
	return unit


## Living units, optionally only one team's. Pass -1 for everyone.
func living(team := -1) -> Array[GridUnit]:
	var out: Array[GridUnit] = []
	for u in units:
		if u.is_alive() and (team == -1 or u.team == team):
			out.append(u)
	return out


## Living units hostile to `team`.
func enemies_of(team: int) -> Array[GridUnit]:
	var out: Array[GridUnit] = []
	for u in units:
		if u.is_alive() and u.team != team:
			out.append(u)
	return out


## The team numbers that still have a living unit, sorted.
func teams_alive() -> Array[int]:
	var seen := {}
	for u in units:
		if u.is_alive():
			seen[u.team] = true
	var out: Array[int] = []
	out.assign(seen.keys())
	out.sort()
	return out


# --- Movement -----------------------------------------------------------------------------

## Every cell `unit` can end its move on, with the steps needed: {cell: steps}. Includes its
## own cell at 0. A flood fill (breadth-first search) outward from the unit, one ring of
## neighbours at a time, stopping at walls, other units and move_range.
func reachable_cells(unit: GridUnit) -> Dictionary:
	var cost := {unit.cell: 0}
	var frontier: Array[Vector2i] = [unit.cell]
	while not frontier.is_empty():
		var current: Vector2i = frontier.pop_front()
		if cost[current] >= unit.data.move_range:
			continue
		for dir in RangeShapes.DIRECTIONS:
			var next: Vector2i = current + dir
			if cost.has(next) or not is_free(next):
				continue
			cost[next] = cost[current] + 1
			frontier.append(next)
	return cost


## Shortest free path between two cells (both included), or empty if there is none. Other
## units count as obstacles, except on the start and end cells themselves.
func find_path(from: Vector2i, to: Vector2i) -> Array[Vector2i]:
	var path: Array[Vector2i] = []
	if not in_bounds(from) or not in_bounds(to) or is_blocked(to):
		return path
	# Temporarily mark unit cells solid so AStarGrid2D routes around them.
	var occupied: Array[Vector2i] = []
	for u in units:
		if u.is_alive() and u.cell != from and u.cell != to:
			occupied.append(u.cell)
			_astar.set_point_solid(u.cell, true)
	path.assign(_astar.get_id_path(from, to))
	for cell in occupied:
		_astar.set_point_solid(cell, false)
	return path


## Moves `unit` to `to` if it is reachable this turn. Returns true on success.
func move_unit(unit: GridUnit, to: Vector2i) -> bool:
	if not unit.is_alive() or unit.has_moved or to == unit.cell:
		return false
	if not reachable_cells(unit).has(to):
		return false
	var path := find_path(unit.cell, to)
	unit.cell = to
	unit.has_moved = true
	unit_moved.emit(unit, path)
	return true


# --- Combat -------------------------------------------------------------------------------

## Cells the unit's basic attack could reach from `from` (defaults to where it stands).
func attack_cells(unit: GridUnit, from := Vector2i(-1, -1)) -> Array[Vector2i]:
	var origin := unit.cell if from == Vector2i(-1, -1) else from
	var out: Array[Vector2i] = []
	for cell in RangeShapes.cells(RangeShapes.Shape.DIAMOND, origin, unit.data.attack_range_max):
		var d := RangeShapes.distance(origin, cell)
		if in_bounds(cell) and d >= unit.data.attack_range_min and d <= unit.data.attack_range_max:
			out.append(cell)
	return out


## Basic attack on the unit standing at `target_cell`. Returns true if it happened.
func attack(unit: GridUnit, target_cell: Vector2i) -> bool:
	var target := unit_at(target_cell)
	if not unit.is_alive() or unit.has_acted or target == null or target.team == unit.team:
		return false
	if not attack_cells(unit).has(target_cell):
		return false
	unit.has_acted = true
	var cells: Array[Vector2i] = [target_cell]
	action_used.emit(unit, cells, null)
	apply_damage(target, unit.data.attack_damage, unit)
	return true


## The cells an ability would affect if aimed at `target_cell` (on-board cells only).
func ability_cells(unit: GridUnit, ability: AbilityData, target_cell: Vector2i) -> Array[Vector2i]:
	var direction := RangeShapes.direction_to(unit.cell, target_cell)
	var out: Array[Vector2i] = []
	for cell in RangeShapes.cells(ability.shape, target_cell, ability.radius, direction):
		if in_bounds(cell):
			out.append(cell)
	return out


## Uses an ability aimed at `target_cell`. Returns true if it happened.
func use_ability(unit: GridUnit, ability: AbilityData, target_cell: Vector2i) -> bool:
	if not unit.is_alive() or unit.has_acted or not unit.can_use(ability):
		return false
	if not in_bounds(target_cell) or RangeShapes.distance(unit.cell, target_cell) > ability.cast_range:
		return false
	unit.has_acted = true
	unit.cooldowns[ability.id] = ability.cooldown + 1    # +1: the tick at the next turn start makes it `cooldown`
	var cells := ability_cells(unit, ability, target_cell)
	action_used.emit(unit, cells, ability)
	for cell in cells:
		var target := unit_at(cell)
		if target == null:
			continue
		var same_team := target.team == unit.team
		# Heals affect allies only; attacks affect enemies, plus allies when friendly_fire is on.
		if ability.is_support() != same_team and not (ability.friendly_fire and not ability.is_support()):
			continue
		apply_damage(target, ability.damage, unit)
	return true


## Damages every unit standing on `cells` (used when telegraphed attacks resolve).
func damage_cells(cells: Array, amount: int, source: GridUnit) -> void:
	for cell: Vector2i in cells:
		var target := unit_at(cell)
		if target and (source == null or target.team != source.team):
			apply_damage(target, amount, source)


## The single place HP changes. Negative `amount` heals (never above max_hp).
func apply_damage(target: GridUnit, amount: int, source: GridUnit = null) -> void:
	if not target.is_alive():
		return
	target.hp = clampi(target.hp - amount, 0, target.data.max_hp)
	unit_damaged.emit(target, amount, source)
	if not target.is_alive():
		target.intent = {}                 # a dead unit's planned attack is cancelled
		intent_changed.emit(target)
		unit_died.emit(target)


## Sets or clears (pass no cells) a unit's telegraphed attack.
func set_intent(unit: GridUnit, cells: Array[Vector2i] = [], damage := 0) -> void:
	unit.intent = {} if cells.is_empty() else {"cells": cells, "damage": damage}
	intent_changed.emit(unit)


## Every cell some enemy of `team` has telegraphed, with the total damage waiting there: {cell: damage}.
func danger_cells(team: int) -> Dictionary:
	var danger := {}
	for u in enemies_of(team):
		if u.intent.is_empty():
			continue
		for cell: Vector2i in u.intent.cells:
			danger[cell] = danger.get(cell, 0) + int(u.intent.damage)
	return danger
