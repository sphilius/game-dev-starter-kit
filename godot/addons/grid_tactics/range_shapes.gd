# RangeShapes: turns "a cross of radius 2 at this cell" into the list of grid cells it covers.
class_name RangeShapes
extends RefCounted
## Pure maths, no nodes. Used for ability areas, attack ranges and enemy telegraphs.
## Cells are Vector2i (integer x, y). Results may include cells outside the board; the
## GridModel filters those out.

enum Shape {
	SINGLE,   ## just the origin cell
	LINE,     ## `radius` cells starting at the origin, going in `direction`
	CROSS,    ## the origin plus four arms of length `radius` (a + shape)
	DIAMOND,  ## every cell within `radius` steps (Manhattan distance), like movement range
	SQUARE,   ## every cell within `radius` in both axes (a (2r+1)×(2r+1) block)
}

## The four grid directions. Note y grows DOWNWARD on a 2D grid, so UP is (0, -1).
const DIRECTIONS: Array[Vector2i] = [Vector2i.RIGHT, Vector2i.DOWN, Vector2i.LEFT, Vector2i.UP]


## The cells a shape covers. `direction` only matters for LINE.
static func cells(shape: Shape, origin: Vector2i, radius: int = 1, direction: Vector2i = Vector2i.RIGHT) -> Array[Vector2i]:
	# Array[Vector2i] is a typed array: Godot checks every element is a Vector2i.
	var out: Array[Vector2i] = []
	# `match` is GDScript's switch statement: run the branch for this shape.
	match shape:
		Shape.SINGLE:
			out.append(origin)
		Shape.LINE:
			for i in maxi(radius, 1):
				out.append(origin + direction * i)
		Shape.CROSS:
			out.append(origin)
			for dir in DIRECTIONS:
				for i in range(1, radius + 1):
					out.append(origin + dir * i)
		Shape.DIAMOND:
			for y in range(-radius, radius + 1):
				for x in range(-radius, radius + 1):
					if absi(x) + absi(y) <= radius:
						out.append(origin + Vector2i(x, y))
		Shape.SQUARE:
			for y in range(-radius, radius + 1):
				for x in range(-radius, radius + 1):
					out.append(origin + Vector2i(x, y))
	return out


## Steps between two cells when you can only move up/down/left/right (Manhattan distance).
static func distance(a: Vector2i, b: Vector2i) -> int:
	return absi(a.x - b.x) + absi(a.y - b.y)


## The main compass direction from `from` toward `to` (used to aim LINE abilities).
static func direction_to(from: Vector2i, to: Vector2i) -> Vector2i:
	var d := to - from
	if d == Vector2i.ZERO:
		return Vector2i.RIGHT
	if absi(d.x) >= absi(d.y):
		return Vector2i(signi(d.x), 0)
	return Vector2i(0, signi(d.y))
