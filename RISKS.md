# RISKS and session roadmap

Constraint E1 (environment): the agent sandbox has Chromium only (no Chrome, no GPU, 4 CPUs). Shots are software-GL; all timing there is NON-TARGET. `npm run shots` falls back to `SHOTS_CHROMIUM` (DEC-016).

## Top 5 technical risks

| # | Risk | Why it is dangerous | Plan if it bites |
|---|---|---|---|
| R1 | **Bike feel: suspension + pumping at 120 Hz** | Wheel-ray suspension can jitter or explode; rider-on-rail pumping may be unstable, unfun, or exploitable; feel cannot be verified by me | Plan B: authored per-roller impulse scaled by timing quality (DEC-014) |
| R2 | **Toon pipeline cost and line artifacts** | Prepass + hulls + Sobel + composite at retina 2.0 inside 16.6 ms; doubled lines, terrain noise lines, shimmer on thin bars; cannot be measured here | Fallback ladder: half-res Sobel -> drop normal term -> hulls only within 30 m -> raise DPR floor |
| R3 | **Track as single truth (visual = collision)** | Heightfield aliasing at jump lips and berm walls; mesh/sim mismatch; no overlapping surfaces allowed; void gap edge | 0.25 m tiles in the corridor, 2 m outside; build the render mesh from the same samples; wall slope guard < 55° |
| R4 | **Zero-asset rider readability** | Procedural anime rider must read at 10–30 m with primitives; merged-mesh hulls gap on hard edges; low fill contrast leans on ink | Rigid-skinned merged mesh with a smooth-normal attribute; liveries use 3 colours; critic review of S04 frames |
| R5 | **Determinism and the headless boundary** | Node/Chrome divergence breaks shots and AI repeatability; one stray `three` import breaks Node | Import-boundary grep; hash test in both engines; polynomial trig contingency (ARCHITECTURE §8) |

Watch list (not top 5): AI jump reliability and pack cohesion without cheating (S05); procedural audio quality (S07); Vite or three upgrade drift (pinned); sandbox vs Chrome rendering differences (E1).

## Session roadmap (PROPOSED; S01+ scope is yours to approve)

| Session | Goal | Exit gate |
|---|---|---|
| S00 | Specs (this) | you approve |
| S01 | Vite/TS skeleton, three@0.186.1, 120 Hz loop, ToonMaterial, 6-stage pipeline on a test scene (slope, ramp, 4 capsule riders), `?perf=1`, `npm run check`, `npm run shots`, critic wired | critic >= 4 on C1–C3, C7 on the test scene; you return one `?perf=1` JSON |
| S02 | core/math, rng, events; analytic Terrain stub; BikeSim (rays, tire, rail, flow); Node harness; wireframe playground | invariants and determinism hash pass; pump experiment shows timed pumping beats coasting; you playtest the playground; Plan A/B chosen |
| S03 | TrackDef from COURSE.md, heightfield bake, parity tests, terrain/sky/props view, checkpoints | scripted line completes headless in ~110 s; mesh-vs-query parity <= 1 cm; all 9 sections shotted |
| S04 | Rider and bike meshes, poses, secondary motion, camera rig | critic >= 4 on C4, C5 for chase-straight and berm-apex |
| S05 | Race, AI, respawn | deterministic full headless race; AI finish in target windows; pack-close reachable on seed 1; CP8 respawn can clear the gap |
| S06 | Flow economy, powerslide, fx, HUD | critic >= 4 on C6; you playtest flow economy |
| S07 | Audio, results, all six reference shots | all six shots >= 4 on all criteria |
| S08 | Perf and feel pass on your machine | p95 <= 16.6 ms at DPR >= 1.25 from your JSON; playtest sign-off |

## How each session de-risks each risk

| Risk | S01 | S02 | S03 | S04 | S05 | S06 | S07 | S08 |
|---|---|---|---|---|---|---|---|---|
| R1 feel | — | headless harness, invariants, pump experiment, wireframe playground you can feel, Plan A/B decision | slope and jump geometry tested against real track | — | AI exercises same sim for 100s of runs | flow economy and powerslide tuned on playtest | — | final feel pass |
| R2 pipeline | builds all 6 stages first on a primitive scene; first `?perf=1`; ink-ownership and terrain-crease rules tested; MSAA vs smoothstep decision | — | real terrain checked for noise lines | hull smooth normals on real characters | pack-close draw-call stress | fx cost added and measured | — | DPR governor tuned on your JSON |
| R3 track | — | analytic Terrain stub fixes the interface | bake, tiles, parity test, lip/berm ray-drop tests, no-overlap check | — | respawn positions validated | — | — | — |
| R4 rider | capsule rider tests hull gaps early | — | backdrop rule applied to scenery | procedural rider, poses, critic on frames | pack-close overlap read | roost and dust on rider | — | — |
| R5 determinism | import-boundary check in `npm run check` | hash test Node vs Chrome | bake is deterministic and hashed | — | full-race hash regression | — | — | — |
