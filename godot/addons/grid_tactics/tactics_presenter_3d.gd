# TacticsPresenter3D: the same board as TacticsPresenter2D, built from 3D meshes.
class_name TacticsPresenter3D
extends Node3D
## Same idea and same method names as the 2D presenter, so a game can switch between them:
## the model emits signals, this node animates. The board lies flat on the XZ plane (Y is up),
## with model cell (x, y) at world (x, 0, y) × cell_size.
##
## Content-free: with nothing assigned it makes flat box tiles, taller boxes for walls and
## coloured capsules for units. To use your own art:
##   • unit_scenes: {UnitData.id: PackedScene} (e.g. an imported .glb mini). Optional methods
##     on the scene root: set_unit(unit), on_unit_damaged(amount), on_unit_died().
##   • floor_material / wall_material for the tiles, or hide Tiles and build your own level.
##
## Call setup(model). Left click emits cell_clicked(cell) using the current Camera3D.

## The player clicked a cell on the board.
signal cell_clicked(cell: Vector2i)
## Every running move/death animation has finished.
signal animation_finished

## World size of one cell in metres.
@export var cell_size := 1.0
## Seconds a unit takes to walk one cell. 0 = teleport.
@export var move_seconds_per_cell := 0.15
@export var unit_scenes := {}
@export var floor_material: Material
@export var wall_material: Material
@export var team_colors: Array[Color] = [Color(0.35, 0.65, 1.0), Color(1.0, 0.4, 0.35), Color(0.5, 0.9, 0.5)]
## Tint telegraphed cells for this team automatically (-1 = do not).
@export var danger_for_team := 0

var model: GridModel
## Vector2i -> the MeshInstance3D tile on that cell.
var tile_nodes := {}
## GridUnit -> the Node3D that represents it.
var unit_nodes := {}
var _highlights := {}              # key -> {"cells": Array, "color": Color}
var _running := 0
var _tint_materials := {}          # Color -> StandardMaterial3D, reused so tiles share materials


## Builds the board for `model` and starts listening to it. Safe to call again with a new model.
func setup(p_model: GridModel) -> void:
	_clear()
	model = p_model
	_build_tiles()
	model.unit_added.connect(_on_unit_added)
	model.unit_moved.connect(_on_unit_moved)
	model.unit_damaged.connect(_on_unit_damaged)
	model.unit_died.connect(_on_unit_died)
	model.intent_changed.connect(_on_intent_changed)
	for unit in model.living():
		_on_unit_added(unit)


# --- Coordinates --------------------------------------------------------------------------

## Centre of a cell on the ground, in this node's local space.
func cell_to_world(cell: Vector2i) -> Vector3:
	return Vector3((cell.x + 0.5) * cell_size, 0.0, (cell.y + 0.5) * cell_size)


## The cell under a local position (its height is ignored).
func world_to_cell(local_position: Vector3) -> Vector2i:
	return Vector2i(floori(local_position.x / cell_size), floori(local_position.z / cell_size))


## The cell under a screen position, seen through `camera`: shoot a ray from the camera and
## find where it crosses the board's ground plane. Returns (-1, -1) if it misses the board.
func cell_at_screen(camera: Camera3D, screen_position: Vector2) -> Vector2i:
	var origin := camera.project_ray_origin(screen_position)
	var direction := camera.project_ray_normal(screen_position)
	var ground := Plane(global_basis.y.normalized(), global_position)
	var hit: Variant = ground.intersects_ray(origin, direction)     # null when parallel/behind
	if hit == null:
		return Vector2i(-1, -1)
	var cell := world_to_cell(to_local(hit))
	return cell if model and model.in_bounds(cell) else Vector2i(-1, -1)


## True while any move or death animation is still playing.
func is_busy() -> bool:
	return _running > 0


# --- Highlights ---------------------------------------------------------------------------

## Tints a set of cells. `key` names the layer so several can be shown and cleared separately.
func show_cells(cells: Array, color: Color, key := "range") -> void:
	_highlights[key] = {"cells": cells, "color": color}
	_refresh_tints()


## Removes one highlight layer, or all of them when key is empty.
func clear_highlights(key := "") -> void:
	if key.is_empty():
		_highlights.clear()
	else:
		_highlights.erase(key)
	_refresh_tints()


## Recolours tiles: telegraphed danger wins over range highlights, which win over the default.
func _refresh_tints() -> void:
	var tint := {}
	for key in _highlights:
		for cell: Vector2i in _highlights[key].cells:
			tint[cell] = _highlights[key].color
	if model and danger_for_team >= 0:
		for cell: Vector2i in model.danger_cells(danger_for_team):
			tint[cell] = Color(1.0, 0.2, 0.15)
	for cell: Vector2i in tile_nodes:
		var tile: MeshInstance3D = tile_nodes[cell]
		# material_override replaces the mesh's own material while set; null restores it.
		tile.material_override = _tint_material(tint[cell]) if tint.has(cell) and not model.is_blocked(cell) else null


## Left click -> which cell? Uses whatever Camera3D is currently active.
func _unhandled_input(event: InputEvent) -> void:
	var click := event as InputEventMouseButton
	if model == null or click == null or not click.pressed or click.button_index != MOUSE_BUTTON_LEFT:
		return
	var camera := get_viewport().get_camera_3d()
	if camera == null:
		return
	var cell := cell_at_screen(camera, click.position)
	if cell != Vector2i(-1, -1):
		cell_clicked.emit(cell)


# --- Model signal handlers ----------------------------------------------------------------

## A unit appeared: make its node (your scene, or a placeholder capsule).
func _on_unit_added(unit: GridUnit) -> void:
	var node: Node3D
	var scene: PackedScene = unit_scenes.get(unit.data.id)
	if scene:
		node = scene.instantiate() as Node3D
	else:
		node = _placeholder_unit(unit)
	node.name = "%s_%d" % [unit.data.id, unit_nodes.size()]
	node.position = cell_to_world(unit.cell)
	add_child(node)
	unit_nodes[unit] = node
	if node.has_method(&"set_unit"):
		node.set_unit(unit)


## A unit walked: turn to face each step and tween through the path.
func _on_unit_moved(unit: GridUnit, path: Array[Vector2i]) -> void:
	var node: Node3D = unit_nodes.get(unit)
	if node == null:
		return
	if move_seconds_per_cell <= 0.0 or path.size() < 2:
		node.position = cell_to_world(unit.cell)
		return
	_running += 1
	var tween := create_tween()
	for i in range(1, path.size()):
		var step := path[i] - path[i - 1]
		# Face the walking direction: models look along -Z, so yaw = atan2(-x, -z).
		tween.tween_property(node, ^"rotation:y", atan2(-float(step.x), -float(step.y)), 0.0)
		tween.tween_property(node, ^"position", cell_to_world(path[i]), move_seconds_per_cell)
	tween.finished.connect(_animation_done)


## HP changed: a quick squash so hits read even without animations.
func _on_unit_damaged(unit: GridUnit, amount: int, _source: GridUnit) -> void:
	var node: Node3D = unit_nodes.get(unit)
	if node == null:
		return
	if node.has_method(&"on_unit_damaged"):
		node.on_unit_damaged(amount)
	node.scale = Vector3(1.25, 0.8, 1.25) if amount > 0 else Vector3(0.9, 1.2, 0.9)
	create_tween().tween_property(node, ^"scale", Vector3.ONE, 0.2)


## A unit died: shrink its node away, then free it.
func _on_unit_died(unit: GridUnit) -> void:
	var node: Node3D = unit_nodes.get(unit)
	if node == null:
		return
	unit_nodes.erase(unit)
	if node.has_method(&"on_unit_died"):
		node.on_unit_died()
	_running += 1
	var tween := create_tween()
	tween.tween_property(node, ^"scale", Vector3.ONE * 0.01, 0.25)
	tween.finished.connect(node.queue_free)
	tween.finished.connect(_animation_done)


## A telegraph changed: repaint the danger tiles.
func _on_intent_changed(_unit: GridUnit) -> void:
	_refresh_tints()


## Counts animations down and announces when the board is at rest.
func _animation_done() -> void:
	_running = maxi(_running - 1, 0)
	if _running == 0:
		animation_finished.emit()


# --- Building -----------------------------------------------------------------------------

## One box per cell: thin slabs for floor, tall blocks for walls. All floors share one mesh
## and one material (cheap to draw, which matters in web builds).
func _build_tiles() -> void:
	var holder := Node3D.new()
	holder.name = "Tiles"
	add_child(holder)
	var floor_mesh := BoxMesh.new()
	floor_mesh.size = Vector3(cell_size * 0.96, 0.1, cell_size * 0.96)
	floor_mesh.material = floor_material if floor_material else _flat_material(Color(0.24, 0.26, 0.3))
	var wall_mesh := BoxMesh.new()
	wall_mesh.size = Vector3(cell_size * 0.96, cell_size, cell_size * 0.96)
	wall_mesh.material = wall_material if wall_material else _flat_material(Color(0.5, 0.5, 0.56))
	for y in model.size.y:
		for x in model.size.x:
			var cell := Vector2i(x, y)
			var wall := model.is_blocked(cell)
			var tile := MeshInstance3D.new()
			tile.mesh = wall_mesh if wall else floor_mesh
			# Slabs sit just under y = 0 so units stand ON the ground plane; walls rise from it.
			tile.position = cell_to_world(cell) + Vector3(0.0, cell_size * 0.5 if wall else -0.05, 0.0)
			holder.add_child(tile)
			tile_nodes[cell] = tile


## A coloured capsule standing on the cell, with a small "nose" box showing which way it faces.
func _placeholder_unit(unit: GridUnit) -> Node3D:
	var node := Node3D.new()
	var material := _flat_material(team_colors[unit.team % team_colors.size()])
	var body := MeshInstance3D.new()
	var capsule := CapsuleMesh.new()
	capsule.radius = cell_size * 0.28
	capsule.height = cell_size * 1.1
	capsule.material = material
	body.mesh = capsule
	body.position.y = capsule.height * 0.5
	node.add_child(body)
	var nose := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3.ONE * cell_size * 0.16
	box.material = material
	nose.mesh = box
	nose.position = Vector3(0.0, capsule.height * 0.75, -capsule.radius)
	node.add_child(nose)
	return node


## A plain, matte material of one colour.
func _flat_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	return material


## One shared material per highlight colour (created on first use).
func _tint_material(color: Color) -> StandardMaterial3D:
	if not _tint_materials.has(color):
		# Tiles are opaque, so "alpha" is faked: mix the highlight into the floor grey by its
		# alpha. Color(0.3, 0.7, 1, 0.35) gives a soft blue wash; alpha 1 gives the pure colour.
		var mixed := Color(0.24, 0.26, 0.3).lerp(Color(color, 1.0), color.a)
		_tint_materials[color] = _flat_material(mixed)
	return _tint_materials[color]


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
	tile_nodes.clear()
	unit_nodes.clear()
	_highlights.clear()
	_running = 0
