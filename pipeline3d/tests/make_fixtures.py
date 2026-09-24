"""
make_fixtures.py - build stand-in "AI generated" meshes so the pipeline can be tested
without spending generation credits.

  quadruped_raw.glb  metaball wolf-like creature, facing +X (tests auto-orient), triangulated
  humanoid_raw.glb   metaball A-pose figure, 3 separate objects + an empty parent,
                     split verts (like glTF from generators), scaled to ~2.4 units tall

Usage: blender -b -P make_fixtures.py -- out_dir=/path
"""

import bpy
import json
import math
import os
import sys


def _clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _metaball(name, elements, resolution=0.05):
    mb = bpy.data.metaballs.new(name)
    mb.resolution = resolution
    mb.render_resolution = resolution
    obj = bpy.data.objects.new(name, mb)
    bpy.context.scene.collection.objects.link(obj)
    for kind, co, size in elements:
        el = mb.elements.new(type=kind)
        el.co = co
        if kind == 'BALL':
            el.radius = size
        else:
            el.radius = size[0]
            el.size_x, el.size_y, el.size_z = size[1]
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    bpy.data.objects.remove(obj, do_unlink=True)
    out = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(out)
    return out


def quadruped():
    # Built facing -Y, then turned to face +X so auto_orient has work to do.
    els = [('ELLIPSOID', (0, 0.05, 0.62), (0.26, (1.0, 2.4, 1.0))),     # body
           ('BALL', (0, -0.55, 0.84), 0.19),                              # head
           ('ELLIPSOID', (0, -0.74, 0.78), (0.11, (1.0, 1.7, 1.0))),     # snout
           ('ELLIPSOID', (0, -0.38, 0.74), (0.16, (1.0, 1.5, 1.2))),     # neck
           ('ELLIPSOID', (0, 0.66, 0.56), (0.11, (1.0, 2.6, 1.0))),      # tail root
           ('BALL', (0, 0.86, 0.46), 0.09)]                               # tail tip
    for x in (-0.13, 0.13):
        for y in (-0.33, 0.45):
            els.append(('ELLIPSOID', (x, y, 0.36), (0.12, (1.0, 1.0, 3.0))))
            els.append(('BALL', (x, y - 0.04, 0.08), 0.11))
    obj = _metaball("Wolf", els)
    obj.rotation_euler.z = math.radians(90)
    return obj


def humanoid():
    body = _metaball("Body", [
        ('ELLIPSOID', (0, 0, 1.22), (0.24, (1.1, 0.7, 1.5))),
        ('BALL', (0, 0, 1.58), 0.19),
        ('ELLIPSOID', (0.34, 0, 1.24), (0.11, (2.6, 1.0, 1.0))),
        ('ELLIPSOID', (-0.34, 0, 1.24), (0.11, (2.6, 1.0, 1.0))),
        ('ELLIPSOID', (0.11, 0, 0.66), (0.15, (1.0, 1.0, 3.4))),
        ('ELLIPSOID', (-0.11, 0, 0.66), (0.15, (1.0, 1.0, 3.4))),
        ('BALL', (0.11, -0.04, 0.12), 0.12),
        ('BALL', (-0.11, -0.04, 0.12), 0.12),
    ])
    for o in (body,):
        o.rotation_euler.y = 0
    # Two "accessory" objects under an empty, like a generator's scene graph
    root = bpy.data.objects.new("GLTF_SceneRootNode", None)
    bpy.context.scene.collection.objects.link(root)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.2, minor_radius=0.03, location=(0, 0, 1.05))
    belt = bpy.context.object
    belt.name = "Belt"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.012, location=(0.5, 0.6, 0.3))
    crumb = bpy.context.object
    crumb.name = "FloatingCrumb"
    for o in (body, belt, crumb):
        o.parent = root
    root.scale = (1.35, 1.35, 1.35)
    # Split every face's vertices at "UV seams": triangulate + edge split everything
    for o in (body, belt):
        bpy.context.view_layer.objects.active = o
        mod = o.modifiers.new("split", 'EDGE_SPLIT')
        mod.split_angle = math.radians(20)
        mod.use_edge_sharp = False
        for sel in bpy.context.view_layer.objects:
            sel.select_set(sel == o)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return root


def _export(path, objs):
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = dict(a.split("=", 1) for a in argv if "=" in a).get("out_dir", ".")
    os.makedirs(out, exist_ok=True)
    _clear()
    wolf = quadruped()
    _export(os.path.join(out, "quadruped_raw.glb"), [wolf])
    _clear()
    root = humanoid()
    _export(os.path.join(out, "humanoid_raw.glb"), [root] + list(root.children))
    print("FIXTURES", json.dumps({"out_dir": out}))
