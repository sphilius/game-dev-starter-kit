extends Node2D
## Metroidvania cell, 2D art: a pixel wanderer running through a tile-built cave.
##
## Art: assets/wanderer/run_*.png (six AI frames, snapped to a 16-colour palette) and
## assets/tiles/atlas.png (one AI ground tile; the rock tile is made from its lower half).
## No kit: a platformer body is twenty lines of CharacterBody2D, shown below.
##
## Controls: A/D or arrow keys run, Space or Up jumps.

const CellArt := preload("res://art_tests/cells/cell_art.gd")
const ASSETS := "res://art_tests/cells/metroidvania_2d/assets/"
const TILE := 32
const SPEED := 110.0
const JUMP_SPEED := 290.0
const GRAVITY := 800.0
const CAVE_WALL := Color("566c86")

## The room, one character per tile: "#" = terrain, "." = empty. A tile with air above it
## gets the mossy ground picture; a tile with terrain above it gets plain rock.
const ROOM: Array[String] = [
	"####################",
	"#..................#",
	"#..................#",
	"#...........###....#",
	"#..................#",
	"#.....###..........#",
	"#..................#",
	"####..........######",
	"####....###...######",
	"####################",
	"####################",
]

var hero: CharacterBody2D
var sprite: AnimatedSprite2D


## _ready(): back wall colour, tile map, hero, and a camera zoomed 4x for chunky pixels.
func _ready() -> void:
	RenderingServer.set_default_clear_color(CAVE_WALL)
	add_child(_build_room())
	hero = CharacterBody2D.new()
	hero.position = Vector2(6.0 * TILE, 7 * TILE)
	var shape := CollisionShape2D.new()
	var box := RectangleShape2D.new()
	box.size = Vector2(14, 40)
	shape.shape = box
	shape.position = Vector2(0, -20)              # the body's origin is at the feet
	hero.add_child(shape)
	sprite = AnimatedSprite2D.new()
	sprite.sprite_frames = CellArt.sprite_frames({"run": [ASSETS + "wanderer/run_", 6, 12.0]})
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	sprite.offset = Vector2(0, -22)               # frames are 52 px tall; this puts the soles on the floor
	sprite.play(&"run")
	hero.add_child(sprite)
	add_child(hero)
	var camera := Camera2D.new()
	camera.zoom = Vector2(4, 4)                   # 1280x720 window shows a 320x180 world
	camera.position = Vector2(0, -34)
	hero.add_child(camera)


## Turns ROOM into a TileMapLayer with collision on every terrain tile.
func _build_room() -> TileMapLayer:
	var source := TileSetAtlasSource.new()
	source.texture = load(ASSETS + "tiles/atlas.png")
	source.texture_region_size = Vector2i(TILE, TILE)
	var tile_set := TileSet.new()
	tile_set.tile_size = Vector2i(TILE, TILE)
	tile_set.add_physics_layer()                  # must exist before a tile can hold a collision shape
	tile_set.add_source(source, 0)
	var half := TILE / 2.0
	for atlas_x in 2:
		source.create_tile(Vector2i(atlas_x, 0))
		var data := source.get_tile_data(Vector2i(atlas_x, 0), 0)
		# One square collision polygon covering the whole tile (points are from the tile's centre).
		data.add_collision_polygon(0)
		data.set_collision_polygon_points(0, 0, PackedVector2Array(
				[Vector2(-half, -half), Vector2(half, -half), Vector2(half, half), Vector2(-half, half)]))
	var layer := TileMapLayer.new()
	layer.tile_set = tile_set
	layer.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	for y in ROOM.size():
		for x in ROOM[y].length():
			if ROOM[y][x] != "#":
				continue
			var open_above := y > 0 and ROOM[y - 1][x] == "."
			layer.set_cell(Vector2i(x, y), 0, Vector2i(0 if open_above else 1, 0))
	return layer


## Run, jump, fall. _physics_process runs at a fixed 60 times a second.
func _physics_process(delta: float) -> void:
	var direction := Input.get_axis(&"ui_left", &"ui_right")
	hero.velocity.x = direction * SPEED
	hero.velocity.y += GRAVITY * delta
	if hero.is_on_floor() and (Input.is_action_just_pressed(&"ui_accept") or Input.is_action_just_pressed(&"ui_up")):
		hero.velocity.y = -JUMP_SPEED
	hero.move_and_slide()
	if direction != 0.0:
		sprite.flip_h = direction < 0.0           # the art faces right; mirror it to run left
		sprite.play(&"run")
	else:
		sprite.pause()
