---
name: blender-godot-pipeline
description: >-
  3D game asset pipeline from AI generation to Godot 4. Activate for any 3D request: generating
  3D models (Tripo, Meshy, Rodin/Hyper3D, Hunyuan3D), cleaning AI meshes, rigging (Mixamo,
  AccuRIG, quadrupeds), animation clips (Mixamo, ActorCore, video mocap, Seedance/Kling
  references), weight transfer for clothing, UDIM/UV fixes, baking, GLB export, Godot import,
  Blender MCP or Godot MCP work.
---

# Blender → Godot 3D Pipeline

Everything lives in [`pipeline3d/`](../../../pipeline3d/README.md). Read its README for the
full picture. This skill is the operating procedure for an agent.

## 1. Pick the execution mode

| Situation | Mode | Entry point |
| --- | --- | --- |
| Terminal access (Claude Code, Antigravity) and the user wants an asset built | **Headless forge** | `python pipeline3d/forge.py pipeline3d/manifests/<asset>.json` |
| Blender open with the MCP add-on, user wants to watch or iterate | **Live Blender MCP** | tools `run_script_file`, `get_viewport_screenshot`, `generate_3d_via_api` ([playbook](../../../pipeline3d/docs/mcp-playbook.md)) |
| Only needs one step (e.g. "clean this GLB") | **Single script** | `blender -b -P pipeline3d/blender/<script>.py -- key=value ...` |

## 2. Route by asset type

| Asset | Rig | Animation | Notes |
| --- | --- | --- | --- |
| Humanoid | `mixamo` or `accurig` (manual gate), `meshy`/`tripo` (API) | `clips_dir` (Mixamo In Place, 30 fps, Without Skin) | cleanup BEFORE rigging |
| Quadruped / creature | `quadruped` | `procedural` (idle, walk, attack, death) | tweak `landmarks` if bones miss legs |
| Clothing / armour | `transfer_weights.py` from the rigged body | inherits | generate parts separately |
| Weapon / mechanism / anything with holes | procedural script (`build_karambit.py` pattern) | none or code | generators fuse holes |
| Prop | none | none | `export.collision: "convex"` |

## 3. Non-negotiable rules

1. One part per generation job; neutral A-pose; flat light; no weapon in the body image.
2. Run `cleanup_for_godot.py` before any rigging. Never join or apply transforms on a skinned mesh.
3. Look after every visible step: `get_viewport_screenshot` (live) or `render_preview.py` (headless).
   Numbers can pass on a broken mesh.
4. Clips are in place, 30 fps, and start at frame 0. The Godot controller moves the character.
5. Don't flip normal-map green for Godot (OpenGL, like Blender). Only Unreal needs it.
6. Stop at manual gates (exit code 3) and relay forge's instructions verbatim. Don't guess
   Mixamo output paths.
7. Before reporting done: `godot --headless --path <game> --import`, then
   `-s res://tools/asset_audit.gd` must exit 0.

## 4. Verify

* Whole chain, no keys: `BLENDER=... GODOT=... pipeline3d/tests/run_all.sh`
* Forge + manual gates: `pipeline3d/tests/test_forge.sh`
* Tool choices (free / trial / open source per stage): [`docs/tool-matrix.md`](../../../pipeline3d/docs/tool-matrix.md)
