extends SceneTree
## Headless asset audit (the Godot 4 version of the blueprint's "Scene & Performance Auditor").
##
##   godot --headless --path <project> --import            # once, so assets are imported
##   godot --headless --path <project> -s res://tools/asset_audit.gd -- [res://assets] [--out=path.json]
##
## For every .glb/.gltf/.fbx/.blend under the folder it reports meshes, triangles, bones,
## clips (length + loop), texture sizes and collision, plus warnings against the budgets
## below. Exit code 0 = no errors, 1 = at least one error (warnings don't fail).

const BUDGET := {
	"max_texture_px": 2048,
	"character_max_tris": 25000,
	"prop_max_tris": 8000,
	"max_bones": 128,
}
const EXTS := ["glb", "gltf", "fbx", "blend"]


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var root := "res://assets"
	var out_path := ""
	for a in args:
		if a.begins_with("--out="):
			out_path = a.substr(6)
		elif a.begins_with("res://"):
			root = a
	var files := _collect(root)
	var report := {"root": root, "assets": [], "errors": 0, "warnings": 0}
	for path in files:
		var entry := _audit(path)
		report.assets.append(entry)
		report.errors += entry.errors.size()
		report.warnings += entry.warnings.size()
	var text := JSON.stringify(report, "  ")
	print(text)
	if out_path != "":
		var f := FileAccess.open(out_path, FileAccess.WRITE)
		if f:
			f.store_string(text)
	quit(1 if report.errors > 0 else 0)


func _collect(dir_path: String) -> Array[String]:
	var found: Array[String] = []
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return found
	for f in dir.get_files():
		if f.get_extension().to_lower() in EXTS:
			found.append(dir_path.path_join(f))
	for d in dir.get_directories():
		found.append_array(_collect(dir_path.path_join(d)))
	return found


func _audit(path: String) -> Dictionary:
	var e := {"path": path, "tris": 0, "meshes": 0, "bones": 0, "clips": [], "textures": [],
			"static_bodies": 0, "errors": [], "warnings": []}
	var packed := load(path) as PackedScene
	if packed == null:
		e.errors.append("not imported or failed to load - run `godot --headless --import` first")
		return e
	var scene := packed.instantiate()
	for mi: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if mi.mesh == null:
			continue
		e.meshes += 1
		for s in mi.mesh.get_surface_count():
			var arrays := mi.mesh.surface_get_arrays(s)
			var idx = arrays[Mesh.ARRAY_INDEX]
			e.tris += (idx as PackedInt32Array).size() / 3 if idx != null else (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
			var mat := mi.get_active_material(s)
			if mat is BaseMaterial3D:
				for tex_prop in ["albedo_texture", "normal_texture", "roughness_texture", "metallic_texture", "emission_texture"]:
					var tex: Texture2D = mat.get(tex_prop)
					if tex:
						var px := maxi(tex.get_width(), tex.get_height())
						e.textures.append({"slot": tex_prop, "px": px})
						if px > BUDGET.max_texture_px:
							e.warnings.append("%s is %dpx (> %d) on %s" % [tex_prop, px, BUDGET.max_texture_px, mi.name])
	for sk: Skeleton3D in scene.find_children("*", "Skeleton3D", true, false):
		e.bones += sk.get_bone_count()
	for player: AnimationPlayer in scene.find_children("*", "AnimationPlayer", true, false):
		for anim_name in player.get_animation_list():
			var anim := player.get_animation(anim_name)
			e.clips.append({"name": String(anim_name), "seconds": snappedf(anim.length, 0.001),
					"loop": anim.loop_mode != Animation.LOOP_NONE})
	e.static_bodies = scene.find_children("*", "StaticBody3D", true, false).size()

	var rigged: bool = e.bones > 0
	var budget: int = BUDGET.character_max_tris if rigged else BUDGET.prop_max_tris
	if e.tris > budget:
		e.warnings.append("%d tris exceeds the %s budget of %d" % [e.tris, "character" if rigged else "prop", budget])
	if e.bones > BUDGET.max_bones:
		e.warnings.append("%d bones (> %d)" % [e.bones, BUDGET.max_bones])
	if rigged and e.clips.is_empty():
		e.warnings.append("skeleton but no animations - expected at least an idle clip")
	if not rigged and e.static_bodies == 0:
		e.warnings.append("static prop without collision - export with collision='convex' (adds -convcolonly)")
	if e.meshes == 0:
		e.errors.append("no MeshInstance3D found")
	scene.free()
	return e
