class_name TestCase
extends RefCounted
## Base class for every headless kit test. Run them with res://addons/kit_tests/run_tests.gd.
## `class_name` registers TestCase as a global type, so test files can write
## `extends TestCase` and the runner can check `case is TestCase`. RefCounted (not Node) means
## a test instance is freed automatically when nothing references it, and never sits in the scene tree.
##
## A test file `extends TestCase` and defines `test_*` methods (they may `await`). Each test
## method gets its own instance. Checks record a failure and carry on, so one run reports
## everything that broke instead of stopping at the first problem.
##
## This class is deliberately generic: no game world, no player. A project that needs a world
## writes its own subclass (e.g. `class_name WorldTestCase extends TestCase`) with a
## load_world() helper, and overrides after_each() to undo its own global side effects.

## Set by the runner before before_each().
var tree: SceneTree
var failures: PackedStringArray = []
## Error messages this test expects (see expect_error). Read by the runner.
var expected_errors: PackedStringArray = []
var _owned: Array[Node] = []


# --- Hooks (override in a test file) ------------------------------------------------------

## Runs before every test method. May await.
func before_each() -> void:
	pass


## Runs after every test method that finished (not after a timeout). May await. Put resets of
## your own globals here, e.g. HitStop.reset() when a test can land a hit.
func after_each() -> void:
	pass


# --- Checks -------------------------------------------------------------------------------

func check(condition: bool, message: String) -> bool:
	if not condition:
		failures.append(message)
	return condition


## Equality check with a readable message: "<what>: expected X, got Y".
func check_eq(actual: Variant, expected: Variant, what: String) -> bool:
	return check(actual == expected, "%s: expected %s, got %s" % [what, expected, actual])


## Float (or Vector) comparison with a tolerance.
func check_near(actual: Variant, expected: Variant, tolerance: float, what: String) -> bool:
	var close: bool
	if actual is float or actual is int:
		close = absf(float(actual) - float(expected)) <= tolerance
	else:
		close = (actual - expected).length() <= tolerance
	return check(close, "%s: expected %s ±%s, got %s" % [what, expected, tolerance, actual])


## Declares that an engine/script error containing `fragment` MUST be logged during this test
## (e.g. a kit refusing bad wiring with push_error). The runner then swallows that error, and
## fails the test if it never appears. Any other error still fails the test as usual.
func expect_error(fragment: String) -> void:
	expected_errors.append(fragment)


# --- Nodes --------------------------------------------------------------------------------

## Adds `node` under the root and frees it automatically after the test. Returns the node so
## `var body := add_node(MyBody.new())` reads naturally.
func add_node(node: Node) -> Node:
	tree.root.add_child(node)
	_owned.append(node)
	return node


# --- Time ---------------------------------------------------------------------------------

## Waits real (wall-clock) seconds.
func seconds(duration: float) -> void:
	var end := Time.get_ticks_msec() + int(duration * 1000.0)
	while Time.get_ticks_msec() < end:
		await tree.process_frame


## Waits for `count` physics ticks (the steps where _physics_process runs and areas/bodies
## update overlaps). Use this, not seconds(), when a test depends on physics having stepped.
func physics_frames(count: int) -> void:
	for i in count:
		await tree.physics_frame


## Waits until `condition` returns true or `timeout` real seconds pass. Returns the final result.
func wait_until(condition: Callable, timeout: float) -> bool:
	var end := Time.get_ticks_msec() + int(timeout * 1000.0)
	while Time.get_ticks_msec() < end:
		if condition.call():
			return true
		await tree.process_frame
	return condition.call()


# --- Teardown (called by the runner; do not override) -------------------------------------

## Frees nodes from add_node() and undoes engine-wide side effects every kit can cause.
func kit_teardown() -> void:
	for node in _owned:
		if is_instance_valid(node):
			node.queue_free()
	_owned.clear()
	Engine.time_scale = 1.0                 # hit-stop and slow-mo change this globally
	for action in InputMap.get_actions():
		Input.action_release(action)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	await tree.process_frame
