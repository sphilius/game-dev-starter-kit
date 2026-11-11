extends SceneTree
## Headless test runner for the jam kits. It is the CI gate before any web build.
##
##   godot --headless --path . --script res://addons/kit_tests/run_tests.gd
##   godot --headless --path . --script res://addons/kit_tests/run_tests.gd -- --filter=test_combat::test_hit
##   godot --headless --path . --script res://addons/kit_tests/run_tests.gd -- --dirs=res://tests,res://addons/fps_kit/tests
##
## Options (after `--`):
##   --dirs=a,b     Folders to search, recursively, for `test_*.gd` files (default: res://tests and
##                  res://addons). Every file found must extend TestCase.
##   --filter=a,b   Only run tests whose label contains one of these terms. A label is
##                  `<file name>::<method>`, e.g. `test_combat::test_hit_once`, so
##                  `test_combat::` runs one file and `::test_hit` runs one method in every file.
##
## Each `test_*` method runs on a fresh TestCase instance: before_each() -> the test ->
## after_each() -> the built-in teardown (frees nodes added with add_node, resets time scale,
## releases input). A test fails on a failed check, a timeout, or ANY engine or script error
## logged while it runs (captured by a Logger). Failures are also printed as GitHub Actions
## annotations. Exits 0 when everything passes, 1 otherwise, and 1 if no test ran at all.

const DEFAULT_DIRS: PackedStringArray = ["res://tests", "res://addons"]
const TEST_TIMEOUT := 60.0


## Collects engine and script errors (not warnings) logged while a test runs.
class ErrorCatcher extends Logger:
	var errors: Array[String] = []
	var _mutex := Mutex.new()           # engine errors can arrive from worker threads

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == ERROR_TYPE_WARNING:
			return
		var text := rationale if not rationale.is_empty() else code
		_mutex.lock()
		errors.append("%s (%s:%d in %s)" % [text, file.get_file(), line, function])
		_mutex.unlock()

	## Returns everything caught so far and starts a fresh list.
	func take() -> Array[String]:
		_mutex.lock()
		var taken := errors.duplicate()
		errors.clear()
		_mutex.unlock()
		return taken


var _catcher := ErrorCatcher.new()


func _initialize() -> void:
	# Deferred so the SceneTree is fully set up before the first test adds nodes to it.
	_run.call_deferred()


## Main loop: parse options, find test files, run each test_* method, print a summary.
## It is a coroutine: `await` pauses it (e.g. while a test waits for frames) without blocking
## the engine, which keeps processing frames and physics underneath.
func _run() -> void:
	OS.add_logger(_catcher)
	var dirs := DEFAULT_DIRS
	var filters := PackedStringArray()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--dirs="):
			dirs = arg.trim_prefix("--dirs=").split(",", false)
		elif arg.begins_with("--filter="):
			filters = arg.trim_prefix("--filter=").split(",", false)

	var passed := 0
	var failed := 0
	var started := Time.get_ticks_msec()
	for path in _test_files(dirs):
		_catcher.take()
		var file := path.get_file().get_basename()
		var script := load(path) as GDScript
		if script == null or not script.can_instantiate():
			failed += 1                         # a broken test file must fail the gate, not vanish
			_report_fail(file, ["failed to load: " + "; ".join(_catcher.take())])
			continue
		for method in script.get_script_method_list():
			var test_name: String = method.name
			var label := "%s::%s" % [file, test_name]
			if not test_name.begins_with("test_") or not _matches(label, filters):
				continue
			var result := await _run_test(script, test_name)
			if result.failures.is_empty():
				passed += 1
				print("  PASS  %s  (%.2f s)" % [label, result.seconds])
			else:
				failed += 1
				print("  FAIL  %s  (%.2f s)" % [label, result.seconds])
				_report_fail(label, result.failures)
			if result.timed_out:
				print("Aborting: a timed-out test may still be running.")
				_finish(passed, failed, started)
				return
	_finish(passed, failed, started)


## True when no filter is set, or the label contains at least one filter term.
func _matches(label: String, filters: PackedStringArray) -> bool:
	if filters.is_empty():
		return true
	for term in filters:
		if label.contains(term):
			return true
	return false


## Runs one test method on a fresh instance and returns
## {failures: PackedStringArray, seconds: float, timed_out: bool}.
## The test body is started without awaiting it, so this function can keep watching the clock
## and give up after TEST_TIMEOUT even if the test awaits something that never happens.
func _run_test(script: GDScript, test_name: String) -> Dictionary:
	var case = script.new()          # untyped: checked against TestCase just below
	if not case is TestCase:
		return {"failures": PackedStringArray(["test file does not extend TestCase"]),
				"seconds": 0.0, "timed_out": false}
	case.tree = self
	_catcher.take()                         # drop anything logged between tests
	var state := {"done": false}
	var start := Time.get_ticks_msec()
	# The body runs as a coroutine; this loop below watches it and enforces the timeout.
	var body := func() -> void:
		await case.before_each()
		await Callable(case, test_name).call()
		await case.after_each()
		state.done = true
	body.call()
	while not state.done and Time.get_ticks_msec() - start < TEST_TIMEOUT * 1000.0:
		await process_frame
	var failures: PackedStringArray = case.failures.duplicate()
	if not state.done:
		failures.append("timed out after %d s" % TEST_TIMEOUT)
	# Errors the test declared with expect_error() are allowed (and required); others fail it.
	var expected: PackedStringArray = case.expected_errors.duplicate()
	for error in _catcher.take():
		var matched := -1
		for i in expected.size():
			if error.contains(expected[i]):
				matched = i
				break
		if matched >= 0:
			expected.remove_at(matched)
		else:
			failures.append("engine/script error: " + error)
	for missing in expected:
		failures.append("expected an error containing '%s', none was logged" % missing)
	if state.done:
		await case.kit_teardown()
	return {"failures": failures, "seconds": (Time.get_ticks_msec() - start) / 1000.0,
			"timed_out": not state.done}


## Every test_*.gd under the given folders (recursively), sorted, skipping kit_tests itself.
func _test_files(dirs: PackedStringArray) -> PackedStringArray:
	var found := PackedStringArray()
	for dir in dirs:
		_collect(dir.trim_suffix("/"), found)
	found.sort()
	return found


## Recursive helper for _test_files: adds this folder's test files, then walks its subfolders.
## PackedStringArray is passed by reference, so appending here fills the caller's array.
func _collect(dir: String, found: PackedStringArray) -> void:
	if dir.ends_with("/kit_tests") or not DirAccess.dir_exists_absolute(dir):
		return
	for file in DirAccess.get_files_at(dir):
		if file.begins_with("test_") and file.ends_with(".gd"):
			found.append(dir + "/" + file)
	for sub in DirAccess.get_directories_at(dir):
		if not sub.begins_with("."):
			_collect(dir + "/" + sub, found)


## Prints each failure twice: indented for people, and as a `::error` line that GitHub Actions
## turns into a red annotation on the run summary.
func _report_fail(label: String, failures: PackedStringArray) -> void:
	for failure in failures:
		print("        - " + failure)
		print("::error title=%s::%s" % [label, failure.replace("\n", " ")])


## Prints the totals and quits with exit code 0 (all passed) or 1 (anything failed), which is
## what CI and shell scripts read to decide pass/fail.
func _finish(passed: int, failed: int, started: int) -> void:
	print("\n%d passed, %d failed in %.1f s" % [passed, failed, (Time.get_ticks_msec() - started) / 1000.0])
	if passed + failed == 0:
		print("::error title=tests::no tests ran")    # discovery broke: never let that pass as green
		failed = 1
	OS.remove_logger(_catcher)
	quit(1 if failed > 0 else 0)
