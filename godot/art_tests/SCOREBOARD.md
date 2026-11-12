# Art pipeline scoreboard

Written by `scoreboard.py` from each cell's `report.json`. Do not edit by hand: re-run the script.

One hero asset and one environment piece per cell, gated and placed in a running demo scene.
Click a cell name to see its screenshot.

- **machine**: time the computer worked (generation, cleanup, Blender, Godot import, gates), min:sec.
- **human (est.)**: time a person is needed. These are ESTIMATES, not stopwatch readings: 20 s per
  look at an output, plus a stated guess for each manual step. Writing the demo scene is not included.
- **looks**: times a person must look at an output and say yes. **re-rolls**: outputs thrown away.
- **gates**: checks from `gates/gate2d.py` and `gates/gate3d.py` on the final assets.

| Cell | Art source | Images | Cost | Machine | Human (est.) | Total | Looks | Re-rolls | Gates |
|---|---|---|---|---|---|---|---|---|---|
| [fps_2d](cells/fps_2d/screenshot.png) | generated | 3 | $0.06 | 0:52 | 1:00 | **1:52** | 2 | 1 | 11 pass, 3 n/a |
| [action_rpg_2d](cells/action_rpg_2d/screenshot.png) | generated | 6 | $0.12 | 0:43 | 1:00 | **1:43** | 2 | 2 | 29 pass, 13 n/a |
| [tactics_2d](cells/tactics_2d/screenshot.png) | generated | 4 | $0.08 | 0:34 | 1:00 | **1:34** | 2 | 1 | 19 pass, 11 n/a |
| [fighter_2d](cells/fighter_2d/screenshot.png) | generated | 2 | $0.04 | 0:21 | 5:40 | **6:01** | 2 | 0 | 27 pass, 15 n/a |
| [metroidvania_2d](cells/metroidvania_2d/screenshot.png) | generated | 3 | $0.06 | 0:26 | 2:40 | **3:06** | 2 | 0 | 13 pass, 2 n/a |
| [platformer_2d](cells/platformer_2d/screenshot.png) | generated | 2 | $0.04 | 0:21 | 2:40 | **3:01** | 2 | 0 | 19 pass, 11 n/a |
| [fps_3d](cells/fps_3d/screenshot.png) | downloaded + built | - | $0.00 | 0:43 | 5:40 | **6:23** | 2 | 0 | 20 pass, 19 n/a |
| [action_rpg_3d](cells/action_rpg_3d/screenshot.png) | downloaded | - | $0.00 | 0:34 | 10:20 | **10:54** | 1 | 0 | 21 pass, 18 n/a |
| [tactics_3d](cells/tactics_3d/screenshot.png) | downloaded | - | $0.00 | 0:23 | 5:20 | **5:43** | 1 | 0 | 14 pass, 18 n/a |
| [fighter_3d](cells/fighter_3d/screenshot.png) | downloaded | - | $0.00 | 0:17 | 0:20 | **0:37** | 1 | 0 | 16 pass, 3 n/a |
| [metroidvania_3d](cells/metroidvania_3d/screenshot.png) | downloaded | - | $0.00 | 0:15 | 7:20 | **7:35** | 1 | 0 | 14 pass, 5 n/a |
| [platformer_3d](cells/platformer_3d/screenshot.png) | downloaded | - | $0.00 | 0:37 | 5:20 | **5:57** | 1 | 0 | 19 pass, 33 n/a |

**All 12 cells:** machine 6:14, human (est.) 48:20, 4 re-rolls, $0.40 of generation.
**Spend ledger** (`logs/spend_log.csv`): $0.42 for 21 images, against a $5.00 cap.

## What each cell used

| Cell | Pipeline |
|---|---|
| action_rpg_2d | nano-banana 4x4 walk sheet + ground tile |
| action_rpg_3d | CC rigged humanoid + clip library (Quaternius), no manual step |
| fighter_2d | nano-banana parts sheet -> Skeleton2D puppet |
| fighter_3d | one CC rigged humanoid used for both fighters + CC0 floor texture |
| fps_2d | nano-banana billboard sheet + tiling wall |
| fps_3d | CC0 kit level (Kenney) + pipeline3d procedural rigged enemy + fog |
| metroidvania_2d | nano-banana run sheet + 2 tiles, one 16-colour palette |
| metroidvania_3d | CC rigged animal (Khronos Fox) + CC0 rock texture on boxes, side camera |
| platformer_2d | nano-banana flat parts sheet -> puppet with procedural run |
| platformer_3d | one CC0 kit (Kenney): hero with clips + matching platforms |
| tactics_2d | nano-banana portrait -> code-made token |
| tactics_3d | static CC0 kit models as minis (Kenney) + CC0 board texture |

## What went wrong (and is now written down)

**action_rpg_2d**
- 4x4 grid sheet: side row flips direction 4 times in 4 frames
- ground: green hero on green grass, readability 1.62
- one image with all four directions: character stays on-model, directions do not
- hero and ground generated separately came out the same green (contrast 1.62)

**action_rpg_3d**
- a clip-library character is a bare mannequin: it gives motion, not identity (tinted per team here; a real costume is extra work)

**fighter_2d**
- parts on one sheet are not drawn at one scale: arms came out long, torso small

**fps_2d**
- readability 1.19 on fog: the AI chose a dark palette for a dark level

**fps_3d**
- a kit's palette sets the mood: this pastel kit fights a horror tone (fog and dim light only go so far)
- kit props are not sized for first-person use: the blaster is 1.6 m long and needed scaling to 0.2

**metroidvania_2d**
- tile images come with a drawn border and far too much detail for 32 px
- two tiles from two requests do not match each other: derive variants from ONE tile

**metroidvania_3d**
- downloaded model is not in metres (79 units tall): scale it in the scene

**platformer_3d**
- kit models reference an external shared texture: copy the Textures folder with them

**tactics_2d**
- knight: armour carried a lion crest resembling a known franchise emblem
- AI portraits drift toward recognisable franchise designs; say 'no emblems or logos' up front
