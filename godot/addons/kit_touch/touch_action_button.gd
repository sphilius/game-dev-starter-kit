class_name TouchActionButton
extends Control
## Round on-screen button, safe for multi-touch. With an `action`, it fires an InputEventAction
## through Input.parse_input_event(). That way _unhandled_input handlers (for example a combat input buffer) and Input.is_action_pressed() polling (sprint, jump) both see it, like a real key.
## Without an action it just emits `activated` (fullscreen, quality, respawn).

signal activated
signal pressed_changed(is_pressed: bool)

@export var action: StringName
@export var label := ""
## Tap to latch on, tap again to release (for example, sprint).
@export var toggle := false
@export var tint := Color(1.0, 0.92, 0.8)
@export var font_size := 26

var is_pressed := false
var _touch := -1


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP


## Only the circle counts as the button, not its square bounding box.
func _has_point(point: Vector2) -> bool:
	return point.distance_to(size * 0.5) <= minf(size.x, size.y) * 0.5


func _gui_input(event: InputEvent) -> void:
	var touch := event as InputEventScreenTouch
	if touch == null:
		return
	if touch.pressed and _touch == -1:
		_touch = touch.index
		_set_pressed(not is_pressed if toggle else true)
		activated.emit()
		accept_event()
	elif not touch.pressed and touch.index == _touch:
		_touch = -1
		if not toggle:
			_set_pressed(false)
		accept_event()


func _notification(what: int) -> void:
	if what in [NOTIFICATION_WM_WINDOW_FOCUS_OUT, NOTIFICATION_APPLICATION_FOCUS_OUT, NOTIFICATION_EXIT_TREE] and not toggle:
		_touch = -1
		_set_pressed(false)


func _set_pressed(on: bool) -> void:
	if on == is_pressed:
		return
	is_pressed = on
	if action != &"":
		var event := InputEventAction.new()
		event.action = action
		event.pressed = on
		event.strength = 1.0 if on else 0.0
		Input.parse_input_event(event)
	pressed_changed.emit(on)
	queue_redraw()


func _draw() -> void:
	var r := minf(size.x, size.y) * 0.5
	var centre := size * 0.5
	draw_circle(centre, r, Color(tint, 0.42 if is_pressed else 0.16))
	draw_arc(centre, r - 1.5, 0.0, TAU, 48, Color(tint, 0.75 if is_pressed else 0.45), 3.0, true)
	var font := get_theme_default_font()
	var baseline := centre.y + font_size * 0.36
	draw_string(font, Vector2(0.0, baseline), label, HORIZONTAL_ALIGNMENT_CENTER, size.x, font_size, Color(tint, 0.95))
