# AbilityData: one special move (fireball, heal, spear thrust) as a tunable .tres Resource.
class_name AbilityData
extends Resource
## An ability is aimed at a cell within `cast_range` of the caster and affects every unit
## inside its area (a RangeShapes shape placed on the target cell). Positive `damage` hurts,
## negative heals. After use it is unavailable for `cooldown` of the owner's turns.

@export var id: StringName = &"ability"
@export var display_name := "Ability"
## Hit points removed from each unit in the area. Negative values heal.
@export var damage := 3
## How far from the caster the target cell may be (Manhattan steps). 0 = self only.
@export var cast_range := 3
## The area placed on the target cell.
@export var shape := RangeShapes.Shape.SINGLE
## Size of the area (see RangeShapes for what radius means per shape).
@export var radius := 1
## Owner turns before it can be used again (0 = every turn).
@export var cooldown := 2
## If false, units on the caster's own team are skipped (heals flip this: they skip enemies).
@export var friendly_fire := false


## True for heals and buffs: they target the caster's own team instead of enemies.
func is_support() -> bool:
	return damage < 0
