"""
bake_diffuse.py - bake colour (and optionally normals) from a high-poly source onto a low-poly target.

Use it when you retopologize or decimate a textured AI mesh, or when you conform a
generated sculpt onto a template body (MetaHuman / a humanoid base) and need its skin
colour and tattoos on the clean topology.

Settings follow the Stefan 3D AI video: Cycles, Diffuse pass with Color only (no direct
or indirect light), selected-to-active, cage extrusion 0.01. The low-poly target needs
UVs; if it has none, Smart UV Project is used as a fallback (fine for props; for
characters use a proper unwrap or Tripo Smart UV first).

Normal maps are baked in OpenGL convention (Y+), which is what Godot expects. Unreal
needs DirectX (Y-): tick "Flip Green Channel" on import there.
"""

import bpy
import json
import os
import sys

CONFIG = {
    "high": None,                  # source mesh name (textured high-poly)
    "low": None,                   # target mesh name (clean low-poly with UVs)
    "size": 2048,
    "out_dir": "~/pipeline_bakes",
    "bake_normal": False,
    "cage_extrusion": 0.01,
    "max_ray_distance": 0.0,
    "samples": 1,                  # diffuse colour needs no more than 1 sample
    "margin_px": 16,
    "assign_to_low": True,         # rebuild the low-poly material with the baked maps
}


def _ensure_uv(obj):
    if obj.data.uv_layers:
        return False
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj],
                                   selected_editable_objects=[obj]):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(island_margin=0.01)
        bpy.ops.object.mode_set(mode='OBJECT')
    return True


def _target_image_node(obj, image):
    """Every material on the target needs an active Image Texture node pointing at the bake image."""
    if not obj.data.materials:
        obj.data.materials.append(bpy.data.materials.new(obj.name + "_baked"))
    nodes_made = []
    for mat in obj.data.materials:
        mat.use_nodes = True
        nt = mat.node_tree
        node = nt.nodes.new('ShaderNodeTexImage')
        node.image = image
        node.name = "_bake_target"
        nt.nodes.active = node
        nodes_made.append((mat, node))
    return nodes_made


def _bake(high, low, pass_type, name, c):
    img = bpy.data.images.new(name, c["size"], c["size"], alpha=False,
                              float_buffer=False, is_data=(pass_type == 'NORMAL'))
    made = _target_image_node(low, img)
    scene = bpy.context.scene
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.cage_extrusion = float(c["cage_extrusion"])
    bake.max_ray_distance = float(c["max_ray_distance"])
    bake.margin = int(c["margin_px"])
    if pass_type == 'DIFFUSE':
        bake.use_pass_direct = False
        bake.use_pass_indirect = False
        bake.use_pass_color = True
    else:
        bake.normal_space = 'TANGENT'
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (high, low))
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.bake(type=pass_type)
    out = os.path.join(os.path.abspath(os.path.expanduser(c["out_dir"])), f"{name}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.filepath_raw = out
    img.file_format = 'PNG'
    img.save()
    for mat, node in made:
        mat.node_tree.nodes.remove(node)
    return img, out


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    high = bpy.data.objects.get(c["high"] or "")
    low = bpy.data.objects.get(c["low"] or "")
    if not high or not low:
        return {"ok": False, "error": "set CONFIG high and low to existing mesh names"}
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = int(c["samples"])
    made_uv = _ensure_uv(low)

    color_img, color_path = _bake(high, low, 'DIFFUSE', f"{low.name}_color", c)
    normal_img, normal_path = (None, None)
    if c.get("bake_normal"):
        normal_img, normal_path = _bake(high, low, 'NORMAL', f"{low.name}_normal", c)

    if c.get("assign_to_low"):
        mat = bpy.data.materials.new(low.name + "_baked")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = color_img
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if normal_img:
            ntex = nt.nodes.new('ShaderNodeTexImage')
            ntex.image = normal_img
            ntex.image.colorspace_settings.name = 'Non-Color'
            nmap = nt.nodes.new('ShaderNodeNormalMap')
            nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        low.data.materials.clear()
        low.data.materials.append(mat)

    report = {"ok": True, "color": color_path, "normal": normal_path,
              "smart_uv_fallback_used": made_uv, "size": c["size"]}
    print("[bake]", report)
    return report


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
