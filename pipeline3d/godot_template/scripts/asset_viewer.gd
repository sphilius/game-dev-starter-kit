extends Node3D
## Drop-in viewer: lines up every model in res://assets, plays their clips, orbits a camera.
##   Tab ........ next clip on every model      Arrows ... orbit / zoom
##   Command line (after --):  --shot=user://viewer.png   save a screenshot after 45 frames and quit
##                             --clip=<name>              start on this clip

const EXTS := ["glb", "gltf", "fbx", "blend"]
const SPACING := 2.5

var _players: Array[AnimationPlayer] = []
var _clip_index := 0
var _yaw := 0.6
var _pitch := -0.25
var _distance := 6.0
var _focus := Vector3(0, 0.9, 0)
var _camera: Camera3D
var _hud: Label
var _shot_path := ""
var _frames := 0


func _ready() -> void:
	_build_stage()
	var models := _load_models("res://assets")
	var start_clip := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			_shot_path = a.substr(7)
		elif a.begins_with("--clip="):
			start_clip = a.substr(7)
	var x := -SPACING * (models.size() - 1) / 2.0
	for m in models:
		m.position.x = x
		x += SPACING
		add_child(m)
		var label := Label3D.new()
		label.text = m.name
		label.position = Vector3(m.position.x, -0.15, 0.6)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.pixel_size = 0.004
		add_child(label)
		for p: AnimationPlayer in m.find_children("*", "AnimationPlayer", true, false):
			_players.append(p)
	_distance = maxf(4.0, SPACING * models.size() * 0.9)
	if start_clip != "":
		_play_named(start_clip)
	else:
		_play_index(0)
	if models.is_empty():
		_hud.text = "No models in res://assets - export .glb files there (export_for_godot.py copy_to=...)"


func _build_stage() -> void:
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.16, 0.17, 0.2)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.45, 0.45, 0.5)
	env.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 35, 0)
	sun.shadow_enabled = true
	add_child(sun)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(40, 40)
	floor_mesh.mesh = plane
	add_child(floor_mesh)
	_camera = Camera3D.new()
	add_child(_camera)
	var layer := CanvasLayer.new()
	_hud = Label.new()
	_hud.position = Vector2(12, 8)
	layer.add_child(_hud)
	add_child(layer)


func _load_models(dir_path: String) -> Array[Node3D]:
	var out: Array[Node3D] = []
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return out
	var files := dir.get_files()
	files.sort()
	for f in files:
		if f.get_extension().to_lower() not in EXTS:
			continue
		var packed := load(dir_path.path_join(f)) as PackedScene
		if packed == null:
			continue
		var inst := packed.instantiate() as Node3D
		if inst:
			inst.name = f.get_basename()
			out.append(inst)
	return out


func _all_clips() -> PackedStringArray:
	var names := PackedStringArray()
	for p in _players:
		for n in p.get_animation_list():
			if not names.has(n):
				names.append(n)
	return names


func _play_index(i: int) -> void:
	var names := _all_clips()
	if names.is_empty():
		_hud.text = "No animations. Tab: next clip, arrows: orbit"
		return
	_clip_index = posmod(i, names.size())
	_play_named(names[_clip_index])


func _play_named(clip: String) -> void:
	for p in _players:
		# Match exact, or by suffix so "idle" also finds "wolf_idle"
		var target := ""
		for n in p.get_animation_list():
			if n == clip or String(n).ends_with("_" + clip) or clip.ends_with("_" + String(n)):
				target = n
				break
		if target == "" and p.get_animation_list().size() > 0:
			target = p.get_animation_list()[0]
		if target != "":
			p.play(target)
	_hud.text = "Clip: %s   (Tab: next clip, arrows: orbit/zoom)" % clip


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("next_clip"):
		_play_index(_clip_index + 1)


func _process(delta: float) -> void:
	_yaw += (Input.get_axis("ui_left", "ui_right")) * delta * 1.5
	_distance = clampf(_distance + Input.get_axis("ui_up", "ui_down") * delta * 4.0, 1.5, 60.0)
	var offset := Vector3(sin(_yaw) * cos(_pitch), -sin(_pitch), cos(_yaw) * cos(_pitch)) * _distance
	_camera.look_at_from_position(_focus + offset, _focus)
	_frames += 1
	if _shot_path != "" and _frames == 45:
		var img := get_viewport().get_texture().get_image()
		img.save_png(_shot_path)
		print("[viewer] screenshot saved: ", ProjectSettings.globalize_path(_shot_path))
		get_tree().quit()
