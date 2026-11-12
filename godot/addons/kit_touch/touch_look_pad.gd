class_name TouchLookPad
extends Control
## Drag anywhere on this area to orbit the camera. It sits beneath the joystick and buttons,
## which take their own touches first. It tracks one finger, so a thumb on the stick and a
## thumb here work at the same time.

signal look_dragged(delta_radians: Vector2)

## Radians of camera turn per UI pixel of drag.
@export var sensitivity := 0.006

var _touch := -1


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP


func _gui_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		var touch := event as InputEventScreenTouch
		if touch.pressed and _touch == -1:
			_touch = touch.index
			accept_event()
		elif not touch.pressed and touch.index == _touch:
			_touch = -1
			accept_event()
	elif event is InputEventScreenDrag and (event as InputEventScreenDrag).index == _touch:
		look_dragged.emit((event as InputEventScreenDrag).relative * sensitivity)
		accept_event()
