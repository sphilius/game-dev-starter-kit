# Art workflows that survive a one-week jam

Measured on Thursday, November 12, 2026 (Godot 4.7.2, Blender 5.1.1, Nano Banana 2 Lite).
Numbers come from [`art_tests/SCOREBOARD.md`](../art_tests/SCOREBOARD.md), which is generated
from each cell's `report.json`. Re-run a cell with `python art_tests/cells/<cell>/build.py`.

## The short answer

**Never generate animation frame by frame.** Every cell below got a usable hero in under
11 minutes, most in under 4, for 12 cents or less, by asking for the *whole* character in one
request (a sheet, a parts sheet or a portrait) or by downloading one that is already rigged.
Medusa's Price spent about two days on frame-by-frame sheets; the same six genres in both 2D
and 3D took 52 minutes of clock time here, scene code included (written by the AI agent).

| Genre | Use this | Why | Fallback |
|---|---|---|---|
| FPS | **2D billboards** (`fps_2d`) | One sheet = one enemy with 4 poses. Fog hides everything else. Shows AI use. | `fps_3d` kit level if you want real geometry |
| Action RPG | **3D clip-library character** (`action_rpg_3d`) | 45 clips ready on the rig; a 2D four-direction walk needs 4 requests per character | `action_rpg_2d` with left mirrored from right |
| Tactics | **2D portrait + token** (`tactics_2d`) | One image per unit type, zero animation | `tactics_3d` static minis |
| Fighter | **3D mirror match** (`fighter_3d`) | Second fighter is free; punches, hits and death are in the library | `fighter_2d` puppet if the look must be hand-drawn |
| Metroidvania | **2D palette-locked pixels** (`metroidvania_2d`) | One palette makes separate requests match | `metroidvania_3d` boxes + fog |
| Platformer | **2D flat puppet** (`platformer_2d`) | Run cycle is a sine wave: no frames at all | `platformer_3d` Kenney kit |

Jamference scores **AI use**. The downloaded 3D cells show none in their art, so if you pick
one, put the AI somewhere a judge can see it (generated textures, portraits, dialogue, or a
`pipeline3d` creature like the `fps_3d` boar).

## What was measured, and what was not

| Measured | Not measured |
|---|---|
| Machine time per step (generation, cleanup, Blender, Godot import, gates) | **Your** time. "Human" figures are estimates: 20 s per look, plus a stated guess per manual step |
| Paid cost per image (estimated at $0.02; real charge is in Cloud Billing) | Time to write each demo scene by hand (the agent wrote them) |
| Re-rolls and why each happened | A full jam's worth of assets: each cell is ONE hero and ONE environment piece |
| Gate results on the final files | Tripo, Meshy, SpriteCook, Mixamo, AccuRIG: no keys or manual steps were used |
| | Web build size and frame rate with the cell art included |

## Rankings per cell

"Measured" rows are real runs. "Not run" rows are listed so the gap is visible, not ranked.

### FPS

| Rank | Pipeline | Total | Cost | Looks | Re-rolls | Verdict |
|---|---|---|---|---|---|---|
| 1 | 2D: one 4-pose billboard sheet + one wall texture | 1:52 | $0.06 | 2 | 1 | Use. Re-roll was an *edit* of take 1 (kept poses, brightened colours) |
| 2 | 3D: Kenney kit level + pipeline3d boar + fog | 6:23 | $0.00 | 2 | 0 | Works, but the kit's pastel palette fights a horror mood |
| - | 3D: AI mesh (Tripo/Meshy) + auto-rig | not run | | | | No keys |

### Action RPG

| Rank | Pipeline | Total | Cost | Looks | Re-rolls | Verdict |
|---|---|---|---|---|---|---|
| 1 | 3D: Quaternius animated base character (45 clips) + scenery | 10:54 | $0.00 | 1 | 0 | Use. Most of the time is finding the model, once |
| 2 | 2D: one row per direction, first sheet as reference, left mirrored | 1:43 | $0.12 | 2 | 2 | Use for few characters. 4 images per character |
| 3 | 2D: all four directions in one 4x4 image | rejected | $0.02 | | | Side rows flip direction every frame. Caught by the `facing` gate |
| - | 3D: Mixamo retarget | not run | | | | Manual web step |

### Tactics

| Rank | Pipeline | Total | Cost | Looks | Re-rolls | Verdict |
|---|---|---|---|---|---|---|
| 1 | 2D: portrait, token cropped from it by code, one floor image | 1:34 | $0.08 | 2 | 1 | Use. Re-roll removed a franchise-like crest |
| 2 | 3D: static kit models as minis + floor texture | 5:43 | $0.00 | 1 | 0 | Use when you want a 3D board |

### Fighter

| Rank | Pipeline | Total | Cost | Looks | Re-rolls | Verdict |
|---|---|---|---|---|---|---|
| 1 | 3D: one rigged character twice, tinted, side camera | 0:37 | $0.00 | 1 | 0 | Use. (0:37 because the character was already found for the action RPG cell) |
| 2 | 2D: six-part puppet from one parts sheet, Bone2D joints | 6:01 | $0.04 | 2 | 0 | Use for a drawn look. 5 min of that is tuning part sizes by eye |
| - | 2D: frame-by-frame sheets | not run | | | | The Medusa's Price method: about 2 days by your account |

### Metroidvania

| Rank | Pipeline | Total | Cost | Looks | Re-rolls | Verdict |
|---|---|---|---|---|---|---|
| 1 | 2D: 6-frame run sheet + ground tile, snapped to one 16-colour palette | 3:06 | $0.06 | 2 | 0 | Use. Rock tile is made from the ground tile, not generated |
| 2 | 3D: Khronos Fox + ambientCG rock on boxes, side camera, fog | 7:35 | $0.00 | 1 | 0 | Use for mood. Hero choice is limited to what is rigged and free |
| 3 | 2D: a second, separately generated rock tile | rejected | $0.02 | | | Did not match the first tile |

### Platformer

| Rank | Pipeline | Total | Cost | Looks | Re-rolls | Verdict |
|---|---|---|---|---|---|---|
| 1 | 2D: four flat parts from one sheet, run cycle from a sine wave | 3:01 | $0.04 | 2 | 0 | Use. No frames drawn, first take worked |
| 2 | 3D: Kenney platformer kit (hero with clips + platforms) | 5:57 | $0.00 | 1 | 0 | Use. Zero risk, but it looks like every other Kenney jam game |

## The rules these runs produced

1. 🎞️ **One request per character, never one per frame.** A sheet, a parts sheet or a portrait.
2. 🧲 **Re-roll by editing.** Send the rejected image back as a reference and describe only the
   change ("same poses, brighter robe"). It kept layout and character both times it was tried.
3. ↔️ **Never ask for left and right.** Generate right, mirror for left. One 4x4 "all directions"
   image fails; one row per direction with the first sheet as reference works.
4. 🎨 **Decide the background colour before the hero.** Four cells failed readability first
   time (dark on dark, green on green). Test with `gate2d.py --bg <colour>` before generating more.
5. 🧱 **Make tile variants from one tile.** Two requests never match. Crop off the border the
   AI draws, and crop in so the detail survives at 32 px.
6. 🚫 **Write "no emblems, crests or logos" in every character prompt.** A knight came back
   wearing a recognisable franchise lion. No gate can see that; you have to look.
7. 🦴 **In 3D, pick the rig first.** One clip-library character covers every humanoid. Budget
   time for telling them apart (tints here; costumes are real work).
8. 📦 **Kits bring baggage.** Copy the `Textures` folder with the models, check the scale
   (a 1.6 m blaster, a 79-unit fox), and accept that the kit's palette sets your mood.
9. 🌫️ **Fog is the cheapest art.** It hid the far wall in every 3D cell and half the 2D FPS one.

## Recipes

Every recipe is the cell's `build.py`; copy it into your jam project and change the prompts.

### 2D sheet character (FPS billboards, metroidvania run, action RPG rows)

1. 🖼️ Generate one image: poses in ONE row, "not touching", "feet on the same line", flat magenta background.
2. 🧹 `python gates/art_cleanup.py raw.png --name hero --fit-height 96 --palette none` (or `--palette <hex list> --hard-alpha` for pixel art).
3. 🚦 `python gates/gate2d.py processed/hero --target-height 96 --bg <level colour> --side-view --loop`.
4. 🔁 Gate fails on readability or facing: edit-re-roll (rule 2). Fails on fringe: lower `--key-threshold`.
5. 🎮 Load the frames into a `SpriteFrames` (`cells/cell_art.gd` has a 12-line helper).

### 2D puppet (fighter, platformer)

1. 🖼️ Generate one parts sheet: parts in a fixed left-to-right order, limbs "straight and vertical".
2. ✂️ `slice_parts()` in the cell's `build.py` cuts and names them by position and writes `rig.json`.
3. 👀 Run the demo, compare against the picture, adjust the `scales` numbers (the one manual step).
4. 🕺 Poses are dictionaries of angles: `puppet.pose({"upper_arm": -92, "forearm": -4}, 0.07)`.

### 3D downloaded character

1. 🔎 Find a rigged, animated model on Poly Pizza (Quaternius), Kenney's GitHub kits, or the Khronos samples.
2. 🚦 `python gates/gate3d.py hero.glb --kind character --height 1.8 --clips <names>`; use `one_shots=` from Python for a big clip library.
3. 🏷️ In Godot, `"X_Loop"` clips are renamed to `"X"` and loop automatically. Use the Godot names in code.
4. 🧾 Write the licence into `CREDITS.md` the moment you download (the cells do this in code).

### 3D creature with no download

1. ⚙️ `python pipeline3d/forge.py boar.json` (presets: wolf, boar, bear, deer, cat). 13 seconds, rigged, 4 clips.

## A 35-hour jam budget

Seven days at five hours. Art is capped at **6 hours**, because the scoreboard says the art
itself is minutes; the hours go on making it feel good in the game.

| Day | Hours | Do | Stop rule |
|---|---|---|---|
| 1 | 5 | Kit + grey boxes playable. **30 min: style test** (one hero through the recipe and its gate) | Hero not through the gate in 30 min: switch to the fallback column, today |
| 2 | 5 | Core loop fun with placeholders. 1 h: hero + one enemy final | An asset on its 3rd re-roll: change the prompt idea, not the wording |
| 3 | 5 | Second mechanic or enemy type. 1 h: environment set (one tile or kit, variants by code) | Tiles do not match: derive from one (rule 5), do not regenerate |
| 4 | 5 | Content: levels or encounters. 1 h: remaining characters via reference-edit | More than 4 character types: cut one |
| 5 | 5 | Theme pass + the visible AI feature. 1 h: portraits, UI, title image | |
| 6 | 5 | Polish: hit feedback, sound, juice. 1.5 h art fixes found by playtests | No new assets after today |
| 7 | 5 | Web export, itch page, screenshots, playtest on a second machine | Submit 3 h before the deadline |

Score mapping: days 1 to 4 are **Fun**, day 5 is **Theme** and **AI use**, day 6 is **Polish**.
The style test on day 1 is what protects the other six days.

## Known gaps to close next

- Time yourself on two cells with a stopwatch, so the "human" column stops being an estimate.
- Run one cell through a web export and record the size and the frame rate.
- `ComboStateMachine` expects an `AnimationTree`; the 3D humanoid demos drive `AnimationPlayer`
  directly. Wiring the Quaternius clips into the kit's combo machine is the natural next kit step.
- The readability gate uses the median pixel, which is harsh on sprites with thick dark outlines.
- With keys: add Tripo or Meshy rows to the FPS and action RPG rankings.
