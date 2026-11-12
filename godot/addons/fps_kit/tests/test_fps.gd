extends TestCase
## Headless tests for fps_kit: one or more per feature (look, sprint, crouch, coyote/buffered
## jump, head bob, viewmodel sway, hitscan, projectile, ammo/reload, recoil, interact, touch look).
## Everything is built from code (a box floor, a box target), so the kit needs no content.
## Movement is driven with Input.action_press(), exactly what a key press does.


## A lever: the only thing FPSInteractor needs is an interact(by) method.
class Lever extends StaticBody3D:
	var uses := 0

	## Called by FPSInteractor.try_interact().
	func interact(_by: Node) -> void:
		uses += 1


# --- helpers ------------------------------------------------------------------------------

## A 40×40 m box floor whose top surface is at y = 0.
func _floor() -> StaticBody3D:
	var floor_body := add_node(StaticBody3D.new()) as StaticBody3D
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40.0, 1.0, 40.0)
	shape.shape = box
	shape.position.y = -0.5
	floor_body.add_child(shape)
	return floor_body


## A static box of `size` centred at `at`, optionally with a HealthComponent to shoot.
func _box(at: Vector3, size: Vector3, with_health := false) -> StaticBody3D:
	var body := add_node(StaticBody3D.new()) as StaticBody3D
	body.position = at
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	body.add_child(shape)
	if with_health:
		var health := HealthComponent.new()
		health.max_health = 100.0
		body.add_child(health)
	return body


## GOTCHA: a body added this frame is not in the physics space until the next physics step, so
## an instant ray (hitscan, interact) cast right away goes straight through it. Await this after
## spawning anything a ray must hit. (Games hit the same thing when spawning enemies and firing
## on the same frame.)
func _settle_physics() -> void:
	await physics_frames(2)


## A controller standing on a fresh floor (feet at `at`). Waits for it to settle on the ground.
func _player(at := Vector3(0.0, 0.05, 0.0), on_floor := true) -> FPSController:
	if on_floor:
		_floor()
	var p := FPSController.new()
	p.position = at
	add_node(p)
	if on_floor:
		await wait_until(func() -> bool: return p.is_on_floor(), 1.0)
	return p


## A weapon on the player's camera with deterministic randomness and no input polling.
func _gun(p: FPSController, data: WeaponData) -> FPSWeapon:
	var gun := FPSWeapon.new()
	gun.data = data
	gun.handle_input = false
	gun.random_seed = 7
	p.camera.add_child(gun)
	return gun


## A small test gun: 25 damage, 2-round magazine, 3 spare rounds, 0.1 s reload (fast tests).
func _pistol() -> WeaponData:
	var d := WeaponData.new()
	d.damage = 25.0
	d.fire_rate = 5.0
	d.magazine_size = 2
	d.reserve_ammo = 3
	d.reload_time = 0.1
	return d


# --- setup / look -------------------------------------------------------------------------

## The controller adds WASD/mouse bindings for any action the project did not define.
func test_default_actions_added() -> void:
	await _player()
	for action in FPSInput.DEFAULTS:
		check(InputMap.has_action(action), "action %s exists" % action)


## Drop-in: an FPSController with no children creates its capsule, head and camera in _ready().
func test_builds_its_own_nodes() -> void:
	var p := await _player()
	check(p.head != null and p.camera != null and p.collision != null, "head, camera, collision created")
	check_near(p.camera.global_position.y, 0.0 + p.stand_height - p.eye_offset, 0.1, "eye height")


## Pitch can never pass the limit, however far the mouse moves; yaw is unlimited.
func test_look_pitch_is_clamped() -> void:
	var p := await _player()
	p.add_look_input(Vector2(0.0, -10.0))          # way up
	check_near(p.get_pitch(), deg_to_rad(p.pitch_limit_degrees), 0.0001, "pitch at upper clamp")
	p.add_look_input(Vector2(0.0, 20.0))           # way down
	check_near(p.get_pitch(), -deg_to_rad(p.pitch_limit_degrees), 0.0001, "pitch at lower clamp")
	p.add_look_input(Vector2(0.5, 0.0))
	check_near(p.get_yaw(), -0.5, 0.0001, "turning right is negative yaw (Godot's Y-up rule)")


## Mouse motion is ignored while the mouse is not captured (menus, pointer lock lost).
func test_mouse_motion_ignored_without_capture() -> void:
	var p := await _player()
	var motion := InputEventMouseMotion.new()
	motion.relative = Vector2(200.0, 0.0)
	p._unhandled_input(motion)
	check_eq(p.get_yaw(), 0.0, "yaw unchanged")


# --- movement -----------------------------------------------------------------------------

func test_walk_reaches_walk_speed_forward() -> void:
	var p := await _player()
	Input.action_press(FPSInput.MOVE_FORWARD)
	await seconds(0.4)
	check_near(p.get_planar_speed(), p.walk_speed, 0.1, "walk speed")
	check(p.global_position.z < -0.5, "moved forward (-Z), z = %.2f" % p.global_position.z)


## Sprint needs forward input: holding Shift while backpedalling stays at walk speed.
func test_sprint_only_when_moving_forward() -> void:
	var p := await _player()
	Input.action_press(FPSInput.MOVE_FORWARD)
	Input.action_press(FPSInput.SPRINT)
	await seconds(0.4)
	check(p.is_sprinting, "sprinting forward")
	check_near(p.get_planar_speed(), p.sprint_speed, 0.15, "sprint speed")
	Input.action_release(FPSInput.MOVE_FORWARD)
	Input.action_press(FPSInput.MOVE_BACK)
	await seconds(0.4)
	check(not p.is_sprinting, "no sprint backwards")
	check_near(p.get_planar_speed(), p.walk_speed, 0.15, "back to walk speed")


## Holding crouch shrinks the collision capsule (fits under vents) and slides the eyes down.
func test_crouch_lowers_capsule_and_eyes() -> void:
	var p := await _player()
	Input.action_press(FPSInput.CROUCH)
	await seconds(0.4)
	check(p.is_crouching, "crouching")
	check_near(p._capsule.height, p.crouch_height, 0.001, "capsule height")
	check_near(p.head.position.y, p.crouch_height - p.eye_offset, 0.05, "eyes lowered")
	Input.action_release(FPSInput.CROUCH)
	await seconds(0.4)
	check(not p.is_crouching, "stood up")
	check_near(p.head.position.y, p.stand_height - p.eye_offset, 0.05, "eyes back up")


## Releasing crouch under a low ceiling keeps you crouched until there is room.
func test_cannot_stand_under_low_ceiling() -> void:
	var p := await _player()
	Input.action_press(FPSInput.CROUCH)
	await physics_frames(3)
	var ceiling := _box(Vector3(0.0, 1.4, 0.0), Vector3(4.0, 0.2, 4.0))   # underside at 1.3 m
	Input.action_release(FPSInput.CROUCH)
	await physics_frames(5)
	check(p.is_crouching, "still crouched under the ceiling")
	ceiling.free()
	await physics_frames(5)
	check(not p.is_crouching, "stands once the ceiling is gone")


## A grounded jump goes up, comes down, and emits `jumped` then `landed` (connect() a lambda
## to each signal to record the order).
func test_jump_and_land_signals() -> void:
	var p := await _player()
	var events: Array[String] = []
	p.jumped.connect(func() -> void: events.append("jumped"))
	p.landed.connect(func(_speed: float) -> void: events.append("landed"))
	p.request_jump()
	await physics_frames(2)
	check(p.velocity.y > 0.0, "moving up after jump")
	check(await wait_until(func() -> bool: return events.has("landed"), 2.0), "landed again")
	check_eq(events, ["jumped", "landed"] as Array[String], "signal order")


## Coyote time: a jump just after leaving the ground still works...
func test_coyote_jump_just_after_leaving_ground() -> void:
	var p := await _player(Vector3(0.0, 3.0, 0.0), false)    # airborne, never jumped
	await seconds(0.05)                                     # inside the 0.12 s window
	p.request_jump()
	await physics_frames(2)
	check(p.velocity.y > 0.0, "coyote jump fired (vy = %.2f)" % p.velocity.y)


## ...but not once the window has passed.
func test_no_jump_after_coyote_window() -> void:
	var p := await _player(Vector3(0.0, 3.0, 0.0), false)
	await seconds(p.coyote_time + 0.1)
	p.request_jump()
	await physics_frames(2)
	check(p.velocity.y < 0.0, "still falling, no mid-air jump")


## Jump buffer: a press just BEFORE landing jumps on the landing frame.
func test_buffered_jump_fires_on_landing() -> void:
	_floor()
	var p := FPSController.new()
	p.position = Vector3(0.0, 0.15, 0.0)
	p.coyote_time = 0.0                    # isolate the buffer from coyote time
	p.jump_buffer = 0.3
	add_node(p)
	var jumped := [false]                  # array: lambdas can change its contents
	p.jumped.connect(func() -> void: jumped[0] = true)
	await physics_frames(1)
	check(not p.is_on_floor(), "starts airborne")
	p.request_jump()
	check(await wait_until(func() -> bool: return jumped[0], 1.0), "buffered press jumped on landing")


## Head bob is zero standing still, peaks while walking, and eases back to zero on stopping.
func test_head_bob_only_while_walking() -> void:
	var p := await _player()
	await seconds(0.2)
	check_near(p.bob_offset.length(), 0.0, 0.001, "no bob standing still")
	Input.action_press(FPSInput.MOVE_FORWARD)
	var peak := [0.0]
	var watch := func() -> bool:
		peak[0] = maxf(peak[0], p.bob_offset.y)
		return false
	await wait_until(watch, 0.8)
	check(peak[0] > p.bob_amplitude * 0.5, "bob peak %.3f m while walking" % peak[0])
	Input.action_release(FPSInput.MOVE_FORWARD)
	check(await wait_until(func() -> bool: return p.bob_offset.length() < 0.002, 1.5), "bob settles when stopping")


## The gun lags a turn (via the controller's `looked` signal), is capped, and springs back.
func test_viewmodel_sways_then_settles() -> void:
	var p := await _player()
	var sway := ViewmodelSway.new()
	p.camera.add_child(sway)
	p.add_look_input(Vector2(0.1, 0.0))
	check(absf(sway.sway.y) > 1.0, "gun swayed (%.2f°)" % sway.sway.y)
	p.add_look_input(Vector2(5.0, 0.0))
	check(absf(sway.sway.y) <= sway.max_sway_degrees + 0.001, "sway is capped")
	check(await wait_until(func() -> bool: return sway.sway.length() < 0.05, 2.0), "gun returns to rest")


# --- weapons ------------------------------------------------------------------------------

## Hitscan: the ray damages the target's HealthComponent instantly and uses one round.
func test_hitscan_damages_target_and_uses_ammo() -> void:
	var p := await _player()
	var target := _box(Vector3(0.0, 1.0, -5.0), Vector3(1.0, 2.0, 1.0), true)
	await _settle_physics()
	var gun := _gun(p, _pistol())
	var hits := [0]
	gun.hit.connect(func(_c: Node, _pos: Vector3, _n: Vector3) -> void: hits[0] += 1)
	check(gun.try_fire(), "first shot fires")
	var health := HealthComponent.resolve(target)
	check_eq(health.current_health, 75.0, "target took 25")
	check_eq(hits[0], 1, "hit signal")
	check_eq(gun.ammo_in_magazine, 1, "one round used")
	check(not gun.try_fire(), "fire rate blocks an instant second shot")


## A weapon saved inside a controller scene runs _ready() before the controller has built its
## camera. It must still find the camera and fire on the first shot.
func test_weapon_ready_before_controller_finds_camera() -> void:
	_floor()
	var p := FPSController.new()
	p.position = Vector3(0.0, 0.05, 0.0)
	var gun := FPSWeapon.new()
	gun.data = _pistol()
	gun.handle_input = false
	p.add_child(gun)                 # child first: its _ready() runs before the controller's
	add_node(p)
	check(gun.aim == null, "aim is not known yet at _ready (the case being tested)")
	await _settle_physics()
	check(gun.try_fire(), "first shot still fires")
	check(gun.aim == p.camera, "aim resolved to the controller's camera")


## The click that captures the mouse must not fire, even while it is still held down.
func test_capture_click_does_not_fire() -> void:
	var p := await _player()
	var gun := _gun(p, _pistol())
	gun.handle_input = true
	p.mouse_capture_enabled = false  # headless Godot cannot really capture; skip that guard
	p.capture_click_held = true      # what _unhandled_input sets on the capturing click
	Input.action_press(FPSInput.FIRE)
	await physics_frames(3)
	check_eq(gun.ammo_in_magazine, 2, "held capture click fired nothing")
	Input.action_release(FPSInput.FIRE)
	await physics_frames(2)
	check(not p.capture_click_held, "released: the flag clears")
	Input.action_press(FPSInput.FIRE)
	await physics_frames(2)
	Input.action_release(FPSInput.FIRE)
	check_eq(gun.ammo_in_magazine, 1, "the next real click fires")


## The controller flags the capturing click itself.
func test_capturing_click_sets_flag() -> void:
	var p := await _player()
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	p._unhandled_input(click)
	check(p.capture_click_held, "capture click is remembered until released")
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


## Each shot pitches the view up by recoil_pitch_degrees (through add_look_input, so it is clamped).
func test_recoil_kicks_view_up() -> void:
	var p := await _player()
	var gun := _gun(p, _pistol())
	gun.try_fire()
	check_near(p.get_pitch(), deg_to_rad(gun.data.recoil_pitch_degrees), 0.0001, "pitch raised by recoil")


## Empty magazine: the trigger clicks (dry_fired), an automatic reload starts, and reload
## takes only what the magazine needs from the reserve.
func test_empty_magazine_dry_fires_and_reloads() -> void:
	var p := await _player()
	var data := _pistol()
	data.fire_rate = 1000.0                    # no cooldown in the way
	var gun := _gun(p, data)
	var dry := [false]
	gun.dry_fired.connect(func() -> void: dry[0] = true)
	gun.try_fire()
	await physics_frames(1)
	gun.try_fire()
	await physics_frames(1)
	check(not gun.try_fire(), "empty gun does not fire")
	check(dry[0], "dry_fired emitted")
	check(gun.is_reloading, "auto-reload started")
	check(await wait_until(func() -> bool: return not gun.is_reloading, 1.0), "reload finished")
	check_eq(gun.ammo_in_magazine, 2, "magazine refilled")
	check_eq(gun.reserve_ammo, 1, "reserve 3 -> 1")


## Projectile mode: no instant damage; the FPSProjectile flies and hits a moment later.
func test_projectile_travels_and_damages() -> void:
	var p := await _player()
	var target := _box(Vector3(0.0, 1.0, -8.0), Vector3(1.0, 2.0, 1.0), true)
	var data := _pistol()
	data.fire_mode = WeaponData.FireMode.PROJECTILE
	data.projectile_speed = 40.0
	var gun := _gun(p, data)
	gun.try_fire()
	var health := HealthComponent.resolve(target)
	check_eq(health.current_health, 100.0, "no instant damage from a projectile")
	check(await wait_until(func() -> bool: return health.current_health < 100.0, 1.0), "projectile hit within 1 s")


## A shotgun is just pellets > 1 with spread: every pellet is its own ray and its own hit.
func test_shotgun_pellets_all_land_at_close_range() -> void:
	var p := await _player()
	var target := _box(Vector3(0.0, 1.0, -2.0), Vector3(3.0, 3.0, 1.0), true)
	await _settle_physics()
	var data := _pistol()
	data.damage = 5.0
	data.pellets = 8
	data.spread_degrees = 6.0
	var gun := _gun(p, data)
	gun.try_fire()
	check_eq(HealthComponent.resolve(target).current_health, 60.0, "8 pellets × 5 damage")


# --- interact / touch ---------------------------------------------------------------------

## Looking at the lever focuses it, try_interact() calls its interact(), looking away clears focus.
func test_interact_ray_focuses_and_uses() -> void:
	var p := await _player()
	var lever := Lever.new()
	lever.position = Vector3(0.0, 1.65, -1.5)
	var shape := CollisionShape3D.new()
	shape.shape = BoxShape3D.new()
	lever.add_child(shape)
	add_node(lever)
	var ray := FPSInteractor.new()
	ray.handle_input = false
	p.camera.add_child(ray)
	check(await wait_until(func() -> bool: return ray.focus == lever, 1.0), "lever in focus")
	check(ray.try_interact(), "interact succeeded")
	check_eq(lever.uses, 1, "lever.interact() called once")
	p.add_look_input(Vector2(PI / 2.0, 0.0))        # turn away
	check(await wait_until(func() -> bool: return ray.focus == null, 1.0), "focus lost when looking away")


## The touch look pad turns the view through the same add_look_input() as the mouse.
func test_touch_look_pad_turns_view() -> void:
	var p := await _player()
	var pad := TouchLookPad.new()
	add_node(pad)
	pad.look_dragged.connect(p.add_look_input)
	var touch := InputEventScreenTouch.new()
	touch.index = 0
	touch.pressed = true
	pad._gui_input(touch)
	var drag := InputEventScreenDrag.new()
	drag.index = 0
	drag.relative = Vector2(100.0, 0.0)
	pad._gui_input(drag)
	check_near(p.get_yaw(), -100.0 * pad.sensitivity, 0.0001, "drag right turned right")
