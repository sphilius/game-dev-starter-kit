# ARCHITECTURE — Switchback (three@0.186.1)

Status v0 (S00). Changes need a logged reason (Change log at the end). Numbers marked PROPOSED are unmeasured. Any three.js API named here is UNVERIFIED until checked against node_modules/three in S01.

## 1. Module map

```
src/
  main.ts       browser composition root
  headless.ts   Node composition root (sim only)
  compose.ts    composeSim(cfg): wires sim-side modules; shared by both roots
  core/         loop.ts time.ts rng.ts events.ts types.ts math.ts input.ts input.dom.ts
  render/       pipeline.ts  materials/ToonMaterial.ts  outlines/{hull,sobel}.ts
                post/{composite,quality}.ts  sky/  fx/{dust,roost,ribbons,speedlines}.ts  camera/rig.ts
  world/        sim/{track,bake,terrain,features}.ts   view/{terrainMesh,props,structures}.ts
  bike/         sim/{bike,wheel,tire,rail,flow}.ts     view/bikeMesh.ts
  rider/        view/{mesh,rig,pose,secondary}.ts
  ai/           driver.ts line.ts speedplan.ts skill.ts
  race/         race.ts checkpoints.ts respawn.ts ranking.ts
  ui/           hud.ts flowmeter.ts countdown.ts results.ts
  audio/        engine.ts wind.ts tire.ts impacts.ts
  debug/        perf.ts overlay.ts shots.ts passes.ts
scripts/        check.mjs  shots.mjs
```

| Module | Layer | Owns | Reads (via core/types) | Emits | Listens |
|---|---|---|---|---|---|
| core | sim | fixed-step loop, rng, typed event bus, plain math, input interface | — | — | — |
| world | sim + view | TrackPath, heightfield bake, Terrain, jump/checkpoint defs; meshes, props, gate/finish | — | — | — |
| bike | sim + view | wheel raycast suspension, tire/slide, rider-on-rail pump, flow, sprint, crash; bike mesh | Terrain, TrackPath | wheel.contact, takeoff, landing, pump, flow.change, sprint.*, slide.*, berm.*, crash, bump | respawn |
| rider | view | procedural rider mesh, pose, secondary motion (scarf, hair) | SimSnapshot | — | landing, crash, takeoff |
| ai | sim | racing line follower, speed planner, skill noise; outputs InputState | SimSnapshot, TrackPath | ai.mistake (debug) | — |
| race | sim | phases, countdown, checkpoints, respawn, ranking, timing, section tracking | SimSnapshot, TrackPath | countdown.tick, race.start, section.enter, checkpoint.pass, position.change, rider.finish, race.end, respawn | crash |
| render | view | ToonMaterial, 6-stage pipeline, sky, fx, camera rig, DPR governor | SimSnapshot | quality.dpr | landing, slide.*, wheel.contact, takeoff |
| ui | view | DOM HUD, flow meter, countdown, results | SimSnapshot | — | flow.change, checkpoint.pass, landing, rider.finish, race.* |
| audio | view | Web Audio synth graph | SimSnapshot | — | pump, landing, slide.*, crash, takeoff, countdown.tick |
| debug | both | perf JSON, overlay, shot director, pass toggles | everything read-only | shot.ready | — |

### Dependency rules (enforced by `npm run check`)
- D1 Sim files (`core/**`, `*/sim/**`, `ai/**`, `race/**`, `compose.ts`, `headless.ts`) may not import `three*`, `render/`, `ui/`, `audio/`, `rider/`, any `*/view/**`, or touch `window`, `document`, `performance`.
- D2 Siblings talk only via `core/types.ts` interfaces and the event bus. Only `compose.ts`, `main.ts`, `headless.ts` import across siblings.
- D3 View code reads `SimSnapshot` and listens to events; it never mutates sim state.
- D4 `ShaderMaterial` / `onBeforeCompile` appear only under `render/materials/`.
- D5 Banned everywhere: MeshStandardMaterial, MeshPhysicalMaterial. Banned in sim: Math.random, Date.now.

## 2. Core types (`src/core/types.ts`, plain data and interfaces only)

```ts
export type RiderId = 0 | 1 | 2 | 3;                       // 0 = player
export interface Vec3 { x: number; y: number; z: number }
export interface Quat { x: number; y: number; z: number; w: number }

export interface InputState {                              // one per rider per tick; AI emits the same type
  steer: number;    // -1..1
  pump: number;     // -1..1  ground: rider-rail push(+)/pull(-); air: pitch trim
  sprint: boolean;  // spend flow -> pedal thrust
  slide: boolean;   // powerslide / rear brake
  reset: boolean;   // manual respawn (costs time)
}

export type SurfaceKind = 'dirt' | 'berm' | 'ramp' | 'landing' | 'rock' | 'void';
export interface SurfaceSample { y: number; n: Vec3; kind: SurfaceKind; grip: number; s: number; u: number }
export interface Terrain {                                 // implemented by world/sim, used by bike/sim
  sample(x: number, z: number, out: SurfaceSample): SurfaceSample;
  raycast(o: Vec3, d: Vec3, maxT: number, out: RayHit): boolean;
}

export type SectionKind = 'start-hill' | 'sprint-straight' | 'hairpin-berm' | 'sweeper'
  | 'chicane-berms' | 'rhythm' | 'step-up' | 'gap-jump' | 'finish';
export interface SectionDef { id: number; kind: SectionKind; s0: number; s1: number }
export interface JumpDef { id: string; kind: 'roller' | 'table' | 'step-up' | 'double' | 'gap' | 'kicker';
  sLip: number; sLand0: number; sLand1: number; minSpeed: number; landPitch: number }
export interface CheckpointDef { index: number; s: number; respawnSpeed: number }
export interface TrackFrame { pos: Vec3; tangent: Vec3; right: Vec3; up: Vec3;
  halfWidth: number; bank: number; grade: number; curvature: number }
export interface TrackPath {                               // implemented by world/sim; used by ai, race, camera, ui
  length: number; finishS: number;
  frameAt(s: number, out: TrackFrame): TrackFrame;
  project(p: Vec3, hintS: number): number;                 // hinted arc-length projection (hairpin-safe)
  line(laneId: number, s: number): number;                 // authored racing-line lateral offset (m)
  sections: readonly SectionDef[]; jumps: readonly JumpDef[]; checkpoints: readonly CheckpointDef[];
}

export interface WheelState { contact: boolean; compression: number; load: number; kind: SurfaceKind; spin: number }
export interface BikeState {                               // authoritative, Float64, sim-owned
  pos: Vec3; rot: Quat; vel: Vec3; angVel: Vec3;
  front: WheelState; rear: WheelState;
  steerAngle: number; lean: number; slipAngle: number;
  rail: { offset: number; vel: number };                   // rider-on-rail (pump)
  mode: 'ground' | 'air' | 'crashed' | 'respawning';
  flow: number;                                            // 0..100
  sprinting: boolean; sliding: boolean;
  s: number; u: number;                                    // progress, lateral offset
}
export interface RaceState { phase: 'grid' | 'countdown' | 'racing' | 'finished'; clock: number;
  order: RiderId[]; checkpoint: number[]; finishTime: (number | null)[] }
export interface SimSnapshot { tick: number; time: number; bikes: readonly BikeState[]; race: RaceState }
export interface Rng { next(): number; int(n: number): number; range(a: number, b: number): number; fork(label: string): Rng }
export interface Sim { readonly tick: number; step(inputs: readonly InputState[]): void; snapshot(): SimSnapshot; hash(): string }
```

## 3. Frame and data flow

```
 input.dom (keys/pad) -> InputSource.sample(tick) --+
 ai.driver.decide(prev snapshot) -------------------+--> inputs[4]
                                                    v
 loop (fixed 120 Hz, max 8 catch-up steps, then drop time):
   race.pre -> bike.step x4 (wheel rays vs Terrain) -> rider/rider bump -> race.post -> bus.flushSim()
                                                    v
 snapshot ring (prev, curr) --alpha--> views: rider/bike meshes, camera, fx, ui, audio
                                                    v
 render/pipeline: prepass -> scene -> hulls -> sobel -> composite -> (DOM) ui
```

Sim hot path does not emit per-tick events. Events fire on state changes only. Listeners register with `phase: 'sim' | 'view'`: sim listeners run synchronously in deterministic order; view listeners are queued and delivered at render time.

## 4. Translations (the requested mapping)

| Requirement | Mechanism | Where |
|---|---|---|
| Wheel-raycast suspension | two wheel rays along bike-down; spring-damper per wheel; friction-circle tires | bike/sim/wheel.ts, tire.ts |
| Pumping rollers fill flow | rider is a point mass on a ±0.25 m rail along bike-up; pump axis drives it; energy comes from real ground compression (Plan A). Plan B: authored per-roller impulse scaled by timing quality | bike/sim/rail.ts, flow.ts |
| Clean landings fill flow | landing graded by pitch alignment error and normal impact: clean (<8°, <6 m/s) +flow, rough (<20°) none and 15% speed loss, worse = crash | bike/sim/bike.ts |
| Flow spent on sprint pedaling | flow 0..100; sprint drains 20/s and adds +1.8 m/s² forward thrust (PROPOSED) | bike/sim/flow.ts |
| Skid / powerslide | slide input drops rear lateral grip to 0.35x; speed bleeds with slip; emits slide.* and skid ribbon | bike/sim/tire.ts, render/fx/ribbons.ts |
| Authored jumps | JumpDef with lip, landing zone, minSpeed, landPitch baked into terrain | world/sim/features.ts |
| Checkpoints + respawn | CheckpointDef per section; crash -> respawning -> reposition at checkpoint, per-checkpoint respawnSpeed, 1.5 s ghosting | race/ |
| Tire dust / roost / track ribbons (replace foam / wake) | inked cel puffs on wheel.contact and slide; roost arcs from the rear tire; ribbon strips with polygon offset | render/fx/ |

Bike model starting constants (all PROPOSED, tuned in S02): mass 85 kg (rider 74 on rail), wheelbase 1.05 m, ray length 0.55 m, spring k ≈ 9000 N/m, damper c ≈ 700 N·s/m, rail muscle force ≈ 900 N, grip dirt 0.65 / berm 0.75 / rock 0.50, lean is kinematic (spring toward atan(a_lat/g)), not balanced physics. Crash if landing misalignment > 35°, normal impact > 9 m/s, lean > 70° on ground, head-sphere ground contact, `void` surface, or > 8 m outside corridor.

## 5. Event list (`core/events.ts`, typed `EventMap`; every payload carries `tick`)

| Event | Payload | Emitter | Typical listeners |
|---|---|---|---|
| countdown.tick | n | race | ui, audio |
| race.start | — | race | ui, audio, camera |
| section.enter | rider, section | race | ui, camera |
| checkpoint.pass | rider, index, s, t | race | ui |
| position.change | rider, from, to | race | ui |
| rider.finish | rider, place, time | race | ui, camera |
| race.end | results | race | ui |
| wheel.contact | rider, wheel, on, kind | bike | fx, audio |
| takeoff | rider, jump?, speed, pitch | bike | rider, audio, camera |
| landing | rider, jump?, grade (clean/rough/case), impact, alignErr | bike | flow, rider, fx, audio, ui |
| pump | rider, quality, dv | bike | flow, audio, ui |
| flow.change | rider, value, delta, cause (pump/landing/slide-exit/sprint/crash/respawn) | bike | ui |
| sprint.start / sprint.end | rider | bike | audio, fx |
| slide.start / slide.end | rider | bike | fx, audio |
| berm.enter / berm.exit | rider, side | bike | camera, audio |
| bump | rider, other, impulse | bike | audio, fx |
| crash | rider, cause | bike | race, rider, audio, camera |
| respawn | rider, checkpoint | race | bike, ui, fx |
| ai.mistake | rider, kind | ai | debug |
| quality.dpr | from, to | render | debug, ui |
| shot.ready | name | debug | shots script |

## 6. Render pass order

Pre-frame (CPU): interpolate snapshot by alpha, solve poses and secondary motion, append skid-ribbon points, step view-side particles, place camera.

| # | Pass | Target | Contents and rules |
|---|---|---|---|
| 1 | **Prepass** | RT_G: RGBA8 + DepthTexture. rg = oct-encoded normal, b = class+id, a = hull weight | all opaque draws via ToonMaterial's prepass variant (skinning- and instancing-aware): terrain, props, bikes, riders, gate, finish arch, fx puffs. Excludes sky, ribbons, hulls |
| 2 | **Scene** | RT_SCENE: RGBA8, shares RT_G depth | sky (no depth write) -> opaque toon shading (3 hard bands from the PALETTE formula, optional rim band; depthFunc LessEqual, Equal evaluated in S01) -> fx puffs -> track ribbons (polygon offset) -> contact-shadow decals |
| 3 | **Hulls** | RT_SCENE, depth-test vs RT_G depth, no depth write | inverted-hull outline for CHARACTER and HERO classes only (riders, bikes, gate, arch). Clip-space inflation so width is constant in pixels; smooth-normal attribute so hard edges leave no gaps. Writes ink colour and `a = 1` as the owner flag |
| 4 | **Sobel** | RT_INK: R8 | reads RT_G depth (linearised), normal, class+id. Edges: id boundary, relative depth jump, normal crease (>= 60° on TERRAIN, >= 35° elsewhere). **Skips pixels where RT_SCENE.a (dilated 1 px) = 1**: hulls own those silhouettes, so no doubled lines |
| 5 | **Composite** | canvas | scene + ink (1 px smoothstep AA) + banded aerial haze (<= 4 steps) + grade + vignette + graphic speed lines + flow-edge glow; sRGB encode here |
| 6 | **UI** | DOM overlay | HUD above the canvas, untouched by passes 4-5 |

- Resolution: all RTs = canvas x DPR. DprGovernor moves DPR in [1.25, 2.0] by rolling p95 with hysteresis. Sobel kernel is 1 physical pixel scaled by DPR so line weight is constant on screen.
- Anti-aliasing: no MSAA by default; ink mask is smoothstepped; DPR floor 1.25. S01 spike measures a 4x-sample scene RT and decides.
- No shadow-map pass (DEC-011).
- Draw-call accounting: `renderer.info.render.calls` with autoReset off, summed over all passes each frame. Estimated worst scene ~120 (prepass ~35, scene ~45, hulls ~10, fullscreen 3, fx ~25). Cap 250.

## 7. Budgets (PROPOSED until `?perf=1` JSON from owner machine)

- Frame p95 <= 16.6 ms; DPR [1.25, 2.0]; draw calls <= 250.
- GPU at DPR 2.0 (starting split): prepass 2.0, scene 4.0, hulls 0.8, sobel 1.5, composite 1.2 ms. JS: sim <= 1.5 ms/frame for 4 riders, view <= 3 ms.
- Characters are one rigid-skinned merged mesh each (rider, bike): 2 draws + 2 hull draws per rider.
- `?perf=1` JSON: `{build, ua, dpr:{min,mean,final}, frames, ms:{mean,p50,p95,p99}, passMs:{prepass,scene,hulls,sobel,composite}|null, drawCalls:{p95,max}, tris, sim:{stepsPerFrame,msPerFrame}, scene}`. `passMs` needs EXT_disjoint_timer_query_webgl2; null if absent.

## 8. Determinism rules

- All randomness from `core/rng` (seeded, `fork(label)` per subsystem). No Math.random, Date.now, performance.now in sim.
- Float64 throughout the sim; fixed iteration order; one `Sim.hash()` over BikeState + RaceState.
- Contingency: if Node and Chrome hashes diverge, replace Math.sin/cos/pow in sim with polynomial versions in core/math.ts.

## 9. Change log

- v0 | S00 | initial module map, types, events, pass order | spec session.
- v0 | S00 | added core/math.ts, sim/ vs view/ folders, compose.ts/headless.ts roots | DEC-005/006/007.
- v0 | S00 | ink single-owner rule, terrain crease rule, cel-puff fx | DEC-008/009/010 from BMX-CRITIC.
