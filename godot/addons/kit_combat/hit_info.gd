class_name HitInfo
extends RefCounted
## Damage payload passed from a hitbox to a HealthComponent.

var damage: float
## The attacker (used for aggro and knockback direction).
var source: Node3D
## Horizontal velocity to apply to the target (m/s).
var knockback: Vector3
var stagger_time: float


func _init(p_damage := 0.0, p_source: Node3D = null, p_knockback := Vector3.ZERO, p_stagger_time := 0.0) -> void:
	damage = p_damage
	source = p_source
	knockback = p_knockback
	stagger_time = p_stagger_time
