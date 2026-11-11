class_name Hurtbox
extends Area3D
## Passive damage receiver (physics layer "hurtbox"). It never scans; hitboxes detect it
## through `area_entered` and deliver damage to `health`.

@export var health: HealthComponent


func _ready() -> void:
	monitoring = false
