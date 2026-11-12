# ViewmodelSway: makes the held gun lag behind the view and bob with the walk, then settle.
class_name ViewmodelSway
extends Node3D
## Put this under the controller's Camera3D, and put the gun mesh (and the FPSWeapon) under it.
## Turning drags the gun a little the other way; it springs back to rest. Small, but it is most
## of what makes a first-person gun feel held rather than glued to the screen.

## The controller whose `looked` signal drives the sway. Found automatically if left empty.
@export var controller: FPSController
## Degrees of tilt per radian of look movement.
@export var sway_degrees_per_radian := 40.0
## Largest tilt in degrees, so a fast flick does not throw the gun off screen.
@export var max_sway_degrees := 6.0
## How quickly the gun returns to rest (higher = stiffer).
@export var return_speed := 8.0
## Share of the controller's head bob applied to the gun (0 = none).
@export var bob_follow := 0.5

## Current sway in degrees (x = pitch, y = yaw). Read-only; exposed for tests and debug.
var sway := Vector2.ZERO
var _rest_position := Vector3.ZERO


## _ready(): remember the rest pose and subscribe to look changes with connect().
func _ready() -> void:
	_rest_position = position
	if controller == null:
		var node := get_parent()
		while node and not node is FPSController:
			node = node.get_parent()
		controller = node as FPSController
	if controller:
		controller.looked.connect(add_sway)


## Pushes the gun opposite to a look movement (radians, same convention as add_look_input).
func add_sway(look_delta: Vector2) -> void:
	sway += Vector2(look_delta.y, look_delta.x) * sway_degrees_per_radian
	sway = sway.clamp(Vector2.ONE * -max_sway_degrees, Vector2.ONE * max_sway_degrees)


## _process() runs every rendered frame: ease the sway back toward zero and apply it.
func _process(delta: float) -> void:
	sway = sway.lerp(Vector2.ZERO, clampf(return_speed * delta, 0.0, 1.0))
	rotation_degrees = Vector3(sway.x, sway.y, 0.0)
	var bob := controller.bob_offset * bob_follow if controller else Vector3.ZERO
	position = _rest_position - bob          # the gun dips against the camera's bob
