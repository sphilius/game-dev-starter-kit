class_name AttackData
extends Resource
## One strike of a combo. Times are seconds from the start of the attack's animation.
## It is a Resource, so each strike can be saved as a .tres file and tuned in the Inspector
## without touching code. With imported animations, set the timings to match the clip.

## State name in the AnimationTree state machine.
@export var animation: StringName = &"attack_1"
@export var damage := 20.0

@export_group("Timing")
## Full length of the strike; the attack ends here unless it chains.
@export var duration := 0.55
## Hitbox and trail switch on…
@export var active_start := 0.14
## …and off.
@export var active_end := 0.3
## Earliest moment a buffered press chains into the next strike. Clamped to at least
## active_end, so a strike's active frames always play out.
@export var combo_window_open := 0.22

@export_group("Feel")
## Forward burst (m/s) at the start of the strike.
@export var lunge_speed := 3.0
@export var lunge_duration := 0.15
## Seconds after the strike starts before the lunge kicks in (a bite's wind-up, for example).
@export var lunge_delay := 0.0
## Real-time seconds the world freezes when this strike connects.
@export var hitstop := 0.06
## How long the target is staggered (movement and AI interrupted).
@export var stagger_time := 0.3
## Horizontal knockback speed applied to the target (m/s).
@export var knockback := 3.0
