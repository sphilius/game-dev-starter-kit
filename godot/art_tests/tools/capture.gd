extends SceneTree
## Renders a scene for a moment and saves a PNG screenshot, then quits.
##
##   godot --path . --script res://art_tests/tools/capture.gd -- --scene=res://scenes/demos/tactics_demo.tscn --out=C:/tmp/shot.png [--frames=60] [--size=1280x720]
##
## IMPORTANT: do NOT pass --headless. Headless Godot uses a dummy renderer that draws nothing,
## so screenshots come out empty. This needs a real (short-lived) window. In CI on Linux, wrap
## it:  xvfb-run -a godot --rendering-driver opengl3 --path . --script ... (a virtual display).
##
## --frames is how many frames to let the scene run first (tweens, physics settling, shaders
## compiling). Exits 1 if the scene fails to load or the image cannot be saved.


## _initialize() is a SceneTree script's entry point. It only parses options and starts _run().
func _initialize() -> void:
	_run.call_deferred()


## Loads the scene, waits, grabs the window's pixels, saves them.
func _run() -> void:
	var opts := {"scene": "", "out": "", "frames": "60", "size": "1280x720"}
	for arg in OS.get_cmdline_user_args():
		for key: String in opts:
			if arg.begins_with("--%s=" % key):
				opts[key] = arg.trim_prefix("--%s=" % key)
	var packed := load(opts.scene) as PackedScene
	if packed == null or opts.out == "":
		printerr("capture: need --scene=<res://...tscn> and --out=<file.png>")
		quit(1)
		return
	var size_parts: PackedStringArray = opts.size.split("x")
	root.size = Vector2i(int(size_parts[0]), int(size_parts[1]))
	var scene := packed.instantiate()
	root.add_child(scene)
	current_scene = scene                   # so code using get_tree().current_scene works
	for i in int(opts.frames):
		await process_frame
	# Wait until the frame is fully drawn before reading the pixels back from the GPU.
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(String(opts.out).get_base_dir())
	var error := image.save_png(opts.out)
	print("[capture] %s -> %s (%dx%d) %s" % [opts.scene, opts.out, image.get_width(), image.get_height(),
			"ok" if error == OK else "FAILED %d" % error])
	quit(0 if error == OK else 1)
