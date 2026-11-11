extends TestCase
## Headless tests for kit_combat: health, hitbox rules, hit-stop, and the combo state machine.
## The state machine is driven through FakeBody/FakeWeapon below. They are not a player or a
## sword, which proves the kit has no hidden dependency on any particular game's classes.


## A stand-in body: just the methods ComboStateMachine's contract asks for, each one recording
## that it was called so tests can check what the state machine did.
class FakeBody extends Node3D:
	var speed := 0.0                 # what get_planar_speed() reports; tests set it to fake running
	var move_dir := Vector3.ZERO     # fake stick/WASD direction
	var locked := false
	var attacks_begun := 0
	var attacks_ended := 0
	var last_knockback := Vector3.ZERO
	var respawned := 0
	var last_attack_dir := Vector3.ZERO

	## Contract: horizontal speed, used to pick IDLE vs RUN.
	func get_planar_speed() -> float:
		return speed

	## Contract: the direction the player is pushing (ZERO = no input).
	func get_move_direction() -> Vector3:
		return move_dir

	## Contract: where the body faces; Godot's forward is -Z (Vector3.FORWARD).
	func get_facing() -> Vector3:
		return Vector3.FORWARD

	## Contract: a strike starts; remember the direction so the soft-lock test can read it.
	func begin_attack(dir: Vector3, _speed: float, _time: float, _delay: float) -> void:
		attacks_begun += 1
		last_attack_dir = dir

	## Contract: a strike finished without being chained.
	func end_attack() -> void:
		attacks_ended += 1

	## Contract: freeze/unfreeze player movement (hurt and dead states).
	func lock_controls(on: bool) -> void:
		locked = on

	## Contract: push the body by this velocity.
	func apply_knockback(velocity: Vector3) -> void:
		last_knockback = velocity

	## Contract (optional): move back to the spawn point after death.
	func respawn() -> void:
		respawned += 1


## A stand-in weapon: records whether its damage window is open and which strikes armed it.
class FakeWeapon extends Node:
	var hitbox := Hitbox.new()
	var active := false
	var swings: Array[AttackData] = []

	## _ready() runs when the node enters the tree; the hitbox becomes our child then.
	func _ready() -> void:
		add_child(hitbox)

	## Contract: open/close the damage window.
	func set_active(on: bool) -> void:
		active = on

	## Contract: arm for a new strike.
	func begin_swing(attack: AttackData) -> void:
		swings.append(attack)


## Many tests here land hits, and a hit can start hit-stop (a global time-scale change).
## Resetting after every test stops one test's hit-stop leaking into the next.
func after_each() -> void:
	HitStop.reset()


# --- helpers ------------------------------------------------------------------------------

## A short strike (0.15 s) so tests run fast. hitstop 0 keeps time normal unless a test wants it.
func _attack(duration := 0.15, active_start := 0.02, active_end := 0.08, hitstop := 0.0) -> AttackData:
	var a := AttackData.new()
	a.duration = duration
	a.active_start = active_start
	a.active_end = active_end
	a.combo_window_open = active_end
	a.hitstop = hitstop
	a.stagger_time = 0.1
	a.knockback = 2.0
	return a


## Builds body + weapon + health + state machine in the tree and returns them by name.
## Adding the FSM last matters: its _ready() checks the body and weapon, so they must exist.
func _rig(strikes := 3) -> Dictionary:
	var body := add_node(FakeBody.new()) as FakeBody
	var weapon := FakeWeapon.new()
	body.add_child(weapon)
	var health := HealthComponent.new()
	health.max_health = 30.0
	body.add_child(health)
	var fsm := ComboStateMachine.new()
	fsm.body = body
	fsm.weapon = weapon
	fsm.health = health
	fsm.min_hurt_time = 0.05
	fsm.respawn_delay = 0.1
	for i in strikes:
		fsm.combo.append(_attack())
	body.add_child(fsm)                   # entering the tree runs fsm._ready()
	return {"body": body, "weapon": weapon, "health": health, "fsm": fsm}


## A target dummy: an empty Node3D with a HealthComponent child.
func _target(hp := 50.0) -> HealthComponent:
	var dummy := add_node(Node3D.new()) as Node3D
	var health := HealthComponent.new()
	health.max_health = hp
	dummy.add_child(health)
	return health


# --- HealthComponent ----------------------------------------------------------------------

func test_health_damage_death_and_revive() -> void:
	var h := _target(50.0)
	# A one-element array so the lambda (func() -> ...) can change it: lambdas capture variables
	# by value, but an array is a reference, so writing died[0] is seen out here.
	var died := [false]
	h.died.connect(func(_hit: HitInfo) -> void: died[0] = true)
	check(h.take_damage(HitInfo.new(20.0)), "first hit applied")
	check_eq(h.current_health, 30.0, "health after 20 damage")
	h.take_damage(HitInfo.new(100.0))
	check(h.is_dead and died[0], "lethal hit kills and emits died")
	check(not h.take_damage(HitInfo.new(1.0)), "the dead take no damage")
	h.revive()
	check_eq(h.current_health, 50.0, "revive restores full health")


## Invulnerability frames ("i-frames"): a second hit right after the first is ignored.
func test_health_invulnerability_window() -> void:
	var h := _target(50.0)
	h.invulnerability_time = 0.2
	h.take_damage(HitInfo.new(10.0))
	check(not h.take_damage(HitInfo.new(10.0)), "second hit inside i-frames is ignored")
	await seconds(0.25)
	check(h.take_damage(HitInfo.new(10.0)), "hit after i-frames lands")


# --- Hitbox -------------------------------------------------------------------------------

## One swing hits one target once, even if both its hurtbox and its body overlap the blade.
func test_hitbox_hits_each_target_once_per_swing() -> void:
	var h := _target()
	var hb := add_node(Hitbox.new()) as Hitbox
	hb.begin(_attack())
	hb.set_active(true)
	var hurt := Hurtbox.new()
	hurt.health = h
	add_node(hurt)
	hb._on_struck(hurt)                   # calling the signal handler directly = "it overlapped"
	hb._on_struck(h.get_parent())         # same target via its body: must not double-hit
	check_eq(h.current_health, 30.0, "one hit of 20 per swing")
	hb.begin(_attack())                   # new swing clears the memory
	hb._on_struck(hurt)
	check_eq(h.current_health, 10.0, "next swing hits again")


## A weapon never damages the body swinging it (ComboStateMachine sets hitbox.source = body).
func test_hitbox_ignores_its_own_source() -> void:
	var r := _rig()
	var hb: Hitbox = r.weapon.hitbox
	hb.begin(_attack())
	hb.set_active(true)
	hb._on_struck(r.body)
	check_eq(r.health.current_health, 30.0, "own body untouched")


## Two overlapping Area3Ds in the real physics world: proves overlaps fire in headless runs.
func test_hitbox_real_physics_overlap() -> void:
	var h := _target()
	var hurt := Hurtbox.new()
	hurt.health = h
	var hs := CollisionShape3D.new()
	hs.shape = SphereShape3D.new()
	hurt.add_child(hs)
	add_node(hurt)
	var hb := Hitbox.new()
	var bs := CollisionShape3D.new()
	bs.shape = SphereShape3D.new()
	hb.add_child(bs)
	add_node(hb)
	hb.begin(_attack())
	hb.set_active(true)
	check(await wait_until(func() -> bool: return h.current_health < 50.0, 2.0),
			"hitbox damaged an overlapping hurtbox through physics")


# --- HitStop ------------------------------------------------------------------------------

func test_hitstop_freezes_then_restores() -> void:
	HitStop.trigger(0.08)
	check_near(Engine.time_scale, HitStop.FROZEN_TIME_SCALE, 0.001, "frozen time scale")
	check(await wait_until(func() -> bool: return Engine.time_scale == 1.0, 1.0), "time restored")


## The bug HitStop.reset() exists for: a long stop from one test (or level) swallowing the next.
func test_hitstop_reset_clears_pending_stop() -> void:
	HitStop.trigger(5.0)                  # a long stop that would outlive the test
	HitStop.reset()
	check_eq(Engine.time_scale, 1.0, "reset restores time")
	HitStop.trigger(0.05)                 # must NOT be swallowed by the cancelled 5 s stop
	check_near(Engine.time_scale, HitStop.FROZEN_TIME_SCALE, 0.001, "new stop after reset works")


# --- ComboStateMachine --------------------------------------------------------------------

## physics_frames(n) waits for _physics_process to run n times, which is where the FSM ticks.
func test_combo_single_strike_opens_and_closes_weapon() -> void:
	var r := _rig()
	r.fsm.request_attack()
	await physics_frames(2)
	check_eq(r.fsm.state, ComboStateMachine.State.ATTACK_1, "state after press")
	check_eq(r.body.attacks_begun, 1, "body lunged once")
	check(await wait_until(func() -> bool: return r.weapon.active, 0.5), "weapon window opened")
	check(await wait_until(func() -> bool: return r.fsm.state == ComboStateMachine.State.IDLE, 1.0),
			"back to IDLE after the strike")
	check(not r.weapon.active, "weapon closed after the strike")
	check_eq(r.body.attacks_ended, 1, "end_attack called")


## Pressing during a strike buffers the press; it chains when the combo window opens.
func test_combo_buffered_press_chains_all_strikes() -> void:
	var r := _rig(3)
	r.fsm.request_attack()
	await physics_frames(2)
	r.fsm.request_attack()                # buffered during strike 1 -> chains to 2
	check(await wait_until(func() -> bool: return r.fsm.combo_index() == 1, 1.0), "chained to strike 2")
	r.fsm.request_attack()
	check(await wait_until(func() -> bool: return r.fsm.combo_index() == 2, 1.0), "chained to strike 3")
	check_eq(r.weapon.swings.size(), 3, "weapon armed three times")


## A press older than input_buffer_seconds is forgotten, so a stale tap never fires late.
func test_combo_stale_press_does_not_attack() -> void:
	var r := _rig()
	r.fsm.input_buffer_seconds = 0.05
	r.fsm.set_physics_process(false)      # pause the FSM's _physics_process so the press ages
	r.fsm.request_attack()
	await seconds(0.1)
	r.fsm.set_physics_process(true)
	await physics_frames(3)
	check_eq(r.fsm.state, ComboStateMachine.State.IDLE, "a press older than the buffer is dropped")


## Locomotion: above run_threshold the state is RUN, below it IDLE (drives idle/run animations).
func test_combo_run_state_follows_speed() -> void:
	var r := _rig()
	r.body.speed = 3.0
	await physics_frames(2)
	check_eq(r.fsm.state, ComboStateMachine.State.RUN, "RUN when moving")
	r.body.speed = 0.0
	await physics_frames(2)
	check_eq(r.fsm.state, ComboStateMachine.State.IDLE, "IDLE when stopped")


## Getting hit mid-swing: the HealthComponent `damaged` signal cancels the swing, locks
## movement, forwards knockback, and gives control back after the stagger time.
func test_combo_hit_interrupts_and_locks_controls() -> void:
	var r := _rig()
	r.fsm.request_attack()
	await physics_frames(3)
	r.health.take_damage(HitInfo.new(5.0, null, Vector3(1, 0, 0), 0.05))
	check_eq(r.fsm.state, ComboStateMachine.State.HURT, "hit -> HURT")
	check(r.body.locked and not r.weapon.active, "controls locked, swing cancelled")
	check_eq(r.body.last_knockback, Vector3(1, 0, 0), "knockback forwarded to the body")
	check(await wait_until(func() -> bool: return not r.body.locked, 1.0), "controls return after the flinch")


## Death: the `died` signal moves to DEAD; with auto_respawn the FSM waits respawn_delay
## (an awaited timer), revives health and calls body.respawn().
func test_combo_death_and_auto_respawn() -> void:
	var r := _rig()
	r.health.take_damage(HitInfo.new(999.0))
	check_eq(r.fsm.state, ComboStateMachine.State.DEAD, "lethal hit -> DEAD")
	check(await wait_until(func() -> bool: return r.fsm.state == ComboStateMachine.State.IDLE, 1.0),
			"respawned to IDLE")
	check_eq(r.body.respawned, 1, "body.respawn() called")
	check_eq(r.health.current_health, 30.0, "health revived")


## Soft lock: with no stick input, a strike turns toward the nearest enemy in front.
func test_combo_soft_lock_turns_toward_enemy() -> void:
	var r := _rig()
	var enemy := add_node(Node3D.new()) as Node3D
	enemy.add_to_group(&"enemies")
	enemy.global_position = Vector3(1.0, 0.0, -2.0)     # ahead (-Z) and to the right
	r.fsm.request_attack()
	await physics_frames(2)
	check_near(r.body.last_attack_dir, Vector3(1, 0, -2).normalized(), 0.01, "strike snapped to enemy")


## Wiring a plain Node3D as the body must be refused at start-up with a clear error that names
## the missing methods, and the FSM must switch itself off instead of crashing mid-fight.
func test_combo_refuses_body_without_contract() -> void:
	expect_error("is missing get_planar_speed")
	var holder := add_node(Node3D.new()) as Node3D
	var fsm := ComboStateMachine.new()
	fsm.body = holder                     # Node3D has none of the contract methods
	fsm.weapon = FakeWeapon.new()
	holder.add_child(fsm.weapon)
	holder.add_child(fsm)                 # _ready() runs here and should push_error
	check(not fsm.is_physics_processing(), "FSM disabled itself")
