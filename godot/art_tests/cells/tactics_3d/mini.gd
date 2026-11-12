extends Node3D
## One board piece for TacticsPresenter3D: a static model on a team-coloured base, HP above it.
## The presenter calls set_unit() once, then on_unit_damaged() whenever the HP changes.
## No skeleton, no clips: the presenter's own slide, flash and fade are the animation.

const ASSETS := "res://art_tests/cells/tactics_3d/assets/"
## Unit id -> [model path, scale, height above the base]. The drone hovers.
const MODELS := {
	&"hero": ["hero/character.glb", 0.85, 0.06],
	&"drone": ["drone/enemy-flying.glb", 0.72, 0.4],
}
const TEAM_COLORS: Array[Color] = [Color(0.3, 0.6, 1.0), Color(1.0, 0.36, 0.3)]

var unit: GridUnit
var hp_label: Label3D


## Called by the presenter right after the piece is added to the board.
func set_unit(p_unit: GridUnit) -> void:
	unit = p_unit
	var spec: Array = MODELS[unit.data.id]
	var model: Node3D = (load(ASSETS + spec[0]) as PackedScene).instantiate()
	model.scale = Vector3.ONE * spec[1]
	model.position.y = spec[2]
	# Team 0 faces +X (toward the enemy side of the board), team 1 faces back at them.
	model.rotation_degrees.y = 90.0 if unit.team == 0 else -90.0
	add_child(model)

	# The base: a flat disc in the team colour, like a painted miniature's stand.
	var disc := CylinderMesh.new()
	disc.top_radius = 0.38
	disc.bottom_radius = 0.42
	disc.height = 0.06
	var paint := StandardMaterial3D.new()
	paint.albedo_color = TEAM_COLORS[unit.team % TEAM_COLORS.size()]
	disc.material = paint
	var base := MeshInstance3D.new()
	base.mesh = disc
	base.position.y = 0.03
	add_child(base)

	hp_label = Label3D.new()
	hp_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED       # always turned toward the camera
	hp_label.no_depth_test = true                               # never hidden behind a model
	hp_label.font_size = 56
	hp_label.outline_size = 14
	hp_label.pixel_size = 0.004
	hp_label.position.y = 1.35
	add_child(hp_label)
	_refresh()


## Called by the presenter whenever this unit's HP changes.
func on_unit_damaged(_amount: int) -> void:
	_refresh()


## Shows the current HP number.
func _refresh() -> void:
	hp_label.text = str(unit.hp)
