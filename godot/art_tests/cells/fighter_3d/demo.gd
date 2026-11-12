extends Node3D
## Fighter cell, 3D art: a side-on mirror match between two copies of one rigged character.
##
## Art (all downloaded, see CREDITS.md): the Quaternius animated base character, twice, and a
## Poly Haven wood-deck texture on the floor. Blue and red tints are the only difference
## between the fighters.
## Kit: HealthComponent and HitInfo from kit_combat drive the health bars and the knockout.
## The demo plays itself: blue jabs, red takes the hit; then red answers with a cross.

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const HERO_SCENE := "res://art_tests/cells/_shared/quaternius/animated_base_character.glb"
const FLOOR_TEXTURE := "res://art_tests/cells/fighter_3d/assets/floor.jpg"

var fighters: Array[Node3D] = []
var bars: Array[ProgressBar] = []


## _ready(): lights, deck, two fighters facing each other, a side camera, bars, then the fight.
func _ready() -> void:
	CellArt.outdoor_light(self, Color(0.24, 0.22, 0.34), 0.02)        # dusk sky, light fog
	var deck := CellArt.ground(self, Vector2(40, 12), Color.WHITE)
	var wood := StandardMaterial3D.new()
	wood.albedo_texture = load(FLOOR_TEXTURE)
	wood.uv1_triplanar = true                 # project the texture from the world axes: no UV work
	wood.uv1_world_triplanar = true
	wood.uv1_scale = Vector3(0.35, 0.35, 0.35)
	(deck.get_child(1) as MeshInstance3D).mesh.surface_set_material(0, wood)

	# This model's front is its -Z side, so -90 degrees of yaw turns it to face +X (screen right).
	fighters.append(_fighter(Vector3(-0.62, 0, 0), -90.0, Color(0.3, 0.85, 3.0), true))
	fighters.append(_fighter(Vector3(0.62, 0, 0), 90.0, Color(1.25, 0.45, 0.4), false))
	var camera := Camera3D.new()
	camera.position = Vector3(0.0, 1.15, 4.3)            # straight side view, like a 2D fighter
	camera.fov = 38.0                                    # a narrow lens flattens the scene
	add_child(camera)
	_fight()


## One fighter: the shared model, tinted, with health from the kit and a bar on screen.
func _fighter(at: Vector3, yaw_degrees: float, tint: Color, left_side: bool) -> Node3D:
	var model: Node3D = (load(HERO_SCENE) as PackedScene).instantiate()
	model.position = at
	model.rotation_degrees.y = yaw_degrees
	add_child(model)
	CellArt.tint(model, tint)
	CellArt.play_clip(model, "Rig|Idle")
	var health := HealthComponent.new()
	health.max_health = 100.0
	model.add_child(health)
	var bar := ProgressBar.new()
	bar.show_percentage = false
	bar.size = Vector2(480, 26)
	bar.position = Vector2(70 if left_side else 730, 40)
	bar.fill_mode = ProgressBar.FILL_END_TO_BEGIN if left_side else ProgressBar.FILL_BEGIN_TO_END
	bar.value = 100.0
	var fill := StyleBoxFlat.new()
	fill.bg_color = Color(0.95, 0.75, 0.2)
	bar.add_theme_stylebox_override(&"fill", fill)
	add_child(bar)
	# connect(): the bar follows the kit's health number; clips follow its hit and death signals.
	health.health_changed.connect(func(current: float, maximum: float) -> void: bar.value = 100.0 * current / maximum)
	health.damaged.connect(func(_hit: HitInfo) -> void: CellArt.play_clip(model, "Rig|Hit_Chest"))
	health.died.connect(func(_hit: HitInfo) -> void: CellArt.play_clip(model, "Rig|Death01"))
	return model


## Fighters take turns: attacker plays a punch clip, the hit lands partway through it.
func _fight() -> void:
	var turn := 0
	while true:
		var attacker := fighters[turn % 2]
		var defender := fighters[(turn + 1) % 2]
		var defender_health := HealthComponent.resolve(defender)
		if defender_health.is_dead or HealthComponent.resolve(attacker).is_dead:
			return
		CellArt.play_clip(attacker, "Rig|Punch_Jab" if turn % 2 == 0 else "Rig|Punch_Cross", 1.4)
		await get_tree().create_timer(0.32).timeout          # `await`: wait for the fist to arrive
		defender_health.take_damage(HitInfo.new(18.0))
		await get_tree().create_timer(0.75).timeout
		for fighter in fighters:
			if not HealthComponent.resolve(fighter).is_dead:
				CellArt.play_clip(fighter, "Rig|Idle")
		await get_tree().create_timer(0.35).timeout
		turn += 1
