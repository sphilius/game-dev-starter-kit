extends Node3D
## Tactics cell, 3D art: the grid_tactics kit with static minis on a concrete board.
##
## Art (all downloaded, see CREDITS.md): two unrigged Kenney models used as miniatures and a
## Poly Haven floor texture on the board tiles.
## Kit: GridModel, EncounterData, TurnManager, TacticsAI, TacticsBot, TacticsPresenter3D.
## The battle plays itself: the bot moves the heroes, the kit's AI moves the drones.

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const ASSETS := "res://art_tests/cells/tactics_3d/assets/"

var model: GridModel
var turns: TurnManager
var view: TacticsPresenter3D


## _ready(): light, battle, presenter with our minis and board texture, camera, then play.
func _ready() -> void:
	CellArt.outdoor_light(self, Color(0.16, 0.19, 0.26))
	model = _encounter().build_model()
	turns = TurnManager.new(model)
	view = TacticsPresenter3D.new()
	var board := StandardMaterial3D.new()
	board.albedo_texture = load(ASSETS + "board.jpg")
	board.albedo_color = Color(1.5, 1.5, 1.6)        # values above 1 brighten a dark texture
	view.floor_material = board
	var block := board.duplicate() as StandardMaterial3D     # walls: the same texture, darker
	block.albedo_color = Color(0.42, 0.4, 0.46)
	view.wall_material = block
	# One piece scene for every unit type: mini.gd picks the model from the unit's id.
	var piece_root := Node3D.new()
	piece_root.set_script(load("res://art_tests/cells/tactics_3d/mini.gd"))
	var piece := PackedScene.new()
	piece.pack(piece_root)                   # pack(): turn a node made in code into a scene
	piece_root.free()
	view.unit_scenes = {&"hero": piece, &"drone": piece}
	add_child(view)
	view.setup(model)

	var camera := Camera3D.new()
	camera.position = Vector3(3.5, 5.6, 8.6)
	camera.fov = 52.0
	add_child(camera)
	camera.look_at(Vector3(3.5, 0.0, 3.9))
	turns.start()
	view.show_cells(model.reachable_cells(model.living(0)[0]).keys(), Color(0.3, 0.7, 1.0, 0.45), "move")
	_play()


## The battle loop, same as the kit's demo: bot for team 0, TacticsAI for team 1.
func _play() -> void:
	await get_tree().create_timer(2.5).timeout          # hold the opening position for a moment
	view.clear_highlights("move")
	while not turns.is_over():
		if turns.current_team() == 0:
			TacticsBot.play_turn(model, 0)
		else:
			TacticsAI.take_turn(model, turns.current_team())
		# `await some.signal` pauses here until the presenter's walk and death tweens finish.
		if view.is_busy():
			await view.animation_finished
		await get_tree().create_timer(0.5).timeout
		turns.end_turn()


## Two heroes against three drones on an 8x8 board with four wall cells.
func _encounter() -> EncounterData:
	var e := EncounterData.new()
	e.grid_size = Vector2i(8, 8)
	e.blocked = [Vector2i(3, 2), Vector2i(3, 3), Vector2i(4, 5), Vector2i(5, 5)] as Array[Vector2i]
	e.add_spawn(_unit(&"hero", 16, 5), Vector2i(1, 3), 0)
	e.add_spawn(_unit(&"hero", 16, 5), Vector2i(0, 5), 0)
	e.add_spawn(_unit(&"drone", 9, 3), Vector2i(6, 2), 1)
	e.add_spawn(_unit(&"drone", 9, 3), Vector2i(7, 4), 1)
	e.add_spawn(_unit(&"drone", 9, 3), Vector2i(6, 6), 1)
	return e


## Shorthand for a melee UnitData built in code.
func _unit(id: StringName, hp: int, damage: int) -> UnitData:
	var data := UnitData.new()
	data.id = id
	data.max_hp = hp
	data.attack_damage = damage
	return data
