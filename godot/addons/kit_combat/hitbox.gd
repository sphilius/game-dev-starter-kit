class_name Hitbox
extends Area3D
## Damage dealer for any melee strike (a sword, a bite, a punch).
##
## The owner arms it with an AttackData (begin) and opens or closes the active window
## (set_active). While active, `area_entered` (Hurtboxes) and `body_entered` (bodies) resolve
## the target's HealthComponent. Each target is hit at most once per activation, even when its
## hurtbox and body both overlap. A landed hit applies damage, knockback and stagger, and
## triggers hit-stop.

signal hit_landed(target: HealthComponent, hit: HitInfo)

## The attacker: knockback pushes away from it, and it never hits itself.
var source: Node3D
var _attack: AttackData
var _active := false
var _hit_this_swing := {}   # HealthComponent -> true


func _ready() -> void:
	monitoring = false
	area_entered.connect(_on_struck)
	body_entered.connect(_on_struck)


## Arms the hitbox for a new strike (clears the one-hit-per-target memory).
func begin(attack: AttackData) -> void:
	_attack = attack
	_hit_this_swing.clear()


func set_active(on: bool) -> void:
	if on == _active:
		return
	_active = on
	set_deferred(&"monitoring", on)   # overlaps already present report on the next physics step


func is_active() -> bool:
	return _active


func _on_struck(node: Node3D) -> void:
	if not _active or _attack == null:
		return
	var health := HealthComponent.resolve(node)
	if health == null or health.is_dead or _hit_this_swing.has(health):
		return
	if source and health.get_parent() == source:
		return
	_hit_this_swing[health] = true

	var push := Vector3.ZERO
	if source:
		push = node.global_position - source.global_position
		push.y = 0.0
		push = push.normalized()
	var hit := HitInfo.new(_attack.damage, source, push * _attack.knockback, _attack.stagger_time)
	if health.take_damage(hit):
		HitStop.trigger(_attack.hitstop)
		hit_landed.emit(health, hit)
