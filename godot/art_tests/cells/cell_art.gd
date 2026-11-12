extends RefCounted
## Small helpers the cell demos share for turning cleaned-up frames into Godot resources.
## Not part of any kit: demos load it with
##     const CellArt := preload("res://art_tests/cells/cell_art.gd")
## All functions are static, so nothing needs to be created: CellArt.sprite_frames(...).


## Builds a SpriteFrames (the resource an AnimatedSprite2D plays) from numbered PNG frames.
## `animations` maps an animation name to [file prefix, frame count, frames per second], e.g.
##     {"walk_down": ["res://.../down/down_", 4, 8.0]}  ->  down_00.png ... down_03.png
static func sprite_frames(animations: Dictionary) -> SpriteFrames:
	var frames := SpriteFrames.new()
	frames.remove_animation(&"default")          # a new SpriteFrames starts with an empty "default"
	for anim_name: String in animations:
		var spec: Array = animations[anim_name]
		frames.add_animation(anim_name)
		frames.set_animation_speed(anim_name, spec[2])
		frames.set_animation_loop(anim_name, true)
		for i in int(spec[1]):
			frames.add_frame(anim_name, load("%s%02d.png" % [spec[0], i]) as Texture2D)
	return frames


## A Sprite2D that repeats `texture` over `size` pixels (a tiled floor or sky).
## region_enabled + texture_repeat is the cheapest way to tile: one node, one draw call.
static func tiled(texture: Texture2D, size: Vector2) -> Sprite2D:
	var sprite := Sprite2D.new()
	sprite.texture = texture
	sprite.centered = false
	sprite.region_enabled = true
	sprite.region_rect = Rect2(Vector2.ZERO, size)
	sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	return sprite
