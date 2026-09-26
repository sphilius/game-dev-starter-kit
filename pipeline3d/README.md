# pipeline3d: AI-assisted 3D asset pipeline, Blender → Godot 4

Turn a prompt or a concept image into a rigged, animated, collision-ready `.glb` that
Godot 4 imports with the right clip lengths and loop flags. Most of it runs unattended.
The stages that need a human are the web-only apps (Mixamo, AccuRIG) and judging the
concept image, and those stop with exact instructions.

```
 concept image ──► 3D generation ──► cleanup ──► rig ──► animate ──► export ──► Godot
 Nano Banana /      Tripo / Meshy /    weld, fill,  quadruped   procedural /  GLB +Y up,  headless import,
 Flux / manual      Rodin / Hunyuan3D  floaters,    auto-rig /  Mixamo /      NLA clips,  loop flags, audit,
                    or procedural      decimate,    Mixamo /    ActorCore /   collision   controller smoke test
                    Blender script     scale, origin AccuRIG /  mocap / API
                                                    API rig
```

Everything is plain Python and GDScript: **Blender 4.2+**, **Godot 4.3+**, and **Python 3.10+**
(or `uv`). The cloud generators are optional and need your own keys.

---

## What's in here

| Path | What it is |
| --- | --- |
| `forge.py` | Orchestrator. One JSON manifest per asset; resumable stages; stops with instructions at manual steps |
| `gen3d.py` | CLI for Tripo / Meshy / Rodin: generate, poll, download, auto-rig, animate. Standard library only |
| `blender/*.py` | Stage scripts. Each has a `CONFIG` dict and a `main(config) -> report` and runs 3 ways (below) |
| `forge_server.py` | Local HTTP API around forge (token auth, manifest whitelist, job queue, uploads for manual steps, previews) |
| `forge_studio/` | **Forge Studio** web app: describe a model by text or voice, Gemini writes the manifest, one button builds it ([README](forge_studio/README.md)) |
| `godot_template/` | Godot 4 project: import plugin (loop flags, summary), asset viewer, character controller, audit and smoke-test tools |
| `manifests/` | Example assets: `karambit`, `fighter` (Mixamo), `wolf` (quadruped), `crate` (prop), `hero_api_rig` (hands-off API rig) |
| `mcp/` | Claude Desktop / Claude Code config for Blender MCP + Godot MCP |
| `docs/` | Tool matrix (free/trial options per stage), MCP prompt playbook, and the source-document analysis |
| `tests/` | End-to-end tests on procedural fixtures. No keys or credits needed |

### Blender stage scripts

| Script | Stage | What it guarantees |
| --- | --- | --- |
| `cleanup_for_godot.py` | cleanup | one joined mesh, welded, holes ≤ 4 sides filled, floaters removed, ≤ tri budget, real-world height, origin at feet; report with χ, non-manifold edges, UV tiles |
| `build_lowpoly_creature.py` | generate (procedural) | faceted low-poly wolf/boar/bear/deer/cat, ~900 tris, watertight, flat colours. Legs follow real stance anatomy (toe-walking, hoofed, flat-footed: elbow back, knee forward, hock back) and the joint positions are stored on the mesh so `quadruped_rig.py` puts bones exactly at the joints. Zero cost, no keys |
| `build_karambit.py` | generate (procedural) | 576-tri watertight karambit, exactly one ring hole (χ = 0), origin = ring centre = swivel pivot |
| `quadruped_rig.py` | rig + animate | 31-bone game skeleton, skinned (bone heat, distance fallback, ≤ 4 influences), `idle` 2.5 s / `walk` 0.833 s / `attack` 1.7 s (bite at 1.3 s) / `death` 1.333 s, 30 fps, in place |
| `transfer_weights.py` | rig (clothing) | garments/armour get the body's weights (Data Transfer, nearest-face interpolated), parented, normalized |
| `merge_clips.py` | animate | Mixamo / ActorCore / mocap clip files → one armature, one NLA track per clip, optional root-motion strip |
| `udim_to_01.py` | UV fix | UDIM tiles 1002+ shifted back into 0-1, one material per tile |
| `bake_diffuse.py` | texture | high → low colour (and optional normal) bake, Cycles, cage 0.01 |
| `export_for_godot.py` | export | GLB, +Y up, clips start at t = 0, `-convcolonly` / `-colonly` collision helpers, copy into the Godot project |
| `render_preview.py` | QA | orthographic front/side/back/¾ PNGs, optionally posed on a clip frame, without a viewport |

Three ways to run any of them:

```bash
# 1. From Claude over Blender MCP (live scene):    run_script_file("cleanup_for_godot.py", {"import_path": "..."})
# 2. In Blender: Scripting tab → Open → edit CONFIG → Run Script
# 3. Headless:
blender -b -P blender/cleanup_for_godot.py -- import_path=incoming/raw.glb target_tris=12000
blender -b -P blender/cleanup_for_godot.py -- --config my_config.json
```

---

## Quick start (≈ 20 min setup, then minutes per asset)

1. **Install** Blender 4.2+, Godot 4.3+ (standard build), Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).
   Check with `./pipeline3d/check_env_3d.sh`.
2. **Point the tools at your executables** (Windows PowerShell shown; use `export` on macOS/Linux):
   ```powershell
   $env:BLENDER = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
   $env:GODOT   = "C:\Tools\Godot_v4.4.1-stable_win64.exe"
   ```
3. **Make your game project** from the template: copy `godot_template/` to e.g. `~/pipeline3d_game`
   (the example manifests export there), open it once in Godot. It already has `shaders/`, `scripts/`,
   `assets/` and `scenes/`, so the karambit benchmark files drop straight in.
4. **Prove the chain works** (no keys needed; about 2 minutes):
   ```bash
   BLENDER=... GODOT=... ./pipeline3d/tests/run_all.sh
   ```
5. **Run a real asset**:
   ```bash
   python pipeline3d/forge.py pipeline3d/manifests/karambit.json    # procedural, fully automatic
   python pipeline3d/forge.py pipeline3d/manifests/wolf.json        # needs TRIPO_API_KEY (or set generate.file)
   python pipeline3d/forge.py pipeline3d/manifests/fighter.json     # stops at the Mixamo step with instructions
   python pipeline3d/forge.py pipeline3d/manifests/fighter.json --status
   ```
   Re-run the same command after a manual step and it resumes. `--from rig` redoes from a stage.
6. **Look at it**: open the Godot project and press F5. The asset viewer lines up every model in
   `res://assets` (Tab = next clip, arrows = orbit).
7. **(Optional) Agent control**: set up `mcp/` so Claude drives Blender and Godot directly
   (see [`docs/mcp-playbook.md`](docs/mcp-playbook.md)).

### Manifest cheat-sheet

```jsonc
{
  "name": "wolf",
  "concept":   {"tool": "banana", "prompt": "...", "out": "wolf_side.png"},   // or {"image": "path.png"}
  "generate":  {"provider": "tripo", "mode": "image", "options": {"face_limit": 10000, "quad": true}},
               // or {"procedural": "build_karambit.py", "config": {...}}  or {"file": "path.glb"}
  "cleanup":   {"target_tris": 8000, "target_height_m": 0.85, "remove_floaters_below": 0.02},  // false = skip
  "rig":       {"method": "quadruped" | "mixamo" | "accurig" | "tripo" | "meshy" | "none"},
  "animations":{"method": "procedural" | "clips_dir" | "tripo" | "meshy" | "none",
                "expect": ["idle", "walk"], "rename": {"standing_idle": "idle"}},
  "export":    {"collision": null | "convex" | "trimesh", "godot_project": "~/pipeline3d_game"}
}
```

Build outputs go to `pipeline3d/build/<name>/` (`refs/`, `incoming/`, `handoff/`, `work/`, `export/`,
`forge_state.json`, and `.forge/*.log` per Blender run).

---

## Which path for which asset

| Asset | Recommended path | Why |
| --- | --- | --- |
| Humanoid hero/NPC | concept → Tripo/Rodin (quad, 12-20k) → cleanup → **Mixamo** or **AccuRIG** → Mixamo/ActorCore clips | Best free humanoid rigs and the biggest free animation library |
| Humanoid, zero clicks | concept → **Meshy** image-to-3D → Meshy rig → Meshy animations (`hero_api_rig.json`) | Fully API-driven, costs credits, less control |
| Quadruped / creature | concept → Tripo → cleanup → **`quadruped_rig.py`** | Mixamo can't rig quadrupeds; procedural clips wire gameplay today and can be replaced later |
| Clothing / armour | generate each part separately → cleanup (`target_height_m: null`, `origin: KEEP`) → **`transfer_weights.py`** | Generated all-in-one characters clip and waste tris on hidden faces |
| Weapons, mechanisms, anything with holes or pivots | **procedural Blender script** (see `build_karambit.py`) | Generators fuse holes and misplace pivots; code is exact and repeatable |
| Stylized / low-poly animals, zero cost | **`build_lowpoly_creature.py`** preset → `quadruped` rig (`lowpoly_boar.json`) | No AI, no keys, 11 s from nothing to an animated asset in Godot |
| Props / set dressing | Meshy/Tripo text-to-3D → cleanup → export `collision: convex` | Cheapest path; Godot builds the StaticBody |
| Environments / HDRIs / textures | **Poly Haven** through Blender MCP | Free (CC0) and already game-scaled |

Engine rules the scripts enforce: in-place clips (the controller moves the body); 30 fps;
clips start at t = 0 so loops close exactly; Blender and Godot both use OpenGL (Y+) normal
maps, so no green flip (only Unreal needs one); never join or apply transforms on a mesh that
is already skinned.

---

## Testing

| Test | Covers | Runtime |
| --- | --- | --- |
| `tests/run_all.sh` | every Blender stage on fixtures → Godot headless import → audit → controller smoke test | ~2 min |
| `tests/test_forge.sh` | forge manifests: procedural karambit, auto-rigged wolf, humanoid through the Mixamo gate (simulated with FBX files) | ~2 min |
| `godot --headless --path <game> -s res://tools/asset_audit.gd` | per-asset tris, bones, clips, texture sizes, collision; exit 1 on errors | seconds |

Headless Godot prints `texture_2d_get ... Parameter "t" is null` while making thumbnails; that
comes from the dummy renderer and is harmless.

Last verified in a Linux sandbox with Blender 4.2.9 LTS and Godot 4.4.1. Not verified there:
the cloud generators (they need your keys; the endpoints and auth were checked), Mixamo and
AccuRIG (web/desktop apps), and the look of `get_viewport_screenshot` (the sandbox's virtual
display returns black frames).
