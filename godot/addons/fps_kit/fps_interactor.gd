# FPSInteractor: "press E to use". A ray from the camera that finds things you can interact with.
class_name FPSInteractor
extends RayCast3D
## Put it under the controller's Camera3D. Anything with an `interact(by: Node)` method (on the
## collider or its parent) becomes the focus while you look at it within `reach` metres;
## pressing the interact action calls it. Doors, switches, pickups and notes only need that one
## method, so they never depend on this kit.
##
## Connect `focus_changed` to show a prompt; read `focus.get("prompt")` for its text, if any.

## The looked-at interactable changed (null = nothing): show or hide the "E: use" prompt.
signal focus_changed(target: Node)
## interact() was just called on `target`.
signal interacted(target: Node)

@export var reach := 2.5
@export var handle_input := true

## What is being looked at right now (null when nothing interactable is in reach).
var focus: Node


## _ready(): point the ray forward, hit areas too, and never hit the player's own body.
func _ready() -> void:
	target_position = Vector3(0.0, 0.0, -reach)
	collide_with_areas = true
	var node := get_parent()
	while node:
		if node is CollisionObject3D:
			add_exception(node)
			break
		node = node.get_parent()


## Every physics tick: re-read the ray, update the focus, handle the button.
func _physics_process(_delta: float) -> void:
	force_raycast_update()                 # read this tick's result, not last tick's
	var found := _interactable(get_collider() as Node) if is_colliding() else null
	if found != focus:
		focus = found
		focus_changed.emit(focus)
	if handle_input and Input.is_action_just_pressed(FPSInput.INTERACT):
		try_interact()


## Calls interact() on the current focus. Returns true if something was used.
func try_interact() -> bool:
	if focus == null or not is_instance_valid(focus):
		return false
	focus.interact(owner if owner else get_parent())
	interacted.emit(focus)
	return true


## The collider itself or its parent, whichever has interact(); otherwise null.
func _interactable(node: Node) -> Node:
	if node == null:
		return null
	if node.has_method(&"interact"):
		return node
	var parent := node.get_parent()
	return parent if parent and parent.has_method(&"interact") else null
