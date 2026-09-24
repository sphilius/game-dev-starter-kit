"""
export_for_godot.py - final GLB export tuned for Godot 4's importer.

Handles rigged characters (armature + skinned meshes + NLA clips) and static props.

Godot conventions applied:
  * binary .glb, textures embedded, +Y up, metres
  * one animation per NLA track (track name = animation name)
  * optional collision helpers using Godot's name suffixes:
      <name>-colonly      invisible trimesh collision (static level geometry)
      <name>-convcolonly  invisible convex collision (props, pickups)
    Godot turns these into StaticBody3D + CollisionShape3D on import.
  * reports what Godot will see: meshes, tris, bones, animations and their lengths
Loop modes are set on the Godot side by the pipeline_import plugin (names listed in
res://addons/pipeline_import/loop_names.txt), because glTF has no loop flag.
"""

import bpy
import bmesh
import json
import os
import sys

CONFIG = {
    "import_path": None,           # optional GLB/FBX to load first (headless use); None = current scene
    "clear_scene": True,           # only used with import_path
    "export_path": "~/game/export/asset.glb",
    "objects": [],                 # names; [] = everything visible in the scene
    "collision": None,             # None | "convex" | "trimesh"
    "collision_decimate_ratio": 0.2,   # simplify the collision copy (convex ignores detail anyway)
    "fps": 30,
    "export_animations": True,
    "copy_to": None,               # e.g. /path/to/godot_project/assets - also copy the GLB there
}


def _make_collision(src, kind, ratio):
    bm = bmesh.new()
    if kind == "convex":
        for v in src.data.vertices:          # hull of the points only, original faces dropped
            bm.verts.new(v.co)
        res = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        loose = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    else:
        bm.from_mesh(src.data)
    mesh = bpy.data.meshes.new(src.name + "_col")
    bm.to_mesh(mesh)
    bm.free()
    suffix = "-convcolonly" if kind == "convex" else "-colonly"
    col = bpy.data.objects.new(src.name + suffix, mesh)
    bpy.context.scene.collection.objects.link(col)
    col.matrix_world = src.matrix_world.copy()
    if kind == "trimesh" and ratio < 1.0:
        mod = col.modifiers.new("Decimate", 'DECIMATE')
        mod.ratio = ratio
        with bpy.context.temp_override(object=col, active_object=col, selected_objects=[col]):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    return col


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    scene = bpy.context.scene
    scene.render.fps = int(c["fps"])          # set before importing: importers rescale keys to scene fps
    scene.render.fps_base = 1.0
    if c.get("import_path"):
        if c.get("clear_scene"):
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o, do_unlink=True)
        path_in = os.path.abspath(os.path.expanduser(c["import_path"]))
        if path_in.lower().endswith(".fbx"):
            bpy.ops.import_scene.fbx(filepath=path_in)
        else:
            bpy.ops.import_scene.gltf(filepath=path_in)
        # glTF import puts clips at frame 1; move every strip to 0 so exported clips start at t=0
        for o in scene.objects:
            if o.type == 'ARMATURE' and o.animation_data:
                for t in o.animation_data.nla_tracks:
                    for s in t.strips:
                        s.frame_start_ui = 0      # moves the strip, keeping its length

    objs = [bpy.data.objects[n] for n in c["objects"]] if c.get("objects") else \
        [o for o in scene.objects if o.visible_get() and o.type in ('MESH', 'ARMATURE', 'EMPTY')]
    extra = []
    if c.get("collision"):
        for o in [o for o in objs if o.type == 'MESH' and not o.find_armature()]:
            extra.append(_make_collision(o, c["collision"], float(c["collision_decimate_ratio"])))
    objs += extra

    for o in scene.objects:
        o.select_set(o in objs)
    arm = next((o for o in objs if o.type == 'ARMATURE'), None)
    bpy.context.view_layer.objects.active = arm or objs[0]

    path = os.path.abspath(os.path.expanduser(c["export_path"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    has_nla = bool(arm and arm.animation_data and arm.animation_data.nla_tracks)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
        export_animations=bool(c["export_animations"]),
        export_animation_mode='NLA_TRACKS' if has_nla else 'ACTIONS',
        export_force_sampling=True, export_def_bones=False)

    meshes = [o for o in objs if o.type == 'MESH']
    report = {
        "ok": True, "export_path": path, "bytes": os.path.getsize(path),
        "meshes": [{"name": o.name, "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                    "materials": len(o.data.materials)} for o in meshes],
        "bones": len(arm.data.bones) if arm else 0,
        "animations": [{"name": t.name,
                        "seconds": round(sum(s.frame_end - s.frame_start for s in t.strips) / c["fps"], 3)}
                       for t in (arm.animation_data.nla_tracks if has_nla else [])],
        "collision_helpers": [o.name for o in extra],
    }
    for o in extra:
        bpy.data.objects.remove(o, do_unlink=True)
    if c.get("copy_to"):
        import shutil
        dest_dir = os.path.abspath(os.path.expanduser(c["copy_to"]))
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(path))
        shutil.copy2(path, dest)
        report["copied_to"] = dest
    print("[export]", json.dumps(report, indent=1))
    return report


def _parse_cli(cfg):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    i = 0
    while i < len(argv):
        if argv[i] == "--config":
            with open(os.path.expanduser(argv[i + 1])) as fh:
                cfg.update(json.load(fh))
            i += 2
            continue
        if "=" in argv[i]:
            k, v = argv[i].split("=", 1)
            try:
                cfg[k] = json.loads(v)
            except ValueError:
                cfg[k] = v
        i += 1
    return cfg


if __name__ == "__main__":
    # Headless: open a .blend first:  blender -b scene.blend -P export_for_godot.py -- export_path=...
    _result = main(_parse_cli(dict(CONFIG)))
    print("PIPELINE_RESULT " + json.dumps(_result))
    if bpy.app.background:
        sys.exit(0 if _result.get("ok") else 1)
