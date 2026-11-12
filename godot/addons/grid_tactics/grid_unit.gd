# GridUnit: one unit on the board during a battle (its position, HP, and what it did this turn).
class_name GridUnit
extends RefCounted
## Plain data, no node. Presenters keep their own visual node per GridUnit and update it from
## the GridModel's signals, so the rules never depend on how the game looks.

var data: UnitData
## 0 = the player's team by convention; 1+ = enemies. Teams with different numbers are hostile.
var team := 0
var cell := Vector2i.ZERO
var hp := 0
## Each unit may move once and act (attack or ability) once per turn.
var has_moved := false
var has_acted := false
## ability id -> turns left before it can be used again.
var cooldowns := {}
## A telegraphed attack that will resolve at the start of this unit's next turn:
## {"cells": Array[Vector2i], "damage": int}. Empty = nothing planned.
var intent := {}


## _init() is the constructor: GridUnit.new(data, team, cell).
func _init(p_data: UnitData = null, p_team := 0, p_cell := Vector2i.ZERO) -> void:
	data = p_data
	team = p_team
	cell = p_cell
	hp = data.max_hp if data else 0


## Dead units stay in the model's list (for stats and revive effects) but are skipped by the rules.
func is_alive() -> bool:
	return hp > 0


## True when the ability exists on this unit and is off cooldown.
func can_use(ability: AbilityData) -> bool:
	return data.abilities.has(ability) and cooldowns.get(ability.id, 0) <= 0
