extends Node3D
## FPS cell, 2D art: a foggy stone hall with billboard cultists, built on fps_kit.
##
## What is art here: assets/cultist/*.png (one AI sheet, four poses) and assets/wall/wall_00.png
## (one AI texture). Everything else is the kit: FPSController, FPSWeapon, HealthComponent.
## Shoot a cultist: it flinches (pose 3), and after 60 damage it is removed.
##
## Controls: click to capture the mouse, WASD, Shift sprint, Space jump, left click fire, R reload.

const ASSETS := "res://art_tests/cells/fps_2d/assets/"
const FOG := Color("1c1f26")
## Sheet order from the prompt: idle, walk, attack, hurt.
enum Pose { IDLE, WALK, ATTACK, HURT }
## Metres per sprite pixel: the 192 px figure stands 1.9 m tall.
const PIXEL_SIZE := 1.9 / 192.0

var player: FPSController
var poses: Array[Texture2D] = []


## _ready(): load the four pose textures, then build level, enemies and player.
func _ready() -> void:
	for i in 4:
		poses.append(load(ASSETS + "cultist/cultist_%02d.png" % i) as Texture2D)
	_build_level()
	_cultist(Vector3(-1.3, 0, -1.6), Pose.ATTACK)
	_cultist(Vector3(1.4, 0, -4.0), Pose.WALK)
	_cultist(Vector3(3.2, 0, -8.0), Pose.IDLE)
	_cultist(Vector3(-3.4, 0, -12.0), Pose.HURT)
	player = FPSController.new()
	player.position = Vector3(0.0, 0.1, 2.0)
	add_child(player)
	var weapon := FPSWeapon.new()
	weapon.data = WeaponData.new()            # defaults: a hitscan weapon
	weapon.data.damage = 20.0
	player.camera.add_child(weapon)
	# A torch on the player: the only light, so fog and falloff do the atmosphere.
	var torch := OmniLight3D.new()
	torch.omni_range = 14.0
	torch.light_energy = 1.6
	torch.light_color = Color(1.0, 0.85, 0.65)
	player.camera.add_child(torch)


## One enemy: a billboard sprite on a collider with health. `pose` is its resting picture.
func _cultist(at: Vector3, pose: Pose) -> void:
	var body := StaticBody3D.new()
	body.position = at
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.4
	capsule.height = 1.9
	shape.shape = capsule
	shape.position.y = 0.95
	body.add_child(shape)
	var sprite := Sprite3D.new()
	sprite.texture = poses[pose]
	sprite.pixel_size = PIXEL_SIZE
	# Every frame has the feet at the same pixel (art_cleanup did that), so lifting the
	# picture by half its height puts the feet on the floor in every pose.
	sprite.offset = Vector2(0.0, poses[pose].get_height() / 2.0)
	# FIXED_Y: turn to face the camera but stay upright (no tilting when you look down).
	sprite.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST      # keep the pixels crisp
	sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD                 # hard edges, correct depth sorting
	sprite.shaded = true                                               # the torch lights it like the walls
	body.add_child(sprite)
	var health := HealthComponent.new()
	health.max_health = 60.0
	body.add_child(health)
	health.damaged.connect(func(_hit: HitInfo) -> void:
		sprite.texture = poses[Pose.HURT]
		# A one-shot timer; "await" pauses only this little function, not the game.
		await get_tree().create_timer(0.25).timeout
		if is_instance_valid(sprite):
			sprite.texture = poses[pose])
	health.died.connect(func(_hit: HitInfo) -> void: body.queue_free())
	add_child(body)


## A 10 x 24 m hall with two pillars. All surfaces share the one wall texture.
func _build_level() -> void:
	var stone := StandardMaterial3D.new()
	stone.albedo_texture = load(ASSETS + "wall/wall_00.png")
	stone.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	# World triplanar: the texture is projected from the world axes, so any box of any size
	# gets correctly sized bricks with no UV work. 0.25 = one texture repeat every 4 m.
	stone.uv1_triplanar = true
	stone.uv1_world_triplanar = true
	stone.uv1_scale = Vector3(0.25, 0.25, 0.25)
	stone.roughness = 1.0
	_solid(Vector3(0, -0.5, -8), Vector3(10, 1, 24), stone)             # floor
	_solid(Vector3(0, 4.5, -8), Vector3(10, 1, 24), stone)              # ceiling
	_solid(Vector3(-5.25, 2, -8), Vector3(0.5, 4, 24), stone)           # left wall
	_solid(Vector3(5.25, 2, -8), Vector3(0.5, 4, 24), stone)            # right wall
	_solid(Vector3(0, 2, -20.25), Vector3(10, 4, 0.5), stone)           # far wall
	_solid(Vector3(0, 2, 4.25), Vector3(10, 4, 0.5), stone)             # wall behind the player
	_solid(Vector3(-2.5, 2, -9), Vector3(1, 4, 1), stone)               # pillars
	_solid(Vector3(2.5, 2, -13), Vector3(1, 4, 1), stone)
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = FOG
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.25, 0.28, 0.34)
	# Fog is the cheapest art there is: it hides the far wall and makes sprites emerge.
	environment.fog_enabled = true
	environment.fog_light_color = FOG
	environment.fog_density = 0.045
	var world := WorldEnvironment.new()
	world.environment = environment
	add_child(world)


## A static, collidable box with the given material.
func _solid(at: Vector3, size: Vector3, material: Material) -> void:
	var body := StaticBody3D.new()
	body.position = at
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	body.add_child(shape)
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = material
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	body.add_child(instance)
	add_child(body)
