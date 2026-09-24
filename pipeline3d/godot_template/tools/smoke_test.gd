extends SceneTree
## Headless smoke test: every rigged asset gets the character controller and must reach its
## idle state; clips must play without errors.
##   godot --headless --path <project> -s res://tools/smoke_test.gd
## Exit code 0 = all good.

const Controller := preload("res://scripts/character_controller.gd")

var _bodies: Array = []
var _frame := 0
var _failures := 0


func _initialize() -> void:
	var dir := DirAccess.open("res://assets")
	if dir == null:
		print("[smoke] no res://assets folder")
		quit(1)
		return
	var floor_body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(50, 1, 50)
	shape.shape = box
	shape.position.y = -0.5
	floor_body.add_child(shape)
	root.add_child(floor_body)
	for f in dir.get_files():
		if f.get_extension().to_lower() not in ["glb", "gltf", "fbx"]:
			continue
		var packed := load("res://assets/" + f) as PackedScene
		if packed == null:
			print("[smoke] FAIL cannot load ", f)
			_failures += 1
			continue
		var probe := packed.instantiate()
		var rigged := not probe.find_children("*", "Skeleton3D", true, false).is_empty()
		probe.free()
		if not rigged:
			print("[smoke] static ok ", f)
			continue
		var body := CharacterBody3D.new()
		body.set_script(Controller)
		body.model_scene = packed
		body.name = f.get_basename()
		var col := CollisionShape3D.new()
		col.shape = CapsuleShape3D.new()
		body.add_child(col)
		root.add_child(body)
		_bodies.append(body)


func _process(_delta: float) -> bool:
	_frame += 1
	if _frame < 30:
		return false
	for body in _bodies:
		var pb = body.get("_playback")
		var states: Dictionary = body.get("_states")
		var current: String = pb.get_current_node() if pb else "<no tree>"
		var ok: bool = pb != null and current == "idle"
		print("[smoke] %s %s states=%s current=%s" % ["PASS" if ok else "FAIL", body.name, states.keys(), current])
		if not ok:
			_failures += 1
	print("[smoke] done, failures=%d" % _failures)
	quit(1 if _failures > 0 else 0)
	return true
