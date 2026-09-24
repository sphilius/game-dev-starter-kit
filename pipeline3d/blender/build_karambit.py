"""
build_karambit.py - deterministic low-poly karambit (finger ring + handle + hawkbill blade).

Why procedural: AI generators usually fuse the finger-ring hole shut and put the pivot
somewhere random. This builds the side profile as a 2D outline with a hole, extrudes it,
then tapers the blade. The result is one watertight mesh with exactly one through-hole
(Euler characteristic chi == 0) and its origin at the ring centre, which is the swivel pivot.

Axes (Blender, metres): ring hole axis = Y, handle runs down -Z, blade hooks toward +X.
Godot (+Y up after glTF export): hole axis = Z, handle along -Y.

Run it the same three ways as cleanup_for_godot.py (MCP run_script_file / GUI / headless).
"""

import bpy
import bmesh
import json
import math
import os
import sys

CONFIG = {
    "export_path": "~/karambit_bench/export/karambit.glb",  # None = don't export
    "object_name": "Karambit",
    "clear_scene": False,
    "ring_major_r": 0.017,      # ring centre-line radius
    "ring_minor_r": 0.005,      # ring half-thickness in the profile
    "handle_length": 0.10,
    "handle_height": 0.018,
    "handle_thickness": 0.011,
    "handle_bend": 0.006,       # forward bow of the handle over its length
    "blade_length": 0.07,       # arc length of the blade centre-line
    "blade_sweep_deg": 140.0,   # 170 = longer hook
    "blade_thickness": 0.004,   # at the spine; the edge tapers further
    "ring_segments": 48,
    "blade_segments": 24,
    "handle_segments": 8,
}


def _arc(cx, cz, r, a0, a1, n):
    """Points on a circle in the XZ profile plane, a0 -> a1 (radians), n segments, inclusive."""
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cz + r * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def _profile(c):
    ro = c["ring_major_r"] + c["ring_minor_r"]
    ri = c["ring_major_r"] - c["ring_minor_r"]
    h2 = c["handle_height"] / 2.0
    zj = -math.sqrt(max(ro * ro - h2 * h2, 1e-9))           # where handle edges meet the ring
    z0 = -(c["ring_major_r"] + c["handle_length"])            # handle end / blade root
    bend = c["handle_bend"]
    n_h = c["handle_segments"]

    def bow(z):  # parabolic forward bow of the handle, 0 at the ring and `bend` at the blade root
        t = (zj - z) / (zj - z0)
        return bend * t * t

    # Ring outer arc: from the handle's back edge, over the top, to its front edge
    a_back = math.atan2(zj, -h2)
    a_front = math.atan2(zj, h2)
    if a_back < a_front:
        a_back += 2 * math.pi
    outline = _arc(0.0, 0.0, ro, a_back, a_front, c["ring_segments"])   # decreasing angle = over the top
    # Handle front edge (+X), top to bottom
    for i in range(1, n_h + 1):
        z = zj + (z0 - zj) * i / n_h
        outline.append((h2 + bow(z), z))
    # Blade: centre-line is an arc hooking toward +X; width tapers to a point
    sweep = math.radians(c["blade_sweep_deg"])
    rc = c["blade_length"] / sweep
    cx0 = bend
    n_b = c["blade_segments"]
    inner, outer = [], []
    for i in range(n_b + 1):
        t = i / n_b
        phi = sweep * t
        px = cx0 + rc - rc * math.cos(phi)
        pz = z0 - rc * math.sin(phi)
        nx, nz = math.cos(phi), math.sin(phi)          # unit normal toward the arc centre (concave side)
        w = c["handle_height"] * (1.0 - t) ** 0.85 / 2.0
        inner.append((px + nx * w, pz + nz * w))       # sharpened concave edge
        outer.append((px - nx * w, pz - nz * w))       # convex spine
    outline += inner[1:-1]
    outline.append(inner[-1])                          # tip (inner[-1] == outer[-1])
    outline += list(reversed(outer[1:-1]))
    outline.append(outer[0])
    # Handle back edge (-X), bottom to top
    for i in range(n_h - 1, 0, -1):
        z = zj + (z0 - zj) * i / n_h
        outline.append((-h2 + bow(z), z))
    hole = _arc(0.0, 0.0, ri, 0.0, 2 * math.pi, c["ring_segments"] - 16)[:-1]
    return outline, hole, z0


def _dedupe(points, eps=1e-7):
    out = []
    for p in points:
        if not out or (abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps):
            out.append(p)
    if len(out) > 2 and abs(out[0][0] - out[-1][0]) < eps and abs(out[0][1] - out[-1][1]) < eps:
        out.pop()
    return out


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    report = {"ok": False}

    if c.get("clear_scene"):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    old = bpy.data.objects.get(c["object_name"])
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    outline, hole, z0 = _profile(c)
    outline, hole = _dedupe(outline), _dedupe(hole)

    # 2D curve with two POLY splines: the fill algorithm cuts the inner loop as a hole.
    curve = bpy.data.curves.new(c["object_name"] + "_profile", 'CURVE')
    curve.dimensions = '2D'
    curve.fill_mode = 'BOTH'
    curve.extrude = c["handle_thickness"] / 2.0
    for loop in (outline, hole):
        sp = curve.splines.new('POLY')
        sp.points.add(len(loop) - 1)
        for p, (x, z) in zip(sp.points, loop):
            p.co = (x, z, 0.0, 1.0)      # curve-local XY = profile XZ
        sp.use_cyclic_u = True
    cobj = bpy.data.objects.new(c["object_name"] + "_profile", curve)
    bpy.context.scene.collection.objects.link(cobj)
    bpy.context.view_layer.update()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(cobj.evaluated_get(depsgraph))
    bpy.data.objects.remove(cobj, do_unlink=True)
    bpy.data.curves.remove(curve)
    mesh.name = c["object_name"]

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    # Rotate curve space into Blender space: local Y (profile Z) -> world Z, extrude axis -> world Y
    for v in bm.verts:
        x, y, z = v.co
        v.co = (x, -z, y)
    # Taper blade thickness: full handle thickness at the root, blade_thickness past it,
    # and thinner toward the concave cutting edge.
    ratio = c["blade_thickness"] / c["handle_thickness"]
    ramp = 0.012
    for v in bm.verts:
        if v.co.z < z0 + ramp:
            t = min(1.0, (z0 + ramp - v.co.z) / (2 * ramp))
            v.co.y *= 1.0 + (ratio - 1.0) * t
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(c["object_name"], mesh)
    bpy.context.scene.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = False           # hard-surface: flat shading keeps the edge readable

    mat = bpy.data.materials.get("KarambitSteel") or bpy.data.materials.new("KarambitSteel")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.55, 0.56, 0.58, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.9
        bsdf.inputs["Roughness"].default_value = 0.35
    mesh.materials.append(mat)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    chi = len(bm.verts) - len(bm.edges) + len(bm.faces)
    bm.free()
    tris = sum(len(p.vertices) - 2 for p in mesh.polygons)

    report.update({
        "object": obj.name, "tris": tris, "chi": chi, "non_manifold": non_manifold,
        "dimensions_m": [round(d, 4) for d in obj.dimensions],
        "origin": "ring centre (world origin)",
    })

    export_path = os.path.abspath(os.path.expanduser(c["export_path"])) if c.get("export_path") else None
    if export_path:
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        for o in bpy.context.view_layer.objects:
            o.select_set(o == obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.gltf(filepath=export_path, export_format='GLB', use_selection=True,
                                  export_yup=True, export_animations=False)
        report["export_path"] = export_path

    report["ok"] = chi == 0 and non_manifold == 0
    print(f"[karambit] tris={tris} chi={chi} non_manifold={non_manifold} -> {'OK' if report['ok'] else 'CHECK'}")
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
