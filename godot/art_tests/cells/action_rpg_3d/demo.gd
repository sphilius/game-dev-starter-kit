extends Node3D
## Action RPG cell, 3D art: a rigged low-poly hero swinging a sword at two sparring partners.
##
## Art (all downloaded, see CREDITS.md): Quaternius's animated base character (45 clips on one
## rig) and two Quaternius scenery models. Enemies are the same model: one rig, one clip
## library, every humanoid in the game.
## Kit: HealthComponent and HitInfo from kit_combat decide who flinches and who falls.
## The demo plays itself: attack, the target reacts, repeat until it drops.

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const HERO_SCENE := "res://art_tests/cells/_shared/quaternius/animated_base_character.glb"
const ASSETS := "res://art_tests/cells/action_rpg_3d/assets/"

var hero: Node3D
var target: Node3D


## _ready(): meadow, scenery, three characters, a third-person camera, then the sparring loop.
func _ready() -> void:
	CellArt.outdoor_light(self, Color(0.62, 0.78, 0.92), 0.012)
	CellArt.ground(self, Vector2(60, 60), Color(0.3, 0.46, 0.24))
	for spot: Array in [["rock_medium", Vector3(-2.2, 0.2, -3.6), 0.8], ["rock_medium", Vector3(4.6, 0.15, -5.0), 0.6],
			["plant_big", Vector3(3.4, 0.0, -1.2), 0.4], ["plant_big", Vector3(-0.4, 0.0, -2.6), 0.35],
			["plant_big", Vector3(-4.6, 0.0, -6.0), 0.6]]:
		var prop: Node3D = (load(ASSETS + spot[0] + ".glb") as PackedScene).instantiate()
		prop.position = spot[1]
		prop.scale = Vector3.ONE * spot[2]
		add_child(prop)

	hero = _character(Vector3(-0.6, 0, 0), -90.0)            # this model's front is -Z: -90 faces +X, the target
	target = _character(Vector3(0.75, 0, 0), 90.0)
	var bystander := _character(Vector3(2.6, 0, -2.4), 50.0)
	# The base character is a bare mannequin: a tint per team is its whole costume budget.
	CellArt.tint(hero, Color(0.3, 0.85, 3.0))
	CellArt.tint(target, Color(1.25, 0.5, 0.45))
	CellArt.tint(bystander, Color(1.25, 0.5, 0.45))
	CellArt.play_clip(bystander, "Rig|Idle")
	CellArt.play_clip(target, "Rig|Sword_Idle")

	var camera := Camera3D.new()
	camera.position = Vector3(-2.1, 1.75, 2.5)                # behind and above the hero's shoulder
	camera.fov = 55.0
	add_child(camera)
	camera.look_at(Vector3(0.5, 0.95, -0.4))
	_spar()


## One humanoid: the shared model plus a HealthComponent from the kit.
func _character(at: Vector3, yaw_degrees: float) -> Node3D:
	var model: Node3D = (load(HERO_SCENE) as PackedScene).instantiate()
	model.position = at
	model.rotation_degrees.y = yaw_degrees
	add_child(model)
	var health := HealthComponent.new()
	health.max_health = 60.0
	model.add_child(health)
	return model


## The loop: swing, the hit lands mid-swing, the target flinches or falls. `await` waits
## without freezing the game.
func _spar() -> void:
	var health := HealthComponent.resolve(target)
	# connect(): react to the kit's signals instead of checking health every frame.
	health.damaged.connect(func(_hit: HitInfo) -> void: CellArt.play_clip(target, "Rig|Hit_Chest"))
	health.died.connect(func(_hit: HitInfo) -> void: CellArt.play_clip(target, "Rig|Death01"))
	while not health.is_dead:
		CellArt.play_clip(hero, "Rig|Sword_Attack", 1.3)
		await get_tree().create_timer(0.55).timeout           # the blade connects about here
		health.take_damage(HitInfo.new(20.0))
		await get_tree().create_timer(0.9).timeout
		if not health.is_dead:
			CellArt.play_clip(target, "Rig|Sword_Idle")
	CellArt.play_clip(hero, "Rig|Idle")
