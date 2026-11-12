"""blender_gate.py - the three 3D checks that need real geometry: holes, bending, and a look.

Run by gate3d.py inside Blender (never directly by Godot or plain Python):

    blender -b --factory-startup --python-exit-code 1 -P blender_gate.py -- \
        glb=model.glb out=result.json render_dir=renders [bend=1] [resolution=512]

Writes result.json with:
  non_manifold_edges   edges that do not join exactly two faces (holes, loose flaps, T-junctions).
                       They break auto-rigging and booleans; a few are normal on flat cards.
  loose_vertices       vertices that belong to no face.
  bounds               the bounding box with the armature applied (Y up, metres); gate3d uses it
                       for rigged models, whose in-file bounds are not the real size.
  bend                 for rigged models: every joint with shared weights is bent 90 degrees and
                       the skin there is measured. retention = how much of its distance from the
                       joint the worst part of the fold keeps (1.0 = rigid, 0.71 = the usual
                       "rubber hose" pinch of plain skinning, far below that = broken weights).
  renders              turnaround PNGs (front, side, back, three-quarter) for a human glance.

"-b" runs Blender with no window, "-P" runs this file, and everything after "--" is ours.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

# pipeline3d's render script already does headless turnarounds; reuse it instead of copying it.
PIPELINE3D_BLENDER = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "..", "..", "..", "pipeline3d", "blender"))


def parse_args() -> dict:
    """Turns ["glb=a.glb", "bend=1"] (the words after "--") into {"glb": "a.glb", "bend": "1"}."""
    words = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    # A dict comprehension; split("=", 1) splits on the first "=" only, so paths may contain "=".
    return {word.split("=", 1)[0]: word.split("=", 1)[1] for word in words if "=" in word}


def import_model(path: str) -> None:
    """Empties the scene and imports the model."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    if path.lower().endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    elif path.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(f"unsupported model format: {path}")
    bpy.context.view_layer.update()        # Blender 5.x: new objects are listed only after an update


def visible_meshes() -> list:
    """Mesh objects that are real geometry.

    Skipped: collision helpers (named -col / -convcolonly), and the little shapes Blender's
    glTF importer creates to DRAW bones with (an "Icosphere" per armature). Those are editor
    decoration, not part of the model, but they are mesh objects and would be measured.
    """
    # A set comprehension: every object used as some bone's display shape.
    bone_shapes = {bone.custom_shape for obj in bpy.context.scene.objects if obj.type == 'ARMATURE'
                   for bone in obj.pose.bones if bone.custom_shape}
    return [o for o in bpy.context.scene.objects
            if o.type == 'MESH' and o not in bone_shapes and "-col" not in o.name and "-convcol" not in o.name]


def topology() -> dict:
    """Counts non-manifold edges and loose vertices over every visible mesh.

    Vertices at the same position are merged first: glTF splits vertices along UV seams and
    hard edges, which would otherwise make every seam look like a hole.
    """
    non_manifold = 0
    loose = 0
    per_mesh = []
    for obj in visible_meshes():
        bm = bmesh.new()                   # bmesh = Blender's editable mesh structure
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bad_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
        loose_verts = sum(1 for vert in bm.verts if not vert.link_faces)
        per_mesh.append({"mesh": obj.name, "non_manifold_edges": bad_edges, "loose_vertices": loose_verts,
                         "faces": len(bm.faces)})
        non_manifold += bad_edges
        loose += loose_verts
        bm.free()
    return {"non_manifold_edges": non_manifold, "loose_vertices": loose, "meshes": per_mesh}


def deformed_positions(obj) -> list:
    """World positions of every vertex of `obj` with the armature's current pose applied."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    positions = [evaluated.matrix_world @ v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    return positions


def rest_pose() -> None:
    """Puts every armature in its rest pose with no animation playing.

    After an import Blender leaves the first clip active (for a character with a clip
    library that can be "crouch"), which would make every measurement below wrong.
    """
    for obj in bpy.context.scene.objects:
        if obj.type != 'ARMATURE':
            continue
        if obj.animation_data:
            obj.animation_data.action = None
        for pose_bone in obj.pose.bones:
            pose_bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def posed_bounds() -> dict:
    """The model's real bounding box with the skeleton applied, in glTF axes (Y up), in metres.

    A rigged .glb stores its vertices in "bind space": before the armature's scale and pose.
    Read straight from the file, a 1.8 m character can look 2 cm tall. Here Blender has
    already applied the armature, so these are the numbers the game will see.
    """
    points = [point for obj in visible_meshes() for point in deformed_positions(obj)]
    if not points:
        return {}
    # Blender is Z-up and glTF/Godot are Y-up: glTF (x, y, z) = Blender (x, z, -y).
    converted = [(p.x, p.z, -p.y) for p in points]
    low = [round(min(c[axis] for c in converted), 4) for axis in range(3)]
    high = [round(max(c[axis] for c in converted), 4) for axis in range(3)]
    return {"min": low, "max": high}


def bend_test(angle_degrees: float = 90.0) -> dict:
    """Bends every skinned joint and measures how well the skin around it holds its volume.

    A joint is a (parent bone, child bone) pair where at least 8 vertices carry weight on
    BOTH bones: that shared band is the fold. Only the child bone is rotated, about its local
    X axis (in Blender a bone's Y axis runs along its length, so X is always a bending axis,
    never a twist). For each fold vertex: distance to the joint after / before. The 10th
    percentile is reported, i.e. the part that caves in most.
    """
    armature = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
    meshes = [o for o in visible_meshes() if o.find_armature() == armature] if armature else []
    if not armature or not meshes:
        return {"tested": False, "reason": "no rigged mesh"}
    # Start from the rest pose with no animation playing.
    if armature.animation_data:
        armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)

    joints = []
    for obj in meshes:
        group_names = {group.index: group.name for group in obj.vertex_groups}
        rest = deformed_positions(obj)
        # weights[i] = {bone name: weight} for vertex i
        weights = [{group_names[g.group]: g.weight for g in v.groups if g.weight > 0.1 and g.group in group_names}
                   for v in obj.data.vertices]
        for pose_bone in armature.pose.bones:
            parent = pose_bone.parent
            if parent is None:
                continue
            fold = [i for i, w in enumerate(weights) if pose_bone.name in w and parent.name in w]
            if len(fold) < 8:
                continue
            joint = armature.matrix_world @ pose_bone.head
            pose_bone.rotation_mode = 'XYZ'
            pose_bone.rotation_euler = (math.radians(angle_degrees), 0.0, 0.0)
            bent = deformed_positions(obj)
            pose_bone.rotation_euler = (0.0, 0.0, 0.0)
            ratios = sorted((bent[i] - joint).length / max((rest[i] - joint).length, 1e-6) for i in fold)
            joints.append({"joint": f"{parent.name}>{pose_bone.name}", "mesh": obj.name, "fold_vertices": len(fold),
                           "retention": round(ratios[len(ratios) // 10], 3),
                           "mean": round(sum(ratios) / len(ratios), 3)})
    if not joints:
        return {"tested": False, "reason": "no joint has 8+ vertices weighted to both bones"}
    worst = min(joints, key=lambda j: j["retention"])
    return {"tested": True, "joints_tested": len(joints), "worst_retention": worst["retention"],
            "worst_joint": worst["joint"], "joints": sorted(joints, key=lambda j: j["retention"])}


def turnaround(render_dir: str, prefix: str, resolution: int) -> list:
    """Renders front / side / back / three-quarter views with pipeline3d's render_preview.py."""
    sys.path.insert(0, PIPELINE3D_BLENDER)
    import render_preview                      # noqa: E402  (imported late: it needs bpy loaded)
    report = render_preview.main({"out_dir": render_dir, "prefix": prefix, "resolution": resolution,
                                  "clear_scene": False})
    return [os.path.abspath(p) for p in report.get("files", report.get("renders", []))]


def main() -> None:
    """Imports the model, runs the checks that were asked for, writes the JSON result."""
    args = parse_args()
    import_model(args["glb"])
    rest_pose()
    result = {"blender": bpy.app.version_string, "topology": topology(), "bounds": posed_bounds()}
    if args.get("bend", "1") == "1":
        result["bend"] = bend_test()
    if args.get("render_dir"):
        prefix = os.path.splitext(os.path.basename(args["glb"]))[0]
        result["renders"] = turnaround(args["render_dir"], prefix, int(args.get("resolution", "512")))
    with open(args["out"], "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(f"[blender_gate] wrote {args['out']}")


main()
