# TacticsBot: plays the PLAYER's side by itself, to prove an encounter can be won.
class_name TacticsBot
extends RefCounted
## Why: in a jam there is no time to playtest every fight after every stat tweak. If this bot
## (which plays simply) wins, a winning line exists, so the encounter is not broken. Run it in
## tests and CI over every EncounterData.
##
## What a result means:
##   won = true   PROOF the encounter is winnable (here is a way to do it).
##   won = false  NOT proof it is impossible: the bot is no genius. Treat it as "review this
##                fight": it is at least hard, and may be unfair.
##
## How it plays, per unit: look at every cell it can reach and every attack or ability it could
## use from there; score = damage dealt (+ a big bonus for a kill, + healing) minus the damage
## telegraphed on that cell, with a small pull toward the enemy; do the best one. It reads
## enemy telegraphs exactly like a human player would.

const KILL_BONUS := 50.0
## How much the bot dislikes standing in a telegraphed cell, per point of incoming damage.
const DANGER_WEIGHT := 1.5


## Plays the whole battle headless. Returns
## {won: bool, winner: int, rounds: int, survivors: int, hp_left: int}.
static func simulate(encounter: EncounterData, max_rounds := 40, player_team := 0) -> Dictionary:
	var model := encounter.build_model()
	var turns := TurnManager.new(model, encounter.teams())
	turns.start()
	while not turns.is_over() and turns.round_number <= max_rounds:
		if turns.current_team() == player_team:
			play_turn(model, player_team)
		else:
			TacticsAI.take_turn(model, turns.current_team())
		turns.end_turn()
	var hp_left := 0
	for unit in model.living(player_team):
		hp_left += unit.hp
	return {
		"won": turns.winner == player_team,
		"winner": turns.winner,                    # -2 = ran out of rounds (a stalemate)
		"rounds": turns.round_number,
		"survivors": model.living(player_team).size(),
		"hp_left": hp_left,
	}


## Runs simulate() on every EncounterData .tres under `dir` (recursively).
## Returns {resource path: result Dictionary}.
static func verify_folder(dir: String, max_rounds := 40) -> Dictionary:
	var results := {}
	for file in DirAccess.get_files_at(dir):
		if file.ends_with(".tres") or file.ends_with(".res"):
			var encounter := load(dir.path_join(file)) as EncounterData
			if encounter:
				results[dir.path_join(file)] = simulate(encounter, max_rounds)
	for sub in DirAccess.get_directories_at(dir):
		results.merge(verify_folder(dir.path_join(sub), max_rounds))
	return results


## One full player turn: every living unit takes its best move and action.
static func play_turn(model: GridModel, team: int) -> void:
	for unit in model.living(team):
		if unit.is_alive():
			play_unit(model, unit)


## Chooses and performs the best (cell, action) pair for one unit.
static func play_unit(model: GridModel, unit: GridUnit) -> void:
	var danger := model.danger_cells(unit.team)
	var reach := model.reachable_cells(unit)
	var best := {"score": -INF, "cell": unit.cell, "action": {}}
	for cell: Vector2i in reach:
		var action := _best_action_from(model, unit, cell)
		var incoming: int = danger.get(cell, 0)
		var score: float = action.get("value", 0.0) - incoming * DANGER_WEIGHT
		if incoming >= unit.hp:
			score -= 100.0                          # never stand where the telegraph would kill
		score -= 0.1 * _distance_to_nearest_enemy(model, unit, cell)   # otherwise, close in
		score -= 0.01 * reach[cell]                 # tie-break: walk less
		if score > best.score:
			best = {"score": score, "cell": cell, "action": action}
	if best.cell != unit.cell:
		model.move_unit(unit, best.cell)
	var chosen: Dictionary = best.action
	if chosen.is_empty():
		return
	if chosen.ability:
		model.use_ability(unit, chosen.ability, chosen.target)
	else:
		model.attack(unit, chosen.target)


## The most valuable thing `unit` could do if it stood on `from`:
## {value: float, target: Vector2i, ability: AbilityData or null}, or {} if nothing.
static func _best_action_from(model: GridModel, unit: GridUnit, from: Vector2i) -> Dictionary:
	var best := {}
	var best_value := 0.0
	# Basic attack on each enemy in range.
	for enemy in model.enemies_of(unit.team):
		var d := RangeShapes.distance(from, enemy.cell)
		if d < unit.data.attack_range_min or d > unit.data.attack_range_max:
			continue
		var value := _hit_value(enemy, unit.data.attack_damage)
		if value > best_value:
			best_value = value
			best = {"value": value, "target": enemy.cell, "ability": null}
	# Abilities: try aiming at every unit's cell (the centre of an area is usually on a unit).
	for ability in unit.data.abilities:
		if not unit.can_use(ability):
			continue
		for aim in model.living():
			if RangeShapes.distance(from, aim.cell) > ability.cast_range:
				continue
			var value := _ability_value(model, unit, ability, from, aim.cell)
			if value > best_value:
				best_value = value
				best = {"value": value, "target": aim.cell, "ability": ability}
	return best


## Total worth of an ability cast from `from` at `target_cell`: damage to enemies (or healing
## actually needed by allies), following the same team rules as GridModel.use_ability.
static func _ability_value(model: GridModel, unit: GridUnit, ability: AbilityData, from: Vector2i, target_cell: Vector2i) -> float:
	var value := 0.0
	var direction := RangeShapes.direction_to(from, target_cell)
	for cell in RangeShapes.cells(ability.shape, target_cell, ability.radius, direction):
		var target := model.unit_at(cell)
		if target == null:
			continue
		var same_team := target.team == unit.team
		if ability.is_support():
			if same_team:
				value += minf(-ability.damage, target.data.max_hp - target.hp) * 0.8
		elif not same_team:
			value += _hit_value(target, ability.damage)
		elif ability.friendly_fire and target != unit:
			value -= _hit_value(target, ability.damage)     # hurting allies counts against it
	return value


## Worth of dealing `damage` to `target`: the HP actually removed, plus a bonus for a kill.
static func _hit_value(target: GridUnit, damage: int) -> float:
	var value := float(mini(damage, target.hp))
	if damage >= target.hp:
		value += KILL_BONUS
	return value


## Steps from `cell` to the closest enemy (0 when there are none).
static func _distance_to_nearest_enemy(model: GridModel, unit: GridUnit, cell: Vector2i) -> int:
	var best := 0
	var first := true
	for enemy in model.enemies_of(unit.team):
		var d := RangeShapes.distance(cell, enemy.cell)
		if first or d < best:
			best = d
			first = false
	return best
