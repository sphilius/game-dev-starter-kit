"""
udim_to_01.py - move UDIM tiles (1002, 1003, ...) back into the 0-1 UV square.

Godot and most game engines sample one 0-1 texture per material, not UDIM arrays.
MetaHuman DNA exports and some generators put the head on tile 1001 and the body on
1002. This shifts every face back into 0-1 by its tile offset (the "-1 on U" fix from
the Stefan 3D AI video) and, by default, gives each tile its own material slot so each
tile can keep its own texture.

Faces are assigned to a tile by the centre of their UVs, so islands must not straddle
tile borders (true for UDIM layouts by definition).
"""

import bpy
import json
import math
import sys

CONFIG = {
    "objects": [],                 # mesh names; [] = all meshes in the scene
    "split_materials": True,       # one material per tile: <material>_<tile>
}


def _process(obj, split):
    mesh = obj.data
    if not mesh.uv_layers:
        return {"mesh": obj.name, "tiles": [], "note": "no UVs"}
    uv = mesh.uv_layers.active.data
    tiles_found = {}
    for poly in mesh.polygons:
        loops = list(poly.loop_indices)
        cu = sum(uv[i].uv.x for i in loops) / len(loops)
        cv = sum(uv[i].uv.y for i in loops) / len(loops)
        du, dv = math.floor(cu), math.floor(cv)
        tile = 1001 + du + 10 * dv
        tiles_found.setdefault(tile, []).append(poly.index)
        if du or dv:
            for i in loops:
                uv[i].uv.x -= du
                uv[i].uv.y -= dv
    if split and len(tiles_found) > 1:
        base_slots = list(mesh.materials)
        slot_for = {}
        for tile, polys in sorted(tiles_found.items()):
            if tile == 1001:
                continue
            for pi in polys:
                poly = mesh.polygons[pi]
                key = (poly.material_index, tile)
                if key not in slot_for:
                    src = base_slots[poly.material_index] if base_slots else None
                    new = src.copy() if src else bpy.data.materials.new("Material")
                    new.name = f"{src.name if src else 'Material'}_{tile}"
                    mesh.materials.append(new)
                    slot_for[key] = len(mesh.materials) - 1
                poly.material_index = slot_for[key]
    mesh.update()
    return {"mesh": obj.name, "tiles": sorted(tiles_found),
            "faces_per_tile": {str(k): len(v) for k, v in sorted(tiles_found.items())}}


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    objs = [bpy.data.objects[n] for n in c["objects"]] if c.get("objects") else \
        [o for o in bpy.context.scene.objects if o.type == 'MESH']
    results = [_process(o, c["split_materials"]) for o in objs]
    for r in results:
        print("[udim]", r)
    return {"ok": True, "meshes": results}


def _parse_cli(cfg):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for a in argv:
        if "=" in a:
            k, v = a.split("=", 1)
            try:
                cfg[k] = json.loads(v)
            except ValueError:
                cfg[k] = v
    return cfg


if __name__ == "__main__":
    _result = main(_parse_cli(dict(CONFIG)))
    print("PIPELINE_RESULT " + json.dumps(_result))
    if bpy.app.background:
        sys.exit(0 if _result.get("ok") else 1)
