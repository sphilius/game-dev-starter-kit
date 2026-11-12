extends Node2D
## Action RPG cell, 2D art: a top-down ranger with a four-direction walk on tiled dry earth.
##
## Art: assets/ranger/<direction>/*.png (three AI rows + one mirrored) and assets/ground/ground_00.png.
## Kit: HealthComponent and HitInfo from kit_combat on the training dummies.
##
## Controls: WASD or arrow keys walk, Space swings (hurts dummies within 40 px).

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const ASSETS := "res://art_tests/cells/action_rpg_2d/assets/"
const SPEED := 90.0                     # pixels per second, in the 426x240 world the camera shows
const DIRECTIONS: Array[String] = ["down", "left", "right", "up"]

var hero: CharacterBody2D
var hero_sprite: AnimatedSprite2D
var facing := "down"
var dummies: Array[Node2D] = []


## _ready(): floor, hero, three dummies and a camera that zooms the small sprites up 3x.
func _ready() -> void:
	var floor_sprite := CellArt.tiled(load(ASSETS + "ground/ground_00.png"), Vector2(1024, 768))
	floor_sprite.position = Vector2(-512, -384)
	add_child(floor_sprite)

	hero = CharacterBody2D.new()
	hero_sprite = _ranger_sprite()
	hero.add_child(hero_sprite)
	add_child(hero)
	# Dummies reuse the hero's frames with a red tint: a second character for free.
	for spot: Array in [[Vector2(-90, -30), "right"], [Vector2(70, -45), "down"], [Vector2(95, 40), "left"], [Vector2(-60, 55), "up"]]:
		_dummy(spot[0], spot[1])

	var camera := Camera2D.new()
	camera.zoom = Vector2(3, 3)             # 1280x720 window shows a 426x240 world: chunky pixels
	hero.add_child(camera)
	# y_sort: things lower on screen draw in front, so the hero can walk behind a dummy.
	y_sort_enabled = true
	floor_sprite.z_index = -1


## An AnimatedSprite2D with the four walk animations, feet at the node's origin.
func _ranger_sprite() -> AnimatedSprite2D:
	var animations := {}
	for direction in DIRECTIONS:
		animations["walk_" + direction] = [ASSETS + "ranger/%s/%s_" % [direction, direction], 4, 8.0]
	var sprite := AnimatedSprite2D.new()
	sprite.sprite_frames = CellArt.sprite_frames(animations)
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	# Frames are 68 px tall with the feet 2 px above the bottom edge (art_cleanup's padding).
	sprite.offset = Vector2(0, -32)
	sprite.play(&"walk_down")
	return sprite


## A stationary ranger copy with 30 HP that flashes when hit and fades out when it dies.
func _dummy(at: Vector2, direction: String) -> void:
	var dummy := Node2D.new()
	dummy.position = at
	var sprite := _ranger_sprite()
	sprite.modulate = Color(1.0, 0.55, 0.5)
	sprite.play("walk_" + direction)
	dummy.add_child(sprite)
	var health := HealthComponent.new()
	health.max_health = 30.0
	dummy.add_child(health)
	health.damaged.connect(func(_hit: HitInfo) -> void:
		sprite.modulate = Color.WHITE
		create_tween().tween_property(sprite, ^"modulate", Color(1.0, 0.55, 0.5), 0.2))
	health.died.connect(func(_hit: HitInfo) -> void:
		dummies.erase(dummy)
		var fade := create_tween()
		fade.tween_property(dummy, ^"modulate:a", 0.0, 0.3)
		fade.tween_callback(dummy.queue_free))
	add_child(dummy)
	dummies.append(dummy)


## Walk with the arrow keys / WASD and pick the animation that matches the direction.
func _physics_process(_delta: float) -> void:
	var move := Input.get_vector(&"ui_left", &"ui_right", &"ui_up", &"ui_down")
	hero.velocity = move * SPEED
	hero.move_and_slide()
	if move != Vector2.ZERO:
		# The larger axis decides the facing, so diagonals do not flicker between two rows.
		if absf(move.x) > absf(move.y):
			facing = "right" if move.x > 0.0 else "left"
		else:
			facing = "down" if move.y > 0.0 else "up"
		hero_sprite.play("walk_" + facing)
	else:
		hero_sprite.pause()                  # stand still on the current frame


## Space: damage every dummy within reach. HitInfo carries the damage number to HealthComponent.
func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_accept"):
		for dummy in dummies.duplicate():       # duplicate(): the list may shrink while we loop
			if dummy.position.distance_to(hero.position) < 40.0:
				HealthComponent.resolve(dummy).take_damage(HitInfo.new(10.0))
