extends Node2D
## Platformer cell, 2D art: a flat-silhouette fox explorer running over flat platforms.
##
## Art: assets/explorer/*.png (four parts sliced from ONE AI image) and assets/backdrop/backdrop_00.png.
## The run cycle is not drawn: _process() swings the arm and leg bones with a sine wave.
## Platforms are flat rectangles made in code, in a colour picked to match the backdrop.
##
## Controls: A/D or arrow keys run, Space or Up jumps. Standing still, the explorer jogs on the spot.

const Puppet := preload("res://art_tests/cells/cut_out_puppet.gd")
const ASSETS := "res://art_tests/cells/platformer_2d/assets/"
const SPEED := 260.0
const JUMP_SPEED := 620.0
const GRAVITY := 1700.0
const PLATFORM_COLOR := Color("2a2f55")          # the puppet's navy: hero and ground read as one world
## Each platform: [left, top, width, height] in screen pixels.
const PLATFORMS := [[0, 600, 520, 120], [600, 520, 300, 200], [980, 430, 300, 290], [330, 380, 190, 28]]

var hero: CharacterBody2D
var puppet: Node2D
var stride := 0.0                                  # where we are in the run cycle, in radians


## _ready(): backdrop, platforms, then the hero body with the puppet inside it.
func _ready() -> void:
	var backdrop := Sprite2D.new()
	backdrop.texture = load(ASSETS + "backdrop/backdrop_00.png")
	backdrop.centered = false
	add_child(backdrop)
	for rect: Array in PLATFORMS:
		_platform(Rect2(rect[0], rect[1], rect[2], rect[3]))

	hero = CharacterBody2D.new()
	hero.position = Vector2(700, 520)
	var shape := CollisionShape2D.new()
	var box := RectangleShape2D.new()
	box.size = Vector2(34, 100)
	shape.shape = box
	shape.position = Vector2(0, -50)               # the body's origin is at the feet
	hero.add_child(shape)
	puppet = Puppet.new()
	puppet.back_tint = Color(0.72, 0.72, 0.86)     # far-side limbs a touch lighter: depth without shading
	hero.add_child(puppet)
	puppet.build(ASSETS + "explorer/")
	puppet.position.y = -puppet.leg_length()       # hips this far above the feet
	add_child(hero)


## A flat rectangle you can stand on.
func _platform(rect: Rect2) -> void:
	var body := StaticBody2D.new()
	body.position = rect.get_center()
	var shape := CollisionShape2D.new()
	var box := RectangleShape2D.new()
	box.size = rect.size
	shape.shape = box
	body.add_child(shape)
	var fill := ColorRect.new()
	fill.color = PLATFORM_COLOR
	fill.size = rect.size
	fill.position = -rect.size / 2.0
	body.add_child(fill)
	add_child(body)


## Movement: run, jump, fall (the same twenty lines as any platformer body).
func _physics_process(delta: float) -> void:
	var direction := Input.get_axis(&"ui_left", &"ui_right")
	hero.velocity.x = direction * SPEED
	hero.velocity.y += GRAVITY * delta
	if hero.is_on_floor() and (Input.is_action_just_pressed(&"ui_accept") or Input.is_action_just_pressed(&"ui_up")):
		hero.velocity.y = -JUMP_SPEED
	hero.move_and_slide()
	if direction != 0.0:
		puppet.scale.x = signf(direction)           # mirror the whole puppet to face the other way


## The whole run animation: opposite sine waves on the near and far limbs.
## _process runs every drawn frame; `delta` is the seconds since the last one.
func _process(delta: float) -> void:
	stride += delta * 11.0
	var swing := sin(stride)
	var bones: Dictionary = puppet.bones
	bones["leg"].rotation_degrees = swing * 38.0
	bones["leg_b"].rotation_degrees = -swing * 38.0
	bones["arm"].rotation_degrees = -swing * 48.0   # arms swing against the legs, like a real runner
	bones["arm_b"].rotation_degrees = swing * 48.0
	bones["body"].rotation_degrees = 9.0            # lean into the run
	bones["head"].rotation_degrees = -6.0 + sin(stride * 2.0) * 3.0
	# Two small bounces per stride, so the feet do not look glued to a rail.
	puppet.position.y = -puppet.leg_length() * 0.97 - absf(swing) * 4.0
