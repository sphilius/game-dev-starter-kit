"""
transfer_weights.py - skin garments / armour / accessories by copying weights from the body.

The "Data Transfer" trick from the Stefan 3D AI MetaHuman video, automated for any number
of meshes: every target gets the body's vertex groups projected onto it (nearest face,
interpolated), is parented to the body's armature with an Armature modifier, then its
weights are limited to N influences and normalized.

Garments must already sit on the body in the rest pose (A-pose / T-pose), and should be
cleaned (cleanup_for_godot.py with target_height_m=None, origin=KEEP) before this step.
"""

import bpy
import json
import os
import sys

CONFIG = {
    "body": None,                  # body mesh name (must be skinned to an armature); None = active object
    "targets": [],                 # mesh names; [] = every selected mesh except the body
    "mapping": "POLYINTERP_NEAREST",   # or NEAREST (nearest vertex) for low-poly bodies
    "max_influences": 4,
    "export_path": None,           # optional GLB of armature + body + targets
}


def _ctx(obj):
    return bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                     selected_editable_objects=[obj])


def _limit_and_normalize(obj, max_inf):
    names = {g.index: g.name for g in obj.vertex_groups}
    empty = 0
    for v in obj.data.vertices:
        ws = sorted(((g.weight, g.group) for g in v.groups if g.weight > 1e-5), reverse=True)
        if not ws:
            empty += 1
            continue
        keep = ws[:max_inf]
        tot = sum(w for w, _ in keep)
        for _, gi in ws[max_inf:]:
            obj.vertex_groups[names[gi]].remove([v.index])
        for w, gi in keep:
            obj.vertex_groups[names[gi]].add([v.index], w / tot, 'REPLACE')
    return empty


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    body = bpy.data.objects[c["body"]] if c.get("body") else bpy.context.view_layer.objects.active
    if body is None or body.type != 'MESH':
        return {"ok": False, "error": "body mesh not found"}
    arm = body.find_armature()
    if arm is None:
        return {"ok": False, "error": f"{body.name} is not skinned to an armature"}

    names = c.get("targets") or [o.name for o in bpy.context.selected_objects if o.type == 'MESH' and o != body]
    targets = [bpy.data.objects[n] for n in names]
    if not targets:
        return {"ok": False, "error": "no target meshes (pass targets or select them)"}

    results = []
    for obj in targets:
        obj.vertex_groups.clear()
        for m in [m for m in obj.modifiers if m.type in ('ARMATURE', 'DATA_TRANSFER')]:
            obj.modifiers.remove(m)
        mw = obj.matrix_world.copy()
        obj.parent = arm
        obj.matrix_world = mw

        dt = obj.modifiers.new("WeightTransfer", 'DATA_TRANSFER')   # first in the stack
        dt.object = body
        dt.use_vert_data = True
        dt.data_types_verts = {'VGROUP_WEIGHTS'}
        dt.vert_mapping = c["mapping"]
        dt.layers_vgroup_select_src = 'ALL'
        dt.layers_vgroup_select_dst = 'NAME'
        with _ctx(obj):
            bpy.ops.object.datalayout_transfer(modifier=dt.name)   # creates the matching groups
            bpy.ops.object.modifier_apply(modifier=dt.name)

        mod = obj.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
        empty = _limit_and_normalize(obj, int(c["max_influences"]))
        used = sum(1 for g in obj.vertex_groups
                   if any(g.index == vg.group for v in obj.data.vertices for vg in v.groups))
        results.append({"mesh": obj.name, "groups": len(obj.vertex_groups), "groups_used": used,
                        "unweighted_verts": empty})
        print(f"[weights] {obj.name}: {used} bone groups used, {empty} unweighted verts")

    report = {"ok": all(r["unweighted_verts"] == 0 for r in results), "armature": arm.name,
              "body": body.name, "targets": results}
    if c.get("export_path"):
        path = os.path.abspath(os.path.expanduser(c["export_path"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for o in bpy.context.scene.objects:
            o.select_set(o in [arm, body] + targets)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True,
                                  export_animations=True, export_animation_mode='NLA_TRACKS')
        report["export_path"] = path
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
