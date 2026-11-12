extends Node2D
## One board piece for TacticsPresenter2D: the unit's token picture with its HP underneath.
## The presenter calls set_unit() once, then on_unit_damaged() / on_unit_died() if they exist.
## (The presenter already flashes and fades the node itself; this only keeps the number right.)

const TOKENS := "res://art_tests/cells/tactics_2d/assets/tokens/"

var unit: GridUnit
var hp_label: Label


## Called by the presenter right after the token is added to the board.
func set_unit(p_unit: GridUnit) -> void:
	unit = p_unit
	var sprite := Sprite2D.new()
	# unit.data.id is the unit type ("knight", "orc"): the token file has the same name.
	sprite.texture = load(TOKENS + "%s.png" % unit.data.id)
	add_child(sprite)
	hp_label = Label.new()
	hp_label.add_theme_font_size_override(&"font_size", 13)
	hp_label.add_theme_color_override(&"font_outline_color", Color.BLACK)
	hp_label.add_theme_constant_override(&"outline_size", 5)
	hp_label.position = Vector2(8, 10)             # lower right corner of the token
	add_child(hp_label)
	_refresh()


## Called by the presenter whenever this unit's HP changes.
func on_unit_damaged(_amount: int) -> void:
	_refresh()


## Shows the current HP number.
func _refresh() -> void:
	hp_label.text = str(unit.hp)
