# Tool matrix: free, open-source and free-trial options per stage

Prices and free tiers change monthly, so this lists **what each tool is for and how it plugs
in**, not what it costs. Check each site's pricing page before you commit credits.
Rule of thumb: spend credits only on the stage where AI saves you the most (the 3D generation);
keep rigging, cleanup, animation wiring and export local and free.

Legend: 🆓 free / open source · 🎟 free credits or trial, then paid · 🖐 manual web/desktop step
(forge stops and tells you what to do) · 🤖 automated by this pipeline.

## 1. Concept and reference images

| Tool | Access | Use it for | Pipeline hook |
| --- | --- | --- | --- |
| Nano Banana (Gemini image models) | 🎟 Google AI Studio free tier / Google AI Pro / Vertex | Turnarounds, A-pose references, part sheets; strong character consistency with reference images | 🤖 `concept.tool: "banana"` runs `.agents/skills/nano-banana/scripts/banana.py` |
| FLUX.1 [schnell] | 🆓 open weights (local GPU, ComfyUI) or free HF Spaces | Unlimited local iterations | 🖐 save to `concept.image` |
| Bing Image Creator, Midjourney, Ideogram | 🎟 | Style targets and key art | 🖐 |

Prompt rules for images that feed 3D generators (from the karambit runbook, which tested them):
one figure, front view, A-pose with arms 45° down, hands open, **flat light, no cast shadows**,
neutral grey clay, plain background, no weapon, no loose cloth. Style goes in the engine
shader, not the geometry. Keep artist and franchise names out of prompts for shipped assets.

## 2. Image/text → 3D mesh

| Tool | Access | Strengths | Pipeline hook |
| --- | --- | --- | --- |
| **Tripo** (tripo3d.ai) | 🎟 free credits monthly; API key | Quad / low-poly options, batches of variants, auto-rig + animation retarget API. Your sources report a P2 model with batch-of-4 low-poly and Smart UV (Sept 2026); I couldn't verify those features | 🤖 `gen3d.py --provider tripo`, `generate_3d_via_api` |
| **Meshy** (meshy.ai) | 🎟 free credits monthly; API on paid plans | Text/image → 3D, remesh to quads, humanoid auto-rig and an animation library over the API | 🤖 `gen3d.py --provider meshy` |
| **Hyper3D Rodin** (hyper3d.ai) | 🎟 Blender MCP add-on has a shared daily free-trial key (it was at 0 balance when checked on 2026-09-24); own key via hyper3d.ai or fal.ai | High-detail single objects, Quad mesh mode, Gen-2 tier | 🤖 Blender MCP `generate_hyper3d_model_via_*` (now with `tier`, `mesh_mode`), `gen3d.py --provider rodin` |
| Hi3D | 🎟 | Your sources show very detailed 2K meshes and an agent that splits concepts into parts (unverified by me) | 🖐 download GLB → `generate.file` |
| Hunyuan3D 2.x (Tencent) | 🆓 open weights, local GPU (~12-16 GB VRAM for shape+texture) or free HF Space; its licence excludes some regions (EU, UK, South Korea) so read it | Good free image-to-3D with textures | 🖐 run locally → `generate.file` |
| TRELLIS (Microsoft) | 🆓 MIT, local GPU or HF Space | Clean geometry from one image | 🖐 → `generate.file` |
| Poly Haven | 🆓 CC0 | Real-world scanned props, textures, HDRIs | 🤖 Blender MCP `download_polyhaven_asset` |
| Procedural Blender scripts | 🆓 | Weapons, mechanisms, modular kits, anything needing exact holes, pivots or dimensions | 🤖 `generate.procedural` |

Generation rules: **one part per job** (body, then each garment/armour piece, then props);
ask for quads and a face budget up front (characters 10-25k, props 1-8k); generate 3-4
variants and keep the one with the cleanest hands and armpits; always run cleanup before rigging.

## 3. Retopology, UVs and textures

| Tool | Access | Use |
| --- | --- | --- |
| `cleanup_for_godot.py` | 🆓 🤖 | weld / fill / floaters / decimate / scale / origin (not true retopology) |
| Blender QuadriFlow / Remesh / Decimate | 🆓 built in | quick quad remesh for props |
| Quad Remesher (Exoside) | 🎟 trial, then paid | best automatic quad retopology for characters |
| Instant Meshes | 🆓 open source | good free alternative for organic retopology |
| Tripo Smart UV | 🎟 (reported in your sources; unverified) | semantic seams on low-poly meshes, including your own uploads |
| `bake_diffuse.py` | 🆓 🤖 | move colour/normals from the high-poly generator output to the clean mesh |
| `udim_to_01.py` | 🆓 🤖 | UDIM → single 0-1 tile for engines |

## 4. Rigging

| Tool | Access | Rigs | Pipeline hook |
| --- | --- | --- | --- |
| **Mixamo** (Adobe) | 🆓 with an Adobe ID | Humanoids only; 65-bone standard skeleton; huge free animation library | 🖐 `rig.method: "mixamo"` (forge exports the FBX to upload and waits for the rigged file) |
| **AccuRIG** (Reallusion) | 🆓 desktop app | Humanoids including fingers; pairs with ActorCore motions | 🖐 `rig.method: "accurig"` |
| Meshy / Tripo auto-rig | 🎟 API | Humanoids (Tripo lists more rig types; check current docs) | 🤖 `rig.method: "meshy"` / `"tripo"` |
| **`quadruped_rig.py`** | 🆓 🤖 | 31-bone quadruped game rig + 4 procedural clips | 🤖 `rig.method: "quadruped"` |
| Rigify (Blender) | 🆓 built in | Human, cat, wolf, horse, bird and shark metarigs; for export keep only DEF bones | manual |
| UniRig (VAST, the team behind Tripo) | 🆓 open source research code, GPU | Auto-rigs arbitrary meshes including animals | 🖐 → `rig.method: "manual"` |
| `transfer_weights.py` | 🆓 🤖 | Clothing / armour skinned from the body's weights | run after the body is rigged |

## 5. Animation and motion

| Source | Access | Output | Pipeline hook |
| --- | --- | --- | --- |
| **Mixamo** library | 🆓 | FBX per clip, 30 fps; tick *In Place* for locomotion | 🖐 drop into `incoming/clips/` → 🤖 `merge_clips.py` |
| **ActorCore** (Reallusion) | 🎟 some free motions, most paid | Mocap-quality clips; apply via AccuRIG / iClone | 🖐 → clips folder |
| Meshy animation library | 🎟 API | Clips on a Meshy-rigged character | 🤖 `animations.method: "meshy"` |
| Tripo retarget presets | 🎟 API | `preset:walk`, `preset:run`, ... | 🤖 `animations.method: "tripo"` |
| Rokoko Vision | 🎟 free tier | Single-camera video → humanoid mocap FBX | 🖐 → clips folder |
| DeepMotion Animate 3D | 🎟 free monthly credits | Video → humanoid FBX/GLB | 🖐 → clips folder |
| FreeMoCap | 🆓 open source | Multi-webcam mocap | 🖐 |
| GVHMR / WHAM | 🆓 research code, GPU | Video → SMPL body motion (needs a retarget to your rig) | advanced |
| Quaternius animation packs | 🆓 CC0 | Ready humanoid clips for prototypes | 🖐 → clips folder |
| `quadruped_rig.py` clips | 🆓 🤖 | idle / walk / attack / death first passes | automatic |

### Video models as motion references (Seedance, Kling, ...)

Video generators give you a **reference to animate from**, not animation data. The workflow
in your Stefan 3D AI short is: generate 3-4 reference clips of the motion you want, then have
a coding agent key the rig over Blender MCP while looking at them (about 21 min of agent time
there). Humanoid clips can also go through Rokoko Vision / DeepMotion to become real mocap.

* **Seedance** is ByteDance's model. You can reach it in ByteDance's own apps (Dreamina /
  CapCut), through the BytePlus ModelArk API, and through third-party hosts such as fal.ai.
  **TopView** lists Seedance among its models as far as I know; check the model picker.
* **Kling** is Kuaishou's own model and a competitor. Kling does not give you Seedance, but it
  works for the same job (image-to-video from your character turnaround).
* Prompt one behaviour per clip on a plain background, locked-off side camera, full body in
  frame, 3-5 s, e.g. "side view of the grey wolf from the reference, trotting in place on a
  treadmill, camera static, plain grey background".

## 6. Engine side (Godot 4)

| Tool | Access | Use |
| --- | --- | --- |
| `godot_template/` | 🆓 🤖 | import plugin (loop flags by clip name), asset viewer, controller, audit, smoke test |
| Godot MCP (Coding-Solo/godot-mcp) | 🆓 open source, Node.js | agent launches the editor, runs scenes, reads debug output, creates scenes/nodes |
| Godot's built-in retargeting | 🆓 | Import → Skeleton → Bone Map with `SkeletonProfileHumanoid` lets Mixamo clips drive any humanoid rig |
| MPFB2 (MakeHuman for Blender) | 🆓 CC0 output | parametric human base mesh for conforming AI sculpts (Godot-friendly MetaHuman alternative) |
