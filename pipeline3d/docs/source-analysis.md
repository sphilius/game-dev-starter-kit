# Source analysis: seven documents compared with the two repos

Written 2026-09-24. Inputs: the karambit benchmark runbook and Option C review (2026-09-23),
the "AI-Assisted 3D Game Development, Animation, and Asset Pipeline" blueprint, and four
transcript analyses (Stefan 3D AI: realistic character, Tripo Smart UV, the GPT-6 Astra wolf
short; AI Evolution: the Blender MCP racer).
Repos: `sphilius/blender-mcp` (fork of ahujasid/blender-mcp) and `sphilius/game-dev-starter-kit`
(Google's 2D Go/Ebitengine workshop kit).

## 1. What each source contributes

| Source | Useful core | Turned into |
| --- | --- | --- |
| Karambit runbook + Option C | "One mesh, two shaders"; procedural karambit; `cleanup_for_godot.py` with a χ ring-hole check; exit checks per step | `build_karambit.py` and `cleanup_for_godot.py` (the kit referenced them but they weren't in the upload, so they were rewritten and tested), `manifests/karambit.json` + `fighter.json`, the playbook's step mapping |
| Blueprint (MECE, 4 pillars) | Part-by-part generation, UDIM fix, Data Transfer skinning, 30 fps in-place NLA clips, normal-map convention, `-col` suffixes, three agent prompts | `udim_to_01.py`, `transfer_weights.py`, `export_for_godot.py`, `asset_audit.gd` (Godot 4 version of prompt 3), cleanup (prompt 1, without the texture-breaking repack) |
| Stefan: realistic character (Hi3D + MetaHuman) | Generate in parts; conform to a template body; bake colour high→low (cage 0.01); Data Transfer for garments; buy hair instead of generating it | `bake_diffuse.py`, `transfer_weights.py`, Godot alternative with MPFB2 (below) |
| Stefan: Tripo Smart UV | Batches of low-poly variants, quads, semantic UV seams, no hidden inner faces on clothing, Mixamo for the final rig | generation rules in the tool matrix, `gen3d.py` Tripo options pass-through |
| Stefan: GPT-6 Astra wolf | Tripo mesh → Seedance reference videos → agent keys 4 clips over Blender MCP (idle 2.5 s, walk 0.833 s, attack 1.7 s with bite at 1.3 s, death 1.333 s; 30 fps; in place; one skeleton) | `quadruped_rig.py` reproduces the exact clip spec procedurally in seconds; the agent-keying route stays in the playbook for refinement |
| AI Evolution: Blender MCP racer | Agent builds and profiles a whole game (WebGL, not Blender) and reports cuts: ~68% fewer tris, no moving shadow map in tunnels, cached minimap, interpolated physics | the optimisation checklist below; the Godot equivalents are in `asset_audit.gd` budgets |

| Repo | Before | Gap for this pipeline | Now |
| --- | --- | --- | --- |
| blender-mcp fork (v1.1.3) | scene info, exec code, Poly Haven, Rodin (Sketch/Raw only) | 15 s socket timeout (real cleanup/export runs die); no screenshot tool (the runbook asks for screenshots at every step); image-URL Rodin path crashed; no Tripo/Meshy; no way to run a script file with a config | v1.2.0: 180 s configurable timeout, `get_viewport_screenshot`, `run_script_file` + `list_pipeline_scripts`, Tripo/Meshy/Rodin API tools, Rodin `tier`/`mesh_mode`, URL bug fixed, `game_asset_pipeline` prompt |
| game-dev-starter-kit | 2D Go/Ebitengine skills: router, Nano Banana, Lyria, sprite animation, swarm coding | no 3D at all | `pipeline3d/` + a `blender-godot-pipeline` skill; the router sends 3D requests there; concept images reuse the kit's `banana.py` |

## 2. Corrections and challenges

Numbered so you can cite them. "Unverified" means it happened after my training data or
can't be checked from here, not that it is wrong.

1. **Unverifiable product claims.** GPT-6 Astra, Tripo P2 and Smart UV, Seedance 2.5,
   Unreal Engine 5.8, Hi3D Agent: all dated Sept 2026 in your sources, after my knowledge.
   The pipeline doesn't depend on any of them: Tripo options pass through unchanged, and
   everything else is local.
2. **The view counts and dates in the transcript JSONs are the transcribing model's output.**
   Option C already warned about this for the Gemini thread; the same applies here. Don't cite them.
3. **Blueprint prompt 1 repacks UVs** (`pack_islands(margin=0.015)`). On a textured
   generated mesh this scrambles the texture mapping. `cleanup_for_godot.py` reports UV health
   and only repacks when you set `pack_uvs: true` (untextured meshes).
4. **Blueprint prompt 3 uses Godot 3 names.** `VisibilityNotifier3D` → Godot 4's
   `VisibleOnScreenNotifier3D`, and that only reports visibility; it does no culling. Godot 4
   culling = `OccluderInstance3D` + project occlusion culling, plus `visibility_range_*` for
   distance/HLOD. "PCF5" is a Godot 3 shadow filter; Godot 4 uses the
   `rendering/lights_and_shadows/positional_shadow/soft_shadow_filter_quality` setting.
5. **"Convex hulls rather than trimesh for static environment geometry" is backwards for
   Godot.** Static level geometry is fine with trimesh (`-colonly`, ConcavePolygonShape3D).
   Convex is needed for moving bodies and cheap props. `export_for_godot.py` offers both.
6. **"Zero clipping" from Data Transfer weights is an overclaim.** Copied weights stop
   garments from tearing away, but loose cloth still clips at extreme poses. Fit garments
   tight, delete hidden body faces under them, or add corrective shape keys.
7. **ARKit has exactly 52 blendshapes**, not "52+".
8. **MetaHuman is an Unreal-first path.** Epic loosened MetaHuman licensing in 2025 to allow
   other engines (check the current licence before shipping), but the facial rig
   (RigLogic/DNA) and strand grooms don't run in Godot, and the meshes are heavy. For Godot, conform
   AI sculpts to **MPFB2** (MakeHuman, CC0 output) and rig with Mixamo/AccuRIG/Rigify. Use
   ARKit-named shape keys if you need faces.
9. **Kling doesn't give access to Seedance.** Kling is Kuaishou's competing model. Seedance
   is ByteDance's (Dreamina/CapCut, BytePlus ModelArk API, hosts like fal.ai; TopView appears
   to list it). Either works as a *reference* for animation, not as animation data.
10. **"Rideon"** in the request is read as **Hyper3D Rodin**, which Blender MCP already
    integrates.
11. **The Option C time claim holds**: about 5× hands-on, not 25×, because generating and
    judging still need you. The same goes for this pipeline: automation removes the
    mechanical 70-80% of the work (cleanup, rigging plumbing, export, import), and the
    judgement calls stay with you.
12. **The AI Evolution demo ran in a browser (WebGL), not in Blender or an engine.** Blender
    MCP made assets there. The Godot equivalent of "agent profiles and fixes lag" is Godot MCP
    + `asset_audit.gd` + the Godot profiler.
13. **Normal maps**: the blueprint is right. Blender and Godot are both OpenGL (Y+), so only
    flip green for Unreal.

## 3. Optimisation checklist for Godot (from the racer case + blueprint §4.2)

* Enclosed spaces: no shadow-casting DirectionalLight3D; use OmniLight3D/SpotLight3D with
  `distance_fade_enabled` and baked LightmapGI.
* Split big levels into chunks and turn on occlusion culling with `OccluderInstance3D`.
  Enable mesh LODs on import (Godot generates them automatically).
* Cache static UI (minimaps) in a SubViewport or texture; update only the moving markers.
* Physics interpolation: Godot 4.4 has `physics/common/physics_interpolation`. Turn it on
  instead of hand-rolled smoothing.
* Budgets enforced by `asset_audit.gd`: characters ≤ 25k tris, props ≤ 8k, textures ≤ 2048 px,
  ≤ 128 bones. Edit `BUDGET` to taste.

## 4. What stays manual, and why

| Step | Why | Time |
| --- | --- | --- |
| Picking the concept image | taste; the 6-point pass list makes it quick | 5 min |
| Mixamo / AccuRIG | no public API | 5-10 min per character |
| Downloading Mixamo clips | no public API | ~1 min per clip |
| Judging generated meshes (hands, armpits) | generators fail here most | 2 min per variant |
| Final animation polish | procedural and video-derived clips are first passes | varies |
