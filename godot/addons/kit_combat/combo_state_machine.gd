class_name ComboStateMachine
extends Node
## (`class_name` makes ComboStateMachine a global type you can add from the Create Node dialog.)
## Melee combo state machine: IDLE, RUN, ATTACK (one state per strike), HURT and DEAD.
## Lifted from the open-world kit's samurai FSM, with every hard type removed so any body and
## any weapon can use it.
##
## HOW IT TALKS TO THE REST OF THE GAME (duck typing: "if it has the method, it fits")
##
##   body (Node3D): the character it drives. Must have these methods:
##     get_planar_speed() -> float          horizontal speed, for IDLE vs RUN
##     get_move_direction() -> Vector3      input direction (ZERO when no input)
##     get_facing() -> Vector3              where the character currently faces
##     begin_attack(dir: Vector3, lunge_speed: float, lunge_time: float, lunge_delay: float)
##     end_attack()
##     lock_controls(locked: bool)          stop/allow player movement (hurt, dead)
##     apply_knockback(velocity: Vector3)
##     respawn()                            only needed when auto_respawn is on
##
##   weapon (Node): the thing that deals damage. Must have:
##     set_active(on: bool)                 open/close the damage window
##     begin_swing(attack: AttackData)      arm it for a new strike
##     and a `hitbox` property (a Hitbox), so it never hits its own body.
##
##   holster (Node, optional): draw(), sheathe(), is_drawn() -> bool.
##   animation_tree (optional): its root must be a StateMachine; states are named idle, run,
##     hurt, death and each AttackData.animation. Without one, listen to `state_changed`.
##
## Behaviour: an attack press is buffered for `input_buffer_seconds`; if it is still fresh when
## the current strike reaches its combo window, the next strike chains. Active frames
## (AttackData.active_start -> active_end) switch the weapon on. A hit cancels the swing and
## flinches; death locks controls and (optionally) respawns after `respawn_delay`.

## Emitted on every state change. A presenter with no AnimationTree plays animations from this.
signal state_changed(previous: State, current: State)

enum State { IDLE, RUN, ATTACK_1, ATTACK_2, ATTACK_3, ATTACK_4, HURT, DEAD }
## The highest ATTACK_n state; combos longer than this are cut to fit.
const MAX_COMBO := 4

## The methods `body` and `weapon` must have. Checked once in _ready() so a missing method is a
## clear error at start-up, not a crash in the middle of a fight.
const BODY_METHODS: PackedStringArray = ["get_planar_speed", "get_move_direction", "get_facing",
		"begin_attack", "end_attack", "lock_controls", "apply_knockback"]
const WEAPON_METHODS: PackedStringArray = ["set_active", "begin_swing"]

## @export makes these fields show in the Inspector, so a scene wires them up without code.
@export var body: Node3D
@export var weapon: Node
@export var holster: Node
@export var animation_tree: AnimationTree
## The body's own health (hurt and death reactions).
@export var health: HealthComponent
## Strikes in combo order: index 0 plays in ATTACK_1, and so on (at most MAX_COMBO).
@export var combo: Array[AttackData] = []
## Input action that attacks. Ignored if the project has no such action; call request_attack().
@export var attack_action: StringName = &"attack"
@export var input_buffer_seconds := 0.35
## Idle seconds before the weapon is sheathed (only with a holster).
@export var sheathe_delay := 3.0
## Horizontal speed (m/s) above which locomotion counts as RUN.
@export var run_threshold := 0.6
## Shortest flinch, even from a light hit (s).
@export var min_hurt_time := 0.3
@export var auto_respawn := true
@export var respawn_delay := 2.5

@export_group("Soft Lock")
## Strikes snap toward the nearest member of `enemy_group` inside this range and cone.
@export var enemy_group: StringName = &"enemies"
@export var lock_range := 3.5
@export_range(0.0, 180.0) var lock_half_angle_degrees := 70.0

const _NO_PRESS := -1_000_000

var state := State.IDLE
var _state_time := 0.0
var _press_msec := _NO_PRESS
var _time_since_attack := 0.0
var _playback: AnimationNodeStateMachinePlayback
var _hurt_duration := 0.0
# Untyped on purpose: these hold whatever body/weapon was assigned, and we call the contract
# methods on them. A typed `Node3D` variable would refuse methods Node3D doesn't declare.
var _body
var _weapon


## _ready() runs once when the node enters the scene tree, after its children are ready.
func _ready() -> void:
	_body = body
	_weapon = weapon
	if not _has_methods(body, BODY_METHODS, "body") or not _has_methods(weapon, WEAPON_METHODS, "weapon"):
		set_physics_process(false)          # refuse to run half-wired
		return
	if combo.size() > MAX_COMBO:
		push_warning("ComboStateMachine: combo has %d strikes, only %d are used" % [combo.size(), MAX_COMBO])
		combo.resize(MAX_COMBO)
	if "hitbox" in weapon and weapon.hitbox is Hitbox:
		(weapon.hitbox as Hitbox).source = body
	if health:
		# connect(): call our method whenever the health component emits that signal.
		health.damaged.connect(_on_damaged)
		health.died.connect(_on_died)
	if animation_tree:
		_playback = animation_tree.get(&"parameters/playback")
		animation_tree.active = true
		_playback.travel(&"idle")


## Records an attack press. Called by _unhandled_input, touch buttons, AI or tests.
func request_attack() -> void:
	_press_msec = Time.get_ticks_msec()


## _unhandled_input() receives input events the UI did not consume.
func _unhandled_input(event: InputEvent) -> void:
	if not InputMap.has_action(attack_action) or not event.is_action_pressed(attack_action):
		return
	# A click that only recaptures the mouse must not attack. Keys and touch buttons
	# (InputEventAction) always may.
	if event is InputEventMouseButton and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	request_attack()


## _physics_process() runs at the fixed physics rate (60 Hz by default), in step with movement.
func _physics_process(delta: float) -> void:
	_state_time += delta
	match state:
		State.HURT:
			_tick_hurt()
		State.DEAD:
			pass                                     # respawn is timer-driven (_on_died)
		_:
			if is_attacking():
				_tick_attack()
			else:
				_tick_locomotion(delta)


## True during any strike. Works because the ATTACK_n values sit next to each other in the enum.
func is_attacking() -> bool:
	return state >= State.ATTACK_1 and state <= State.ATTACK_4


## Which strike (0-based) is playing, or -1 when not attacking.
func combo_index() -> int:
	return state - State.ATTACK_1 if is_attacking() else -1


## IDLE/RUN: start a strike on a fresh press, sheathe after a while, pick IDLE or RUN by speed.
func _tick_locomotion(delta: float) -> void:
	if not combo.is_empty() and _consume_press():
		_start_attack(0)
		return
	_time_since_attack += delta
	if holster and _time_since_attack >= sheathe_delay and holster.is_drawn():
		holster.sheathe()
	var next := State.RUN if _body.get_planar_speed() > run_threshold else State.IDLE
	if next != state:
		_change_state(next)


## ATTACK_n: open the weapon during active frames, chain on a buffered press, end on time.
func _tick_attack() -> void:
	var index := combo_index()
	var attack := combo[index]
	_weapon.set_active(_state_time >= attack.active_start and _state_time < attack.active_end)

	# Never chain before the active frames finish, or mashing would cut every swing short.
	var chain_time := maxf(attack.combo_window_open, attack.active_end)
	var can_chain := index + 1 < combo.size() and _state_time >= chain_time
	if can_chain and _consume_press():
		_start_attack(index + 1)
	elif _state_time >= attack.duration:
		_weapon.set_active(false)
		_body.end_attack()
		_time_since_attack = 0.0
		_change_state(State.RUN if _body.get_planar_speed() > run_threshold else State.IDLE)


## Begins strike `index`: draw the weapon, lunge toward the (soft-locked) target, arm the hitbox.
func _start_attack(index: int) -> void:
	var attack := combo[index]
	_weapon.set_active(false)                 # close the previous strike's window, if any
	if holster:
		holster.draw()
	_body.begin_attack(_attack_direction(), attack.lunge_speed, attack.lunge_duration, attack.lunge_delay)
	_weapon.begin_swing(attack)
	_time_since_attack = 0.0
	_change_state((State.ATTACK_1 + index) as State)


## HURT: wait out the flinch, then hand control back to the player.
func _tick_hurt() -> void:
	if _state_time >= _hurt_duration:
		_body.lock_controls(false)
		_change_state(State.RUN if _body.get_planar_speed() > run_threshold else State.IDLE)


## Signal handler for HealthComponent.damaged: cancel the swing and flinch.
func _on_damaged(hit: HitInfo) -> void:
	if health.is_dead:
		return                                   # _on_died handles lethal hits
	_weapon.set_active(false)                    # a hit cancels the swing
	_press_msec = _NO_PRESS
	_body.lock_controls(true)
	_body.apply_knockback(hit.knockback)
	_hurt_duration = maxf(hit.stagger_time, min_hurt_time)
	_change_state(State.HURT)


## Signal handler for HealthComponent.died. `await` on a timer pauses only this function;
## the game keeps running, and it resumes here when the timer fires.
func _on_died(_hit: HitInfo) -> void:
	_weapon.set_active(false)
	_press_msec = _NO_PRESS
	_body.lock_controls(true)
	_change_state(State.DEAD)
	if not auto_respawn:
		return
	await get_tree().create_timer(respawn_delay).timeout
	if not is_inside_tree():
		return                                   # freed while waiting (level unloaded)
	health.revive()
	if _body.has_method(&"respawn"):
		_body.respawn()
	_body.lock_controls(false)
	_time_since_attack = 0.0
	_change_state(State.IDLE)


## The single place state changes: resets the state timer, drives the AnimationTree (if any)
## and emits `state_changed` (`.emit()` calls every function connected to the signal).
func _change_state(next: State) -> void:
	var previous := state
	state = next
	_state_time = 0.0
	if _playback:
		_playback.travel(_animation_for(next))
	state_changed.emit(previous, next)


## Maps a state to its AnimationTree state name (&"..." is a StringName: a fast, interned string).
func _animation_for(s: State) -> StringName:
	match s:
		State.IDLE:
			return &"idle"
		State.RUN:
			return &"run"
		State.HURT:
			return &"hurt"
		State.DEAD:
			return &"death"
	return combo[s - State.ATTACK_1].animation


## A press counts once, and only while it is younger than the buffer window.
func _consume_press() -> bool:
	if Time.get_ticks_msec() - _press_msec > int(input_buffer_seconds * 1000.0):
		return false
	_press_msec = _NO_PRESS
	return true


## Strike toward the input direction (or current facing), snapped to a nearby enemy in front.
func _attack_direction() -> Vector3:
	var direction: Vector3 = _body.get_move_direction()
	if direction == Vector3.ZERO:
		direction = _body.get_facing()
	var min_dot := cos(deg_to_rad(lock_half_angle_degrees))
	var best_distance := lock_range
	var best_direction := direction
	for enemy: Node3D in get_tree().get_nodes_in_group(enemy_group):
		var to_enemy := enemy.global_position - body.global_position
		to_enemy.y = 0.0
		var distance := to_enemy.length()
		if distance > 0.01 and distance < best_distance and direction.dot(to_enemy / distance) >= min_dot:
			best_distance = distance
			best_direction = to_enemy / distance
	return best_direction


## True when `target` has every method in `methods`; otherwise logs which are missing.
func _has_methods(target: Object, methods: PackedStringArray, role: String) -> bool:
	if target == null:
		push_error("ComboStateMachine: no %s assigned" % role)
		return false
	var missing := PackedStringArray()
	for m in methods:
		if not target.has_method(m):
			missing.append(m)
	if not missing.is_empty():
		push_error("ComboStateMachine: %s '%s' is missing %s" % [role, target.name, ", ".join(missing)])
		return false
	return true
