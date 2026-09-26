"""
build_lowpoly_creature.py - procedural low-poly quadruped from a stick-figure graph (no AI, no keys).

A faceted, flat-shaded look hides what procedural modelling is bad at (smooth organic
surfaces) and plays to what it is good at: exact proportions, clean silhouettes and
tiny triangle counts. This builds a creature from a graph of joints with radii using
Blender's Skin modifier (which wraps a quad hull around the graph), then decimates to a
budget and flat-shades. The result is one watertight mesh facing -Y with its feet on the
ground, ready for quadruped_rig.py.

Presets give recognisable animals by changing proportions and stance:
    wolf, cat   digitigrade (toe-walking)       boar, deer   unguligrade (hoofed)
    bear        plantigrade (flat-footed)
Legs are anatomical chains (see STANCES): the front elbow points back, the hind knee forward and
the hock back, so front and hind legs are different shapes, not mirror copies. The joint
positions are saved on the object ("quadruped_landmarks", exported as glTF extras), and
quadruped_rig.py uses them so bones bend exactly where the mesh has joints.
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
        "stance": "digitigrade",
        "body": [(0.42, 0.62, 0.13), (0.15, 0.64, 0.17), (-0.15, 0.66, 0.18), (-0.35, 0.68, 0.16)],
        "head": [(-0.50, 0.80, 0.10), (-0.62, 0.84, 0.11), (-0.78, 0.78, 0.06), (-0.88, 0.75, 0.04)],
        "ears": 0.09, "front_y": -0.30, "hind_y": 0.36, "leg_len": 0.58, "leg_r": 0.055, "spread": 0.11,
        "tail": [(0.12, -0.02, 0.06), (0.14, -0.08, 0.05), (0.13, -0.12, 0.035), (0.10, -0.10, 0.02)],
        "palette": [(0.42, 0.42, 0.45), (0.78, 0.76, 0.72), (0.12, 0.12, 0.13)],
    },
    "boar": {
        "stance": "unguligrade",
        "body": [(0.40, 0.58, 0.17), (0.12, 0.62, 0.22), (-0.18, 0.66, 0.24), (-0.36, 0.64, 0.20)],
        "head": [(-0.50, 0.58, 0.15), (-0.64, 0.52, 0.12), (-0.78, 0.46, 0.08), (-0.86, 0.44, 0.06)],
        "ears": 0.07, "front_y": -0.28, "hind_y": 0.34, "leg_len": 0.44, "leg_r": 0.055, "spread": 0.13,
        "tail": [(0.08, -0.04, 0.03), (0.06, -0.08, 0.02)],
        "palette": [(0.32, 0.22, 0.16), (0.55, 0.42, 0.32), (0.10, 0.08, 0.07)],
    },
    "bear": {
        "stance": "plantigrade",
        "body": [(0.45, 0.70, 0.22), (0.15, 0.78, 0.28), (-0.20, 0.84, 0.28), (-0.42, 0.82, 0.24)],
        "head": [(-0.58, 0.86, 0.17), (-0.72, 0.86, 0.16), (-0.86, 0.80, 0.09), (-0.94, 0.78, 0.06)],
        "ears": 0.06, "front_y": -0.36, "hind_y": 0.40, "leg_len": 0.62, "leg_r": 0.085, "spread": 0.16,
        "tail": [(0.08, -0.02, 0.05)],
        "palette": [(0.30, 0.20, 0.13), (0.50, 0.36, 0.25), (0.08, 0.06, 0.05)],
    },
    "deer": {
        "stance": "unguligrade",
        "body": [(0.38, 0.92, 0.12), (0.12, 0.95, 0.15), (-0.14, 0.97, 0.15), (-0.32, 1.00, 0.13)],
        "head": [(-0.40, 1.20, 0.07), (-0.46, 1.42, 0.09), (-0.60, 1.40, 0.06), (-0.70, 1.36, 0.04)],
        "ears": 0.10, "front_y": -0.28, "hind_y": 0.32, "leg_len": 0.90, "leg_r": 0.035, "spread": 0.10,
        "tail": [(0.08, 0.02, 0.04), (0.05, -0.04, 0.03)],
        "palette": [(0.55, 0.38, 0.22), (0.86, 0.80, 0.70), (0.12, 0.09, 0.07)],
    },
    "cat": {
        "stance": "digitigrade",
        "body": [(0.20, 0.26, 0.07), (0.07, 0.27, 0.08), (-0.07, 0.28, 0.08), (-0.18, 0.29, 0.07)],
        "head": [(-0.26, 0.36, 0.07), (-0.32, 0.38, 0.07), (-0.39, 0.36, 0.035), (-0.42, 0.35, 0.025)],
        "ears": 0.05, "front_y": -0.14, "hind_y": 0.17, "leg_len": 0.24, "leg_r": 0.022, "spread": 0.05,
        "tail": [(0.08, 0.06, 0.02), (0.06, 0.12, 0.018), (0.02, 0.12, 0.015), (-0.03, 0.08, 0.012)],
        "palette": [(0.85, 0.55, 0.25), (0.95, 0.90, 0.82), (0.15, 0.10, 0.08)],
    },
}


# Leg chains by stance. Each point: (forward, height, radius-scale).
#   forward: metres of forward (+) / backward (-) offset per metre of leg height, from the leg root
#   height:  fraction of the spine height at the leg root (1.0 = spine, 0 = ground)
#   radius:  multiple of the preset's leg_r
# Front chain: scapula top, shoulder, elbow, carpus (wrist), paw/fetlock, toe tip
# Hind chain:  hip, stifle (knee), hock (ankle), paw/fetlock, toe tip
# The anatomy that matters: the elbow points BACK, the stifle points FORWARD, the hock points
# BACK and sits well off the ground on toe- and hoof-walkers, and hind legs carry a heavy thigh.
STANCES = {
    "digitigrade": {   # walks on toes: wolf, dog, cat
        "front": [(0.10, 1.18, 1.3), (0.06, 0.88, 1.7), (-0.08, 0.55, 1.2), (0.00, 0.15, 0.8), (0.05, 0.04, 0.9), (0.12, 0.01, 0.6)],
        "hind":  [(0.00, 0.98, 2.2), (0.15, 0.60, 1.5), (-0.14, 0.27, 0.8), (-0.06, 0.04, 0.9), (0.03, 0.01, 0.6)],
    },
    "unguligrade": {   # walks on hoof tips: deer, boar, horse
        "front": [(0.10, 1.15, 1.3), (0.06, 0.88, 1.6), (-0.07, 0.62, 1.1), (0.00, 0.33, 0.6), (0.02, 0.07, 0.55), (0.05, 0.00, 0.65)],
        "hind":  [(0.00, 0.98, 2.1), (0.13, 0.66, 1.4), (-0.14, 0.38, 0.65), (-0.07, 0.07, 0.55), (-0.04, 0.00, 0.65)],
    },
    "plantigrade": {   # walks on the whole foot: bear
        "front": [(0.08, 1.12, 1.4), (0.05, 0.88, 1.8), (-0.07, 0.52, 1.35), (0.00, 0.10, 1.0), (0.10, 0.03, 1.0), (0.20, 0.02, 0.7)],
        "hind":  [(0.00, 0.98, 2.2), (0.10, 0.55, 1.5), (-0.06, 0.08, 1.0), (0.10, 0.03, 1.0), (0.20, 0.02, 0.7)],
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
    p["_spine"] = [verts[i][0].copy() for i in spine]
    p["_head"] = [verts[i][0].copy() for i in head_ids]
    p["_head_r"] = [verts[i][1] for i in head_ids]
    tail_pts = [verts[spine[0]][0].copy()]
    pos = tail_pts[0].copy()
    for dy, dz, _ in p["tail"]:
        pos = pos + Vector((0, dy, dz))
        tail_pts.append(pos.copy())
    p["_tail"] = tail_pts
    # legs: anatomical chains per stance (see STANCES); front and hind are NOT mirror images
    stance = STANCES[p.get("stance", "digitigrade")]
    spine_at = lambda y: min(p["body"], key=lambda j: abs(j[0] - y))
    body_i = lambda y: spine[min(range(len(p["body"])), key=lambda k: abs(p["body"][k][0] - y))]
    r = p["leg_r"]
    chains = {}
    for side in (-1, 1):
        x = side * p["spread"]
        for leg, y0 in (("front", p["front_y"]), ("hind", p["hind_y"])):
            h = spine_at(y0)[1]                          # spine height above the leg
            pts = []
            prev = body_i(y0)
            for i, (fwd, hz, rs) in enumerate(stance[leg]):
                # the scapula top / hip sit closer to the midline than the lower leg
                xi = x * (0.55 if i == 0 else 1.0)
                co = (xi, y0 - fwd * h, max(0.0, hz * h))
                prev = add(co, r * rs, prev)
                pts.append(co)
            chains[(leg, side)] = pts
    p["_chains"] = chains
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
    # One level of smoothing covers low-poly budgets; higher budgets need more source detail
    sub.levels = sub.render_levels = 1 if c["target_tris"] <= 2500 else (2 if c["target_tris"] <= 12000 else 3)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)

    # Clean the skin hull, then decimate to the low-poly budget
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    # Skin can leave small holes or stray edges where several limbs meet the body; patch them
    loose = [e for e in bm.edges if not e.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='EDGES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context='VERTS')
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
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

    # Tell quadruped_rig where the joints really are (fractions of the final bounding box),
    # so bones bend exactly at the mesh's elbows, knees and hocks.
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    lo = Vector((min(xs), min(ys), min(zs)))
    size = Vector((max(xs) - lo.x, max(ys) - lo.y, max(zs) - lo.z))
    k = s if c.get("height_m") else 1.0

    def frac(co):
        w = (Vector(co) * k) + shift
        return [round((w.y - lo.y) / size.y, 4), round((w.z - lo.z) / size.z, 4),
                round(abs(w.x) / (size.x / 2), 4)]

    fl = [frac(co) for co in p["_chains"][("front", 1)]]
    hl = [frac(co) for co in p["_chains"][("hind", 1)]]
    def resample(points, n):
        """n+1 evenly spaced points along a polyline (so any tail/spine length maps to fixed bones)."""
        pts = [Vector(q) for q in points]
        if len(pts) == 1:
            pts.append(pts[0] + Vector((0, 0.05, -0.02)))
        seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
        total = sum(seg) or 1e-6
        out = []
        for j in range(n + 1):
            d, i = total * j / n, 0
            while i < len(seg) - 1 and d > seg[i]:
                d -= seg[i]
                i += 1
            t = min(1.0, d / seg[i]) if seg[i] else 0.0
            out.append(pts[i].lerp(pts[i + 1], t))
        return out

    sp = [frac(q) for q in resample(p["_spine"], 4)]          # rump -> chest, 4 bones
    hd = p["_head"]
    jaw_drop = Vector((0, 0, -0.45 * p["_head_r"][2]))
    tl = [frac(q) for q in resample(p["_tail"], 4)]
    landmarks = {
        "pelvis": [sp[0], sp[1]], "spine_01": [sp[1], sp[2]], "spine_02": [sp[2], sp[3]], "spine_03": [sp[3], sp[4]],
        "neck_01": [sp[4], frac(hd[0])], "neck_02": [frac(hd[0]), frac(hd[1])],
        "head": [frac(hd[1]), frac(hd[3])],
        "jaw": [frac(hd[1].lerp(hd[2], 0.5) + jaw_drop), frac(hd[3] + jaw_drop * 0.5)],
        "tail_01": [tl[0], tl[1]], "tail_02": [tl[1], tl[2]], "tail_03": [tl[2], tl[3]], "tail_04": [tl[3], tl[4]],
        "scapula": [fl[0], fl[1]], "upperarm": [fl[1], fl[2]], "forearm": [fl[2], fl[3]],
        "hand": [fl[3], fl[4]], "front_toe": [fl[4], fl[5]],
        "thigh": [hl[0], hl[1]], "shin": [hl[1], hl[2]], "hock": [hl[2], hl[3]], "hind_toe": [hl[3], hl[4]],
    }
    obj["quadruped_landmarks"] = json.dumps(landmarks)
    obj["quadruped_head_direction"] = "-Y"
    obj["flat_shaded"] = True          # quadruped_rig keeps the faceted look after welding

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    report = {
        "ok": True, "object": obj.name, "preset": preset,
        "tris": sum(len(f.verts) - 2 for f in bm.faces),
        "non_manifold": sum(1 for e in bm.edges if not e.is_manifold),
        "dimensions_m": [round(d, 3) for d in obj.dimensions],
        "stance": p.get("stance", "digitigrade"),
        "landmarks": landmarks,
    }
    bm.free()
    if c.get("export_path"):
        path = os.path.abspath(os.path.expanduser(c["export_path"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True,
                                  export_extras=True)   # carries the rig landmarks
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
