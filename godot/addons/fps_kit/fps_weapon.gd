# FPSWeapon: fires a WeaponData from the camera. Handles ammo, fire rate, reload and recoil.
class_name FPSWeapon
extends Node3D
## Put it anywhere under the FPSController (usually inside a ViewmodelSway under the camera,
## next to your gun mesh). It aims along `aim` (the camera by default), so shots go where the
## crosshair points even though the gun model sits off to the side.
##
## Signals let content react without this kit knowing about it: connect `fired` to a muzzle
## flash and sound, `hit` to an impact decal, `ammo_changed` to the HUD.

signal fired
## A hitscan ray hit something (projectiles report through their own `impacted` signal).
signal hit(collider: Node, position: Vector3, normal: Vector3)
## After every shot and reload: drive the HUD ammo counter from this.
signal ammo_changed(in_magazine: int, reserve: int)
## Reload began / ended: play the reload animation and sound between these two.
signal reload_started
signal reload_finished
## Fire was pressed with an empty magazine (play a click).
signal dry_fired

@export var data: WeaponData
## The body that holds the gun: gets the recoil, is never hit by its own shots.
@export var controller: FPSController
## Where shots come from and point (-Z forward). Defaults to the controller's camera.
@export var aim: Node3D
## Read fire/reload input itself. Turn off when AI or touch buttons call try_fire() directly.
@export var handle_input := true
## Physics layers shots can hit.
@export_flags_3d_physics var collision_mask := 0xFFFFFFFF
## Seed for spread and recoil randomness (fixed so tests and replays are repeatable; 0 = random).
@export var random_seed := 0

var ammo_in_magazine := 0
var reserve_ammo := 0
var is_reloading := false
var _next_shot_msec := 0
var _rng := RandomNumberGenerator.new()


## _ready(): fill the magazine and find the camera if `aim` was left empty.
func _ready() -> void:
	if random_seed != 0:
		_rng.seed = random_seed
	if controller == null:
		controller = _find_controller()
	if aim == null and controller:
		aim = controller.camera
	if data:
		ammo_in_magazine = data.magazine_size
		reserve_ammo = data.reserve_ammo


## Polls the fire and reload actions every physics tick when handle_input is on.
func _physics_process(_delta: float) -> void:
	if not handle_input or data == null:
		return
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED and controller and controller.mouse_capture_enabled:
		return                          # the click that captures the mouse must not shoot
	var trigger := Input.is_action_pressed(FPSInput.FIRE) if data.automatic \
			else Input.is_action_just_pressed(FPSInput.FIRE)
	if trigger:
		try_fire()
	if Input.is_action_just_pressed(FPSInput.RELOAD):
		reload()


## Fires one shot if the gun is ready. Returns true when a shot went out.
func try_fire() -> bool:
	if data == null or is_reloading or Time.get_ticks_msec() < _next_shot_msec:
		return false
	if ammo_in_magazine <= 0:
		dry_fired.emit()
		if reserve_ammo != 0:
			reload()                    # auto-reload on an empty click
		return false
	ammo_in_magazine -= 1
	_next_shot_msec = Time.get_ticks_msec() + int(data.shot_interval() * 1000.0)
	for i in maxi(data.pellets, 1):
		var direction := _spread(-aim.global_basis.z)
		if data.fire_mode == WeaponData.FireMode.HITSCAN:
			_fire_ray(direction)
		else:
			_fire_projectile(direction)
	_kick()
	fired.emit()
	ammo_changed.emit(ammo_in_magazine, reserve_ammo)
	return true


## Refills the magazine from reserve after reload_time. `await` waits for the timer without
## freezing the game; the gun cannot fire meanwhile (is_reloading).
func reload() -> void:
	if data == null or is_reloading or ammo_in_magazine >= data.magazine_size or reserve_ammo == 0:
		return
	is_reloading = true
	reload_started.emit()
	await get_tree().create_timer(data.reload_time, false).timeout
	if not is_inside_tree():
		return
	var needed: int = data.magazine_size - ammo_in_magazine
	var taken: int = needed if reserve_ammo < 0 else mini(needed, reserve_ammo)   # -1 reserve = infinite
	ammo_in_magazine += taken
	if reserve_ammo > 0:
		reserve_ammo -= taken
	is_reloading = false
	reload_finished.emit()
	ammo_changed.emit(ammo_in_magazine, reserve_ammo)


## Instant shot: one ray from the aim point. Damage goes to whatever HealthComponent it finds.
func _fire_ray(direction: Vector3) -> void:
	var from := aim.global_position
	var query := PhysicsRayQueryParameters3D.create(from, from + direction * data.max_range, collision_mask)
	query.collide_with_areas = true                       # Hurtboxes are Area3Ds
	if controller:
		query.exclude = [controller.get_rid()]
	var result := get_world_3d().direct_space_state.intersect_ray(query)
	if result.is_empty():
		return
	var collider: Node = result.collider
	var health := HealthComponent.resolve(collider)
	if health:
		health.take_damage(HitInfo.new(data.damage, controller, direction * data.knockback))
	hit.emit(collider, result.position, result.normal)


## Moving shot: spawns the projectile in the current scene (not under the gun, or it would
## follow the camera around after leaving the barrel).
func _fire_projectile(direction: Vector3) -> void:
	var p: FPSProjectile
	if data.projectile_scene:
		p = data.projectile_scene.instantiate() as FPSProjectile
	else:
		p = FPSProjectile.new()
	p.velocity = direction * data.projectile_speed
	p.gravity = data.projectile_gravity
	p.damage = data.damage
	p.knockback = data.knockback
	p.lifetime = data.projectile_lifetime
	p.source = controller
	p.collision_mask = collision_mask
	var parent := get_tree().current_scene if get_tree().current_scene else get_tree().root
	parent.add_child(p)
	p.global_position = aim.global_position


## Recoil kicks the view up (and randomly sideways) through the controller, so the pitch clamp applies.
func _kick() -> void:
	if controller == null:
		return
	var up := deg_to_rad(data.recoil_pitch_degrees)
	var side := deg_to_rad(_rng.randf_range(-data.recoil_yaw_degrees, data.recoil_yaw_degrees))
	controller.add_look_input(Vector2(side, -up))     # negative y = look up


## Tilts `forward` by a random angle inside the spread cone.
func _spread(forward: Vector3) -> Vector3:
	if data.spread_degrees <= 0.0:
		return forward
	var angle := deg_to_rad(_rng.randf_range(0.0, data.spread_degrees))
	var around := _rng.randf_range(0.0, TAU)
	var side := forward.cross(Vector3.UP if absf(forward.y) < 0.99 else Vector3.RIGHT).normalized()
	return forward.rotated(side.rotated(forward, around), angle).normalized()


## Walks up the tree to the FPSController that owns this gun.
func _find_controller() -> FPSController:
	var node := get_parent()
	while node:
		if node is FPSController:
			return node
		node = node.get_parent()
	return null
