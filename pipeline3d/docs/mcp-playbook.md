# MCP playbook: driving Blender and Godot from Claude

Use this when you want Claude Desktop or Claude Code to run the pipeline in the live
apps, where you can watch it work, instead of the headless `forge.py`. The prompts are
copy-paste ready. Swap `<...>` for your paths.

## Setup (≈ 15 min)

1. **Blender add-on**: download `addon.py` from
   [sphilius/blender-mcp](https://github.com/sphilius/blender-mcp) (this fork adds the
   screenshot, script and API tools) → Blender → Edit → Preferences → Add-ons → ▾ →
   *Install from Disk* → enable → N-panel → **BlenderMCP** → *Connect to MCP server*.
2. **Godot MCP** (optional): clone and build
   [Coding-Solo/godot-mcp](https://github.com/Coding-Solo/godot-mcp)
   (`npm install && npm run build`). Set `GODOT_PATH` to your Godot executable.
3. **Claude config**: copy [`../mcp/claude_desktop_config.json`](../mcp/claude_desktop_config.json)
   (Claude Desktop → Settings → Developer → Edit Config) or
   [`../mcp/mcp.json`](../mcp/mcp.json) (Claude Code, saved as `.mcp.json` in your project).
   Fill in the paths and any API keys, then restart Claude.

**Check prompt:**
> Check my MCP connections without changing anything: (1) Blender: get_scene_info, report the
> Blender version, whether Hyper3D Rodin is enabled, and list_pipeline_scripts. (2) Godot, if
> connected: list your tools and my Godot version.

Tool names differ between Godot MCP servers. Always tell Claude to list the tools first.

## Prompts by stage

### 1. Generate a body
> Using Blender MCP: generate a 3D model from `<refs/body_front.png>` with
> generate_3d_via_api (provider tripo, options {"face_limit": 15000, "quad": true, "texture": false}).
> Poll every 10 s until done, import it as "character_raw", then take a viewport screenshot
> from the front and side. Report the object names, triangle count and size in metres.
> Don't clean, decimate or rig yet.

Rodin alternative: use generate_hyper3d_model_via_images with tier "Gen-2" and mesh_mode "Quad".

### 2. Clean it
> Using Blender MCP run_script_file("cleanup_for_godot.py", {"import_path": null,
> "export_path": "<~/game/export/character.glb>", "target_tris": 12000, "target_height_m": 1.78,
> "origin": "FEET", "remove_floaters_below": 0.02}). Show me the report and a front + side
> screenshot. Flag anything with non_manifold_edges > 300 or pieces > 3.

### 3a. Quadruped rig + clips
> run_script_file("quadruped_rig.py", {"clip_prefix": "wolf_", "export_path": "<~/game/export/wolf.glb>"}).
> Then run render_preview.py for the side view on clips wolf_walk frame 6 and wolf_attack frame 39
> and show me both. If the legs bend the wrong way or the bones miss the legs, change the
> landmarks override (fractions of the bounding box) and rerun.

### 3b. Humanoid via Mixamo
> Export the cleaned character as FBX for Mixamo (Selected Objects, Path Mode Copy, embed
> textures, Apply Scalings FBX All) to `<handoff/character_for_mixamo.fbx>`, then tell me the
> Mixamo steps. I'll put the rigged file at `<incoming/character_rigged.fbx>` and the clips in
> `<incoming/clips/>`.

After you download the clips:
> run_script_file("merge_clips.py", {"character_path": "<incoming/character_rigged.fbx>",
> "clips_dir": "<incoming/clips>", "rename": {"standing_idle": "idle", "walking": "walk"},
> "export_path": "<export/character.glb>"}). Report the clips and any bone-name warnings.

### 3c. Clothing and armour
> With the rigged body in the scene, import `<incoming/jacket_raw.glb>`, run
> cleanup_for_godot.py on it with target_height_m null and origin "KEEP", fit it to the body
> in rest pose, then run transfer_weights.py with body "<Body mesh name>" and targets
> ["<Jacket>"]. Pose the armature at 45° shoulder and knee bends and show me a screenshot.

### 4. Animate from a reference video (Stefan's Seedance workflow)
> I've saved reference clips of the wolf in `<refs/motion/>` (walk, attack, death). The wolf
> is rigged with quadruped_rig.py. For each clip: describe the key poses and their timing at
> 30 fps, then key the pose bones over Blender MCP (rotation_euler, XYZ) on an action named
> wolf_<clip>, in place, starting at frame 0, with the contact frames where the video shows
> them. Push each action to its own NLA track. After each clip, render_preview the side view
> at 3 key frames and compare with the video.

### 5. Export and drop into Godot
> run_script_file("export_for_godot.py", {"export_path": "<export/wolf.glb>",
> "copy_to": "<~/pipeline3d_game/assets>"}). Then with Godot MCP: run the project's asset
> viewer scene and return the debug output. List every `[pipeline_import]` line.

### 6. Godot audit (Godot MCP or terminal)
> Run `godot --headless --path <game> -s res://tools/asset_audit.gd -- res://assets`
> and summarise errors and warnings per asset. Suggest fixes in pipeline terms (which script
> and which CONFIG value).

## Karambit benchmark (from `2026-09-23-karambit-benchmark-runbook`)

| Runbook step | Now |
| --- | --- |
| 0.3 Blender MCP | Install this fork's `addon.py` so `run_script_file` and the screenshot tool exist |
| 3 Rodin body | Prompt 1 above (Tripo or Rodin `mesh_mode: "Quad"`), or `forge.py manifests/fighter.json` |
| 4 Clean the body | Prompt 2, or it happens inside forge |
| 5 Build the karambit | `run_script_file("build_karambit.py")`: 576 tris, χ = 0, origin at the ring centre (tested) |
| 6 Mixamo | Prompt 3b; forge's rig stage stops here with the same steps |
| 7 Into Godot | `export_for_godot.py` with `copy_to` + Godot MCP, or forge's `godot` stage |
| 8-10 Tune, score, decide | Unchanged. That part is your judgement |

The shaders and `benchmark_room.gd` from the benchmark kit go into `shaders/` and `scripts/`
of a project made from `godot_template/`. The folder layout matches.
