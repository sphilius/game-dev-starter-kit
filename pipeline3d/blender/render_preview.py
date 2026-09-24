"""
render_preview.py - orthographic QA renders (front / side / back / three-quarter) as PNGs.

Works headless (no viewport needed), so an agent can look at the result of every stage.
Uses Workbench with a matcap-like studio light and cavity, which shows topology problems
(holes, fused limbs, inverted normals) better than a textured render.

Optionally imports a file first (import_path) and can play an action to a given frame so
you can check a pose (action + frame).
"""

import bpy
import json
import os
import sys
from mathutils import Vector

CONFIG = {
    "import_path": None,           # None = render the current scene
    "clear_scene": False,
    "out_dir": "~/pipeline_previews",
    "prefix": "preview",
    "views": ["front", "side", "back", "three_quarter"],
    "resolution": 768,
    "color": "MATERIAL",           # MATERIAL | TEXTURE | SINGLE | OBJECT
    "action": None,                # name of an action to show (on the first armature)
    "frame": 1,
}

# View directions: camera looks FROM this vector toward the target. Blender front = -Y.
_VIEWS = {
    "front": Vector((0, -1, 0)),
    "back": Vector((0, 1, 0)),
    "side": Vector((1, 0, 0)),
    "left": Vector((-1, 0, 0)),
    "top": Vector((0, 0, 1)),
    "three_quarter": Vector((0.7, -0.7, 0.35)),
}


def _import(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"import_path not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"Unsupported format {ext}")


def _scene_bounds():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    found = False
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or obj.hide_render:
            continue
        ev = obj.evaluated_get(depsgraph)
        for corner in ev.bound_box:
            w = ev.matrix_world @ Vector(corner)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
            found = True
    if not found:
        return Vector((0, 0, 0)), 1.0
    return (lo + hi) / 2, max((hi - lo).length, 1e-3)


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    if c.get("clear_scene"):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    if c.get("import_path"):
        _import(os.path.abspath(os.path.expanduser(c["import_path"])))

    scene = bpy.context.scene
    if c.get("action"):
        arm = next((o for o in scene.objects if o.type == 'ARMATURE'), None)
        # glTF import renames actions to "<clip>_<armature>", so accept a prefix match
        act = bpy.data.actions.get(c["action"]) or next(
            (a for a in bpy.data.actions if a.name.startswith(c["action"])), None)
        if arm and act:
            arm.animation_data_create()
            arm.animation_data.action = act
    scene.frame_set(int(c.get("frame") or 1))

    scene.render.engine = 'BLENDER_WORKBENCH'
    shading = scene.display.shading
    shading.light = 'STUDIO'
    shading.color_type = c.get("color", "MATERIAL")
    shading.show_cavity = True
    shading.show_object_outline = True
    scene.display.shading.show_xray = False
    scene.render.resolution_x = scene.render.resolution_y = int(c["resolution"])
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.world.color = (0.18, 0.18, 0.2)
    except AttributeError:
        pass

    center, size = _scene_bounds()
    cam_data = bpy.data.cameras.new("_preview_cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = size * 1.1
    cam_data.clip_end = size * 20
    cam = bpy.data.objects.new("_preview_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    out_dir = os.path.abspath(os.path.expanduser(c["out_dir"]))
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for view in c["views"]:
        d = _VIEWS[view].normalized()
        cam.location = center + d * size * 3
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        path = os.path.join(out_dir, f"{c['prefix']}_{view}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        files.append(path)

    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    print("[preview]", *files, sep="\n  ")
    return {"ok": True, "files": files, "center": list(center), "size": size}


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
    _result = main(_parse_cli(dict(CONFIG)))
    print("PIPELINE_RESULT " + json.dumps(_result))
    if bpy.app.background:
        sys.exit(0 if _result.get("ok") else 1)
