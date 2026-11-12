# UnitData: the stat sheet for one kind of unit (knight, archer, slime) as a .tres Resource.
class_name UnitData
extends Resource
## Shared by every unit of that kind on the board; per-battle state (current HP, position)
## lives in GridUnit. Make one .tres per unit type and tune it in the Inspector.

## Stable key for save files and for presenters to look up this unit's art.
@export var id: StringName = &"unit"
@export var display_name := "Unit"
@export var max_hp := 10
## Cells it can walk per turn.
@export var move_range := 3
@export var attack_damage := 3
## Basic attack reach in Manhattan steps: 1..1 is melee, 2..4 is an archer that cannot hit adjacent.
@export var attack_range_min := 1
@export var attack_range_max := 1
## Special moves, in the order a UI should list them.
@export var abilities: Array[AbilityData] = []
