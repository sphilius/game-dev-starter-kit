"""
cleanup_for_godot.py - sanitize an AI-generated mesh and export a game-ready GLB.

Pipeline stage: 2 (after generation, BEFORE rigging).
Run it BEFORE Mixamo / AccuRIG / auto-rig. Joining meshes and applying transforms
on an already-skinned mesh breaks its skin weights.

What it does, in order:
  1. (optional) clear the scene, import a GLB/GLTF/FBX/OBJ
  2. drop cameras/lights/empties, join all meshes into one object
  3. apply transforms, weld split vertices, recalc normals, fill small holes
  4. decimate to a triangle budget
  5. scale to a target height, set the origin (feet / centre / cursor / keep)
  6. report UV health (never repacks by default - repacking destroys baked textures)
  7. export GLB (+Y up, embedded textures) and return a JSON-able report

The report includes chi = V - E + F (Euler characteristic) per connected piece.
A closed mesh with one through-hole (a finger ring) has chi == 0; a fused ring gives 2.

Three ways to run it:
  * Blender MCP:   run_script_file(script_path=<this file>, config={...})
  * Blender GUI:   Scripting tab -> Open -> edit CONFIG -> Run Script
  * Headless:      blender -b -P cleanup_for_godot.py -- --config cfg.json
                   blender -b -P cleanup_for_godot.py -- import_path=in.glb target_tris=8000
"""

import bpy
import bmesh
import json
import math
import os
import sys

CONFIG = {
    "import_path": "~/karambit_bench/incoming/character_raw.glb",  # None = operate on the current scene
    "export_path": "~/karambit_bench/export/character.glb",       # None = don't export
    "object_name": "Character",
    "clear_scene": True,
    "target_tris": 12000,          # None = no decimation
    "target_height_m": 1.78,       # None = keep the scale
    "origin": "FEET",              # FEET | CENTER | CURSOR | KEEP
    "merge_distance": 0.0001,      # raise to 0.001 if outlines crack at shoulders/wrists
    "fill_holes_sides": 4,         # 0 = don't fill
    "remove_floaters_below": 0.0,  # drop loose pieces whose size < this fraction of the whole (0.02 is a good start)
    "smooth_shading": True,
    "pack_uvs": False,             # True only for untextured meshes; repacking breaks existing textures
    "uv_margin": 0.015,
    "keep_materials": True,
}


# ----------------------------------------------------------------------------- helpers

def _abspath(path):
    return os.path.abspath(os.path.expanduser(path)) if path else None


def _clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.armatures, bpy.data.actions):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def _import(path):
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        raise ValueError(f"Unsupported import format: {ext}")
    return [o for o in bpy.data.objects if o not in before]


def _select_only(objs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def _tri_count(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def _mesh_stats(obj):
    """Topology stats per connected piece, computed with bmesh on the evaluated mesh."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)

    # Connected components via flood fill over edges
    seen = set()
    pieces = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack = [v]
        comp_verts = set()
        while stack:
            cur = stack.pop()
            if cur.index in comp_verts:
                continue
            comp_verts.add(cur.index)
            for e in cur.link_edges:
                other = e.other_vert(cur)
                if other.index not in comp_verts:
                    stack.append(other)
        seen |= comp_verts
        edges = {e.index for vi in comp_verts for e in bm.verts[vi].link_edges}
        faces = {f.index for vi in comp_verts for f in bm.verts[vi].link_faces}
        tris = sum(len(bm.faces[fi].verts) - 2 for fi in faces) if faces else 0
        pieces.append({"verts": len(comp_verts), "tris": tris,
                       "chi": len(comp_verts) - len(edges) + len(faces)})
    chi = len(bm.verts) - len(bm.edges) + len(bm.faces)
    bm.free()
    pieces.sort(key=lambda p: -p["tris"])
    return {"non_manifold_edges": non_manifold, "boundary_edges": boundary,
            "chi": chi, "pieces": len(pieces), "largest_pieces": pieces[:5]}


def _uv_report(mesh):
    if not mesh.uv_layers:
        return {"uv_layers": 0}
    uv = mesh.uv_layers.active.data
    total = len(uv)
    outside = sum(1 for d in uv if not (-1e-4 <= d.uv.x <= 1.0001 and -1e-4 <= d.uv.y <= 1.0001))
    tiles = sorted({1001 + int(math.floor(d.uv.x)) + 10 * int(math.floor(d.uv.y)) for d in uv})
    return {"uv_layers": len(mesh.uv_layers), "loops": total,
            "loops_outside_0_1": outside, "udim_tiles": tiles[:20]}


def _remove_floaters(obj, fraction):
    """Delete disconnected pieces whose bounding-box diagonal is < fraction of the object's."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if not bm.verts:
        bm.free()
        return 0

    def diag(verts):
        xs, ys, zs = zip(*((v.co.x, v.co.y, v.co.z) for v in verts))
        return math.dist((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    limit = diag(bm.verts) * fraction
    remaining = set(bm.verts)
    doomed = []
    while remaining:
        seed = remaining.pop()
        island = {seed}
        stack = [seed]
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                o = e.other_vert(v)
                if o not in island:
                    island.add(o)
                    stack.append(o)
        remaining -= island
        if diag(island) < limit:
            doomed.append(island)
    for island in doomed:
        bmesh.ops.delete(bm, geom=list(island), context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    return len(doomed)


# ----------------------------------------------------------------------------- main

def main(config=None):
    cfg = dict(CONFIG)
    cfg.update(config or {})
    log = []
    report = {"ok": False, "log": log}

    import_path = _abspath(cfg.get("import_path"))
    export_path = _abspath(cfg.get("export_path"))

    if cfg.get("clear_scene") and import_path:
        _clear_scene()
    if import_path:
        if not os.path.exists(import_path):
            report["error"] = f"import_path not found: {import_path}"
            return report
        imported = _import(import_path)
        log.append(f"imported {len(imported)} objects from {import_path}")
        candidates = imported
    else:
        candidates = list(bpy.context.scene.objects)

    # Armatures mean the asset is already rigged: refuse, joining would wreck the skin.
    if any(o.type == 'ARMATURE' for o in candidates):
        report["error"] = ("Input contains an armature. Run cleanup BEFORE rigging; "
                           "use export_for_godot.py for rigged assets.")
        return report

    meshes = [o for o in candidates if o.type == 'MESH']
    if not meshes:
        report["error"] = "No mesh objects found"
        return report

    # Unparent while keeping world transforms, then remove non-mesh helpers (empties, cameras, lights).
    for o in meshes:
        if o.parent:
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
    for o in candidates:
        if o.type != 'MESH' and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Join into one object
    _select_only(meshes, meshes[0])
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = cfg.get("object_name") or obj.name
    obj.data.name = obj.name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    tris_in = _tri_count(obj.data)
    log.append(f"joined {len(meshes)} meshes -> {obj.name}, {tris_in} tris")

    if not cfg.get("keep_materials", True):
        obj.data.materials.clear()

    # Weld, normals, holes
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    v_before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=float(cfg["merge_distance"]))
    welded = v_before - len(bm.verts)
    filled = 0
    if cfg.get("fill_holes_sides"):
        res = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary],
                                   sides=int(cfg["fill_holes_sides"]))
        filled = len(res.get("faces", []))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    log.append(f"welded {welded} verts, filled {filled} small holes, normals recalculated")

    floaters = 0
    if cfg.get("remove_floaters_below"):
        floaters = _remove_floaters(obj, float(cfg["remove_floaters_below"]))
        log.append(f"removed {floaters} floating pieces smaller than {cfg['remove_floaters_below']:.0%} of the model")

    # Decimate to budget
    target = cfg.get("target_tris")
    cur = _tri_count(obj.data)
    if target and cur > target:
        mod = obj.modifiers.new("Decimate", 'DECIMATE')
        mod.decimate_type = 'COLLAPSE'
        mod.ratio = max(0.001, float(target) / cur)
        mod.use_collapse_triangulate = False
        _select_only([obj])
        bpy.ops.object.modifier_apply(modifier=mod.name)
        log.append(f"decimated {cur} -> {_tri_count(obj.data)} tris (ratio {mod.ratio:.3f})")

    # Scale to target height (Z up in Blender)
    height = obj.dimensions.z
    if cfg.get("target_height_m") and height > 0:
        s = float(cfg["target_height_m"]) / height
        obj.scale = (s, s, s)
        _select_only([obj])
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        log.append(f"scaled x{s:.4f} to height {cfg['target_height_m']} m")

    # Origin
    origin = (cfg.get("origin") or "KEEP").upper()
    _select_only([obj])
    if origin in ("FEET", "CENTER"):
        xs = [v.co.x for v in obj.data.vertices]
        ys = [v.co.y for v in obj.data.vertices]
        zs = [v.co.z for v in obj.data.vertices]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        cz = min(zs) if origin == "FEET" else (min(zs) + max(zs)) / 2
        for v in obj.data.vertices:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= cz
        obj.location = (0.0, 0.0, 0.0)
    elif origin == "CURSOR":
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        obj.location = (0.0, 0.0, 0.0)
    obj.data.update()

    if cfg.get("smooth_shading"):
        for p in obj.data.polygons:
            p.use_smooth = True

    if cfg.get("pack_uvs") and obj.data.uv_layers:
        _select_only([obj])
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pack_islands(margin=float(cfg["uv_margin"]))
        bpy.ops.object.mode_set(mode='OBJECT')
        log.append("UV islands repacked")

    report.update({
        "object": obj.name,
        "tris_in": tris_in,
        "floaters_removed": floaters,
        "tris": _tri_count(obj.data),
        "verts": len(obj.data.vertices),
        "dimensions_m": [round(d, 4) for d in obj.dimensions],
        "materials": [m.name for m in obj.data.materials if m],
        "uv": _uv_report(obj.data),
        **_mesh_stats(obj),
    })

    if export_path:
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        _select_only([obj])
        bpy.ops.export_scene.gltf(filepath=export_path, export_format='GLB', use_selection=True,
                                  export_apply=True, export_yup=True, export_animations=False)
        report["export_path"] = export_path
        report["export_bytes"] = os.path.getsize(export_path)
        log.append(f"exported {export_path}")

    report["ok"] = True
    for line in log:
        print("[cleanup]", line)
    return report


# ----------------------------------------------------------------------------- CLI

def _parse_cli(cfg):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config":
            with open(os.path.expanduser(argv[i + 1])) as fh:
                cfg.update(json.load(fh))
            i += 2
            continue
        if "=" in arg:
            key, val = arg.split("=", 1)
            try:
                cfg[key] = json.loads(val)
            except ValueError:
                cfg[key] = val
        i += 1
    return cfg


if __name__ == "__main__":
    _result = main(_parse_cli(dict(CONFIG)))
    print("PIPELINE_RESULT " + json.dumps(_result))
    if bpy.app.background:
        sys.exit(0 if _result.get("ok") else 1)
