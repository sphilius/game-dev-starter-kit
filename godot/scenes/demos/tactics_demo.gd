extends Node
## Self-playing grid_tactics demo: the bot plays the heroes, TacticsAI plays the enemies, and a
## presenter shows it. No art: everything on screen is the kit's placeholders. Use it as the
## starting template for a tactics game (replace the bot's turn with player input).
##
## Flip `use_3d` to see the same battle through the other presenter: the rules do not change.

@export var use_3d := true
## Seconds to pause between turns so a viewer can follow.
@export var turn_pause := 0.5

var model: GridModel
var turns: TurnManager
var view: Node                     # TacticsPresenter2D or TacticsPresenter3D (same API)


## _ready(): build the encounter, the presenter and a camera, then start the battle loop.
func _ready() -> void:
	model = _encounter().build_model()
	turns = TurnManager.new(model)
	if use_3d:
		view = TacticsPresenter3D.new()
		add_child(view)
		_add_3d_camera_and_light()
	else:
		view = TacticsPresenter2D.new()
		view.position = Vector2(384, 104)        # centre the 8×8 board in a 1280×720 window
		add_child(view)
	view.setup(model)
	turns.start()
	_play()


## The battle loop. `await` pauses here between steps while the game keeps drawing frames.
func _play() -> void:
	while not turns.is_over():
		if turns.current_team() == 0:
			# Show where the first hero could walk, like a player selecting a unit.
			var heroes := model.living(0)
			if not heroes.is_empty():
				view.show_cells(model.reachable_cells(heroes[0]).keys(), Color(0.3, 0.7, 1.0, 0.35), "move")
			await get_tree().create_timer(turn_pause).timeout
			view.clear_highlights("move")
			TacticsBot.play_turn(model, 0)
		else:
			TacticsAI.take_turn(model, turns.current_team())
		# Wait for walk/death tweens: `await some.signal` resumes when that signal is emitted.
		if view.is_busy():
			await view.animation_finished
		await get_tree().create_timer(turn_pause).timeout
		turns.end_turn()
	print("[tactics_demo] winner: team %d after %d rounds" % [turns.winner, turns.round_number])


## Two heroes against three enemies on an 8×8 board with a few walls. Built in code so the
## demo needs no .tres files; a real game would load EncounterData resources instead.
func _encounter() -> EncounterData:
	var e := EncounterData.new()
	e.grid_size = Vector2i(8, 8)
	e.blocked = [Vector2i(3, 2), Vector2i(3, 3), Vector2i(4, 5), Vector2i(5, 5)] as Array[Vector2i]
	var bolt := AbilityData.new()
	bolt.id = &"bolt"
	bolt.damage = 4
	bolt.cast_range = 4
	bolt.cooldown = 1
	var mage := _unit(&"mage", 8, 3, 2, 1, 2)
	mage.abilities.append(bolt)
	e.add_spawn(_unit(&"knight", 16, 3, 5, 1, 1), Vector2i(1, 3), 0)
	e.add_spawn(mage, Vector2i(0, 4), 0)
	e.add_spawn(_unit(&"orc", 9, 3, 3, 1, 1), Vector2i(6, 2), 1)
	e.add_spawn(_unit(&"orc", 9, 3, 3, 1, 1), Vector2i(7, 4), 1)
	e.add_spawn(_unit(&"archer", 6, 3, 2, 2, 4), Vector2i(7, 7), 1)
	return e


## Shorthand for a UnitData built in code.
func _unit(id: StringName, hp: int, move: int, damage: int, range_min: int, range_max: int) -> UnitData:
	var d := UnitData.new()
	d.id = id
	d.max_hp = hp
	d.move_range = move
	d.attack_damage = damage
	d.attack_range_min = range_min
	d.attack_range_max = range_max
	return d


## An angled camera over the board, a sun, and a plain dark background.
func _add_3d_camera_and_light() -> void:
	var camera := Camera3D.new()
	camera.position = Vector3(4.0, 6.6, 9.4)
	add_child(camera)
	camera.fov = 60.0
	camera.look_at(Vector3(4.0, 0.0, 4.4))
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	sun.shadow_enabled = true
	add_child(sun)
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.08, 0.09, 0.12)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.55, 0.6, 0.7)
	var world := WorldEnvironment.new()
	world.environment = environment
	add_child(world)
