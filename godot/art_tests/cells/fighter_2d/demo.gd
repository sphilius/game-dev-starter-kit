extends Node2D
## Fighter cell, 2D art: a mirror match between two cut-out puppets on a painted stage.
##
## Art: assets/boxer/*.png (six parts sliced from ONE AI image) and assets/stage/stage_00.png.
## Every pose below is a handful of joint angles, so a new move costs no new art.
## Kit: HealthComponent and HitInfo from kit_combat drive the two health bars.
## The demo plays itself: the left boxer jabs, the right boxer flinches.

const Puppet := preload("res://art_tests/cells/cut_out_puppet.gd")
const ASSETS := "res://art_tests/cells/fighter_2d/assets/"
const FLOOR_Y := 640.0

## Joint angles in degrees. 0 = the limb hangs straight down, negative = swung forward.
const GUARD := {"torso": 4.0, "head": -4.0, "upper_arm": -55.0, "forearm": -95.0,
		"upper_arm_b": -25.0, "forearm_b": -115.0,
		"thigh": -26.0, "shin": 34.0, "thigh_b": 14.0, "shin_b": 20.0}
const JAB := {"torso": 10.0, "upper_arm": -92.0, "forearm": -4.0, "thigh": -30.0, "shin": 34.0}
const FLINCH := {"torso": -14.0, "head": -16.0, "upper_arm": -20.0, "forearm": -60.0}

var left: Node2D
var right: Node2D
var bars: Array[ProgressBar] = []


## _ready(): stage, two boxers facing each other, health bars, then the fight loop.
func _ready() -> void:
	var stage := Sprite2D.new()
	stage.texture = load(ASSETS + "stage/stage_00.png")
	stage.centered = false
	add_child(stage)
	left = _boxer(Vector2(505, FLOOR_Y), false, Color.WHITE)
	# The second fighter is the same art mirrored and tinted: a full roster slot for free.
	right = _boxer(Vector2(775, FLOOR_Y), true, Color(0.75, 0.85, 1.25))
	_fight()


## One boxer: a puppet in guard pose with a HealthComponent and a bar at the top of the screen.
func _boxer(feet: Vector2, mirrored: bool, tint: Color) -> Node2D:
	var boxer: Node2D = Puppet.new()
	add_child(boxer)
	boxer.build(ASSETS + "boxer/")
	boxer.position = feet - Vector2(0.0, boxer.leg_length() * 0.93 * 1.15)       # bent knees: a little lower
	boxer.scale = Vector2(-1.15 if mirrored else 1.15, 1.15)      # negative x scale = facing left
	boxer.modulate = tint
	boxer.pose(GUARD, 0.0)
	var health := HealthComponent.new()
	health.max_health = 100.0
	boxer.add_child(health)
	var bar := ProgressBar.new()
	bar.show_percentage = false
	bar.size = Vector2(480, 26)
	bar.position = Vector2(730 if mirrored else 70, 40)
	bar.fill_mode = ProgressBar.FILL_BEGIN_TO_END if mirrored else ProgressBar.FILL_END_TO_BEGIN
	bar.value = 100.0
	# A flat coloured fill instead of the default grey theme, so the bar reads as health.
	var fill := StyleBoxFlat.new()
	fill.bg_color = Color(0.95, 0.75, 0.2)
	bar.add_theme_stylebox_override(&"fill", fill)
	add_child(bar)
	# connect(): the bar follows the health number whenever the kit reports a change.
	health.health_changed.connect(func(current: float, maximum: float) -> void: bar.value = 100.0 * current / maximum)
	return boxer


## The loop: bob in guard, jab, the other boxer flinches and loses health, back to guard.
func _fight() -> void:
	while HealthComponent.resolve(right).current_health > 0.0:
		await get_tree().create_timer(1.2).timeout
		await left.pose(JAB, 0.07).finished             # `await tween.finished`: wait for the punch to land
		HealthComponent.resolve(right).take_damage(HitInfo.new(12.0))
		right.pose(FLINCH, 0.06)
		await get_tree().create_timer(0.45).timeout
		left.pose(GUARD, 0.18)
		right.pose(GUARD, 0.25)
