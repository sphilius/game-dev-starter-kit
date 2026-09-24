"""
test_blender_stages.py - run every Blender stage script on fixtures and assert on the reports.

    blender -b --factory-startup -P pipeline3d/tests/test_blender_stages.py -- out_dir=/tmp/p3d

Produces, in out_dir:
    fixtures/        quadruped_raw.glb, humanoid_raw.glb
    export/          character.glb, karambit.glb, wolf.glb, wolf_geared.glb, wolf_merged.glb, crate.glb
    previews/        PNG renders of the results
and exits non-zero on the first failed check.
"""

import bpy
import json
import os
import runpy
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "blender")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(dict(a.split("=", 1) for a in argv if "=" in a).get("out_dir", "/tmp/p3d"))
EXPORT = os.path.join(OUT, "export")
FX = os.path.join(OUT, "fixtures")
results = {}


def stage(name):
    return runpy.run_path(os.path.join(SCRIPTS, name + ".py"))


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)


def check(label, cond, detail=""):
    print(f"[test] {'PASS' if cond else 'FAIL'} {label} {detail}")
    if not cond:
        print(json.dumps(results, indent=1, default=str))
        sys.exit(1)


# --- fixtures (separate process: it exits when done)
subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", "-P", os.path.join(HERE, "make_fixtures.py"),
                "--", f"out_dir={FX}"], check=True, stdout=subprocess.DEVNULL)

# --- 1. cleanup: fragmented, split, wrongly scaled humanoid
r = stage("cleanup_for_godot")["main"]({
    "import_path": os.path.join(FX, "humanoid_raw.glb"), "export_path": os.path.join(EXPORT, "character.glb"),
    "target_tris": 3000, "target_height_m": 1.78, "origin": "FEET", "remove_floaters_below": 0.05})
results["cleanup"] = r
check("cleanup ok", r["ok"], r.get("error", ""))
check("cleanup height 1.78", abs(r["dimensions_m"][2] - 1.78) < 0.01, r["dimensions_m"])
check("cleanup tri budget", r["tris"] <= 3000, r["tris"])
check("cleanup dropped floating crumb", r["floaters_removed"] == 1, r["floaters_removed"])

# --- 2. procedural karambit
clear()
r = stage("build_karambit")["main"]({"export_path": os.path.join(EXPORT, "karambit.glb")})
results["karambit"] = r
check("karambit watertight with one hole", r["ok"] and r["chi"] == 0, f"chi={r['chi']} tris={r['tris']}")

# --- 3. quadruped auto-rig + clips
clear()
r = stage("quadruped_rig")["main"]({"import_path": os.path.join(FX, "quadruped_raw.glb"), "clip_prefix": "wolf_",
                                   "export_path": os.path.join(EXPORT, "wolf.glb")})
results["quadruped"] = r
check("quadruped rigged", r["ok"] and r["bones"] == 31, f"bones={r['bones']} skin={r['skinning']}")
check("quadruped 4 clips", [c["name"] for c in r["clips"]] == ["wolf_idle", "wolf_walk", "wolf_attack", "wolf_death"])
check("quadruped faces -Y", r["bounds_m"]["length"] > r["bounds_m"]["width"])

# --- 4. weight transfer: a collar + saddle "garment" on the rigged wolf
body = bpy.data.objects[r["mesh"]]
arm = bpy.data.objects[r["armature"]]
head = arm.data.bones["neck_01"].head_local
bpy.ops.mesh.primitive_torus_add(major_radius=0.16, minor_radius=0.035, location=head, rotation=(1.2, 0, 0))
collar = bpy.context.object
collar.name = "Collar"
spine = arm.data.bones["spine_02"].head_local
bpy.ops.mesh.primitive_cube_add(size=0.3, location=(spine.x, spine.y, spine.z + 0.18))
saddle = bpy.context.object
saddle.name = "Saddle"
saddle.scale = (1.3, 1.5, 0.3)
r = stage("transfer_weights")["main"]({"body": body.name, "targets": ["Collar", "Saddle"],
                                       "export_path": os.path.join(EXPORT, "wolf_geared.glb")})
results["weights"] = r
check("weights transferred", r["ok"], r.get("targets"))
check("collar follows neck/head bones",
      any(g.name.startswith(("neck", "spine_03", "head")) for g in collar.vertex_groups if
          any(vg.group == g.index and vg.weight > 0.3 for v in collar.data.vertices for vg in v.groups)))

# --- 5. UDIM -> 0-1
clear()
bpy.ops.mesh.primitive_plane_add()
plane = bpy.context.object
for d in plane.data.uv_layers.active.data:
    d.uv.x += 1.0                      # whole mesh on tile 1002
bpy.ops.mesh.primitive_plane_add(location=(3, 0, 0))
r = stage("udim_to_01")["main"]({})
results["udim"] = r
check("udim shifted", all(0 <= d.uv.x <= 1 for d in plane.data.uv_layers.active.data), r)

# --- 6. bake: raw textured quadruped -> decimated copy
clear()
bpy.ops.import_scene.gltf(filepath=os.path.join(FX, "quadruped_raw.glb"))
high = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
mat = bpy.data.materials.new("fur")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
noise = nt.nodes.new("ShaderNodeTexNoise")
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.25, 0.18, 0.12, 1)
ramp.color_ramp.elements[1].color = (0.8, 0.75, 0.7, 1)
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
high.data.materials.clear()
high.data.materials.append(mat)
low = high.copy()
low.data = high.data.copy()
low.name = "WolfLow"
bpy.context.scene.collection.objects.link(low)
low.data.materials.clear()
while low.data.uv_layers:
    low.data.uv_layers.remove(low.data.uv_layers[0])
dec = low.modifiers.new("d", 'DECIMATE')
dec.ratio = 0.3
with bpy.context.temp_override(object=low, active_object=low, selected_objects=[low]):
    bpy.ops.object.modifier_apply(modifier="d")
r = stage("bake_diffuse")["main"]({"high": high.name, "low": low.name, "size": 256,
                                   "out_dir": os.path.join(OUT, "bakes")})
results["bake"] = r
check("bake wrote color map", r["ok"] and os.path.exists(r["color"]), r)

# --- 7. merge clips: split wolf.glb into one file per clip, then merge them back
clear()
clip_dir = os.path.join(OUT, "clips")
os.makedirs(clip_dir, exist_ok=True)
bpy.context.scene.render.fps = 30          # glTF import rescales keys to the scene fps
for clip in ["wolf_idle", "wolf_walk", "wolf_attack", "wolf_death"]:
    clear()
    bpy.ops.import_scene.gltf(filepath=os.path.join(EXPORT, "wolf.glb"))
    arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    for t in list(arm.animation_data.nla_tracks):
        if t.name != clip:
            arm.animation_data.nla_tracks.remove(t)
    for o in bpy.context.scene.objects:
        o.select_set(o.type == 'ARMATURE')
    bpy.ops.export_scene.gltf(filepath=os.path.join(clip_dir, clip.replace("wolf_", "Wolf ") + ".glb"),
                              export_format='GLB', use_selection=True, export_animation_mode='NLA_TRACKS')
clear()
r = stage("merge_clips")["main"]({"character_path": os.path.join(EXPORT, "wolf.glb"), "clips_dir": clip_dir,
                                 "rename": {"wolf_idle": "idle", "wolf_walk": "walk"},
                                 "export_path": os.path.join(EXPORT, "wolf_merged.glb")})
results["merge"] = r
names = sorted(c["name"] for c in r["clips"])
check("merged 4 clips with renames", r["ok"] and "idle" in names and "walk" in names and len(names) == 4, names)
lengths = {c["name"]: c["frames"][1] - c["frames"][0] for c in r["clips"]}
check("merged clip lengths preserved", abs(lengths["idle"] - 75) < 1.01 and abs(lengths["walk"] - 25) < 1.01, lengths)

# --- 8. export a static prop with convex collision
clear()
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
bpy.context.object.name = "Crate"
r = stage("export_for_godot")["main"]({"export_path": os.path.join(EXPORT, "crate.glb"), "collision": "convex"})
results["export"] = r
check("prop exported with collision helper", r["collision_helpers"] == ["Crate-convcolonly"], r)

# --- previews for human/agent review
clear()
stage("render_preview")["main"]({"import_path": os.path.join(EXPORT, "character.glb"),
                                 "out_dir": os.path.join(OUT, "previews"), "prefix": "character",
                                 "views": ["front", "side"], "resolution": 384})

with open(os.path.join(OUT, "test_report.json"), "w") as fh:
    json.dump(results, fh, indent=1, default=str)
print("[test] ALL BLENDER STAGES PASSED ->", OUT)
sys.exit(0)
