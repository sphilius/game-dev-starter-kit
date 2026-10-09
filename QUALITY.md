# QUALITY

## 1. Rubric — BMX-CRITIC v1 (verbatim, owner-supplied)

```
[BMX-CRITIC v1]
You are a visual critic with no stake in this code. Inputs: {{SHOT_PATHS}} (PNGs and contact sheets), QUALITY.md rubric, PALETTE.md.
Score each frame 1–5 on: band legibility (3–4 hard bands, no mush) · line quality (constant screen width, no breaks, no doubled lines, no noise lines on terrain) · palette discipline · silhouette read · rider pose read · effects stay graphic (not photographic or static-noise) · aliasing/shimmer · composition.
For every score <4, name the defect, the frame, the screen region, and the likely cause. No praise. No "overall looks good."
Output a table, then the top 5 defects ranked by visual damage. If you cannot see a criterion clearly in the frame, say "unjudgeable from stills" instead of guessing.
```

### Score anchors (calibration for the critic and for me; not part of the critic text above)

| ID | Criterion | 1 | 3 | 5 | Owner |
|---|---|---|---|---|---|
| C1 | Band legibility | gradients or mush; bands <3 or >4; soft terminators | bands present but terminator wobbles or some surface has 2 or 5 tones | every surface exactly 3 hard bands (4 with rim); stable in motion | render/materials |
| C2 | Line quality | broken, doubled or noise lines | mostly constant; gaps on thin geometry or ±1 px width drift | constant screen width at DPR 1.25–2.0, closed silhouettes, no doubles, no terrain noise | render/outlines |
| C3 | Palette discipline | off-palette hues or free gradients | <= 5% of non-UI pixels off the derived set | 100% of non-UI pixels within tolerance of a derived tone | render/post, world |
| C4 | Silhouette read | rider or bike lost against background at 20 m | readable only if you know what to look for | instantly readable; each rider identifiable by livery | rider, bike view |
| C5 | Rider pose read | pose state ambiguous | state readable but stiff | pedal / pump / lean / tuck / absorb readable from silhouette alone | rider |
| C6 | Effects graphic | photographic or noisy dust | graphic but inconsistent line weight | puffs, roost, ribbons are inked cel shapes with hard bands | render/fx |
| C7 | Aliasing / shimmer | crawling edges visible | occasional crawl on thin or distant geometry | stable across the contact sheet | render/post, quality |
| C8 | Composition | subject lost | subject clear but cluttered or off-frame-spec | matches the reference-shot spec in section 3 | render/camera, world |

Aliasing and pose timing are temporal; stills may legitimately be "unjudgeable from stills", which is why every shot also produces a contact sheet.

### Gates
- **Demo gate:** all six shots score >= 4 on all eight criteria; no "unjudgeable" left on C1–C4; no open P0/P1 defect.
- **Non-visual gates:** `npm run check` passes; determinism hash identical in Node and Chrome; `?perf=1` JSON from owner machine shows p95 <= 16.6 ms at DPR >= 1.25.
- Feel (handling, pump, powerslide) and animation timing stay UNVERIFIED until owner playtest, whatever the stills score.

## 2. Subsystem scores (evidence paths required; "—" = not yet scored)

| Subsystem | Criteria | Score | Evidence | Scored in |
|---|---|---|---|---|
| render/materials | C1 C3 | — | — | — |
| render/outlines | C2 C7 | — | — | — |
| render/post | C3 C7 | — | — | — |
| render/fx | C6 | — | — | — |
| render/camera | C8 | — | — | — |
| world (view) | C1 C3 C8 | — | — | — |
| bike (view) | C4 | — | — | — |
| rider | C4 C5 | — | — | — |
| ui | C3 C8 | — | — | — |
| bike/sim (feel) | — | UNVERIFIED | owner playtest | — |
| determinism | — | not run | `tests/` hash | — |
| perf | — | no data | owner `?perf=1` JSON | — |

## 3. Six reference shots

Capture: `npm run shots -- --shot=<name>` writes to `shots/<session>/`:
- `<name>.png`: the still, rendered at the trigger tick (1280x720 CSS at DPR 2 = 2560x1440).
- `<name>.sheet.png`: 8 frames sampled at trigger tick + k·Δ for k = 0..7 with Δ = 4 sim ticks (1/30 s at 120 Hz), covering 7/30 s of real motion for edge crawl and pose change. The sim and camera **keep running** after the trigger; only the still is a single instant, and a frozen sim would give 8 identical frames.
- `finish-orbit` also writes `finish-orbit.orbit.png`: 8 frames with Δ = 103 sim ticks (≈0.858 s), so k = 0..7 spans 721 ticks ≈ 6.0 s, the whole orbit.
- `report.json`: draw calls, palette conformance %, ink coverage %, rider height as % of frame.

Seed 1, all four riders on AI autopilot, state reached by simulation (no teleport). Frames from the agent sandbox are software-GL: valid for the critic, NON-TARGET for timing.

| Shot | Trigger | Camera | Must see | Auto-fail | Stresses |
|---|---|---|---|---|---|
| **gate-wide** | countdown T-2 s, s=0, riders in lanes | 14 m downhill of gate, 1.1 m high, looking up at the gate centre, vFOV 52° | 4 riders in distinct liveries, gate silhouette complete, >= 3 layered ridge bands, sky >= 35% of height, horizon in upper third | thin gate bars break or shimmer; two riders same hue | C1 C2 C3 C4 C8 |
| **chase-straight** | player at s=250, ~19 m/s | 5.5 m behind, 1.9 m up, +0.6 m lateral, look 4 m ahead; vFOV 50° + 8° × clamp((v-10)/10) | rider ~22% of frame height, graphic speed lines, dust trail of inked puffs, tyre ribbon behind, a rival ~15 m ahead | speed lines or dust photographic/noisy; ribbon z-fights terrain | C2 C4 C5 C6 C8 |
| **berm-apex** | player at s=473.5, lean 30–38° | outside the turn, 7 m lateral, 1.3 m high, look at rider +1 m, vFOV 38° | lean readable, powerslide ribbon arc, roost from rear tyre, berm wall curvature read through bands, crest edge | wall shows noise lines; rider lost against PINE | C1 C2 C5 C6 |
| **midair-gap** | player 0.85 s after takeoff at s≈1567 | side-on from the far lip, 26 m back, 2 m above lip height, vFOV 40° | both lips and the void in frame, rider tuck pose, full hull outline against sky, no ground shadow while airborne | rider silhouette breaks against SKY; void floor reads as flat fill | C2 C4 C5 C8 |
| **pack-close** | four riders within 6 m, sweeper s≈700–760 | 9 m behind rear rider, 3 m right, 2.4 m up, vFOV 48° | ID-edge ink between overlapping riders, four distinct liveries, overlapping dust still graphic, **draw calls <= 250** (worst-case stress) | doubled lines at hull/Sobel seam; hull z-fighting; budget exceeded | C2 C4 C6 C7 |
| **finish-orbit** | line crossed + 1.0 s, s=1690 | orbit on the arch centre, radius 10 m, 2.2 m high, azimuth -30° to +150° over 6 s (`finish-orbit.orbit.png` spans the orbit; `.sheet.png` covers shimmer) | banner text legible (canvas texture), results UI over 3D without clash, valley bands, smooth orbit | UI illegible over bright sky; text shimmer | C3 C7 C8 |

If a shot cannot be reached on seed 1 (for example the pack never closes), that is a defect in AI pacing, not permission to teleport.

## 4. Defect backlog

Severity: P0 blocks the demo gate, P1 fails a criterion (<4) on a shot, P2 visible but passes, P3 polish. Status ANTICIPATED = predicted from the design, **not observed** (no frames exist yet).

| ID | Sev | Criterion | Shot | Region | Likely cause | Owner session | Status |
|---|---|---|---|---|---|---|---|
| Q-001 | P1 | C2 | pack-close, any character edge | silhouette seams | hull and Sobel both draw the edge | S01 | ANTICIPATED |
| Q-002 | P1 | C2 | berm-apex, sweeper | terrain surface | normal-edge Sobel on noisy heightfield | S01 | ANTICIPATED |
| Q-003 | P1 | C6 | chase-straight | dust trail | alpha or dither fade instead of inked puffs | S06 | ANTICIPATED |
| Q-004 | P2 | C7 | gate-wide | gate bars | thin geometry under 1 px at distance | S01 | ANTICIPATED |
| Q-005 | P1 | C4 | berm-apex (forest) | rider vs PINE | VIOLET on PINE 1.02:1, ink on PINE 2.8:1 | S03 | ANTICIPATED |
| Q-006 | P2 | C2 | midair-gap | hull outline | smooth-normal attribute missing on merged mesh, gaps at hard edges | S04 | ANTICIPATED |
