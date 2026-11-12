extends Node3D
## Metroidvania cell, 3D art from the side: a fox running through a foggy cave of rock boxes.
##
## Art (all downloaded, see CREDITS.md): the Khronos sample Fox with its Run clip, and one
## ambientCG rock colour map on every box. Everything else is code: boxes, fog, two lights.
## The camera looks along -Z, so gameplay would be 2D (X and Y) even though the art is 3D.

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const ASSETS := "res://art_tests/cells/metroidvania_3d/assets/"
const CAVE := Color(0.07, 0.09, 0.14)

var rock: StandardMaterial3D


## _ready(): cave lighting, a ledge layout built from boxes, the fox, a side-on camera.
func _ready() -> void:
	var world := CellArt.outdoor_light(self, CAVE, 0.035)
	world.environment.ambient_light_energy = 0.25           # caves are dark: let the lamps do the work
	(get_child(0) as DirectionalLight3D).light_energy = 0.35
	rock = StandardMaterial3D.new()
	rock.albedo_texture = load(ASSETS + "rock.jpg")
	rock.uv1_triplanar = true                                 # one texture on any box size, no UV work
	rock.uv1_world_triplanar = true
	rock.uv1_scale = Vector3(0.3, 0.3, 0.3)
	rock.roughness = 1.0

	# The play lane sits at z = 0. Each box: [centre, size].
	for box: Array in [[Vector3(0, -1.0, 0), Vector3(9, 2, 4)], [Vector3(7.5, -0.25, 0), Vector3(6, 3.5, 4)],
			[Vector3(-7.0, 0.5, 0), Vector3(5, 5, 4)], [Vector3(2.5, 3.6, 0), Vector3(4, 0.6, 3)],
			[Vector3(0, 7.5, 0), Vector3(24, 3, 4)]]:
		_box(box[0], box[1])
	# Rock further back, swallowed by fog: depth for free.
	for box: Array in [[Vector3(-3, 2.5, -7), Vector3(5, 9, 3)], [Vector3(5, 3.5, -10), Vector3(6, 11, 3)],
			[Vector3(11, 2, -6), Vector3(3, 8, 3)]]:
		_box(box[0], box[1])

	var fox: Node3D = (load(ASSETS + "fox.glb") as PackedScene).instantiate()
	# The file is modelled in centimetres (the gate measured it 75 "metres" tall): scale to metres.
	fox.scale = Vector3.ONE * 0.012
	fox.position = Vector3(0.6, 0.0, 0.6)
	fox.rotation_degrees.y = 90.0                             # nose toward +X, the direction of travel
	add_child(fox)
	CellArt.play_clip(fox, "Run")

	_lamp(Vector3(-1.5, 1.6, 1.5), Color(0.3, 0.9, 1.0), 9.0)      # cyan crystal glow on the left
	_lamp(Vector3(6.5, 3.0, 1.5), Color(1.0, 0.55, 0.25), 8.0)     # warm torch on the right ledge
	var camera := Camera3D.new()
	camera.position = Vector3(1.5, 2.2, 11.0)
	camera.fov = 40.0
	add_child(camera)


## A rock box. Collision is included so a CharacterBody3D could walk on it.
func _box(centre: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.position = centre
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	body.add_child(shape)
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = rock
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	body.add_child(instance)
	add_child(body)


## A coloured point light: the cheapest way to make grey rock look like a place.
func _lamp(at: Vector3, color: Color, reach: float) -> void:
	var lamp := OmniLight3D.new()
	lamp.position = at
	lamp.light_color = color
	lamp.light_energy = 2.2
	lamp.omni_range = reach
	add_child(lamp)
