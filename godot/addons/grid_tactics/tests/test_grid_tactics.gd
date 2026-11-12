extends TestCase
## Headless tests for grid_tactics. The rules live in plain data classes (no nodes), so most
## tests here run instantly with no scene at all; only the presenter tests touch the scene tree.


# --- RangeShapes --------------------------------------------------------------------------

## Each shape covers the expected number of cells (the quickest check that the maths is right).
func test_shape_cell_counts() -> void:
	var o := Vector2i(5, 5)
	check_eq(RangeShapes.cells(RangeShapes.Shape.SINGLE, o).size(), 1, "single")
	check_eq(RangeShapes.cells(RangeShapes.Shape.LINE, o, 3).size(), 3, "line of 3")
	check_eq(RangeShapes.cells(RangeShapes.Shape.CROSS, o, 2).size(), 9, "cross radius 2 = 1 + 4×2")
	check_eq(RangeShapes.cells(RangeShapes.Shape.DIAMOND, o, 2).size(), 13, "diamond radius 2")
	check_eq(RangeShapes.cells(RangeShapes.Shape.SQUARE, o, 1).size(), 9, "square radius 1 = 3×3")


## A LINE follows its direction; direction_to() picks the dominant axis toward a target.
func test_line_follows_direction() -> void:
	var line := RangeShapes.cells(RangeShapes.Shape.LINE, Vector2i(2, 2), 3, Vector2i.UP)
	check_eq(line, [Vector2i(2, 2), Vector2i(2, 1), Vector2i(2, 0)] as Array[Vector2i], "line going up")
	check_eq(RangeShapes.direction_to(Vector2i(0, 0), Vector2i(3, 1)), Vector2i.RIGHT, "mostly right")
	check_eq(RangeShapes.direction_to(Vector2i(0, 0), Vector2i(-1, -4)), Vector2i.UP, "mostly up")
	check_eq(RangeShapes.distance(Vector2i(1, 1), Vector2i(4, -1)), 5, "manhattan distance")


# --- helpers ------------------------------------------------------------------------------

## A unit stat sheet built in code (games use .tres files; tests keep everything in one place).
func _unit(id: StringName, hp := 10, move := 3, dmg := 3, rmin := 1, rmax := 1) -> UnitData:
	var d := UnitData.new()
	d.id = id
	d.display_name = String(id)
	d.max_hp = hp
	d.move_range = move
	d.attack_damage = dmg
	d.attack_range_min = rmin
	d.attack_range_max = rmax
	return d


## An ability built in code.
func _ability(id: StringName, dmg: int, cast_range: int, shape: RangeShapes.Shape, radius := 1, cooldown := 2) -> AbilityData:
	var a := AbilityData.new()
	a.id = id
	a.damage = dmg
	a.cast_range = cast_range
	a.shape = shape
	a.radius = radius
	a.cooldown = cooldown
	return a


# --- GridUnit -----------------------------------------------------------------------------

## A new unit starts at full HP, alive, and can use only abilities it owns that are off cooldown.
func test_unit_starts_full_and_tracks_cooldowns() -> void:
	var data := _unit(&"knight", 12)
	var slash := _ability(&"slash", 4, 1, RangeShapes.Shape.SINGLE)
	data.abilities.append(slash)
	var u := GridUnit.new(data, 0, Vector2i(2, 3))
	check_eq(u.hp, 12, "starts at max hp")
	check(u.is_alive(), "alive")
	check(u.can_use(slash), "owned ability is usable")
	u.cooldowns[slash.id] = 2
	check(not u.can_use(slash), "not while on cooldown")
	check(not u.can_use(_ability(&"other", 1, 1, RangeShapes.Shape.SINGLE)), "not an ability it does not own")


# --- GridModel: board and movement --------------------------------------------------------

## Units cannot be placed on walls, on each other, or off the board.
func test_model_placement_rules() -> void:
	var m := GridModel.new(Vector2i(4, 4))
	m.set_blocked(Vector2i(1, 1))
	check(m.add_unit(_unit(&"a"), 0, Vector2i(0, 0)) != null, "free cell accepts a unit")
	check(m.add_unit(_unit(&"b"), 0, Vector2i(0, 0)) == null, "occupied cell refuses")
	check(m.add_unit(_unit(&"c"), 0, Vector2i(1, 1)) == null, "wall refuses")
	check(m.add_unit(_unit(&"d"), 0, Vector2i(9, 9)) == null, "off-board refuses")
	check_eq(m.living().size(), 1, "one unit on the board")


## Reachable cells respect move_range, walls and other units.
func test_model_reachable_respects_range_and_obstacles() -> void:
	var m := GridModel.new(Vector2i(7, 7))
	var u := m.add_unit(_unit(&"scout", 10, 2), 0, Vector2i(3, 3))
	check_eq(m.reachable_cells(u).size(), 13, "open board, move 2 = diamond of 13")
	m.set_blocked(Vector2i(4, 3))                       # wall to the right
	m.add_unit(_unit(&"foe"), 1, Vector2i(3, 2))        # enemy above
	var reach := m.reachable_cells(u)
	check(not reach.has(Vector2i(4, 3)), "cannot stand in a wall")
	check(not reach.has(Vector2i(5, 3)), "cannot pass through the wall in a straight line")
	check(not reach.has(Vector2i(3, 2)), "cannot stand on another unit")
	check(not reach.has(Vector2i(3, 1)), "cannot pass through another unit")
	check(reach.has(Vector2i(4, 4)), "can still go around diagonally in 2 steps")


## Paths go around walls (AStarGrid2D), and a walled-off target has no path.
func test_model_path_goes_around_walls() -> void:
	var m := GridModel.new(Vector2i(5, 5))
	for y in 4:
		m.set_blocked(Vector2i(2, y))                   # a wall with a gap at the bottom row
	var path := m.find_path(Vector2i(0, 0), Vector2i(4, 0))
	check_eq(path.size(), 13, "detour through the gap: 12 steps + the start cell")
	check(path.has(Vector2i(2, 4)), "path uses the gap")
	m.set_blocked(Vector2i(2, 4))
	check(m.find_path(Vector2i(0, 0), Vector2i(4, 0)).is_empty(), "no path when sealed")


## A move updates the cell, emits the walked path, and is allowed once per turn.
func test_model_move_emits_path_once_per_turn() -> void:
	var m := GridModel.new(Vector2i(6, 6))
	var u := m.add_unit(_unit(&"scout", 10, 3), 0, Vector2i(0, 0))
	var seen: Array = []
	m.unit_moved.connect(func(_unit: GridUnit, path: Array[Vector2i]) -> void: seen.append(path))
	check(not m.move_unit(u, Vector2i(5, 5)), "too far is refused")
	check(m.move_unit(u, Vector2i(2, 1)), "legal move accepted")
	check_eq(u.cell, Vector2i(2, 1), "unit cell updated")
	check_eq(seen.size(), 1, "unit_moved emitted once")
	check_eq(seen[0].size(), 4, "path has start + 3 steps")
	check(not m.move_unit(u, Vector2i(2, 2)), "second move in the same turn refused")


# --- GridModel: combat --------------------------------------------------------------------

## Melee reaches adjacent cells only; an archer (range 2..3) cannot hit an adjacent enemy.
func test_model_attack_ranges() -> void:
	var m := GridModel.new(Vector2i(8, 3))
	var knight := m.add_unit(_unit(&"knight", 10, 3, 4), 0, Vector2i(0, 1))
	var archer := m.add_unit(_unit(&"archer", 8, 3, 3, 2, 3), 0, Vector2i(1, 0))
	var near := m.add_unit(_unit(&"near"), 1, Vector2i(1, 1))
	var far := m.add_unit(_unit(&"far"), 1, Vector2i(3, 0))
	check(not m.attack(knight, far.cell), "melee cannot reach 3 away")
	check(m.attack(knight, near.cell), "melee hits adjacent")
	check_eq(near.hp, 6, "10 - 4")
	check(not m.attack(knight, near.cell), "one action per turn")
	check(not m.attack(archer, Vector2i(0, 1)), "no attacking your own team")
	check(not m.attack(archer, near.cell), "archer cannot hit inside minimum range")
	check(m.attack(archer, far.cell), "archer hits at range 2")


## Death: HP stops at 0, unit_died fires once, the cell becomes free.
func test_model_death_frees_cell() -> void:
	var m := GridModel.new(Vector2i(4, 4))
	var brute := m.add_unit(_unit(&"brute", 10, 3, 99), 0, Vector2i(0, 0))
	var victim := m.add_unit(_unit(&"victim", 5), 1, Vector2i(1, 0))
	var deaths := [0]
	m.unit_died.connect(func(_u: GridUnit) -> void: deaths[0] += 1)
	m.attack(brute, victim.cell)
	check_eq(victim.hp, 0, "hp floors at 0")
	check_eq(deaths[0], 1, "unit_died emitted once")
	check(m.unit_at(Vector2i(1, 0)) == null and m.is_free(Vector2i(1, 0)), "cell is free again")
	check_eq(m.teams_alive(), [0] as Array[int], "only team 0 remains")


## An area ability hits every enemy in its shape, spares allies, and goes on cooldown.
func test_model_area_ability_and_cooldown() -> void:
	var m := GridModel.new(Vector2i(7, 7))
	var blast := _ability(&"blast", 4, 4, RangeShapes.Shape.CROSS, 1, 2)
	var mage_data := _unit(&"mage")
	mage_data.abilities.append(blast)
	var mage := m.add_unit(mage_data, 0, Vector2i(0, 3))
	var ally := m.add_unit(_unit(&"ally"), 0, Vector2i(3, 2))
	var e1 := m.add_unit(_unit(&"e1"), 1, Vector2i(3, 3))
	var e2 := m.add_unit(_unit(&"e2"), 1, Vector2i(4, 3))
	var e3 := m.add_unit(_unit(&"e3"), 1, Vector2i(6, 6))
	check(not m.use_ability(mage, blast, Vector2i(6, 3)), "target beyond cast_range refused")
	check(m.use_ability(mage, blast, Vector2i(3, 3)), "cast accepted")
	check_eq([e1.hp, e2.hp, e3.hp], [6, 6, 10], "two enemies in the cross hit, one outside spared")
	check_eq(ally.hp, 10, "ally inside the area spared (friendly_fire off)")
	mage.has_acted = false
	check(not m.use_ability(mage, blast, Vector2i(3, 3)), "on cooldown")


## A heal (negative damage) restores allies only and never exceeds max HP.
func test_model_heal_targets_allies_only() -> void:
	var m := GridModel.new(Vector2i(5, 5))
	var heal := _ability(&"heal", -5, 3, RangeShapes.Shape.DIAMOND, 1, 0)
	var cleric_data := _unit(&"cleric")
	cleric_data.abilities.append(heal)
	var cleric := m.add_unit(cleric_data, 0, Vector2i(0, 0))
	var hurt := m.add_unit(_unit(&"hurt"), 0, Vector2i(2, 1))
	var foe := m.add_unit(_unit(&"foe"), 1, Vector2i(2, 2))
	hurt.hp = 7
	foe.hp = 4
	m.use_ability(cleric, heal, Vector2i(2, 1))
	check_eq(hurt.hp, 10, "healed, capped at max")
	check_eq(foe.hp, 4, "enemy in the area not healed")


## Telegraphed attacks: danger_cells() reports them, damage_cells() resolves them on whoever is there.
func test_model_intents_and_danger() -> void:
	var m := GridModel.new(Vector2i(5, 5))
	var ogre := m.add_unit(_unit(&"ogre", 10, 2, 6), 1, Vector2i(2, 2))
	var hero := m.add_unit(_unit(&"hero"), 0, Vector2i(2, 3))
	var cells: Array[Vector2i] = [Vector2i(2, 3), Vector2i(2, 4)]
	m.set_intent(ogre, cells, 6)
	check_eq(m.danger_cells(0), {Vector2i(2, 3): 6, Vector2i(2, 4): 6}, "danger map for the hero's team")
	check(m.danger_cells(1).is_empty(), "the ogre's own team is not in danger from it")
	hero.cell = Vector2i(3, 3)                          # the hero steps out
	m.damage_cells(ogre.intent.cells, ogre.intent.damage, ogre)
	check_eq(hero.hp, 10, "dodged the telegraphed attack")


# --- TurnManager --------------------------------------------------------------------------

## Turns alternate, the round counter goes up when the order wraps, flags reset, cooldowns tick.
func test_turns_alternate_and_refresh_units() -> void:
	var m := GridModel.new(Vector2i(6, 6))
	var zap := _ability(&"zap", 1, 12, RangeShapes.Shape.SINGLE, 1, 2)
	var hero_data := _unit(&"hero", 10, 3, 1)
	hero_data.abilities.append(zap)
	var hero := m.add_unit(hero_data, 0, Vector2i(0, 0))
	m.add_unit(_unit(&"foe", 10), 1, Vector2i(5, 5))
	var tm := TurnManager.new(m)
	var log: Array[String] = []
	tm.turn_started.connect(func(team: int, r: int) -> void: log.append("t%d r%d" % [team, r]))
	tm.start()
	m.move_unit(hero, Vector2i(1, 0))
	m.use_ability(hero, zap, Vector2i(5, 5))
	check(hero.has_moved and hero.has_acted, "hero spent its turn")
	tm.end_turn()                                       # -> team 1
	tm.end_turn()                                       # -> team 0, round 2
	check_eq(log, ["t0 r1", "t1 r1", "t0 r2"] as Array[String], "turn order and rounds")
	check(not hero.has_moved and not hero.has_acted, "flags reset on the hero's new turn")
	check(not hero.can_use(zap), "cooldown 2: still unavailable on the next turn")
	tm.end_turn()
	tm.end_turn()                                       # hero's third turn
	check(not hero.can_use(zap), "cooldown 2: unavailable for two of the owner's turns")
	tm.end_turn()
	tm.end_turn()
	check(hero.can_use(zap), "available again after the cooldown")


## The battle ends, once, when one team is left; end_turn() then does nothing.
func test_battle_ends_when_one_team_left() -> void:
	var m := GridModel.new(Vector2i(4, 4))
	var hero := m.add_unit(_unit(&"hero", 10, 3, 99), 0, Vector2i(0, 0))
	m.add_unit(_unit(&"foe", 5), 1, Vector2i(1, 0))
	var tm := TurnManager.new(m)
	var winners: Array[int] = []
	tm.battle_ended.connect(func(w: int) -> void: winners.append(w))
	tm.start()
	m.attack(hero, Vector2i(1, 0))
	check(tm.check_winner(), "battle over after the kill")
	tm.end_turn()
	check_eq(winners, [0] as Array[int], "battle_ended emitted once, team 0 wins")
	check(tm.is_over(), "is_over")


# --- TacticsAI ----------------------------------------------------------------------------

## The AI walks toward the nearest enemy; out of range it plans no attack.
func test_ai_approaches_when_out_of_range() -> void:
	var m := GridModel.new(Vector2i(10, 3))
	var hero := m.add_unit(_unit(&"hero"), 0, Vector2i(0, 1))
	var orc := m.add_unit(_unit(&"orc", 10, 3, 4), 1, Vector2i(9, 1))
	TacticsAI.take_turn(m, 1)
	check_eq(orc.cell, Vector2i(6, 1), "moved 3 cells straight at the hero")
	check(orc.intent.is_empty(), "no telegraph while out of range")
	check_eq(hero.hp, 10, "no damage yet")


## In range, the AI telegraphs first and the hit lands on its NEXT turn (so it can be dodged).
func test_ai_telegraphs_then_strikes_next_turn() -> void:
	var m := GridModel.new(Vector2i(6, 3))
	var hero := m.add_unit(_unit(&"hero"), 0, Vector2i(0, 1))
	var orc := m.add_unit(_unit(&"orc", 10, 3, 4), 1, Vector2i(3, 1))
	TacticsAI.take_turn(m, 1)
	check_eq(orc.cell, Vector2i(1, 1), "stepped adjacent")
	check_eq(orc.intent.get("cells"), [Vector2i(0, 1)] as Array[Vector2i], "telegraphs the hero's cell")
	check_eq(hero.hp, 10, "the telegraph itself does no damage")
	TacticsAI.take_turn(m, 1)                           # hero stayed put
	check_eq(hero.hp, 6, "the telegraphed hit lands on the next enemy turn")


## Stepping out of the marked cell dodges; killing the attacker cancels its telegraph.
func test_ai_telegraph_can_be_dodged_or_cancelled() -> void:
	var m := GridModel.new(Vector2i(6, 3))
	var hero := m.add_unit(_unit(&"hero", 10, 3, 99), 0, Vector2i(0, 1))
	var orc := m.add_unit(_unit(&"orc", 10, 1, 4), 1, Vector2i(1, 1))
	TacticsAI.take_turn(m, 1)
	check(not orc.intent.is_empty(), "attack telegraphed")
	hero.cell = Vector2i(0, 0)                          # the player steps aside
	TacticsAI.resolve_intents(m, 1)
	check_eq(hero.hp, 10, "dodged")
	TacticsAI.act(m, orc)                               # it aims again
	check(not m.danger_cells(0).is_empty(), "new telegraph on the hero")
	m.attack(hero, orc.cell)                            # kill it first
	check(m.danger_cells(0).is_empty(), "a dead unit's telegraph is cancelled")


## A ranged AI unit stops as soon as it can shoot instead of walking into melee.
func test_ai_ranged_unit_keeps_distance() -> void:
	var m := GridModel.new(Vector2i(10, 3))
	m.add_unit(_unit(&"hero"), 0, Vector2i(0, 1))
	var archer := m.add_unit(_unit(&"archer", 6, 4, 3, 2, 4), 1, Vector2i(7, 1))
	TacticsAI.take_turn(m, 1)
	check_eq(archer.cell, Vector2i(4, 1), "stopped at max range (4), walking only 3 of its 4 steps")
	check(not archer.intent.is_empty(), "and telegraphed a shot")


# --- EncounterData and TacticsBot ---------------------------------------------------------

## A fair fight used by several tests: two heroes (one with a ranged ability) against two orcs,
## with a short wall in the middle of an 8×6 board.
func _fair_encounter() -> EncounterData:
	var e := EncounterData.new()
	e.id = &"fair"
	e.grid_size = Vector2i(8, 6)
	e.blocked = [Vector2i(4, 2), Vector2i(4, 3)] as Array[Vector2i]
	var mage := _unit(&"mage", 8, 3, 2, 1, 2)
	mage.abilities.append(_ability(&"bolt", 4, 4, RangeShapes.Shape.SINGLE, 1, 1))
	e.add_spawn(_unit(&"knight", 14, 3, 4), Vector2i(0, 2), 0)
	e.add_spawn(mage, Vector2i(0, 3), 0)
	e.add_spawn(_unit(&"orc", 9, 3, 3), Vector2i(7, 2), 1)
	e.add_spawn(_unit(&"orc", 9, 3, 3), Vector2i(7, 3), 1)
	return e


## build_model() places walls and units; every call gives an independent fresh board.
func test_encounter_builds_fresh_models() -> void:
	var e := _fair_encounter()
	var a := e.build_model()
	var b := e.build_model()
	check_eq(a.living(0).size(), 2, "two heroes")
	check_eq(a.living(1).size(), 2, "two orcs")
	check(a.is_blocked(Vector2i(4, 2)), "wall placed")
	a.apply_damage(a.living(0)[0], 99)
	check_eq(b.living(0).size(), 2, "a second model is unaffected by the first")
	check_eq(e.teams(), [0, 1] as Array[int], "teams sorted, player first")


## A spawn on a wall is a design mistake: build_model() reports it loudly.
func test_encounter_reports_bad_spawn() -> void:
	expect_error("spawn 0 at (1, 1) is off-board, in a wall, or occupied")
	var e := EncounterData.new()
	e.grid_size = Vector2i(3, 3)
	e.blocked = [Vector2i(1, 1)] as Array[Vector2i]
	e.add_spawn(_unit(&"lost"), Vector2i(1, 1), 0)
	check_eq(e.build_model().living().size(), 0, "the bad spawn is not placed")


## The headline feature: the bot wins the fair fight, which PROVES it is winnable.
func test_bot_proves_fair_encounter_winnable() -> void:
	var result := TacticsBot.simulate(_fair_encounter())
	check(result.won, "bot won: %s" % result)
	check(result.rounds <= 20, "and did not need a stalemate-length battle (%d rounds)" % result.rounds)
	check(result.survivors >= 1, "with a survivor")


## Same setup, same result every time: no hidden randomness, so a CI pass is trustworthy.
func test_bot_is_deterministic() -> void:
	var first := TacticsBot.simulate(_fair_encounter())
	var second := TacticsBot.simulate(_fair_encounter())
	check_eq(first, second, "two runs of the same encounter")


## A lopsided fight is flagged (won = false) and the simulation still ends.
func test_bot_flags_lopsided_encounter() -> void:
	var e := EncounterData.new()
	e.grid_size = Vector2i(6, 6)
	e.add_spawn(_unit(&"peasant", 4, 2, 1), Vector2i(0, 0), 0)
	for i in 3:
		e.add_spawn(_unit(&"ogre", 30, 4, 6), Vector2i(5, i), 1)
	var result := TacticsBot.simulate(e)
	check(not result.won, "bot cannot win 1 peasant vs 3 ogres: %s" % result)
	check_eq(result.winner, 1, "the ogres win outright")


## Two units that cannot reach each other: the round cap ends the simulation as a stalemate.
func test_bot_stops_at_round_cap() -> void:
	var e := EncounterData.new()
	e.grid_size = Vector2i(5, 1)
	e.blocked = [Vector2i(2, 0)] as Array[Vector2i]     # a wall splits the corridor
	e.add_spawn(_unit(&"a"), Vector2i(0, 0), 0)
	e.add_spawn(_unit(&"b"), Vector2i(4, 0), 1)
	var result := TacticsBot.simulate(e, 10)
	check(not result.won, "no winner")
	check_eq(result.winner, -2, "-2 marks 'ran out of rounds'")


## The bot reads telegraphs: it steps out of a marked cell when staying would cost HP for nothing.
func test_bot_dodges_telegraphed_cell() -> void:
	var m := GridModel.new(Vector2i(5, 5))
	var hero := m.add_unit(_unit(&"hero", 10, 2, 3), 0, Vector2i(2, 2))
	var archer := m.add_unit(_unit(&"archer", 50, 0, 6, 2, 4), 1, Vector2i(2, 0))
	var marked: Array[Vector2i] = [Vector2i(2, 2)]
	m.set_intent(archer, marked, 6)
	TacticsBot.play_unit(m, hero)
	check(hero.cell != Vector2i(2, 2), "left the marked cell (now at %s)" % hero.cell)
	check(not m.danger_cells(0).has(hero.cell), "and is standing somewhere safe")


## verify_folder() checks every saved encounter under a folder: the call a jam project puts in CI.
func test_bot_verifies_a_folder_of_encounters() -> void:
	var dir := "user://kit_test_encounters"
	DirAccess.make_dir_recursive_absolute(dir)
	ResourceSaver.save(_fair_encounter(), dir + "/fair.tres")
	var results := TacticsBot.verify_folder(dir)
	check_eq(results.size(), 1, "one encounter found")
	check(results[dir + "/fair.tres"].won, "and proven winnable from its saved file")
	DirAccess.remove_absolute(dir + "/fair.tres")
	DirAccess.remove_absolute(dir)


# --- Presenters ---------------------------------------------------------------------------

## A small board with one wall, one hero and one orc, shared by the presenter tests.
func _presenter_model() -> GridModel:
	var m := GridModel.new(Vector2i(5, 4))
	m.set_blocked(Vector2i(2, 2))
	m.add_unit(_unit(&"hero", 10, 3, 99), 0, Vector2i(0, 0))
	m.add_unit(_unit(&"orc", 6), 1, Vector2i(4, 3))
	return m


## 2D: tiles match the model (floor vs wall) and each unit gets a node at its cell centre.
func test_presenter_2d_builds_board_and_units() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter2D.new()) as TacticsPresenter2D
	view.setup(m)
	check_eq(view.tiles.get_used_cells().size(), 20, "one tile per cell (5×4)")
	check_eq(view.tiles.get_cell_atlas_coords(Vector2i(2, 2)), Vector2i(1, 0), "wall tile on the blocked cell")
	check_eq(view.tiles.get_cell_atlas_coords(Vector2i(0, 0)), Vector2i(0, 0), "floor tile elsewhere")
	check_eq(view.unit_nodes.size(), 2, "one node per unit")
	var hero := m.living(0)[0]
	check_eq((view.unit_nodes[hero] as Node2D).position, Vector2(32, 32), "hero drawn at its cell centre")
	check_eq(view.world_to_cell(view.cell_to_world(Vector2i(3, 2))), Vector2i(3, 2), "cell <-> world round trip")


## 2D: a model move becomes a tween that ends on the destination; death removes the node.
func test_presenter_2d_animates_moves_and_deaths() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter2D.new()) as TacticsPresenter2D
	view.move_seconds_per_cell = 0.02
	view.setup(m)
	var hero := m.living(0)[0]
	var orc := m.living(1)[0]
	var hero_node := view.unit_nodes[hero] as Node2D
	m.move_unit(hero, Vector2i(2, 1))
	check(view.is_busy(), "busy while the move animates")
	check(await wait_until(func() -> bool: return not view.is_busy(), 2.0), "animation finishes")
	check_eq(hero_node.position, view.cell_to_world(Vector2i(2, 1)), "node ended on the destination cell")
	m.apply_damage(orc, 99, hero)
	check(not view.unit_nodes.has(orc), "dead unit no longer tracked")
	check(await wait_until(func() -> bool: return not view.is_busy(), 2.0), "death fade finishes")
	check_eq(view.unit_nodes.size(), 1, "only the hero remains on screen")


## 2D: units added after setup() appear too, and setup() can be called again for a new battle.
func test_presenter_2d_follows_later_spawns_and_resets() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter2D.new()) as TacticsPresenter2D
	view.setup(m)
	m.add_unit(_unit(&"late"), 1, Vector2i(4, 0))
	check_eq(view.unit_nodes.size(), 3, "reinforcement got a node")
	view.setup(_presenter_model())
	check_eq(view.unit_nodes.size(), 2, "second setup starts clean")
	m.add_unit(_unit(&"ghost"), 1, Vector2i(3, 0))
	check_eq(view.unit_nodes.size(), 2, "the old model no longer drives this presenter")


## 3D: one tile mesh per cell, walls are tall, units stand on the ground plane at their cell.
func test_presenter_3d_builds_board_and_units() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter3D.new()) as TacticsPresenter3D
	view.setup(m)
	check_eq(view.tile_nodes.size(), 20, "one tile per cell")
	var wall := view.tile_nodes[Vector2i(2, 2)] as MeshInstance3D
	var floor_tile := view.tile_nodes[Vector2i(0, 0)] as MeshInstance3D
	check(wall.mesh.get_aabb().size.y > floor_tile.mesh.get_aabb().size.y * 5.0, "walls are much taller than floor slabs")
	var hero := m.living(0)[0]
	check_eq((view.unit_nodes[hero] as Node3D).position, Vector3(0.5, 0.0, 0.5), "hero on the ground at its cell centre")
	check_eq(view.world_to_cell(view.cell_to_world(Vector2i(4, 1))), Vector2i(4, 1), "cell <-> world round trip")


## 3D: moves tween to the destination and turn the unit to face its last step; deaths remove it.
func test_presenter_3d_animates_moves_and_deaths() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter3D.new()) as TacticsPresenter3D
	view.move_seconds_per_cell = 0.02
	view.setup(m)
	var hero := m.living(0)[0]
	var orc := m.living(1)[0]
	var hero_node := view.unit_nodes[hero] as Node3D
	m.move_unit(hero, Vector2i(3, 0))                   # three steps along +X
	check(await wait_until(func() -> bool: return not view.is_busy(), 2.0), "animation finishes")
	check_near(hero_node.position, view.cell_to_world(Vector2i(3, 0)), 0.001, "node ended on the destination")
	check_near(hero_node.rotation.y, -PI / 2.0, 0.001, "facing +X after walking along +X")
	m.apply_damage(orc, 99, hero)
	check(await wait_until(func() -> bool: return not view.is_busy(), 2.0), "death animation finishes")
	check_eq(view.unit_nodes.size(), 1, "only the hero remains")


## 3D: telegraphed cells and range highlights tint tiles; clearing restores them.
func test_presenter_3d_tints_danger_and_ranges() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter3D.new()) as TacticsPresenter3D
	view.setup(m)
	var orc := m.living(1)[0]
	var marked: Array[Vector2i] = [Vector2i(1, 1)]
	m.set_intent(orc, marked, 3)
	var danger_tile := view.tile_nodes[Vector2i(1, 1)] as MeshInstance3D
	check(danger_tile.material_override != null, "telegraphed cell is tinted")
	view.show_cells([Vector2i(0, 1), Vector2i(1, 1)], Color.CYAN)
	check((view.tile_nodes[Vector2i(0, 1)] as MeshInstance3D).material_override != null, "range cell is tinted")
	check_eq((danger_tile.material_override as StandardMaterial3D).albedo_color, Color(1.0, 0.2, 0.15), "danger colour wins over range colour")
	m.set_intent(orc)
	view.clear_highlights()
	check(danger_tile.material_override == null, "tints removed")


## 3D picking: a camera looking straight down maps the screen centre to the cell beneath it.
func test_presenter_3d_picks_cell_under_screen_point() -> void:
	var m := _presenter_model()
	var view := add_node(TacticsPresenter3D.new()) as TacticsPresenter3D
	view.setup(m)
	var camera := add_node(Camera3D.new()) as Camera3D
	camera.position = Vector3(3.5, 10.0, 1.5)           # directly above cell (3, 1)
	camera.rotation.x = -PI / 2.0                       # look straight down
	await tree.process_frame
	var centre := Vector2(tree.root.get_visible_rect().size) * 0.5
	check_eq(view.cell_at_screen(camera, centre), Vector2i(3, 1), "screen centre -> cell under the camera")
	camera.position = Vector3(50.0, 10.0, 50.0)
	check_eq(view.cell_at_screen(camera, centre), Vector2i(-1, -1), "off the board -> (-1, -1)")
