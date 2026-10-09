# COURSE — "Switchback" ridge run

One point-to-point run, 1690 m timed + 60 m runout, 126.8 m of descent, mean grade 7.5%. Targets below are design intent; headless runs in S03/S05 confirm or retune them.

## Timing targets

| Run | Time |
|---|---|
| Perfect flow (every pump and landing clean, sprint always spent) | 100–104 s |
| Par (clean, competent, no exploits) | 110 s |
| AI: Pro / Rival / Rookie | 112 / 116 / 122 s (±1.5 s seeded) |
| Typical first run | 125–135 s |
| One respawn | +8–12 s |
| Hard cap | 150 s: unfinished riders ranked by progress and flagged DNF |

## Sections

| # | Section | s0 → s1 (m) | Len | Grade | v in → out (m/s) | Avg v | Time (s) | Cum (s) | Drop (m) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Start hill | 0 → 110 | 110 | 17% | 0 → 16 | 9.5 | 11.6 | 11.6 | 18.7 |
| 2 | Sprint straight | 110 → 410 | 300 | 9% | 16 → 20 | 18.5 | 16.2 | 27.8 | 27.0 |
| 3 | Hairpin berm | 410 → 560 | 150 | 7% | 20 → 13 → 16 | 12.5 | 12.0 | 39.8 | 10.5 |
| 4 | Wide sweeper | 560 → 900 | 340 | 8% | 16 → 19 | 17.0 | 20.0 | 59.8 | 27.2 |
| 5 | S-chicane of berms | 900 → 1100 | 200 | 7% | 19 → 13.5 → 15 | 14.5 | 13.8 | 73.6 | 14.0 |
| 6 | Rhythm section | 1100 → 1380 | 280 | 5% | 15 → 17 | 16.0 | 17.5 | 91.1 | 14.0 |
| 7 | Step-up | 1380 → 1480 | 100 | 4% | 17 → 16 | 15.5 | 6.5 | 97.6 | 4.0 |
| 8 | Gap jump | 1480 → 1630 | 150 | 6% | 16 → 17 | 16.5 | 9.1 | 106.7 | 9.0 |
| 9 | Finish (timed) | 1630 → 1690 | 60 | 4% | 17 → 17 | 17.0 | 3.5 | 110.2 | 2.4 |
| — | Runout (untimed) | 1690 → 1750 | 60 | — | brake | — | — | — | — |

Totals: 1690 m, 110.2 s, 126.8 m drop, mean 15.3 m/s. Grades and drops are net design values (±10%); local jump geometry exceeds them.

## Plan-view layout (x east, y north, metres; heading CCW from east)

| Anchor | s | x | y | Heading |
|---|---|---|---|---|
| Gate | 0 | 0 | 0 | 0° |
| Hairpin turn start | 450 | 450 | 0 | 0° |
| Hairpin turn end | 497 | 450 | 30 | 180° |
| Sweeper start | 560 | 387 | 30 | 180° |
| Chicane start | 900 | 251 | 274 | 58° |
| Rhythm start | 1100 | 414 | 328 | -22° |
| Step-up start | 1380 | 674 | 224 | -22° |
| Gap start | 1480 | 767 | 187 | -22° |
| Finish line | 1690 | 962 | 109 | -22° |
| Runout end | 1750 | 1018 | 86 | -22° |

Footprint 1018 x 338 m. No self-crossing: the closest approach of non-adjacent course is 30 m (hairpin legs s=388 vs 560). The sweeper turns **right**: a left sweeper crosses the first leg, which a heightfield cannot represent.

## Section design

**1. Start hill (0–110).** Gate at s=0, four lanes at lateral -1.95 / -0.65 / +0.65 / +1.95 m. Gate slope 28% for 12 m, then 17%. Width 9 m funnelling to 7 m at s=100 (forces the pack together). Alpine ridge: ROCK, snow patches (PAPER), DIRT track. Flow starts at 30 so the first sprint is available. Checkpoint 0 = gate.

**2. Sprint straight (110–410).** Dead straight in plan (keeps the anchor maths exact); width 10 m, cliff drop on the right. Three low pump bumps (amplitude 0.35 m, period 40 m) with crests at s=190, 230, 270: the first flow lesson. Brake boards at 400 / 425 / 440 (50 / 25 / 10 m before the turn at 450). Checkpoint 1 at s=380 (respawn 14 m/s).

**3. Hairpin berm (410–560).** Entry straight 410–450, turn 450–497 (apex s=473.5), exit 497–560. Left turn, 180°, centre radius 15 m (arc 47.1 m), width 12 m, bank 38°, outer wall 2.4 m, max wall slope 52° (guard < 55°). Check: balance speed with zero friction = 10.7 m/s; carving at 13 m/s needs lateral μ ≈ 0.19; unbraked 20 m/s needs μ ≈ 0.62, so braking or a powerslide is the intended tool. Checkpoint 2 at s=560 (respawn 11 m/s).

**4. Wide sweeper (560–900).** Right turn 121.8°, centre radius 160 m (arc 340 m), width 14 m, bank 12°, soft wall 0.9 m. Inside line (R 153 m) is ~8% shorter than the outside line (R 167 m), so the pack spreads and re-forms here (pack-close home). Optional inside kicker K1 at s=720–740, lateral -4 m (clean landing +flow). Big vista: the valley opens to the right. Checkpoint 3 at s=730 (respawn 14 m/s).

**5. S-chicane of berms (900–1100).** Entry 900–922, berm A 922–962 (right), link 962–980, berm B 980–1020 (left), link 1020–1038, berm C 1038–1078 (right), exit 1078–1100. Each berm 80° over 40 m (radius 28.6 m), bank 32°, wall 1.6 m, width 9 m. Balance speed 13.3 m/s (14.5 m/s needs lateral μ ≈ 0.08), so it is carved, not slid. Net heading change -80° (right). Trees stand >= 6 m off the corridor. Checkpoints 4 at s=900 (respawn 13 m/s) and 5 at s=1100 (respawn 12 m/s).

**6. Rhythm section (1100–1380).** Entry flat 1100–1120. Rollers 1120–1216: four, period 24 m, amplitude 0.9 m, crests at 1132 / 1156 / 1180 / 1204 (pump training). Tables T1 1216–1252, T2 1252–1288, T3 1288–1324, each lip 6 + top 8 + landing 10 + flat 12 (airtime ~0.6–0.9 s, PROPOSED). Closing double 1324–1380: lip 8, gap 10, landing 14, runout 24; minimum speed 13 m/s (20° launch, level). Checkpoint 6 at s=1246 (flat after T1, respawn 13 m/s). A bail in the rollers costs a full replay from s=1100.

**7. Step-up (1380–1480).** Approach 1380–1420, lip 1420–1428 (22° launch), gap 1428–1436 (8 m), deck/landing 1436–1452 (+1.2 m above the lip), transition 1452–1470, runout 1470–1480. Minimum speed 13.5 m/s (marginal), 15 m/s clears with margin. Undershoot hits a 50° face: heavy speed loss or crash. Checkpoint 7 at s=1380 (respawn 13 m/s).

**8. Gap jump (1480–1630).** Approach 1480–1540 (60 m straight, sprint zone), take-off ramp 1540–1552 (28° launch), gap 1552–1574 (22 m, void 14 m deep, waterfall decor), landing slope 1574–1604 (-14°, landPitch -14°, 2 m below the lip), runout 1604–1630. Minimum speed 15.0 m/s (clears 22.2 m); arrival target 17 (27.7 m range), airtime ~1.8 s. Fall into the void -> respawn at checkpoint 8 (s=1480, 12 m/s, flow floor 25); the S05 headless test must show a sprint-assisted respawn can clear the gap. Camera apex at s≈1567.

**9. Finish (1630–1750).** Flat 1630–1670, banner arch and timing line at s=1690, 60 m braking runout with stop zone, instanced cel flags, valley floor in MEADOW and DIRT. Finish-orbit camera pivots on the arch.

## Checkpoints

| # | s | Respawn m/s | Note |
|---|---|---|---|
| 0 | 0 | 0 | gate |
| 1 | 380 | 14 | before brake zone |
| 2 | 560 | 11 | hairpin exit |
| 3 | 730 | 14 | mid-sweeper |
| 4 | 900 | 13 | chicane entry |
| 5 | 1100 | 12 | rhythm entry |
| 6 | 1246 | 13 | after table 1 |
| 7 | 1380 | 13 | step-up entry |
| 8 | 1480 | 12 | gap approach |
| F | 1690 | — | finish line |

Respawn gives 1.5 s of ghosting and a flow floor of 25.

## Features index (seed for TrackDef in S03)

minSpeed is computed for SU, D1, GAP (ballistic maths in this session); K1 and T1–T3 values are PROPOSED.

| id | kind | s (lip start → landing end) | minSpeed (m/s) | landPitch |
|---|---|---|---|---|
| R1–R4 | roller | crests 1132 / 1156 / 1180 / 1204 | — | — |
| P1–P3 | roller (straight bumps) | crests 190 / 230 / 270 | — | — |
| K1 | kicker | 720 → 740 | 12 | -6° |
| T1 / T2 / T3 | table | 1216 / 1252 / 1288 → +24 | 11 | -8° |
| D1 | double | 1324 → 1356 | 13 | -10° |
| SU | step-up | 1420 → 1452 | 13.5 | -12° |
| GAP | gap | 1540 → 1604 | 15.0 | -14° |

## Flow economy (PROPOSED, tuned in S06)

Capacity 100. Sprint drains 20/s. Perfect pump +6 (good +3, ok +1). Clean landing +10 (tables, double, kicker), +15 (step-up, gap). Crash resets to the floor of 25.

| Section | Max flow earnable | Suggested spend |
|---|---|---|
| Start hill | 30 (start charge) | start sprint |
| Straight | 18 (3 bumps) | exit toward hairpin |
| Hairpin | 6 | out of the turn |
| Sweeper | 10 (K1) | mid-sweeper |
| Chicane | 18 | out of berm C |
| Rhythm | 64 (rollers 24, tables 30, double 10) | between features |
| Step-up | 15 | approach |
| Gap | 15 | hold >= 25 for the approach |

Perfect total ≈ 176, about 8.8 s of sprint across the run.

## Backdrop rule

Never let PINE or ROCK-shade sit directly behind a rider on the line: forest is >= 6 m off the corridor and fog-lifts to haze at distance. Reason: ink loses contrast on PINE (2.8:1) and a VIOLET rider on PINE is 1.02:1. Far mountains are three layered ridge silhouettes plus a valley floor, all unreachable.

## Camera hooks (used by QUALITY.md shots)

Gate s=0 · straight s≈250 · hairpin apex s=473.5 · sweeper s≈730 · gap apex s≈1567 · finish s=1690.
