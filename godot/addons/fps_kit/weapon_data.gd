# WeaponData: every number that makes one gun feel different, saved as a .tres Resource.
class_name WeaponData
extends Resource
## One weapon's stats. Make a .tres per gun (right-click in FileSystem > New Resource >
## WeaponData) and tune it in the Inspector while the game runs. FPSWeapon reads it.
##
## HITSCAN: the shot is an instant ray (rifles, pistols, shotguns with `pellets` > 1).
## PROJECTILE: a moving FPSProjectile (rockets, plasma, thrown knives). Slower bullets are
## easier to read in a jam game and let enemies dodge.

enum FireMode { HITSCAN, PROJECTILE }

@export var display_name := "Weapon"
@export var fire_mode := FireMode.HITSCAN
@export var damage := 10.0
## Shots per second.
@export var fire_rate := 6.0
## Hold to keep firing (true) or one shot per click (false).
@export var automatic := false
## Hitscan reach in metres.
@export var max_range := 100.0
## Random cone half-angle in degrees (0 = perfectly accurate).
@export var spread_degrees := 0.0
## Rays (or projectiles) per shot: 1 for most guns, 6-10 for a shotgun.
@export var pellets := 1
## Push applied to whatever is hit, m/s.
@export var knockback := 1.0

@export_group("Ammo")
@export var magazine_size := 12
## Spare rounds outside the magazine. -1 = infinite.
@export var reserve_ammo := 48
@export var reload_time := 1.2

@export_group("Recoil")
## Upward kick per shot, degrees.
@export var recoil_pitch_degrees := 1.5
## Random sideways kick per shot, ± degrees.
@export var recoil_yaw_degrees := 0.4

@export_group("Projectile")
## Optional scene with an FPSProjectile root (for a mesh/trail). Empty = a bare FPSProjectile.
@export var projectile_scene: PackedScene
@export var projectile_speed := 40.0
## Gravity on the projectile, m/s² (0 = flies straight).
@export var projectile_gravity := 0.0
@export var projectile_lifetime := 4.0


## Seconds between shots, derived from fire_rate.
func shot_interval() -> float:
	return 1.0 / maxf(fire_rate, 0.01)
