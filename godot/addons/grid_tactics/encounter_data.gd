# EncounterData: one battle setup (board size, walls, who starts where) as a .tres Resource.
class_name EncounterData
extends Resource
## Design each fight as a small .tres file. build_model() turns it into a fresh GridModel, so the
## game, the tests and the winnability bot all start from exactly the same setup.

@export var id: StringName = &"encounter"
@export var grid_size := Vector2i(8, 8)
## Wall cells.
@export var blocked: Array[Vector2i] = []
## Parallel arrays (same length): spawn i is spawn_units[i] at spawn_cells[i] on spawn_teams[i].
## Three simple arrays edit more easily in the Inspector than an array of sub-resources.
@export var spawn_units: Array[UnitData] = []
@export var spawn_cells: Array[Vector2i] = []
## Team per spawn: 0 = player, 1+ = enemies.
@export var spawn_teams: Array[int] = []


## Adds one spawn (handy when building encounters from code or a level generator).
func add_spawn(unit: UnitData, cell: Vector2i, team: int) -> void:
	spawn_units.append(unit)
	spawn_cells.append(cell)
	spawn_teams.append(team)


## A brand-new board with the walls and units placed. Reports bad spawns with push_error.
func build_model() -> GridModel:
	var model := GridModel.new(grid_size)
	for cell in blocked:
		model.set_blocked(cell)
	for i in spawn_units.size():
		if model.add_unit(spawn_units[i], spawn_teams[i], spawn_cells[i]) == null:
			push_error("EncounterData '%s': spawn %d at %s is off-board, in a wall, or occupied" % [id, i, spawn_cells[i]])
	return model


## The teams taking part, sorted, so the player (0) goes first.
func teams() -> Array[int]:
	var seen := {}
	for t in spawn_teams:
		seen[t] = true
	var out: Array[int] = []
	out.assign(seen.keys())
	out.sort()
	return out
