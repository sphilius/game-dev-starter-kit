extends Node3D
## FPS cell, 3D art: a foggy low-poly yard with boars, played through fps_kit.
##
## Art: walls, floor slabs and the blaster are Kenney's CC0 FPS kit (downloaded, see CREDITS.md).
## The boar was made by this repo's pipeline3d: a Blender script built, rigged and animated it.
## Kit: FPSController, FPSWeapon, WeaponData, ViewmodelSway, and HealthComponent on the boars.
## Shoot a boar three times and it plays its death clip.
##
## Controls: click to capture the mouse, WASD, Shift sprint, Space jump, left click fire, R reload.

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const ASSETS := "res://art_tests/cells/fps_3d/assets/"
const FOG := Color(0.3, 0.37, 0.4)

var player: FPSController


## _ready(): fog and light, the yard, three boars, then the player with a blaster in view.
func _ready() -> void:
	# Fog this thick hides the edge of the level and the low polygon count at the same time.
	CellArt.outdoor_light(self, FOG, 0.085)
	# The kit's palette is cheerful pastel. A dim sun and cold fog pull it toward "eerie";
	# a real horror game would want a darker kit or its own colour map.
	(get_child(0) as DirectionalLight3D).light_energy = 0.55
	_build_yard()
	_boar(Vector3(-1.3, 0.5, -1.2), 25.0, "boar_attack")
	_boar(Vector3(1.5, 0.5, -3.6), -40.0, "boar_walk")
	_boar(Vector3(-2.6, 0.5, -6.5), 70.0, "boar_idle")

	player = FPSController.new()
	player.position = Vector3(0.0, 0.6, 2.5)
	add_child(player)                       # its _ready() creates the capsule, head and camera
	var sway := ViewmodelSway.new()
	sway.position = Vector3(0.2, -0.2, -0.45)       # lower right of the view
	player.camera.add_child(sway)
	var blaster: Node3D = (load(ASSETS + "blaster.glb") as PackedScene).instantiate()
	blaster.scale = Vector3.ONE * 0.2             # the kit model is 1.6 m long: far too big to hold
	blaster.rotation_degrees.y = 180.0              # the kit's blaster points at +Z; the camera looks at -Z
	sway.add_child(blaster)
	var weapon := FPSWeapon.new()
	weapon.data = WeaponData.new()
	weapon.data.damage = 20.0
	sway.add_child(weapon)


## Floor slabs in a grid with a wall of kit pieces around them.
func _build_yard() -> void:
	# The slab is 5.2 m square and 0.5 m thick: nine of them make a 15.6 m yard.
	for x in range(-1, 2):
		for z in range(-3, 1):
			_piece("platform-large-grass", Vector3(x * 5.2, 0.0, z * 5.2), 0.0, Vector3(5.2, 0.5, 5.2))
	# wall-high is 1.5 m wide: line them up along the far side and both flanks.
	for i in range(-5, 6):
		_piece("wall-high", Vector3(i * 1.5, 0.5, -17.8), 0.0, Vector3(1.5, 1.7, 0.7))
	for i in range(0, 14):
		_piece("wall-high", Vector3(-7.6, 0.5, 2.0 - i * 1.5), 90.0, Vector3(1.5, 1.7, 0.7))
		_piece("wall-high", Vector3(7.6, 0.5, 2.0 - i * 1.5), 90.0, Vector3(1.5, 1.7, 0.7))
	for spot: Vector3 in [Vector3(3.5, 0.5, -3.0), Vector3(-3.0, 0.5, -8.0), Vector3(1.0, 0.5, -12.0)]:
		_piece("wall-low", spot, 20.0, Vector3(2.2, 0.8, 0.7))


## One kit model with a box collider of `size` so the player and bullets hit it.
func _piece(model_name: String, at: Vector3, yaw_degrees: float, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.position = at
	body.rotation_degrees.y = yaw_degrees
	body.add_child((load(ASSETS + model_name + ".glb") as PackedScene).instantiate())
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	shape.position.y = size.y / 2.0                 # kit pieces have their origin at the bottom
	body.add_child(shape)
	add_child(body)


## A boar: the rigged model on a collider with 60 HP. `clip` is what it does until shot.
func _boar(at: Vector3, yaw_degrees: float, clip: String) -> void:
	var body := StaticBody3D.new()
	body.position = at
	body.rotation_degrees.y = yaw_degrees
	var model: Node3D = (load(ASSETS + "boar.glb") as PackedScene).instantiate()
	body.add_child(model)
	CellArt.play_clip(model, clip)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.5, 0.9, 1.5)
	shape.shape = box
	shape.position.y = 0.45
	body.add_child(shape)
	var health := HealthComponent.new()
	health.max_health = 60.0
	body.add_child(health)
	# connect(): the kit announces death once; we answer with the clip and drop the collider.
	health.died.connect(func(_hit: HitInfo) -> void:
		CellArt.play_clip(model, "boar_death")
		shape.set_deferred(&"disabled", true))
	add_child(body)
