# FPSInput: the FPS kit's default controls (WASD, mouse, Space, Shift, Ctrl/C, R, E).
class_name FPSInput
extends RefCounted
## Default key and mouse bindings for the FPS kit, added at run time ONLY for actions the
## project has not defined itself. That makes the kit drop-in (it works in an empty project)
## while letting a game rebind anything in Project Settings > Input Map.
##
## A `static func` belongs to the class, not an instance: call FPSInput.ensure_default_actions().

const MOVE_FORWARD := &"move_forward"
const MOVE_BACK := &"move_back"
const MOVE_LEFT := &"move_left"
const MOVE_RIGHT := &"move_right"
const JUMP := &"jump"
const SPRINT := &"sprint"
const CROUCH := &"crouch"
const FIRE := &"fire"
const AIM := &"aim"
const RELOAD := &"reload"
const INTERACT := &"interact"

## action -> list of bindings. An int below 10 is a mouse button index, anything else a Key.
const DEFAULTS := {
	MOVE_FORWARD: [KEY_W, KEY_UP],
	MOVE_BACK: [KEY_S, KEY_DOWN],
	MOVE_LEFT: [KEY_A, KEY_LEFT],
	MOVE_RIGHT: [KEY_D, KEY_RIGHT],
	JUMP: [KEY_SPACE],
	SPRINT: [KEY_SHIFT],
	CROUCH: [KEY_CTRL, KEY_C],
	FIRE: [MOUSE_BUTTON_LEFT],
	AIM: [MOUSE_BUTTON_RIGHT],
	RELOAD: [KEY_R],
	INTERACT: [KEY_E, KEY_F],
}


## Adds every missing action with its default bindings. Safe to call many times.
static func ensure_default_actions() -> void:
	for action: StringName in DEFAULTS:
		if InputMap.has_action(action):
			continue                      # the project defined it: respect its bindings
		InputMap.add_action(action, 0.2)  # 0.2 = deadzone for analog sticks
		for code: int in DEFAULTS[action]:
			InputMap.action_add_event(action, _event_for(code))


## Builds the InputEvent for one binding code.
static func _event_for(code: int) -> InputEvent:
	if code < 10:
		var mouse := InputEventMouseButton.new()
		mouse.button_index = code as MouseButton
		return mouse
	var key := InputEventKey.new()
	key.physical_keycode = code as Key   # physical = same position on AZERTY/QWERTZ keyboards
	return key
