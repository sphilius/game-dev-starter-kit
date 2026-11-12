extends TestCase
## Smoke test: the project boots the way jams need it to, and the test harness itself works.
## If this file fails, nothing else in the run can be trusted.

## `static var` belongs to the script, not an instance, so it survives from one test's instance
## to the next. That lets a later test see what an earlier test's after_each() did.
static var after_each_calls := 0


## Runs after each test in this file (see TestCase.after_each). Counted to prove the hook fires.
func after_each() -> void:
	after_each_calls += 1


## Web builds need the Compatibility (OpenGL) renderer; Forward+ does not run in browsers.
func test_project_uses_compatibility_renderer() -> void:
	check_eq(ProjectSettings.get_setting("rendering/renderer/rendering_method"), "gl_compatibility",
			"desktop renderer")
	check_eq(ProjectSettings.get_setting("rendering/renderer/rendering_method.mobile"), "gl_compatibility",
			"mobile/web renderer")


## Every kit class is registered as a global class (class_name), so scenes and other kits can use it.
func test_kit_classes_are_registered() -> void:
	var registered := {}
	for entry in ProjectSettings.get_global_class_list():
		registered[entry["class"]] = true
	for name in ["TestCase", "HitStop", "HealthComponent", "HitInfo", "Hitbox", "Hurtbox",
			"AttackData", "ComboStateMachine"]:
		check(registered.has(name), "global class %s is not registered" % name)


## The main scene loads and instantiates without errors (any error logged fails the test).
func test_main_scene_instantiates() -> void:
	var path: String = ProjectSettings.get_setting("application/run/main_scene")
	var scene := load(path) as PackedScene
	if not check(scene != null, "main scene %s did not load" % path):
		return
	add_node(scene.instantiate())
	await tree.process_frame


## Teardown contract: kit_teardown() (run after every test) puts the engine back to normal.
## This test breaks time scale on purpose; the next test checks it was restored.
func test_teardown_part_1_breaks_time_scale() -> void:
	Engine.time_scale = 0.25
	check_eq(Engine.time_scale, 0.25, "time scale set")


## Part 2 of the pair above. Tests run in the order they appear in the file, so this one
## always runs after part 1; teardown in between must have reset the time scale.
func test_teardown_part_2_time_scale_restored() -> void:
	check_eq(Engine.time_scale, 1.0, "time scale after the previous test's teardown")
	# Every earlier test in this file finished, so after_each() ran once for each of them.
	check(after_each_calls >= 4, "after_each ran after earlier tests (count %d)" % after_each_calls)


## add_node() puts a node in the tree for this test only; teardown frees it afterwards.
func test_add_node_puts_node_in_tree() -> void:
	var node := add_node(Node.new())
	check(node.is_inside_tree(), "add_node() puts the node in the tree")


## Every demo scene under res://scenes/demos loads and runs for a moment without logging an
## error. The demos double as templates, so a kit change that breaks one must fail CI.
func test_demo_scenes_run_without_errors() -> void:
	var dir := "res://scenes/demos"
	var count := 0
	for file in DirAccess.get_files_at(dir):
		if not file.ends_with(".tscn"):
			continue
		count += 1
		var scene := load(dir + "/" + file) as PackedScene
		if not check(scene != null, "%s did not load" % file):
			continue
		var instance := add_node(scene.instantiate())
		await seconds(0.3)
		instance.queue_free()               # free now so the next demo starts from a clean tree
		await tree.process_frame
	check(count >= 3, "found the demo scenes (%d)" % count)
