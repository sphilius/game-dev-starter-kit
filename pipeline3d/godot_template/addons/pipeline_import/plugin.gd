@tool
extends EditorPlugin
## Registers the scene post-import step for every imported .glb/.gltf/.fbx/.blend.

var _post_import: EditorScenePostImportPlugin


func _enter_tree() -> void:
	_post_import = preload("res://addons/pipeline_import/post_import.gd").new()
	add_scene_post_import_plugin(_post_import)


func _exit_tree() -> void:
	remove_scene_post_import_plugin(_post_import)
	_post_import = null
