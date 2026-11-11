class_name HitStop
extends RefCounted
## Global hit-stop: time nearly freezes for a few frames when a strike lands, which sells the
## weight of the impact. Overlapping requests extend the stop instead of stacking, and the
## timer ignores time scale, so the freeze always ends on schedule.
## A static utility rather than an autoload, so it works in-game, in the editor and in tests.

## Engine.time_scale while frozen. Not 0, so tweens and physics interpolation stay stable.
const FROZEN_TIME_SCALE := 0.03

static var _end_msec := 0
static var _token := 0


static func trigger(duration: float) -> void:
	if duration <= 0.0:
		return
	var end_msec := Time.get_ticks_msec() + int(duration * 1000.0)
	if end_msec <= _end_msec:
		return                        # an ongoing, longer stop already covers this
	_end_msec = end_msec
	_token += 1
	var token := _token
	Engine.time_scale = FROZEN_TIME_SCALE
	var tree := Engine.get_main_loop() as SceneTree
	await tree.create_timer(duration, true, false, true).timeout
	if token == _token:               # only the most recent request restores time
		Engine.time_scale = 1.0


## Cancels any stop in progress and restores normal time. Call it when a level reloads, and in
## every test's after_each() that can land a hit. Without it a stale `_end_msec` from the
## previous test makes the next test's trigger() return early ("a longer stop covers this").
static func reset() -> void:
	_token += 1                       # any pending restore from trigger() now does nothing
	_end_msec = 0
	Engine.time_scale = 1.0
