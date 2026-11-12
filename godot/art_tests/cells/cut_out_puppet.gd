extends Node2D
## A cut-out puppet: separate body-part pictures pinned together with Bone2D joints.
## Shared by the fighter_2d and platformer_2d cells (not part of any kit). Usage:
##
##     const Puppet := preload("res://art_tests/cells/cut_out_puppet.gd")
##     var boxer := Puppet.new()
##     add_child(boxer)
##     boxer.build("res://art_tests/cells/fighter_2d/assets/boxer/")
##     boxer.pose({"upper_arm": -85.0, "forearm": -5.0}, 0.08)      # a jab, in degrees
##
## build() reads rig.json from the folder (written by the cell's build.py):
##     { "torso": {"parent": "", "pivot": [0.5, 0.95], "attach": [0, 0], "size": [w, h]}, ... }
##   pivot   where the part rotates, as a fraction of its own picture (0,0 = top-left)
##   attach  where that pivot sits on the PARENT's picture, as a fraction of the parent's size
##   back    optional true: also make a darker copy behind the body (the far arm, the far leg)
##   scale   optional number: draw this part larger or smaller
## An angle of 0 is the pose the part was drawn in. Positive angles turn clockwise.

## Tint of the far-side limbs, so the two arms read as near and far.
@export var back_tint := Color(0.62, 0.62, 0.72)

## Part name -> its Bone2D. Far-side copies are stored as "<name>_b".
var bones := {}
var rig := {}
var _skeleton: Skeleton2D


## Builds the bones and sprites from <folder>/rig.json and <folder>/<part>.png.
func build(folder: String) -> void:
	rig = JSON.parse_string(FileAccess.get_file_as_string(folder + "rig.json"))
	_skeleton = Skeleton2D.new()
	add_child(_skeleton)
	# Far-side limbs first, so they are created (and drawn) before the body covers them.
	for part: String in rig:
		if rig[part].get("back", false):
			_add_part(folder, part, "_b")
	for part: String in rig:
		_add_part(folder, part, "")


## Total height from the root joint down to the soles: the leg chain's lengths added up.
## Use it to stand the puppet on a floor: puppet.position.y = floor_y - leg_length().
func leg_length() -> float:
	var total := 0.0
	for part: String in ["thigh", "shin", "leg"]:
		if rig.has(part):
			var entry: Dictionary = rig[part]
			total += float(entry.size[1]) * float(entry.get("scale", 1.0)) * (1.0 - float(entry.pivot[1]))
	return total


## Turns joints to the given angles (degrees) over `seconds`. Parts not named keep their angle.
## Far-side limbs are named with "_b": {"upper_arm": -50, "upper_arm_b": -20}.
func pose(angles: Dictionary, seconds := 0.15) -> Tween:
	var tween := create_tween().set_parallel(true)          # all joints move at the same time
	tween.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	for part: String in angles:
		if bones.has(part):
			tween.tween_property(bones[part], ^"rotation_degrees", float(angles[part]), seconds)
	return tween


## Creates one bone with its picture. `suffix` is "" for the near side and "_b" for the far side.
func _add_part(folder: String, part: String, suffix: String) -> void:
	var entry: Dictionary = rig[part]
	var parent_name: String = entry.parent
	var bone := Bone2D.new()
	bone.name = part + suffix
	# A far-side forearm hangs from the far-side upper arm; a far-side upper arm from the torso.
	var parent_bone: Node2D = bones.get(parent_name + suffix, bones.get(parent_name, _skeleton))
	if parent_name != "" and rig.has(parent_name):
		var parent: Dictionary = rig[parent_name]
		# JSON values have no fixed type, so the types are written out (": Vector2", "float(...)").
		var parent_size: Vector2 = Vector2(parent.size[0], parent.size[1]) * float(parent.get("scale", 1.0))
		# The parent's bone sits at the parent's pivot, so measure the attach point from there.
		bone.position = (Vector2(entry.attach[0], entry.attach[1]) - Vector2(parent.pivot[0], parent.pivot[1])) * parent_size
	parent_bone.add_child(bone)
	bone.rest = bone.transform                    # the "zero" pose Skeleton2D returns to
	bone.set_autocalculate_length_and_angle(false)
	bone.set_length(float(entry.size[1]) * 0.8)

	var sprite := Sprite2D.new()
	sprite.texture = load(folder + part + ".png")
	sprite.centered = false
	var part_scale := float(entry.get("scale", 1.0))
	sprite.scale = Vector2.ONE * part_scale
	# Shift the picture so its pivot point lands exactly on the bone.
	sprite.position = -Vector2(entry.pivot[0], entry.pivot[1]) * Vector2(entry.size[0], entry.size[1]) * part_scale
	if suffix == "_b":
		sprite.modulate = back_tint
		sprite.show_behind_parent = true          # draw under whatever this bone hangs from
	bone.add_child(sprite)
	bones[part + suffix] = bone
