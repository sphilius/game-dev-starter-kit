extends Node3D
## Platformer cell, 3D art: Kenney's little hero walking across Kenney platforms.
##
## Art (all downloaded, see CREDITS.md): eight models from Kenney's CC0 3D platformer kit.
## They share one small colour-palette texture, so everything matches without any work.
## No kit of ours is needed for this picture; a playable version would put the hero on a
## CharacterBody3D (the same twenty lines as the 2D platformer cells, with a Vector3).

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const ASSETS := "res://art_tests/cells/platformer_3d/assets/"

var hero: Node3D
var coins: Array[Node3D] = []
var walked := 0.0


## _ready(): sky, a short course of platforms with coins and a flag, the hero, a chase camera.
func _ready() -> void:
	CellArt.outdoor_light(self, Color(0.55, 0.78, 0.95))
	# Each entry: [model name, position, yaw in degrees].
	for piece: Array in [["platform-grass-large-round", Vector3(0, 0, 0), 0.0],
			["platform-medium", Vector3(5.2, 0.8, 0), 0.0], ["platform", Vector3(8.6, 1.7, -0.6), 0.0],
			["platform-medium", Vector3(12.2, 2.3, 0.4), 0.0], ["brick", Vector3(3.0, 0.5, -1.6), 0.0],
			["flag", Vector3(12.9, 2.85, 0.4), 90.0], ["cloud", Vector3(4.0, 5.0, -7.0), 0.0],
			["cloud", Vector3(11.0, 6.2, -9.0), 30.0], ["cloud", Vector3(-4.0, 4.2, -8.0), -20.0]]:
		_place(piece[0], piece[1], piece[2])
	for at: Vector3 in [Vector3(4.4, 2.0, 0), Vector3(5.2, 2.2, 0), Vector3(6.0, 2.0, 0), Vector3(8.6, 3.0, -0.6)]:
		coins.append(_place("coin", at, 0.0))

	hero = _place("character", Vector3(-0.8, 0.5, 0.3), 90.0)       # yaw 90: facing +X, along the course
	CellArt.play_clip(hero, "walk")
	var camera := Camera3D.new()
	camera.position = Vector3(1.0, 3.4, 7.2)
	camera.fov = 50.0
	add_child(camera)
	camera.look_at(Vector3(4.2, 1.5, 0.0))


## Instances one kit model at a position. Returns the node so callers can animate it.
func _place(model_name: String, at: Vector3, yaw_degrees: float) -> Node3D:
	var node: Node3D = (load(ASSETS + model_name + ".glb") as PackedScene).instantiate()
	node.position = at
	node.rotation_degrees.y = yaw_degrees
	add_child(node)
	return node


## Spin the coins and stroll the hero across the first platform and back.
## _process runs every drawn frame; `delta` is the seconds since the last one.
func _process(delta: float) -> void:
	for coin in coins:
		coin.rotate_y(delta * 3.0)
	walked += delta
	# pingpong(t, length) goes 0 -> length -> 0 -> ...: a walk there and back.
	var offset := pingpong(walked * 1.2, 2.6)
	var heading := 1.0 if fmod(walked * 1.2, 5.2) < 2.6 else -1.0
	hero.position.x = -0.8 + offset
	hero.rotation_degrees.y = 90.0 * heading
