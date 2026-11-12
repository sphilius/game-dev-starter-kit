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


## The AnimationPlayer inside an imported .glb scene (Godot puts one there when the file has clips).
static func animator(model: Node) -> AnimationPlayer:
	return model.find_child("AnimationPlayer", true, false) as AnimationPlayer


## Plays a clip on an imported model. Prints the clip names it does have when `clip` is missing,
## which is the fastest way to find out what Godot renamed on import.
static func play_clip(model: Node, clip: String, speed := 1.0) -> void:
	var player := animator(model)
	if player == null or not player.has_animation(clip):
		push_warning("%s has no clip '%s'. It has: %s" % [model.name, clip, player.get_animation_list() if player else []])
		return
	player.play(clip, 0.2, speed)                 # 0.2 s blend from whatever was playing


## Adds a sun, a flat sky colour, ambient light and (optional) distance fog to a 3D scene.
## One call gives every 3D cell the same cheap, readable outdoor lighting.
static func outdoor_light(parent: Node, sky: Color, fog_density := 0.0) -> WorldEnvironment:
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48.0, 35.0, 0.0)
	sun.shadow_enabled = true
	parent.add_child(sun)
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = sky.lightened(0.3)
	environment.ambient_light_energy = 0.45       # low enough that the sun still shapes the models
	if fog_density > 0.0:
		environment.fog_enabled = true
		environment.fog_light_color = sky
		environment.fog_density = fog_density
	var world := WorldEnvironment.new()
	world.environment = environment
	parent.add_child(world)
	return world


## A flat, collidable ground slab with a plain colour: enough floor for a demo.
static func ground(parent: Node, size: Vector2, color: Color) -> StaticBody3D:
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(size.x, 1.0, size.y)
	shape.shape = box
	shape.position.y = -0.5                       # top face at y = 0
	body.add_child(shape)
	var mesh := BoxMesh.new()
	mesh.size = box.size
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 1.0
	mesh.material = material
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position.y = -0.5
	body.add_child(instance)
	parent.add_child(body)
	return body


## Recolours every surface of an imported model by multiplying its colours with `color`.
## The cheapest way to tell teams apart when every character is the same downloaded model.
## Materials are duplicated first, so other instances of the model keep their own colours.
static func tint(model: Node, color: Color) -> void:
	for node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		for surface in mesh_instance.mesh.get_surface_count():
			var material := mesh_instance.get_active_material(surface)
			if material is BaseMaterial3D:
				var copy := material.duplicate() as BaseMaterial3D
				copy.albedo_color = copy.albedo_color * color
				mesh_instance.set_surface_override_material(surface, copy)
