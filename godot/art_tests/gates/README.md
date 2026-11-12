# Art gates

A gate is a check with a number and a limit. Art that passes can go in the game without a
person inspecting it; art that fails says which re-roll or cleanup step it needs. Every gate
has a test that breaks one thing and confirms that gate (and only that gate) fails.

| File | What it does |
|---|---|
| `art_cleanup.py` | Raw AI image → keyed, palette-snapped, sliced, feet-aligned frames (from Medusa's Price, plus `--palette` and `--key-color`) |
| `gate2d.py` | 9 gates for sprites, tilesets, portraits, backgrounds |
| `glb_facts.py` | Reads triangles, size, bones, clips out of a `.glb` in milliseconds (no Blender) |
| `gate3d.py` | 13 gates for models, in three layers: file → Blender → Godot |
| `blender_gate.py` | The Blender layer (non-manifold edges, bend test, turnaround renders) |
| `runlog.py` | Stopwatch + ledger: wall time, approvals, re-rolls, cost → `report.json`; enforces the $5 cap |
| `build_sprites.py` | Medusa's sprite-sheet → SpriteFrames builder (copied as the base; adapted per cell) |

## Run

```bash
export GODOT="<4.7.2 console exe>"   BLENDER="<blender exe>"     # see ../ENV.md for the paths
python gate2d.py processed/hero --palette vase --target-height 64 --bg 2b2d3a
python gate3d.py hero.glb --kind character --height 1.8 --clips idle,walk --loops idle,walk --render-dir renders
bash run_tests.sh                                                # all gate tests, about 80 s
```

Without `GODOT` or `BLENDER` the gates that need them are reported as `skip`, never as a fail.

## Measured on this laptop (2026-11-11)

| Gate run | Time |
|---|---|
| `gate2d` without the Godot import | under 1 s |
| `gate2d` with the Godot import | about 7 s (Godot start-up) |
| `gate3d` file layer only | under 0.1 s |
| `gate3d` all three layers, rigged wolf (2116 tris, 39 bones, 4 clips) | 11.9 s |

## Things the gates taught us already

- **Run the silhouette gate per animation, not per sheet.** Medusa's `medusa_a` sheet (idle,
  run, jump, fall together) scores 0.206 because a run frame is compared with a jump frame.
  Her hoplite sheet (one walk + attacks) passes at 0.359.
- **The generic bend gate is a floor, not a quality bar.** It bends every joint 90°, including
  necks that never bend that far, so 0.5 only catches broken weights. pipeline3d's own
  `bend_test.py` (limb joints, 0.85) stays the bar for rigs it generates.
- **Open edges are normal on scenery.** `non_manifold` is enforced for characters and props
  (it breaks auto-rigging) and only reported for `--kind environment`.
