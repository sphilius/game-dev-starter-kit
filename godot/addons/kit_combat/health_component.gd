class_name HealthComponent
extends Node
## Reusable health pool. Add it as a child of anything that can be hurt.
##
## Hitboxes resolve it from what they touched (a Hurtbox, or a body with a HealthComponent
## child) via HealthComponent.resolve(), then call take_damage(). Owners react through signals:
## `damaged` for stagger or flash, `died` for death.

signal damaged(hit: HitInfo)
signal health_changed(current: float, maximum: float)
signal died(hit: HitInfo)

@export var max_health := 100.0
## Real-time seconds of immunity after each accepted hit (0 = none).
@export var invulnerability_time := 0.0

var current_health := 0.0
var is_dead := false
var _invulnerable_until_msec := 0


func _ready() -> void:
	current_health = max_health


## Returns true if the hit was applied (false when dead or invulnerable).
func take_damage(hit: HitInfo) -> bool:
	if is_dead or Time.get_ticks_msec() < _invulnerable_until_msec:
		return false
	current_health = maxf(current_health - hit.damage, 0.0)
	_invulnerable_until_msec = Time.get_ticks_msec() + int(invulnerability_time * 1000.0)
	var lethal := current_health <= 0.0
	is_dead = lethal                  # set first, so `damaged` listeners can skip lethal hits
	health_changed.emit(current_health, max_health)
	damaged.emit(hit)
	if lethal:
		died.emit(hit)
	return true


func heal(amount: float) -> void:
	if is_dead:
		return
	current_health = minf(current_health + amount, max_health)
	health_changed.emit(current_health, max_health)


## Back to full health after death (respawn).
func revive() -> void:
	is_dead = false
	current_health = max_health
	_invulnerable_until_msec = 0
	health_changed.emit(current_health, max_health)


## Finds the HealthComponent behind whatever a hitbox touched: a Hurtbox, a HealthComponent,
## or a node that has one as a direct child.
static func resolve(node: Node) -> HealthComponent:
	if node is Hurtbox:
		return (node as Hurtbox).health
	if node is HealthComponent:
		return node
	for child in node.get_children():
		if child is HealthComponent:
			return child
	return null
