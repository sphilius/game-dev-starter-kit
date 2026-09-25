"""
build_lowpoly_creature.py - procedural low-poly quadruped from a stick-figure graph (no AI, no keys).

A faceted, flat-shaded look hides what procedural modelling is bad at (smooth organic
surfaces) and plays to what it is good at: exact proportions, clean silhouettes and
tiny triangle counts. This builds a creature from a graph of joints with radii using
Blender's Skin modifier (which wraps a quad hull around the graph), then decimates to a
budget and flat-shades. The result is one watertight mesh facing -Y with its feet on the
ground, ready for quadruped_rig.py.

Presets give recognisable animals by changing proportions only:
    wolf, boar, bear, deer, cat
Every number is in the preset dict and can be overridden through CONFIG["overrides"].
Colours come from a small palette as vertex-free material slots (body, belly/muzzle,
dark accents: hooves/nose), so no UVs or textures are needed.
"""

import bpy
import bmesh
import json
import os
import sys
from mathutils import Vector

CONFIG = {
    "preset": "wolf",
    "name": None,                  # object name; default = preset
    "height_m": None,              # shoulder-ish height override, metres (None = preset)
    "target_tris": 900,            # low-poly budget
    "export_path": None,           # e.g. ~/game/incoming/wolf_lowpoly.glb
    "clear_scene": True,
    "seed_jitter": 0.0,            # 0..0.15 random proportion variation (same seed = same result)
    "seed": 1,
    "overrides": {},               # e.g. {"leg_len": 0.5, "tail": [..]}
    "palette": None,               # [[r,g,b], [r,g,b], [r,g,b]] body, light, dark (0-1)
}

# Proportions in metres for a creature whose body runs along Y (head at -Y).
# body: spine joints (y, z, radius), head: (y, z, radius) list from neck to nose,
# legs: shoulder/hip y, leg length, thickness, spread; tail: list of (dy, dz, radius).
PRESETS = {
    "wolf": {
        "body": [(0.42, 0.62, 0.13), (0.15, 0.64, 0.17), (-0.15, 0.66, 0.18), (-0.35, 0.68, 0.16)],
        "head": [(-0.50, 0.80, 0.10), (-0.62, 0.84, 0.11), (-0.78, 0.78, 0.06), (-0.88, 0.75, 0.04)],
        "ears": 0.09, "front_y": -0.30, "hind_y": 0.36, "leg_len": 0.58, "leg_r": 0.055, "spread": 0.11,
        "tail": [(0.12, -0.02, 0.06), (0.14, -0.08, 0.05), (0.13, -0.12, 0.035), (0.10, -0.10, 0.02)],
        "palette": [(0.42, 0.42, 0.45), (0.78, 0.76, 0.72), (0.12, 0.12, 0.13)],
    },
    "boar": {
        "body": [(0.40, 0.58, 0.17), (0.12, 0.62, 0.22), (-0.18, 0.66, 0.24), (-0.36, 0.64, 0.20)],
        "head": [(-0.50, 0.58, 0.15), (-0.64, 0.52, 0.12), (-0.78, 0.46, 0.08), (-0.86, 0.44, 0.06)],
        "ears": 0.07, "front_y": -0.28, "hind_y": 0.34, "leg_len": 0.44, "leg_r": 0.055, "spread": 0.13,
        "tail": [(0.08, -0.04, 0.03), (0.06, -0.08, 0.02)],
        "palette": [(0.32, 0.22, 0.16), (0.55, 0.42, 0.32), (0.10, 0.08, 0.07)],
    },
    "bear": {
        "body": [(0.45, 0.70, 0.22), (0.15, 0.78, 0.28), (-0.20, 0.84, 0.28), (-0.42, 0.82, 0.24)],
        "head": [(-0.58, 0.86, 0.17), (-0.72, 0.86, 0.16), (-0.86, 0.80, 0.09), (-0.94, 0.78, 0.06)],
        "ears": 0.06, "front_y": -0.36, "hind_y": 0.40, "leg_len": 0.62, "leg_r": 0.085, "spread": 0.16,
        "tail": [(0.08, -0.02, 0.05)],
        "palette": [(0.30, 0.20, 0.13), (0.50, 0.36, 0.25), (0.08, 0.06, 0.05)],
    },
    "deer": {
        "body": [(0.38, 0.92, 0.12), (0.12, 0.95, 0.15), (-0.14, 0.97, 0.15), (-0.32, 1.00, 0.13)],
        "head": [(-0.40, 1.20, 0.07), (-0.46, 1.42, 0.09), (-0.60, 1.40, 0.06), (-0.70, 1.36, 0.04)],
        "ears": 0.10, "front_y": -0.28, "hind_y": 0.32, "leg_len": 0.90, "leg_r": 0.035, "spread": 0.10,
        "tail": [(0.08, 0.02, 0.04), (0.05, -0.04, 0.03)],
        "palette": [(0.55, 0.38, 0.22), (0.86, 0.80, 0.70), (0.12, 0.09, 0.07)],
    },
    "cat": {
        "body": [(0.20, 0.26, 0.07), (0.07, 0.27, 0.08), (-0.07, 0.28, 0.08), (-0.18, 0.29, 0.07)],
        "head": [(-0.26, 0.36, 0.07), (-0.32, 0.38, 0.07), (-0.39, 0.36, 0.035), (-0.42, 0.35, 0.025)],
        "ears": 0.05, "front_y": -0.14, "hind_y": 0.17, "leg_len": 0.24, "leg_r": 0.022, "spread": 0.05,
        "tail": [(0.08, 0.06, 0.02), (0.06, 0.12, 0.018), (0.02, 0.12, 0.015), (-0.03, 0.08, 0.012)],
        "palette": [(0.85, 0.55, 0.25), (0.95, 0.90, 0.82), (0.15, 0.10, 0.08)],
    },
}


def _graph(p):
    """Joints [(co, radius)] and edges [(i, j)] for Skin."""
    verts, edges = [], []

    def add(co, r, parent=None):
        verts.append((Vector(co), r))
        idx = len(verts) - 1
        if parent is not None:
            edges.append((parent, idx))
        return idx

    # spine, rump to chest
    spine = []
    for i, (y, z, r) in enumerate(p["body"]):
        spine.append(add((0, y, z), r, spine[-1] if spine else None))
    # neck and head from the chest
    prev = spine[-1]
    head_ids = []
    for y, z, r in p["head"]:
        prev = add((0, y, z), r, prev)
        head_ids.append(prev)
    # ears on the skull joint (second head joint)
    skull = verts[head_ids[1]][0]
    if p.get("ears"):
        er = verts[head_ids[1]][1]
        for side in (-1, 1):
            base = add((side * er * 0.55, skull.y + 0.01, skull.z + er * 0.85), p["ears"] * 0.32, head_ids[1])
            add((side * er * 0.62, skull.y + 0.02, skull.z + er * 0.85 + p["ears"]), 0.006, base)
    # tail from the rump
    prev = spine[0]
    pos = verts[spine[0]][0].copy()
    for dy, dz, r in p["tail"]:
        pos = pos + Vector((0, dy, dz))
        prev = add(tuple(pos), r, prev)
    # legs: shoulder -> elbow -> wrist -> paw, hip -> knee -> hock -> paw
    body_z = lambda y: min(p["body"], key=lambda j: abs(j[0] - y))[1]
    body_i = lambda y: spine[min(range(len(p["body"])), key=lambda k: abs(p["body"][k][0] - y))]
    L, r = p["leg_len"], p["leg_r"]
    for side in (-1, 1):
        x = side * p["spread"]
        for y0, bend in ((p["front_y"], -1), (p["hind_y"], 1)):
            top = body_z(y0) - 0.02
            a = add((x, y0, top), r * 1.5, body_i(y0))
            b = add((x, y0 + bend * 0.04 * L / 0.6, top - L * 0.45), r)
            c = add((x, y0 - bend * 0.03 * L / 0.6, top - L * 0.85), r * 0.8, b)
            edges.append((a, b))
            add((x, y0 - 0.05 * L / 0.6, max(0.0, top - L)), r * 0.9, c)
    return verts, edges


def _material(name, rgb):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    preset = c["preset"]
    if preset not in PRESETS:
        return {"ok": False, "error": f"preset must be one of {sorted(PRESETS)}"}
    p = json.loads(json.dumps(PRESETS[preset]))       # deep copy
    p.update(c.get("overrides") or {})
    name = c.get("name") or preset

    if c.get("clear_scene"):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)

    if c.get("seed_jitter"):
        import random
        rnd = random.Random(int(c["seed"]))
        j = float(c["seed_jitter"])
        p["leg_len"] *= 1 + rnd.uniform(-j, j)
        p["body"] = [(y, z, r * (1 + rnd.uniform(-j, j))) for y, z, r in p["body"]]

    verts, edges = _graph(p)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([v for v, _ in verts], edges, [])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)

    skin = obj.modifiers.new("Skin", 'SKIN')
    skin.use_smooth_shade = False
    for sv, (_, r) in zip(mesh.skin_vertices[0].data, verts):
        sv.radius = (r, r)
    mesh.skin_vertices[0].data[0].use_root = True
    sub = obj.modifiers.new("Subdiv", 'SUBSURF')
    sub.levels = 1
    sub.render_levels = 1
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)

    # Clean the skin hull, then decimate to the low-poly budget
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    tris = sum(len(f.vertices) - 2 for f in obj.data.polygons)
    if tris > c["target_tris"]:
        dec = obj.modifiers.new("Decimate", 'DECIMATE')
        dec.ratio = c["target_tris"] / tris
        bpy.ops.object.modifier_apply(modifier=dec.name)
    for poly in obj.data.polygons:
        poly.use_smooth = False                        # faceted look

    # Scale to height, feet on the ground, centred
    zs = [v.co.z for v in obj.data.vertices]
    if c.get("height_m"):
        s = float(c["height_m"]) / (max(zs) - min(zs))
        for v in obj.data.vertices:
            v.co *= s
        zs = [v.co.z for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    shift = Vector((0, -(min(ys) + max(ys)) / 2, -min(zs)))
    for v in obj.data.vertices:
        v.co += shift

    # Three flat colours by region: dark paws/nose, light belly/muzzle, body elsewhere
    pal = c.get("palette") or p["palette"]
    mats = [_material(f"{name}_body", pal[0]), _material(f"{name}_light", pal[1]), _material(f"{name}_dark", pal[2])]
    for m in mats:
        obj.data.materials.append(m)
    zs = [v.co.z for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    h, front = max(zs), min(ys)
    for poly in obj.data.polygons:
        cz, cy = poly.center.z, poly.center.y
        if cz < h * 0.07 or (cy < front + 0.03 * (max(ys) - front)):
            poly.material_index = 2                    # paws / nose tip
        elif poly.normal.z < -0.55 and cz < h * 0.75 or (cy < front + 0.16 * (max(ys) - front) and cz < h * 0.85):
            poly.material_index = 1                    # belly / muzzle
        else:
            poly.material_index = 0

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    report = {
        "ok": True, "object": obj.name, "preset": preset,
        "tris": sum(len(f.verts) - 2 for f in bm.faces),
        "non_manifold": sum(1 for e in bm.edges if not e.is_manifold),
        "dimensions_m": [round(d, 3) for d in obj.dimensions],
    }
    bm.free()
    if c.get("export_path"):
        path = os.path.abspath(os.path.expanduser(c["export_path"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True)
        report["export_path"] = path
    print(f"[lowpoly] {preset}: {report['tris']} tris, non-manifold edges {report['non_manifold']}")
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
