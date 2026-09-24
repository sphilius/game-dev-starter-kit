extends CharacterBody3D
## Third-person controller for any pipeline character (biped or quadruped).
##
## Instance your imported .glb as a child named "Model" (or set model_scene), attach this
## script to the CharacterBody3D, add a CollisionShape3D. On _ready it finds the model's
## AnimationPlayer, builds an AnimationTree state machine (idle / walk / run / attack /
## death) from whichever clips exist, and drives it from movement.
## Clips are matched by name suffix, so "wolf_walk", "Walk" and "walk" all map to walk.
## Clips must be in-place (stationary root): this script owns the displacement.

@export var model_scene: PackedScene
@export var walk_speed := 2.0
@export var run_speed := 5.0
@export var turn_speed := 10.0
@export var crossfade := 0.15

var _tree: AnimationTree
var _playback: AnimationNodeStateMachinePlayback
var _states: Dictionary = {}          # state -> clip name
var _model: Node3D
var _dead := false
var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _ready() -> void:
	_model = get_node_or_null("Model") as Node3D
	if _model == null and model_scene:
		_model = model_scene.instantiate() as Node3D
		_model.name = "Model"
		add_child(_model)
	if _model == null:
		push_error("character_controller: no Model child and no model_scene set")
		return
	var players := _model.find_children("*", "AnimationPlayer", true, false)
	if players.is_empty():
		push_warning("character_controller: model has no AnimationPlayer; movement only")
		return
	var player: AnimationPlayer = players[0]
	for state in ["idle", "walk", "run", "attack", "death"]:
		for clip in player.get_animation_list():
			var c := String(clip).to_lower()
			if c == state or c.ends_with("_" + state) or c.ends_with("-" + state):
				_states[state] = String(clip)
				break
	_build_tree(player)


func _build_tree(player: AnimationPlayer) -> void:
	var sm := AnimationNodeStateMachine.new()
	var pos := 0.0
	for state in _states:
		var node := AnimationNodeAnimation.new()
		node.animation = _states[state]
		sm.add_node(state, node, Vector2(pos, 0))
		pos += 200.0
	for a in _states:
		for b in _states:
			if a == b or a == "death":
				continue
			var t := AnimationNodeStateMachineTransition.new()
			t.xfade_time = crossfade
			if a == "attack" and b == "idle":
				t.switch_mode = AnimationNodeStateMachineTransition.SWITCH_MODE_AT_END
				t.advance_mode = AnimationNodeStateMachineTransition.ADVANCE_MODE_AUTO
			sm.add_transition(a, b, t)
	if _states.has("idle"):
		sm.add_transition("Start", "idle", AnimationNodeStateMachineTransition.new())
	_tree = AnimationTree.new()
	_tree.tree_root = sm
	add_child(_tree)
	_tree.anim_player = _tree.get_path_to(player)
	_tree.active = true
	_playback = _tree.get("parameters/playback")


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= _gravity * delta
	if _dead:
		velocity.x = 0.0
		velocity.z = 0.0
		move_and_slide()
		return
	var input := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	var running := Input.is_key_pressed(KEY_SHIFT)
	var speed := run_speed if running else walk_speed
	var dir := Vector3(input.x, 0, input.y)
	velocity.x = dir.x * speed
	velocity.z = dir.z * speed
	move_and_slide()
	if dir.length() > 0.1 and _model:
		# Blender -Y front exports as Godot +Z front; face the movement direction.
		var target := atan2(dir.x, dir.z)
		_model.rotation.y = lerp_angle(_model.rotation.y, target, turn_speed * delta)

	if _playback == null:
		return
	if Input.is_action_just_pressed("attack") and _states.has("attack"):
		_playback.travel("attack")
	elif Input.is_key_pressed(KEY_K) and _states.has("death"):
		_dead = true
		_playback.travel("death")
	elif _playback.get_current_node() != "attack":
		var moving := dir.length() > 0.1
		var want := "idle"
		if moving:
			want = "run" if running and _states.has("run") else "walk"
		if _states.has(want):
			_playback.travel(want)
