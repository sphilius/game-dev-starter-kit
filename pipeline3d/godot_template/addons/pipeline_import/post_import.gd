@tool
extends EditorScenePostImportPlugin
## Runs on every imported 3D scene.
##  - glTF has no loop flag, so loop modes are set here from clip names (loop_names.txt).
##  - Prints a one-line summary per file, so headless imports (`godot --headless --import`)
##    and Godot MCP debug output show what arrived: meshes, tris, bones, clips.

const LOOP_FILE := "res://addons/pipeline_import/loop_names.txt"


func _post_process(scene: Node) -> void:
	var keywords := _load_keywords()
	var clips: Array[String] = []
	var looped := 0
	for player: AnimationPlayer in scene.find_children("*", "AnimationPlayer", true, false):
		for lib_name: StringName in player.get_animation_library_list():
			var lib: AnimationLibrary = player.get_animation_library(lib_name)
			for anim_name: StringName in lib.get_animation_list():
				var anim: Animation = lib.get_animation(anim_name)
				if _should_loop(String(anim_name), keywords):
					anim.loop_mode = Animation.LOOP_LINEAR
					looped += 1
				clips.append("%s(%.2fs%s)" % [anim_name, anim.length,
						", loop" if anim.loop_mode != Animation.LOOP_NONE else ""])

	var tris := 0
	for mi: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if mi.mesh == null:
			continue
		for s in mi.mesh.get_surface_count():
			var arrays := mi.mesh.surface_get_arrays(s)
			var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
			tris += idx.size() / 3 if idx.size() > 0 else (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
	var bones := 0
	for sk: Skeleton3D in scene.find_children("*", "Skeleton3D", true, false):
		bones += sk.get_bone_count()
	var bodies := scene.find_children("*", "StaticBody3D", true, false).size()

	print("[pipeline_import] %s: tris=%d bones=%d static_bodies=%d clips=%d looping=%d %s" % [
			scene.name, tris, bones, bodies, clips.size(), looped, ", ".join(clips)])


func _load_keywords() -> PackedStringArray:
	var words := PackedStringArray()
	var f := FileAccess.open(LOOP_FILE, FileAccess.READ)
	if f == null:
		return PackedStringArray(["idle", "walk", "run", "loop", "cycle"])
	while not f.eof_reached():
		var line := f.get_line().strip_edges().to_lower()
		if line != "" and not line.begins_with("#"):
			words.append(line)
	return words


func _should_loop(anim_name: String, keywords: PackedStringArray) -> bool:
	var lower := anim_name.to_lower()
	if lower.ends_with("_once") or lower.ends_with("-once"):
		return false
	var normalized := lower.replace("-", "_").replace(".", "_").replace(" ", "_")
	for kw in keywords:
		if normalized == kw or normalized.begins_with(kw + "_") or normalized.ends_with("_" + kw) \
				or normalized.contains("_" + kw + "_"):
			return true
	return false
