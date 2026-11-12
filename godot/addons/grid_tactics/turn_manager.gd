# TurnManager: whose turn it is, what round it is, and who has won.
class_name TurnManager
extends RefCounted
## Team-based turns ("all of mine, then all of yours"), the simplest scheme to read and to
## balance in a week. Plain data like GridModel, so tests and the bot can drive it directly.
##
## Typical loop:  start()  ->  (current team moves/attacks through GridModel)  ->  end_turn()
##                ...repeat until battle_ended fires.

## A team's turn begins: its units may move and act again.
signal turn_started(team: int, round_number: int)
signal turn_ended(team: int)
## Only one team is left standing (or none: winner = -1 for a draw).
signal battle_ended(winner: int)

var model: GridModel
## Turn order. Team 0 is the player by convention.
var teams: Array[int] = [0, 1]
var round_number := 1
## -2 while the battle is running; the winning team (or -1 for a draw) once it is over.
var winner := -2
var _index := 0


## TurnManager.new(model) or TurnManager.new(model, [0, 1, 2]) for three sides.
func _init(p_model: GridModel = null, p_teams: Array[int] = [0, 1]) -> void:
	model = p_model
	teams = p_teams


## Begins round 1 with the first team.
func start() -> void:
	_index = 0
	round_number = 1
	winner = -2
	_begin_turn()


## The team whose turn it is right now.
func current_team() -> int:
	return teams[_index]


## True once battle_ended has fired.
func is_over() -> bool:
	return winner != -2


## Finishes the current team's turn and starts the next living team's.
func end_turn() -> void:
	if is_over():
		return
	turn_ended.emit(current_team())
	if check_winner():
		return
	# Advance to the next team that still has units; wrapping past the end starts a new round.
	for i in teams.size():
		_index += 1
		if _index >= teams.size():
			_index = 0
			round_number += 1
		if not model.living(current_team()).is_empty():
			break
	_begin_turn()


## Ends the battle if at most one team is alive. Call after any action that can kill.
## Returns true when the battle is over.
func check_winner() -> bool:
	if is_over():
		return true
	var alive := model.teams_alive()
	if alive.size() > 1:
		return false
	winner = alive[0] if alive.size() == 1 else -1
	battle_ended.emit(winner)
	return true


## Refreshes the current team: clears "moved/acted" flags and counts cooldowns down by one.
func _begin_turn() -> void:
	for unit in model.living(current_team()):
		unit.has_moved = false
		unit.has_acted = false
		for id in unit.cooldowns:
			unit.cooldowns[id] = maxi(unit.cooldowns[id] - 1, 0)
	turn_started.emit(current_team(), round_number)
