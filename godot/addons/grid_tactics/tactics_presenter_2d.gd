# TacticsPresenter2D: draws a GridModel as a 2D board and animates what happens on it.
class_name TacticsPresenter2D
extends Node2D
## The model holds the rules; this node only SHOWS them. It connect()s to the model's signals
## and reacts: a unit_moved signal becomes a tween along the path, unit_damaged a flash, and so
## on. Swap this presenter for the 3D one and the game logic does not change at all.
##
## Content-free: with nothing assigned it makes grey placeholder tiles and coloured discs.
## To use your own art:
##   • tile_set: a TileSet whose source 0 has the floor at atlas (0,0) and the wall at (1,0).
##   • unit_scenes: {UnitData.id: PackedScene}. If the scene's root has set_unit(unit) it is
##     called once, and on_unit_damaged(amount) / on_unit_died() are called if present.
##
## Call setup(model) once the model exists. Input: left click emits cell_clicked(cell).

## The player clicked a cell on the board.
signal cell_clicked(cell: Vector2i)
## Every running move/death animation has finished (wait for this before the next turn).
signal animation_finished

## Pixel size of one square cell.
@export var cell_size := 64
## Seconds a unit takes to walk one cell. 0 = teleport (useful for fast-forward).
@export var move_seconds_per_cell := 0.12
## Optional art: see the class notes above.
@export var tile_set: TileSet
@export var unit_scenes := {}
## Placeholder disc colour per team number (wraps around if there are more teams).
@export var team_colors: Array[Color] = [Color(0.35, 0.65, 1.0), Color(1.0, 0.4, 0.35), Color(0.5, 0.9, 0.5)]
## Draw enemy telegraphs for this team automatically (-1 = do not).
@export var danger_for_team := 0

var model: GridModel
var tiles: TileMapLayer
## GridUnit -> the Node2D that represents it.
var unit_nodes := {}
var _highlights := {}              # key -> {"cells": Array[Vector2i], "color": Color}
var _running := 0                  # animations in progress


## Builds the board for `model` and starts listening to it. Safe to call again with a new model.
func setup(p_model: GridModel) -> void:
	_clear()
	model = p_model
	_build_tiles()
	# connect(): from now on, the model calls these functions whenever it emits each signal.
	model.unit_added.connect(_on_unit_added)
	model.unit_moved.connect(_on_unit_moved)
	model.unit_damaged.connect(_on_unit_damaged)
	model.unit_died.connect(_on_unit_died)
	model.intent_changed.connect(_on_intent_changed)
	for unit in model.living():
		_on_unit_added(unit)


# --- Coordinates --------------------------------------------------------------------------

## Centre of a cell, in this node's local space (pixels).
func cell_to_world(cell: Vector2i) -> Vector2:
	return (Vector2(cell) + Vector2(0.5, 0.5)) * cell_size


## The cell under a local position (may be off the board: check model.in_bounds).
func world_to_cell(local_position: Vector2) -> Vector2i:
	return Vector2i((local_position / cell_size).floor())


## True while any move or death animation is still playing.
func is_busy() -> bool:
	return _running > 0


# --- Highlights ---------------------------------------------------------------------------

## Tints a set of cells (movement range, attack range...). `key` names the layer so several
## can be shown at once and cleared separately.
func show_cells(cells: Array, color: Color, key := "range") -> void:
	_highlights[key] = {"cells": cells, "color": color}
	queue_redraw()                         # ask Godot to call _draw() again


## Removes one highlight layer, or all of them when key is empty.
func clear_highlights(key := "") -> void:
	if key.is_empty():
		_highlights.clear()
	else:
		_highlights.erase(key)
	queue_redraw()


## _draw() is where a CanvasItem paints custom shapes; it runs after queue_redraw().
func _draw() -> void:
	for key in _highlights:
		var layer: Dictionary = _highlights[key]
		for cell: Vector2i in layer.cells:
			draw_rect(Rect2(Vector2(cell) * cell_size, Vector2.ONE * cell_size).grow(-3.0), layer.color)
	if model and danger_for_team >= 0:
		# Telegraphed enemy attacks: a red outline plus the damage waiting there.
		var danger := model.danger_cells(danger_for_team)
		for cell: Vector2i in danger:
			var rect := Rect2(Vector2(cell) * cell_size, Vector2.ONE * cell_size).grow(-5.0)
			draw_rect(rect, Color(1.0, 0.2, 0.15, 0.25))
			draw_rect(rect, Color(1.0, 0.2, 0.15), false, 3.0)


## Left click -> which cell? Emitted only for cells on the board.
func _unhandled_input(event: InputEvent) -> void:
	var click := event as InputEventMouseButton
	if model == null or click == null or not click.pressed or click.button_index != MOUSE_BUTTON_LEFT:
		return
	var cell := world_to_cell(get_local_mouse_position())
	if model.in_bounds(cell):
		cell_clicked.emit(cell)


# --- Model signal handlers ----------------------------------------------------------------

## A unit appeared: make its node (your scene, or a placeholder disc with an HP label).
func _on_unit_added(unit: GridUnit) -> void:
	var node: Node2D
	var scene: PackedScene = unit_scenes.get(unit.data.id)
	if scene:
		node = scene.instantiate() as Node2D
	else:
		node = _placeholder_unit(unit)
	node.name = "%s_%d" % [unit.data.id, unit_nodes.size()]
	node.position = cell_to_world(unit.cell)
	add_child(node)
	unit_nodes[unit] = node
	if node.has_method(&"set_unit"):
		node.set_unit(unit)


## A unit walked: tween its node through every cell of the path, in order.
func _on_unit_moved(unit: GridUnit, path: Array[Vector2i]) -> void:
	var node: Node2D = unit_nodes.get(unit)
	if node == null:
		return
	if move_seconds_per_cell <= 0.0 or path.size() < 2:
		node.position = cell_to_world(unit.cell)
		return
	_running += 1
	var tween := create_tween()            # a Tween animates properties over time
	for i in range(1, path.size()):
		tween.tween_property(node, ^"position", cell_to_world(path[i]), move_seconds_per_cell)
	tween.finished.connect(_animation_done)


## HP changed: refresh the label and flash white (damage) or green (healing).
func _on_unit_damaged(unit: GridUnit, amount: int, _source: GridUnit) -> void:
	var node: Node2D = unit_nodes.get(unit)
	if node == null:
		return
	var label := node.get_node_or_null(^"HP") as Label
	if label:
		label.text = str(unit.hp)
	if node.has_method(&"on_unit_damaged"):
		node.on_unit_damaged(amount)
	node.modulate = Color(3.0, 3.0, 3.0) if amount > 0 else Color(0.6, 2.0, 0.6)
	create_tween().tween_property(node, ^"modulate", Color.WHITE, 0.2)


## A unit died: fade its node out, then free it.
func _on_unit_died(unit: GridUnit) -> void:
	var node: Node2D = unit_nodes.get(unit)
	if node == null:
		return
	unit_nodes.erase(unit)
	if node.has_method(&"on_unit_died"):
		node.on_unit_died()
	_running += 1
	var tween := create_tween()
	tween.tween_property(node, ^"modulate:a", 0.0, 0.25)
	tween.finished.connect(node.queue_free)
	tween.finished.connect(_animation_done)


## A telegraph changed: the danger markers are painted in _draw(), so just repaint.
func _on_intent_changed(_unit: GridUnit) -> void:
	queue_redraw()


## Counts animations down and announces when the board is at rest.
func _animation_done() -> void:
	_running = maxi(_running - 1, 0)
	if _running == 0:
		animation_finished.emit()


# --- Building -----------------------------------------------------------------------------

## Fills a TileMapLayer with floor and wall tiles from the model.
func _build_tiles() -> void:
	tiles = TileMapLayer.new()
	tiles.name = "Tiles"
	tiles.tile_set = tile_set if tile_set else _placeholder_tile_set()
	tiles.z_index = -1                     # draw under units and highlights
	add_child(tiles)
	for y in model.size.y:
		for x in model.size.x:
			var cell := Vector2i(x, y)
			# set_cell(cell, source id, atlas coordinates): (0,0) = floor, (1,0) = wall
			tiles.set_cell(cell, 0, Vector2i(1, 0) if model.is_blocked(cell) else Vector2i(0, 0))


## A two-tile TileSet painted in code (floor, wall), so the kit ships no image files.
func _placeholder_tile_set() -> TileSet:
	var image := Image.create(cell_size * 2, cell_size, false, Image.FORMAT_RGBA8)
	image.fill_rect(Rect2i(0, 0, cell_size, cell_size), Color(0.16, 0.17, 0.2))
	image.fill_rect(Rect2i(1, 1, cell_size - 2, cell_size - 2), Color(0.22, 0.24, 0.28))
	image.fill_rect(Rect2i(cell_size, 0, cell_size, cell_size), Color(0.42, 0.42, 0.46))
	image.fill_rect(Rect2i(cell_size + 4, 4, cell_size - 8, cell_size - 8), Color(0.55, 0.55, 0.6))
	var source := TileSetAtlasSource.new()
	source.texture = ImageTexture.create_from_image(image)
	source.texture_region_size = Vector2i(cell_size, cell_size)
	source.create_tile(Vector2i(0, 0))
	source.create_tile(Vector2i(1, 0))
	var made := TileSet.new()
	made.tile_size = Vector2i(cell_size, cell_size)
	made.add_source(source, 0)
	return made


## A coloured disc with the unit's HP on it.
func _placeholder_unit(unit: GridUnit) -> Node2D:
	var node := Node2D.new()
	var disc := Polygon2D.new()
	var points := PackedVector2Array()
	for i in 20:
		points.append(Vector2.from_angle(TAU * i / 20.0) * cell_size * 0.36)
	disc.polygon = points
	disc.color = team_colors[unit.team % team_colors.size()]
	node.add_child(disc)
	var label := Label.new()
	label.name = "HP"
	label.text = str(unit.hp)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.size = Vector2.ONE * cell_size
	label.position = -label.size * 0.5
	node.add_child(label)
	return node


## Removes everything from a previous setup() and disconnects from the old model.
func _clear() -> void:
	if model:
		for pair in [[model.unit_added, _on_unit_added], [model.unit_moved, _on_unit_moved],
				[model.unit_damaged, _on_unit_damaged], [model.unit_died, _on_unit_died],
				[model.intent_changed, _on_intent_changed]]:
			if (pair[0] as Signal).is_connected(pair[1]):
				(pair[0] as Signal).disconnect(pair[1])
	for child in get_children():
		child.queue_free()
	unit_nodes.clear()
	_highlights.clear()
	_running = 0
