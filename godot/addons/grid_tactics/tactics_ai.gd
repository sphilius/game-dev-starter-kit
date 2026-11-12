# TacticsAI: a simple, readable enemy brain that TELLS the player what it will do next turn.
class_name TacticsAI
extends RefCounted
## "Greedy" means each unit just takes the best-looking step right now: walk toward the
## nearest enemy, then aim an attack at it. No look-ahead. That is plenty for a jam game, because
## the interesting decisions come from the TELEGRAPH:
##
##   Enemy turn, for each unit:   1. the attack it aimed LAST turn lands on those cells now
##                                   (hitting whoever stands there, or nobody);
##                                2. it moves toward its target;
##                                3. it aims a new attack and shows the cells (GridUnit.intent).
##   Player turn:                 the marked cells are visible, so the player can step out,
##                                kill the attacker first (a dead unit's intent is cancelled),
##                                or accept the hit to do something better.
##
## All functions are static: TacticsAI.take_turn(model, 1).


## Plays one whole turn for `team`. Call it when TurnManager.turn_started fires for an AI team.
static func take_turn(model: GridModel, team: int) -> void:
	resolve_intents(model, team)
	for unit in model.living(team):
		act(model, unit)


## Step 1: every attack this team telegraphed last turn hits its cells.
static func resolve_intents(model: GridModel, team: int) -> void:
	for unit in model.living(team):
		if unit.intent.is_empty():
			continue
		var cells: Array[Vector2i] = []
		cells.assign(unit.intent.cells)
		var damage: int = unit.intent.damage
		model.action_used.emit(unit, cells, null)
		model.set_intent(unit)                      # clear before applying, so UI updates first
		model.damage_cells(cells, damage, unit)


## Steps 2 and 3 for one unit: move toward the best target, then telegraph an attack on it.
static func act(model: GridModel, unit: GridUnit) -> void:
	var target := pick_target(model, unit)
	if target == null:
		return
	var destination := best_cell_toward(model, unit, target.cell)
	if destination != unit.cell:
		model.move_unit(unit, destination)
	if model.attack_cells(unit).has(target.cell):
		var cells: Array[Vector2i] = [target.cell]
		model.set_intent(unit, cells, unit.data.attack_damage)
		unit.has_acted = true


## The nearest enemy; ties go to the one with less HP (finish off the wounded).
static func pick_target(model: GridModel, unit: GridUnit) -> GridUnit:
	var best: GridUnit = null
	var best_key := Vector2i(999999, 999999)
	for enemy in model.enemies_of(unit.team):
		var key := Vector2i(RangeShapes.distance(unit.cell, enemy.cell), enemy.hp)
		if key < best_key:                          # Vector2i compares x first, then y
			best_key = key
			best = enemy
	return best


## The reachable cell to stand on: one the target can be attacked from if any (the closest such
## cell, so ranged units keep their distance), otherwise the cell nearest to the target.
static func best_cell_toward(model: GridModel, unit: GridUnit, target_cell: Vector2i) -> Vector2i:
	var best := unit.cell
	var best_score := -999999.0
	var reach := model.reachable_cells(unit)
	for cell: Vector2i in reach:
		var d := RangeShapes.distance(cell, target_cell)
		var in_range := d >= unit.data.attack_range_min and d <= unit.data.attack_range_max
		# Being able to attack dominates; then prefer fewer steps walked; else just get closer.
		var score: float = (1000.0 - reach[cell]) if in_range else -float(d)
		if score > best_score:
			best_score = score
			best = cell
	return best
