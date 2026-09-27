"""
bend_test.py - does this rigged model bend without collapsing? Measured, not eyeballed.

Same idea as a topology comparison with one fixed rig: bend each leg joint (elbow, carpus,
stifle, hock) to 90 degrees in the direction it really flexes, and measure what the skin does:

    retention   for the joint's blend zone (vertices shared between the upper and lower bone):
                distance to the joint centre, bent / rest, at the 10th-percentile vertex (the
                part of the fold that caves in most). A rigid bend keeps 1.0. Linear-blend
                skinning (what glTF and Godot use) averages the two bones' positions, which
                pulls a 50/50 vertex in to cos(45 deg) = 0.71 at a 90 deg bend: the "rubber
                hose" pinch. Plain skinning measured 0.71-0.87 on the presets; with volume
                helpers 0.93-0.97. The gate is 0.85.
    mean        the same ratio averaged over the zone.
    hinge       true when no vertex is shared between the two bones at all: the joint folds like
                a hinge and the faces across it stretch into a thin strip (the "single loop"
                failure). Fails regardless of retention.

Only the joint's own bones move, so every change comes from that joint's skinning. Works
on any quadruped_rig.py skeleton (including models from Tripo / Meshy / Rodin rigged with it)
and moves volume helper bones (<bone>_vol.L) half-way, as the game clips do.

    blender -b -P bend_test.py -- import_path=wolf.glb
    blender -b -P bend_test.py -- import_path=wolf.glb render_dir=renders prefix=wolf
"""

import bpy
import json
import math
import os
import sys
from mathutils import Matrix, Vector

CONFIG = {
    "import_path": None,          # rigged GLB/FBX; None = the current scene
    "clear_scene": True,
    "angle": 90.0,                # degrees of flexion
    "sides": [".L"],              # the rig is symmetric; add ".R" to test both
    "min_retention": 0.85,        # below this a joint fails
    "render_dir": None,           # also render the legs bent (side view) into this folder
    "prefix": "bend",
    "resolution": 768,
}

# joint -> (bone that rotates, flexion when the chain is too straight to tell:
#           +1 = the lower end swings back, -1 = forward)
JOINTS = {
    "elbow": ("forearm", -1),
    "carpus": ("hand", +1),
    "stifle": ("shin", +1),
    "hock": ("hock", -1),
}
HELPER_SUFFIX = "_vol"


def _import(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(f"unsupported format {ext}")


def _find_rig():
    arm = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH'
              and any(m.type == 'ARMATURE' for m in o.modifiers)]
    if not arm or not meshes:
        raise RuntimeError("need an armature and a mesh skinned to it")
    return arm, max(meshes, key=lambda o: len(o.data.vertices))


def _reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def _deformed(mesh_obj):
    """World positions of the evaluated (skinned) mesh vertices."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh_obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return co


def _blend_zone(arm, mesh_obj, bone):
    """Vertices that follow the lower bone only partly: where skinning can collapse."""
    moving = {bone} | {c.name for c in arm.data.bones[bone].children_recursive if HELPER_SUFFIX not in c.name}
    base, side = bone.split(".")[0], bone[len(bone.split(".")[0]):]
    helper = base + HELPER_SUFFIX + side
    names = {g.index: g.name for g in mesh_obj.vertex_groups}
    zone = []
    for v in mesh_obj.data.vertices:
        total = sum(g.weight for g in v.groups) or 1.0
        w = sum(g.weight for g in v.groups if names.get(g.group) in moving)
        w += 0.5 * sum(g.weight for g in v.groups if names.get(g.group) == helper)
        if 0.05 < w / total < 0.95:
            zone.append(v.index)
    return zone


def _flex_sign(arm, bone, default):
    """Which way closes the joint: the child's lower end swings toward the parent's upper end."""
    b = arm.data.bones[bone]
    mw = arm.matrix_world
    pivot, tail = mw @ b.head_local, mw @ b.tail_local
    up = mw @ b.parent.head_local if b.parent else pivot + Vector((0, 0, 1))
    a, c = (up - pivot).normalized(), (tail - pivot).normalized()
    if a.angle(c) > math.radians(170):          # straight limb: use anatomy
        return default
    lateral = Vector((1, 0, 0))
    turn = lambda s: (Matrix.Rotation(s * 0.2, 3, lateral) @ c).angle(a)
    return 1 if turn(1) < turn(-1) else -1


def bend(arm, bone, degrees):
    """Rotate `bone` (and its volume helper by half) about the lateral axis through its head."""
    b = arm.data.bones[bone]
    sign = _flex_sign(arm, bone, dict((v[0], v[1]) for v in JOINTS.values()).get(bone.split(".")[0], 1))
    inv = arm.matrix_world.inverted()
    axis = (inv.to_3x3() @ Vector((1, 0, 0))).normalized()
    pivot = b.head_local
    for name, frac in ((bone, 1.0), (bone.split(".")[0] + HELPER_SUFFIX + bone[len(bone.split(".")[0]):], 0.5)):
        pb = arm.pose.bones.get(name)
        if pb is None:
            continue
        if frac < 1 and any(c.type == 'COPY_ROTATION' and c.enabled and c.influence > 0 for c in pb.constraints):
            continue                               # a live rig's half-turn constraint already drives it
        rot = (Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(degrees) * sign * frac, 4, axis)
               @ Matrix.Translation(-pivot))
        pb.matrix = rot @ pb.matrix
        bpy.context.view_layer.update()
    return sign


def measure(arm, mesh_obj, cfg):
    _reset(arm)
    rest = _deformed(mesh_obj)
    joints = {}
    for side in cfg["sides"]:
        for joint, (base, _) in JOINTS.items():
            bone = base + side
            if bone not in arm.data.bones:
                continue
            pivot = arm.matrix_world @ arm.data.bones[bone].head_local
            zone = _blend_zone(arm, mesh_obj, bone)
            _reset(arm)
            bend(arm, bone, cfg["angle"])
            bent = _deformed(mesh_obj)
            ratios = sorted((bent[i] - pivot).length / max((rest[i] - pivot).length, 1e-9) for i in zone)
            joints[joint + side] = {
                "retention": round(ratios[len(ratios) // 10], 3) if ratios else None,
                "mean": round(sum(ratios) / len(ratios), 3) if ratios else None,
                "hinge": not ratios,
                "zone_verts": len(ratios),
            }
    _reset(arm)
    return joints


def render(arm, cfg):
    """Legs bent (elbow + stifle, then carpus + hock) from the left side, via render_preview.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("render_preview", os.path.join(os.path.dirname(__file__), "render_preview.py"))
    rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rp)
    files = []
    for label, pair in (("elbow_stifle", ("forearm", "shin")), ("carpus_hock", ("hand", "hock"))):
        _reset(arm)
        for base in pair:
            if base + ".L" in arm.data.bones:
                bend(arm, base + ".L", cfg["angle"])
        out = rp.main({"out_dir": cfg["render_dir"], "prefix": f"{cfg['prefix']}_{label}", "views": ["side"],
                       "resolution": cfg["resolution"], "frame": 0})
        # where the bent joints land in the image (side view: +X camera, image right = +Y, up = +Z)
        centre, size, res = Vector(out["center"]), out["size"] * 1.1, cfg["resolution"]
        joints_px = {}
        for base in pair:
            if base + ".L" in arm.data.bones:
                p = arm.matrix_world @ arm.data.bones[base + ".L"].head_local
                joints_px[base] = [round(res / 2 + (p.y - centre.y) / size * res), round(res / 2 - (p.z - centre.z) / size * res)]
        files.append({"file": out["files"][0], "joints_px": joints_px})
    _reset(arm)
    return files


def main(config=None):
    cfg = dict(CONFIG)
    cfg.update(config or {})
    if cfg.get("import_path"):
        if cfg.get("clear_scene"):
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o, do_unlink=True)
        _import(os.path.abspath(os.path.expanduser(cfg["import_path"])))
    try:
        arm, mesh_obj = _find_rig()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    # measure the rest pose, not a clip frame; put the scene's animation back afterwards
    saved = None
    if arm.animation_data:
        saved = (arm.animation_data.action, [(t, t.mute) for t in arm.animation_data.nla_tracks])
        arm.animation_data.action = None
        for t in arm.animation_data.nla_tracks:
            t.mute = True
    try:
        return _run(arm, mesh_obj, cfg)
    finally:
        _reset(arm)
        if saved:
            arm.animation_data.action = saved[0]
            for t, mute in saved[1]:
                t.mute = mute
        bpy.context.view_layer.update()


def _run(arm, mesh_obj, cfg):
    joints = measure(arm, mesh_obj, cfg)
    if not joints:
        return {"ok": False, "error": "no quadruped leg bones (forearm/hand/shin/hock) found"}
    for j in joints.values():
        j["ok"] = not j["hinge"] and j["retention"] >= cfg["min_retention"]
    worst = min(joints.items(), key=lambda kv: (kv[1]["ok"], kv[1]["retention"] or 0.0))
    report = {"ok": all(j["ok"] for j in joints.values()), "angle": cfg["angle"],
              "min_retention": cfg["min_retention"],
              "worst_joint": worst[0], "worst_retention": worst[1]["retention"],
              "failed": sorted(k for k, j in joints.items() if not j["ok"]), "joints": joints,
              "volume_helpers": any(HELPER_SUFFIX in b.name for b in arm.data.bones)}
    if cfg.get("render_dir"):
        report["renders"] = render(arm, cfg)
    print("[bend]", json.dumps({k: "hinge" if v["hinge"] else v["retention"] for k, v in joints.items()}))
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
    _result = main(_parse_cli(dict(CONFIG)))
    print("PIPELINE_RESULT " + json.dumps(_result))
    if bpy.app.background:
        sys.exit(0 if _result.get("ok") else 1)
