# FPSProjectile: a bullet that travels. Moves by ray steps so fast shots never skip through walls.
class_name FPSProjectile
extends Node3D
## Each physics tick it casts a ray from where it is to where it will be. Anything that ray
## touches is hit, however thin, which a moving Area3D can miss at high speed ("tunnelling").
## Damage goes through kit_combat's HealthComponent.resolve(), like melee hits.

## Emitted on impact (before freeing). `collider` is null when the lifetime ran out.
signal impacted(collider: Node, position: Vector3, normal: Vector3)

var velocity := Vector3.ZERO
var gravity := 0.0
var damage := 10.0
var knockback := 1.0
var lifetime := 4.0
## The shooter: never hit, and credited as the damage source.
var source: Node3D
var collision_mask := 0xFFFFFFFF
var _age := 0.0


## _physics_process(): step forward, checking the path in between for hits.
func _physics_process(delta: float) -> void:
	_age += delta
	if _age >= lifetime:
		impacted.emit(null, global_position, Vector3.ZERO)
		queue_free()
		return
	velocity.y -= gravity * delta
	var from := global_position
	var to := from + velocity * delta
	var query := PhysicsRayQueryParameters3D.create(from, to, collision_mask)
	query.collide_with_areas = true
	if source is CollisionObject3D:
		query.exclude = [(source as CollisionObject3D).get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		global_position = to
		return
	global_position = hit.position
	var collider: Node = hit.collider
	var health := HealthComponent.resolve(collider)
	if health:
		health.take_damage(HitInfo.new(damage, source, velocity.normalized() * knockback))
	impacted.emit(collider, hit.position, hit.normal)
	queue_free()
