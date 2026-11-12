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
