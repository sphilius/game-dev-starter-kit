extends Node2D
## Tactics cell, 2D art: the grid_tactics kit with painted tokens, a stone board and portraits.
##
## Art: assets/portraits/*.png (one AI portrait per unit type), assets/tokens/*.png (cropped
## from the portraits by build.py) and assets/board/tiles.png (one AI floor + a wall made from it).
## Kit: GridModel, EncounterData, TurnManager, TacticsAI, TacticsBot, TacticsPresenter2D.
## The battle plays itself: the bot moves the knights, the kit's AI moves the orcs.

const ASSETS := "res://art_tests/cells/tactics_2d/assets/"
const CELL_PX := 64
const PANEL_COLOR := Color("d8cfb8")

var model: GridModel
var turns: TurnManager
var view: TacticsPresenter2D


## _ready(): build the battle, hand the presenter our art, add the portrait panel, start playing.
func _ready() -> void:
	RenderingServer.set_default_clear_color(Color("20222a"))
	model = _encounter().build_model()
	turns = TurnManager.new(model)
	view = TacticsPresenter2D.new()
	view.cell_size = CELL_PX
	view.tile_set = _tile_set()
	# One token scene serves every unit type: token.gd picks the picture from the unit's id.
	var token := PackedScene.new()
	var token_root := Node2D.new()
	token_root.set_script(load("res://art_tests/cells/tactics_2d/token.gd"))
	token.pack(token_root)                   # pack(): turn a node made in code into a scene
	token_root.free()
	view.unit_scenes = {&"knight": token, &"orc": token}
	view.position = Vector2(64, 104)
	add_child(view)
	view.setup(model)
	_portrait_panel()
	turns.start()
	# Show what a player would see when selecting the first knight: its move range.
	view.show_cells(model.reachable_cells(model.living(0)[0]).keys(), Color(0.3, 0.7, 1.0, 0.35), "move")
	_play()


## The battle loop, same as the kit's demo: bot for team 0, TacticsAI for team 1.
func _play() -> void:
	await get_tree().create_timer(2.5).timeout          # hold the opening position for a moment
	view.clear_highlights("move")
	while not turns.is_over():
		if turns.current_team() == 0:
			TacticsBot.play_turn(model, 0)
		else:
			TacticsAI.take_turn(model, turns.current_team())
		# `await some.signal` pauses this function until the presenter's walk and death
		# tweens are done, while the rest of the game keeps running.
		if view.is_busy():
			await view.animation_finished
		await get_tree().create_timer(0.5).timeout
		turns.end_turn()


## The two-tile TileSet the presenter expects: floor at atlas (0,0), wall at (1,0).
func _tile_set() -> TileSet:
	var source := TileSetAtlasSource.new()
	source.texture = load(ASSETS + "board/tiles.png")
	source.texture_region_size = Vector2i(CELL_PX, CELL_PX)
	source.create_tile(Vector2i(0, 0))
	source.create_tile(Vector2i(1, 0))
	var tile_set := TileSet.new()
	tile_set.tile_size = Vector2i(CELL_PX, CELL_PX)
	tile_set.add_source(source, 0)
	return tile_set


## A parchment panel on the right with each unit type's big portrait and stats.
func _portrait_panel() -> void:
	var panel := ColorRect.new()
	panel.color = PANEL_COLOR
	panel.position = Vector2(672, 72)
	panel.size = Vector2(544, 576)
	add_child(panel)
	var rows := [[&"knight", "Knight Captain", "16 HP   move 3   sword 5", 0],
			[&"orc", "Orc Shaman", "9 HP   move 3   claw 3", 1]]
	for i in rows.size():
		var portrait := TextureRect.new()
		portrait.texture = load(ASSETS + "portraits/%s_00.png" % rows[i][0])
		portrait.position = Vector2(16, 16 + i * 280)
		panel.add_child(portrait)
		var title := Label.new()
		title.text = "%s\n%s" % [rows[i][1], rows[i][2]]
		title.position = Vector2(284, 96 + i * 280)
		title.add_theme_font_size_override(&"font_size", 20)
		title.add_theme_color_override(&"font_color", view.team_colors[rows[i][3]].darkened(0.55))
		panel.add_child(title)


## Two knights against three orcs on an 8x8 board with four wall cells.
func _encounter() -> EncounterData:
	var e := EncounterData.new()
	e.grid_size = Vector2i(8, 8)
	e.blocked = [Vector2i(3, 2), Vector2i(3, 3), Vector2i(4, 5), Vector2i(5, 5)] as Array[Vector2i]
	e.add_spawn(_unit(&"knight", 16, 5), Vector2i(1, 3), 0)
	e.add_spawn(_unit(&"knight", 16, 5), Vector2i(0, 5), 0)
	e.add_spawn(_unit(&"orc", 9, 3), Vector2i(6, 2), 1)
	e.add_spawn(_unit(&"orc", 9, 3), Vector2i(7, 4), 1)
	e.add_spawn(_unit(&"orc", 9, 3), Vector2i(6, 6), 1)
	return e


## Shorthand for a melee UnitData built in code.
func _unit(id: StringName, hp: int, damage: int) -> UnitData:
	var data := UnitData.new()
	data.id = id
	data.max_hp = hp
	data.attack_damage = damage
	return data
