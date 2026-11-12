extends Node3D
## Playable fps_kit demo: a grey-box arena, three target dummies, a lever, and a box "gun".
## No art: every mesh is a primitive made in code. Use it as the starting template for an FPS
## jam entry: swap the boxes for a level, the gun box for a viewmodel, the dummies for enemies.
##
## Controls: click to capture the mouse, WASD move, Shift sprint, Ctrl/C crouch, Space jump,
## left click fire, R reload, E use the lever, Esc release the mouse.

var player: FPSController
var weapon: FPSWeapon
var hud: Label
var lever_uses := 0


## A switch you can use with E. FPSInteractor only needs the interact() method.
class Lever extends StaticBody3D:
	signal used

	## Called by FPSInteractor when the player presses the interact action while looking at it.
	func interact(_by: Node) -> void:
		used.emit()


## _ready(): build the level, the player and the HUD, then wire signals to the HUD text.
func _ready() -> void:
	_build_level()
	player = FPSController.new()
	player.position = Vector3(0.0, 0.1, 6.0)
	add_child(player)                       # its _ready() creates the capsule, head and camera

	# Gun: a ViewmodelSway under the camera holds a box mesh and the FPSWeapon.
	var sway := ViewmodelSway.new()
	sway.position = Vector3(0.28, -0.24, -0.55)      # lower right of the view
	player.camera.add_child(sway)
	sway.add_child(_box_mesh(Vector3(0.08, 0.1, 0.5), Color(0.2, 0.2, 0.24)))
	weapon = FPSWeapon.new()
	weapon.data = _rifle()
	sway.add_child(weapon)

	var interactor := FPSInteractor.new()
	player.camera.add_child(interactor)

	hud = Label.new()
	hud.position = Vector2(24, 24)
	hud.add_theme_font_size_override(&"font_size", 22)
	add_child(hud)
	add_child(_crosshair())
	# connect(): update the HUD whenever these things happen, instead of polling every frame.
	weapon.ammo_changed.connect(func(_mag: int, _reserve: int) -> void: _refresh_hud())
	weapon.reload_started.connect(_refresh_hud)
	interactor.focus_changed.connect(func(_target: Node) -> void: _refresh_hud(interactor.focus != null))
	_refresh_hud()


## Rewrites the HUD text (ammo, reload state, lever count, and a prompt when something is usable).
func _refresh_hud(can_use := false) -> void:
	var ammo := "RELOADING" if weapon.is_reloading else "%d / %d" % [weapon.ammo_in_magazine, weapon.reserve_ammo]
	hud.text = "%s   %s\nLever pulled: %d%s" % [weapon.data.display_name, ammo, lever_uses,
			"\n[E] use" if can_use else ""]


## An automatic hitscan rifle built in code (a game would save this as a .tres).
func _rifle() -> WeaponData:
	var data := WeaponData.new()
	data.display_name = "Rifle"
	data.damage = 20.0
	data.fire_rate = 8.0
	data.automatic = true
	data.magazine_size = 24
	data.reserve_ammo = 96
	data.spread_degrees = 0.6
	return data


## Floor, walls, a crouch-under beam, steps, three dummies and a lever.
func _build_level() -> void:
	_solid(Vector3(0, -0.5, 0), Vector3(24, 1, 24), Color(0.3, 0.32, 0.36))             # floor
	for wall in [[Vector3(0, 2, -12), Vector3(24, 4, 0.5)], [Vector3(0, 2, 12), Vector3(24, 4, 0.5)],
			[Vector3(-12, 2, 0), Vector3(0.5, 4, 24)], [Vector3(12, 2, 0), Vector3(0.5, 4, 24)]]:
		_solid(wall[0], wall[1], Color(0.42, 0.44, 0.5))
	_solid(Vector3(-5, 1.55, 0), Vector3(4, 0.5, 1), Color(0.75, 0.55, 0.3))            # beam: crouch under it (1.3 m gap)
	_solid(Vector3(5, 0.25, 1), Vector3(2, 0.5, 2), Color(0.5, 0.6, 0.5))               # low step
	_solid(Vector3(7, 0.6, 1), Vector3(2, 1.2, 2), Color(0.5, 0.6, 0.5))                # high step (jump)
	for x in [-3.0, 0.0, 3.0]:
		_dummy(Vector3(x, 0.9, -6.0))
	var lever := Lever.new()
	lever.position = Vector3(-10.5, 1.3, 6.0)
	_add_box_shape(lever, Vector3(0.4, 0.6, 0.4))
	lever.add_child(_box_mesh(Vector3(0.4, 0.6, 0.4), Color(0.95, 0.8, 0.2)))
	lever.used.connect(func() -> void:
		lever_uses += 1
		_refresh_hud(true))
	add_child(lever)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 30.0, 0.0)
	sun.shadow_enabled = true
	add_child(sun)
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.5, 0.62, 0.78)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.6, 0.65, 0.75)
	# Distance fog is cheap in the Compatibility renderer and hides low-detail far walls.
	environment.fog_enabled = true
	environment.fog_light_color = Color(0.5, 0.62, 0.78)
	environment.fog_density = 0.008
	var world := WorldEnvironment.new()
	world.environment = environment
	add_child(world)


## A static, collidable box.
func _solid(at: Vector3, size: Vector3, color: Color) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.position = at
	_add_box_shape(body, size)
	body.add_child(_box_mesh(size, color))
	add_child(body)
	return body


## A target with 60 HP that turns dark and stops blocking when "killed".
func _dummy(at: Vector3) -> void:
	var body := _solid(at, Vector3(0.7, 1.8, 0.4), Color(0.85, 0.3, 0.25))
	var health := HealthComponent.new()
	health.max_health = 60.0
	body.add_child(health)
	var mesh := body.get_child(1) as MeshInstance3D
	# Signals from kit_combat: flash on every hit, fall over on death.
	health.damaged.connect(func(_hit: HitInfo) -> void:
		mesh.scale = Vector3(1.15, 0.92, 1.15)
		create_tween().tween_property(mesh, ^"scale", Vector3.ONE, 0.12))
	health.died.connect(func(_hit: HitInfo) -> void:
		create_tween().tween_property(body, ^"rotation:x", -PI / 2.0, 0.3))


## Adds a box collision shape of `size` to a physics body.
func _add_box_shape(body: CollisionObject3D, size: Vector3) -> void:
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	body.add_child(shape)


## A box mesh with a flat colour.
func _box_mesh(size: Vector3, color: Color) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	mesh.material = material
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	return instance


## A small dot in the middle of the screen.
func _crosshair() -> Control:
	var dot := ColorRect.new()
	dot.color = Color(1, 1, 1, 0.8)
	dot.size = Vector2(4, 4)
	dot.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	return dot
