# FPSController: a drop-in first-person body. Add it to a scene and it builds what it needs.
class_name FPSController
extends CharacterBody3D
## First-person character: mouse look (pointer lock on the web), pitch clamp, walk/sprint/crouch,
## jumps with coyote time and an input buffer, head bob. Content-free: no meshes, no sounds.
##
## NODE LAYOUT (created in _ready() if you did not add them yourself):
##   FPSController (this, origin at the FEET)
##   ├─ CollisionShape3D   capsule, resized when crouching
##   └─ Head (Node3D)      yaw is on the body, pitch is on the head
##      └─ Camera3D        head bob moves the camera, never the head
##         (put a ViewmodelSway with your gun model under the camera)
##
## INPUT: uses FPSInput's actions (added automatically if the project lacks them). Touch
## controls and recoil call add_look_input() directly.
##
## WEB POINTER LOCK: browsers only allow the mouse to be captured in response to a click, so
## the first click captures (and does not fire), and Esc releases.

## Emitted when a jump starts.
signal jumped
## Emitted on touching the ground after being airborne; fall_speed is in m/s (positive).
signal landed(fall_speed: float)
signal crouch_changed(is_crouching: bool)
## Every look change in radians (x = yaw right, y = pitch down). ViewmodelSway listens to this.
signal looked(delta: Vector2)

@export_group("Movement")
@export var walk_speed := 5.0
@export var sprint_speed := 8.0
@export var crouch_speed := 2.5
## Ground acceleration and braking, m/s². High = snappy arena shooter, low = heavy horror walk.
@export var acceleration := 60.0
## How much control you keep in the air, m/s².
@export var air_acceleration := 12.0

@export_group("Jump")
@export var jump_velocity := 4.8
## Seconds after walking off a ledge during which a jump still works ("coyote time").
@export var coyote_time := 0.12
## Seconds a jump press is remembered before landing, so an early press is not lost.
@export var jump_buffer := 0.12

@export_group("Look")
## Radians of turn per pixel of mouse movement.
@export var mouse_sensitivity := 0.0025
## Pitch is clamped to ±this many degrees so the view can never flip over.
@export_range(1.0, 89.9) var pitch_limit_degrees := 89.0
## Capture the mouse on click. Turn off for menus, or when touch controls drive the look.
@export var mouse_capture_enabled := true

@export_group("Crouch")
@export var stand_height := 1.8
@export var crouch_height := 1.0
## Eye distance below the top of the capsule.
@export var eye_offset := 0.15
## How fast the head slides between standing and crouched eye height.
@export var crouch_transition_speed := 12.0

@export_group("Head Bob")
## Bob cycles per metre walked.
@export var bob_frequency := 0.6
## Vertical bob in metres (the sideways sway is half of this). 0 disables bob.
@export var bob_amplitude := 0.04

var head: Node3D
var camera: Camera3D
var collision: CollisionShape3D
var is_crouching := false
var is_sprinting := false
## The camera's current head-bob offset (read it to sync footstep sounds or a viewmodel).
var bob_offset := Vector3.ZERO

var _capsule: CapsuleShape3D
var _air_time := 0.0
var _jumped_since_floor := false
var _jump_pressed_msec := -100000
var _was_on_floor := true
var _fall_speed := 0.0
var _bob_distance := 0.0
var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)


## _ready(): set up input defaults and build any missing child nodes.
func _ready() -> void:
	FPSInput.ensure_default_actions()
	_build_nodes()
	_set_capsule_height(stand_height)
	head.position.y = stand_height - eye_offset


# --- Look --------------------------------------------------------------------------------

## Pitch in radians (positive = looking up).
func get_pitch() -> float:
	return head.rotation.x


## Yaw in radians (the body's rotation around Y).
func get_yaw() -> float:
	return rotation.y


## Turns the view. delta.x > 0 turns right, delta.y > 0 looks down (same as mouse movement).
## Mouse, touch look pad and weapon recoil all come through here, so the clamp always applies.
func add_look_input(delta: Vector2) -> void:
	rotate_y(-delta.x)
	var limit := deg_to_rad(pitch_limit_degrees)
	head.rotation.x = clampf(head.rotation.x - delta.y, -limit, limit)
	looked.emit(delta)


## _unhandled_input() gets input the UI did not use: mouse capture and mouse look live here.
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and mouse_capture_enabled \
			and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED     # a click is the user gesture browsers need
		get_viewport().set_input_as_handled()            # so this click does not also fire
	elif event.is_action_pressed(&"ui_cancel") and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		add_look_input((event as InputEventMouseMotion).relative * mouse_sensitivity)


# --- Movement ----------------------------------------------------------------------------

## Remembers a jump press for `jump_buffer` seconds. Called by input polling, touch or AI.
func request_jump() -> void:
	_jump_pressed_msec = Time.get_ticks_msec()


## Horizontal speed in m/s (for animations, footsteps, ComboStateMachine).
func get_planar_speed() -> float:
	return Vector2(velocity.x, velocity.z).length()


## _physics_process(): runs at the fixed physics rate. Order matters: gravity, crouch, jump,
## walk, then move_and_slide() applies it all and updates is_on_floor() for the next tick.
func _physics_process(delta: float) -> void:
	if Input.is_action_just_pressed(FPSInput.JUMP):
		request_jump()
	_apply_gravity(delta)
	_update_crouch(delta)
	_try_jump()
	_walk(delta)
	move_and_slide()
	_track_landing()
	_update_bob(delta)


## Falls while airborne and tracks air time (for coyote time) and the fastest fall (for `landed`).
func _apply_gravity(delta: float) -> void:
	if is_on_floor():
		_air_time = 0.0
		_jumped_since_floor = false
	else:
		_air_time += delta
		velocity.y -= _gravity * delta
		_fall_speed = maxf(_fall_speed, -velocity.y)


## A buffered press jumps if we are on the floor, or just left it without jumping (coyote).
func _try_jump() -> void:
	var buffered := Time.get_ticks_msec() - _jump_pressed_msec <= int(jump_buffer * 1000.0)
	var grounded := is_on_floor() or (_air_time <= coyote_time and not _jumped_since_floor)
	if buffered and grounded and not is_crouching:
		velocity.y = jump_velocity
		_jump_pressed_msec = -100000          # consume the press so it fires once
		_jumped_since_floor = true
		_air_time = coyote_time + 1.0         # no coyote second jump
		jumped.emit()


## Turns WASD/stick input into horizontal velocity. Input.get_vector() returns a Vector2 with
## length ≤ 1 (analog sticks give partial values), x = right, y = back.
func _walk(delta: float) -> void:
	var input := Input.get_vector(FPSInput.MOVE_LEFT, FPSInput.MOVE_RIGHT, FPSInput.MOVE_FORWARD, FPSInput.MOVE_BACK)
	# Sprint only while pushing forward (input.y < 0 is forward) and standing.
	is_sprinting = Input.is_action_pressed(FPSInput.SPRINT) and input.y < -0.1 and not is_crouching
	var speed := crouch_speed if is_crouching else (sprint_speed if is_sprinting else walk_speed)
	# basis turns stick input (x right, y back) into a world direction that follows our yaw.
	var direction := (global_basis * Vector3(input.x, 0.0, input.y))
	direction.y = 0.0
	var target := direction.normalized() * speed * minf(input.length(), 1.0)
	var accel := acceleration if is_on_floor() else air_acceleration
	velocity.x = move_toward(velocity.x, target.x, accel * delta)
	velocity.z = move_toward(velocity.z, target.z, accel * delta)


## Crouch while held; stand up only when there is room above the head.
func _update_crouch(delta: float) -> void:
	var want := Input.is_action_pressed(FPSInput.CROUCH)
	if want and not is_crouching:
		_set_crouching(true)
	elif not want and is_crouching and can_stand():
		_set_crouching(false)
	var eye := (crouch_height if is_crouching else stand_height) - eye_offset
	head.position.y = lerpf(head.position.y, eye, clampf(crouch_transition_speed * delta, 0.0, 1.0))


## True when standing up would not push the capsule into a ceiling. test_move() sweeps our
## current (crouched) shape upward without actually moving and reports any collision.
func can_stand() -> bool:
	return not test_move(global_transform, Vector3.UP * (stand_height - crouch_height))


## Resizes the capsule and announces the change (a HUD or sound can connect to crouch_changed).
func _set_crouching(on: bool) -> void:
	is_crouching = on
	_set_capsule_height(crouch_height if on else stand_height)
	crouch_changed.emit(on)


## Emits `landed` on the first tick back on the ground (for landing sounds, camera dip, fall damage).
func _track_landing() -> void:
	var on_floor := is_on_floor()
	if on_floor and not _was_on_floor:
		landed.emit(_fall_speed)
		_fall_speed = 0.0
	_was_on_floor = on_floor


## Head bob: a figure-of-eight driven by distance walked, so it matches stride at any speed,
## and eases back to rest when you stop or leave the ground.
func _update_bob(delta: float) -> void:
	var speed := get_planar_speed()
	if bob_amplitude > 0.0 and is_on_floor() and speed > 0.5:
		_bob_distance += speed * delta
		var phase := _bob_distance * bob_frequency * TAU
		bob_offset = Vector3(cos(phase * 0.5) * bob_amplitude * 0.5, absf(sin(phase)) * bob_amplitude, 0.0)
	else:
		bob_offset = bob_offset.lerp(Vector3.ZERO, clampf(10.0 * delta, 0.0, 1.0))
	camera.position = bob_offset


# --- Setup -------------------------------------------------------------------------------

## Uses child nodes named CollisionShape3D, Head and Head/Camera3D if present; creates them otherwise.
func _build_nodes() -> void:
	collision = get_node_or_null(^"CollisionShape3D") as CollisionShape3D
	if collision == null:
		collision = CollisionShape3D.new()
		collision.name = "CollisionShape3D"
		add_child(collision)
	_capsule = collision.shape as CapsuleShape3D
	if _capsule == null:
		_capsule = CapsuleShape3D.new()
		_capsule.radius = 0.35
		collision.shape = _capsule
	head = get_node_or_null(^"Head") as Node3D
	if head == null:
		head = Node3D.new()
		head.name = "Head"
		add_child(head)
	camera = head.get_node_or_null(^"Camera3D") as Camera3D
	if camera == null:
		camera = Camera3D.new()
		camera.name = "Camera3D"
		camera.fov = 80.0
		camera.near = 0.05               # close enough for a viewmodel not to clip
		head.add_child(camera)


## Capsule height includes its rounded ends; the shape is lifted so the body origin stays at the feet.
func _set_capsule_height(h: float) -> void:
	_capsule.height = maxf(h, _capsule.radius * 2.0)
	collision.position.y = _capsule.height * 0.5
