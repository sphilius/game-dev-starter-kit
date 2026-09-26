"""
quadruped_rig.py - auto-rig a quadruped mesh and generate in-place game clips.

Mixamo and most free auto-riggers are humanoid-only. This builds a 31-bone game skeleton
(root, pelvis, 3 spine, 2 neck, head, jaw, 4 tail, 5 per front leg, 4 per hind leg),
skins the mesh (bone heat, falling back to distance weights), keys four starter clips
at 30 fps with a stationary root, stores each as its own NLA track, and exports a GLB
Godot imports as one skeleton with N animations.

Starter clips (names follow the Stefan 3D AI wolf example; rename with clip_prefix):
    idle    2.5 s   loop  breathing, head glance, tail sway
    walk    0.833 s loop  diagonal trot cycle
    attack  1.7 s   once  anticipation -> lunge -> bite contact at 1.3 s -> recover
    death   1.333 s once  stagger -> collapse onto side -> hold

These are procedural first passes: good enough to wire gameplay, not final animation.
Refine them in Blender (Graph Editor / NLA), replace them with video-mocap output, or
ask an agent to key specific beats over Blender MCP using a reference video.

Input expectations: mesh stands on the ground (lowest point = feet), body length along
one horizontal axis. auto_orient rotates it so the head faces -Y (Blender "front").
Every landmark is a fraction of the bounding box; override any of them in CONFIG
["landmarks"] after looking at render_preview.py output.
"""

import bpy
import json
import math
import os
import sys
from mathutils import Matrix, Vector

CONFIG = {
    "mesh_name": None,            # None = largest mesh in the scene
    "import_path": None,          # optional GLB/FBX/OBJ to import first
    "clear_scene": False,
    "auto_orient": True,          # rotate so the body runs along Y with the head at -Y
    "head_direction": "AUTO",     # AUTO | -Y | +Y  (after auto_orient)
    "armature_name": "QuadrupedRig",
    "skinning": "AUTO",           # AUTO (bone heat, fallback) | PROXIMITY
    "max_influences": 4,
    "fps": 30,
    "clip_prefix": "",            # e.g. "wolf_" -> wolf_idle, wolf_walk ...
    "clips": ["idle", "walk", "attack", "death"],
    "stride_deg": 24.0,           # upper-leg swing amplitude in the walk
    "export_path": None,          # e.g. ~/game/export/wolf.glb
    "landmarks": {},              # overrides, see DEFAULT_LANDMARKS
}

# (u, z, x): u = 0 at the nose .. 1 at the rump, z = 0 ground .. 1 top, x = lateral fraction of half-width
DEFAULT_LANDMARKS = {
    "pelvis": [(0.80, 0.62, 0), (0.66, 0.64, 0)],
    "spine_01": [(0.66, 0.64, 0), (0.52, 0.65, 0)],
    "spine_02": [(0.52, 0.65, 0), (0.39, 0.66, 0)],
    "spine_03": [(0.39, 0.66, 0), (0.27, 0.68, 0)],
    "neck_01": [(0.27, 0.68, 0), (0.19, 0.76, 0)],
    "neck_02": [(0.19, 0.76, 0), (0.13, 0.82, 0)],
    "head": [(0.13, 0.82, 0), (0.02, 0.78, 0)],
    "jaw": [(0.11, 0.74, 0), (0.03, 0.70, 0)],
    "tail_01": [(0.82, 0.62, 0), (0.87, 0.56, 0)],
    "tail_02": [(0.87, 0.56, 0), (0.92, 0.48, 0)],
    "tail_03": [(0.92, 0.48, 0), (0.96, 0.40, 0)],
    "tail_04": [(0.96, 0.40, 0), (1.00, 0.32, 0)],
    "scapula": [(0.28, 0.70, 0.45), (0.25, 0.52, 0.55)],
    "upperarm": [(0.25, 0.52, 0.55), (0.27, 0.32, 0.55)],
    "forearm": [(0.27, 0.32, 0.55), (0.26, 0.10, 0.55)],
    "hand": [(0.26, 0.10, 0.55), (0.245, 0.03, 0.55)],
    "front_toe": [(0.245, 0.03, 0.55), (0.215, 0.0, 0.55)],
    "thigh": [(0.76, 0.60, 0.55), (0.72, 0.36, 0.55)],
    "shin": [(0.72, 0.36, 0.55), (0.80, 0.17, 0.55)],
    "hock": [(0.80, 0.17, 0.55), (0.79, 0.04, 0.55)],
    "hind_toe": [(0.79, 0.04, 0.55), (0.76, 0.0, 0.55)],
}

PARENTS = {
    "pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02",
    "neck_01": "spine_03", "neck_02": "neck_01", "head": "neck_02", "jaw": "head",
    "tail_01": "pelvis", "tail_02": "tail_01", "tail_03": "tail_02", "tail_04": "tail_03",
    "scapula": "spine_03", "upperarm": "scapula", "forearm": "upperarm", "hand": "forearm",
    "front_toe": "hand", "thigh": "pelvis", "shin": "thigh", "hock": "shin", "hind_toe": "hock",
}
LEG_BONES = ["scapula", "upperarm", "forearm", "hand", "front_toe", "thigh", "shin", "hock", "hind_toe"]
CONNECTED = {"spine_01", "spine_02", "spine_03", "neck_01", "neck_02", "head", "tail_02", "tail_03",
             "tail_04", "upperarm", "forearm", "hand", "front_toe", "shin", "hock", "hind_toe"}


# ----------------------------------------------------------------------------- geometry

def _pick_mesh(name):
    if name:
        return bpy.data.objects[name]
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("No mesh in scene")
    return max(meshes, key=lambda o: len(o.data.vertices))


def _world_verts(obj):
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def _bounds(pts):
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _orient(obj, cfg, log):
    pts = _world_verts(obj)
    lo, hi = _bounds(pts)
    if cfg["auto_orient"] and (hi.x - lo.x) > (hi.y - lo.y) * 1.15:
        obj.matrix_world = Matrix.Rotation(math.radians(90), 4, 'Z') @ obj.matrix_world
        bpy.context.view_layer.update()
        log.append("rotated 90 deg about Z so the body runs along Y")
        pts = _world_verts(obj)
        lo, hi = _bounds(pts)
    head = cfg["head_direction"].upper()
    if head == "AUTO":
        # Heuristic: the head end carries more mass high up than the tail end.
        length = hi.y - lo.y
        top = lo.z + 0.6 * (hi.z - lo.z)
        front = sum(1 for p in pts if p.y < lo.y + 0.25 * length and p.z > top)
        back = sum(1 for p in pts if p.y > hi.y - 0.25 * length and p.z > top)
        head = "-Y" if front >= back else "+Y"
        log.append(f"head direction guessed {head} (high verts front={front}, back={back})")
    if head == "+Y" and cfg["auto_orient"]:
        obj.matrix_world = Matrix.Rotation(math.radians(180), 4, 'Z') @ obj.matrix_world
        bpy.context.view_layer.update()
        log.append("rotated 180 deg so the head faces -Y")
    # Bake the transform so the rest pose equals the mesh as-is
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _bounds(_world_verts(obj))


# ----------------------------------------------------------------------------- armature

def _build_armature(cfg, lo, hi):
    L, H, W = hi.y - lo.y, hi.z - lo.z, hi.x - lo.x
    xc = (lo.x + hi.x) / 2
    marks = dict(DEFAULT_LANDMARKS)
    for k, v in (cfg.get("landmarks") or {}).items():
        marks[k] = [tuple(p) for p in v]

    def P(u, z, x):
        return Vector((xc + x * W / 2, lo.y + u * L, lo.z + z * H))

    arm_data = bpy.data.armatures.new(cfg["armature_name"])
    arm = bpy.data.objects.new(cfg["armature_name"], arm_data)
    bpy.context.scene.collection.objects.link(arm)
    arm_data.display_type = 'STICK'
    for o in bpy.context.view_layer.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones

    root = eb.new("root")
    root.head = Vector((xc, (lo.y + hi.y) / 2, lo.z))
    root.tail = root.head + Vector((0, -0.25 * L, 0))
    root.use_deform = False
    root.align_roll(Vector((0, 0, 1)))

    def make(name, spec, side=""):
        (u0, z0, x0), (u1, z1, x1) = spec
        sign = 1.0 if side == ".L" else (-1.0 if side == ".R" else 0.0)   # facing -Y, .L is +X
        b = eb.new(name + side)
        b.head = P(u0, z0, x0 * sign)
        b.tail = P(u1, z1, x1 * sign)
        vertical = abs((b.tail - b.head).normalized().z) > 0.6
        b.align_roll(Vector((0, -1, 0)) if vertical else Vector((0, 0, 1)))
        return b

    bones = {}
    for name, spec in marks.items():
        if name in LEG_BONES:
            for side in (".L", ".R"):
                bones[name + side] = make(name, spec, side)
        else:
            bones[name] = make(name, spec)
    bones["root"] = root
    for name, b in bones.items():
        if name == "root":
            continue
        base, side = (name[:-2], name[-2:]) if name[-2:] in (".L", ".R") else (name, "")
        parent_base = PARENTS[base]
        parent = bones.get(parent_base + side) or bones.get(parent_base)
        b.parent = parent
        b.use_connect = base in CONNECTED and (b.head - parent.tail).length < 1e-4
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm


# ----------------------------------------------------------------------------- skinning

def _dist_to_segment(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (a + ab * t - p).length


def _proximity_weights(mesh_obj, arm, only=None):
    """Distance-to-bone weights. With `only` (vertex indices), fill just those and keep the rest."""
    segs = [(b.name, arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)
            for b in arm.data.bones if b.use_deform]
    if only is None:
        mesh_obj.vertex_groups.clear()
    groups = {n: (mesh_obj.vertex_groups.get(n) or mesh_obj.vertex_groups.new(name=n)) for n, _, _ in segs}
    mw = mesh_obj.matrix_world
    targets = mesh_obj.data.vertices if only is None else [mesh_obj.data.vertices[i] for i in only]
    for v in targets:
        p = mw @ v.co
        d = sorted(((_dist_to_segment(p, a, b), n) for n, a, b in segs))[:3]
        dmin = max(d[0][0], 1e-6)
        ws = [(n, 1.0 / (dd / dmin) ** 4) for dd, n in d if dd < dmin * 1.6]
        tot = sum(w for _, w in ws)
        for n, w in ws:
            groups[n].add([v.index], w / tot, 'REPLACE')


def _limit_and_normalize(mesh_obj, max_inf):
    names = {g.index: g.name for g in mesh_obj.vertex_groups}
    unweighted = 0
    for v in mesh_obj.data.vertices:
        ws = sorted(((g.weight, g.group) for g in v.groups if g.weight > 1e-5), reverse=True)
        if not ws:
            unweighted += 1
            continue
        keep = ws[:max_inf]
        tot = sum(w for w, _ in keep)
        for w, gi in ws[max_inf:]:
            mesh_obj.vertex_groups[names[gi]].remove([v.index])
        for w, gi in keep:
            mesh_obj.vertex_groups[names[gi]].add([v.index], w / tot, 'REPLACE')
    return unweighted


def _weld(mesh_obj, log):
    """glTF stores flat-shaded / UV-seamed meshes with vertices split at every hard edge, so an
    imported low-poly model is a soup of loose faces and bone heat fails. Welding restores the
    connected surface; flat shading is per face, so the faceted look is unchanged."""
    import bmesh
    me = mesh_obj.data
    # Remember which faces are flat-shaded (all corner normals == face normal) before welding,
    # because welding blends the imported custom normals and would smooth a faceted model.
    corner = me.corner_normals if hasattr(me, "corner_normals") else None
    flat = []
    for poly in me.polygons:
        if corner is None:
            flat.append(not poly.use_smooth)
            continue
        n = poly.normal
        flat.append(all(corner[li].vector.dot(n) > 0.999 for li in poly.loop_indices))
    bm = bmesh.new()
    bm.from_mesh(me)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    after = len(bm.verts)
    bm.to_mesh(me)
    bm.free()
    if after < before:
        with bpy.context.temp_override(object=mesh_obj, active_object=mesh_obj,
                                       selected_objects=[mesh_obj], selected_editable_objects=[mesh_obj]):
            if me.has_custom_normals:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
        if mesh_obj.get("flat_shaded"):
            flat = [True] * len(me.polygons)          # tagged faceted asset (build_lowpoly_creature)
        if len(flat) == len(me.polygons):
            for poly, is_flat in zip(me.polygons, flat):
                poly.use_smooth = not is_flat
        log.append(f"welded {before - after} split vertices before skinning "
                   f"({sum(flat)} flat-shaded faces kept flat)")
    me.update()


def _heat_weights(mesh_obj, arm, log):
    """Bone-heat weights computed on a temporary copy scaled to ~10 m.

    Blender's heat solver often fails on small (sub-metre) meshes; scaling a copy up and
    copying the resulting weights back by vertex index avoids that without touching the
    real mesh or armature. The real mesh is then parented with an Armature modifier.
    """
    dims = max(mesh_obj.dimensions) or 1.0
    k = max(1.0, 10.0 / dims)
    m2 = mesh_obj.copy()
    m2.data = mesh_obj.data.copy()
    a2 = arm.copy()
    a2.data = arm.data.copy()
    for o in (m2, a2):
        bpy.context.scene.collection.objects.link(o)
        o.matrix_world = arm.matrix_world.copy() if o is a2 else mesh_obj.matrix_world.copy()
        o.scale = tuple(v * k for v in o.scale)
        o.location = o.location * k
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (m2, a2))
    bpy.context.view_layer.objects.active = a2
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except RuntimeError as exc:
        log.append(f"bone heat failed: {exc}")
    mesh_obj.vertex_groups.clear()
    groups = {g.index: mesh_obj.vertex_groups.new(name=g.name) for g in m2.vertex_groups}
    for v, v2 in zip(mesh_obj.data.vertices, m2.data.vertices):
        for g in v2.groups:
            if g.weight > 1e-5:
                groups[g.group].add([v.index], g.weight, 'REPLACE')
    for o in (m2, a2):
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.armatures).remove(data)
    mesh_obj.parent = arm
    mesh_obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = next((m for m in mesh_obj.modifiers if m.type == 'ARMATURE'), None) \
        or mesh_obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm


def _skin(mesh_obj, arm, cfg, log):
    method = cfg["skinning"].upper()
    _weld(mesh_obj, log)
    if method == "AUTO":
        _heat_weights(mesh_obj, arm, log)
        missing = sum(1 for v in mesh_obj.data.vertices if not any(g.weight > 1e-5 for g in v.groups))
        if missing > len(mesh_obj.data.vertices) * 0.02:
            log.append(f"bone heat left {missing} verts unweighted -> using proximity weights")
            method = "PROXIMITY"
        else:
            if missing:
                # Bone heat can skip a few verts (thin tips, ears): give just those distance weights
                left = [v.index for v in mesh_obj.data.vertices if not any(g.weight > 1e-5 for g in v.groups)]
                _proximity_weights(mesh_obj, arm, only=left)
            log.append(f"bone heat weights ok ({missing} verts filled with distance weights)")
    if method == "PROXIMITY":
        mesh_obj.parent = arm
        mod = next((m for m in mesh_obj.modifiers if m.type == 'ARMATURE'), None) \
            or mesh_obj.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
        _proximity_weights(mesh_obj, arm)
    unweighted = _limit_and_normalize(mesh_obj, int(cfg["max_influences"]))
    return method, unweighted


# ----------------------------------------------------------------------------- animation

def _r(deg):
    return math.radians(deg)


def _clip_idle(t, n, cfg):
    s = t / n
    breath = math.sin(2 * math.pi * 2 * s)
    glance = math.sin(math.pi * min(1.0, max(0.0, (s - 0.25) / 0.5))) if 0.25 <= s <= 0.75 else 0.0
    return {
        "spine_02": (breath * 1.2, 0, 0), "spine_03": (breath * 1.5, 0, 0),
        "neck_01": (-breath * 1.0, 0, glance * 8), "head": (breath * 1.0, 0, glance * 14),
        "tail_01": (0, 0, math.sin(2 * math.pi * s) * 6), "tail_02": (0, 0, math.sin(2 * math.pi * s - 0.6) * 8),
        "tail_03": (0, 0, math.sin(2 * math.pi * s - 1.2) * 10),
    }


def _clip_walk(t, n, cfg):
    a = cfg["stride_deg"]
    ph = 2 * math.pi * t / n
    pose = {}
    # Diagonal pairs: front-left with hind-right, front-right with hind-left
    for side, off in ((".L", 0.0), (".R", math.pi)):
        f = ph + off
        h = ph + off + math.pi
        pose["upperarm" + side] = (a * math.sin(f), 0, 0)
        pose["forearm" + side] = (-max(0.0, math.cos(f)) * a * 1.4, 0, 0)
        pose["hand" + side] = (max(0.0, math.cos(f)) * a * 0.9, 0, 0)
        pose["thigh" + side] = (a * math.sin(h), 0, 0)
        pose["shin" + side] = (max(0.0, math.cos(h)) * a * 1.2, 0, 0)
        pose["hock" + side] = (-max(0.0, math.cos(h)) * a * 1.1, 0, 0)
    bob = math.sin(2 * ph)
    pose["pelvis"] = ((0, 0, 0), (0, 0, -0.012 * bob))       # (rot, loc) - loc in bone space
    pose["spine_02"] = (0, 0, math.sin(ph) * 2.0)
    pose["neck_01"] = (bob * 2.0, 0, 0)
    pose["head"] = (-bob * 2.5, 0, 0)
    pose["tail_01"] = (4, 0, math.sin(ph) * 8)
    pose["tail_02"] = (0, 0, math.sin(ph - 0.7) * 10)
    return pose


def _ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _clip_attack(t, n, cfg):
    f = t                         # frame 0..51 at 30 fps; bite contact at frame 39 (1.3 s)
    antic = _ease((f - 1) / 14) * (1 - _ease((f - 15) / 8))
    lunge = _ease((f - 15) / 19) * (1 - _ease((f - 41) / 10))
    jaw = _ease((f - 22) / 10) * (1 - _ease((f - 34) / 5))   # open, snaps shut at contact
    return {
        "pelvis": ((0, 0, 0), (0, 0.06 * lunge - 0.02 * antic, -0.03 * antic)),
        "spine_01": (-4 * antic + 3 * lunge, 0, 0), "spine_03": (-6 * antic + 4 * lunge, 0, 0),
        "neck_01": (10 * antic - 14 * lunge, 0, 0), "neck_02": (6 * antic - 10 * lunge, 0, 0),
        "head": (8 * antic - 12 * lunge, 0, 0), "jaw": (-32 * jaw, 0, 0),
        "thigh.L": (18 * antic - 10 * lunge, 0, 0), "thigh.R": (18 * antic - 10 * lunge, 0, 0),
        "shin.L": (-22 * antic + 8 * lunge, 0, 0), "shin.R": (-22 * antic + 8 * lunge, 0, 0),
        "upperarm.L": (-6 * antic + 18 * lunge, 0, 0), "upperarm.R": (-6 * antic + 14 * lunge, 0, 0),
        "forearm.L": (-12 * antic, 0, 0), "forearm.R": (-12 * antic, 0, 0),
        "tail_01": (12 * antic - 6 * lunge, 0, 0), "tail_02": (6 * antic, 0, 0),
    }


def _clip_death(t, n, cfg, height):
    f = t                         # frame 0..40; collapse by frame 30, hold to 40
    stagger = _ease((f - 1) / 9) * (1 - _ease((f - 12) / 10))
    fall = _ease((f - 8) / 22)
    drop = height * 0.42 * fall
    return {
        "pelvis": ((0, 78 * fall, 0), (0, 0, -drop)),
        "spine_03": (0, 8 * fall, 0), "neck_01": (14 * stagger - 10 * fall, 0, 12 * fall),
        "head": (18 * stagger - 20 * fall, 0, 10 * fall), "jaw": (-10 * fall, 0, 0),
        "upperarm.L": (30 * fall, 0, 0), "upperarm.R": (22 * fall, 0, 0),
        "forearm.L": (-40 * fall, 0, 0), "forearm.R": (-30 * fall, 0, 0),
        "thigh.L": (-25 * fall, 0, 0), "thigh.R": (-18 * fall, 0, 0),
        "shin.L": (30 * fall, 0, 0), "shin.R": (22 * fall, 0, 0),
        "tail_01": (-10 * fall, 0, 15 * fall), "tail_02": (-6 * fall, 0, 10 * fall),
    }


# Clips are keyed on frames 0..n, so at 30 fps each lasts exactly n/30 s in the engine and
# loops close on themselves (frame n == frame 0).
CLIPS = {  # name -> (length in frames at 30 fps, loop, generator)
    "idle": (75, True, _clip_idle),
    "walk": (25, True, _clip_walk),
    "attack": (51, False, _clip_attack),
    "death": (40, False, None),       # needs height, bound in _make_clips
}


def _make_clips(arm, cfg, height, log):
    scene = bpy.context.scene
    scene.render.fps = int(cfg["fps"])
    scene.render.fps_base = 1.0
    arm.animation_data_create()
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
    made = []
    for base in cfg["clips"]:
        if base not in CLIPS:
            log.append(f"unknown clip {base}, skipped")
            continue
        n, loop, gen = CLIPS[base]
        if base == "death":
            gen = lambda t, n_, c: _clip_death(t, n_, c, height)
        name = cfg["clip_prefix"] + base
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        arm.animation_data.action = act
        poses = {t: gen(t, n, cfg) for t in range(n + 1)}
        touched = sorted({b for p in poses.values() for b in p})
        for frame, pose in poses.items():
            for bname in touched:
                pb = arm.pose.bones.get(bname)
                if pb is None:
                    continue
                val = pose.get(bname, (0, 0, 0))
                rot, loc = (val if isinstance(val[0], tuple) else (val, (0, 0, 0)))
                pb.rotation_euler = (_r(rot[0]), _r(rot[1]), _r(rot[2]))
                pb.keyframe_insert("rotation_euler", frame=frame)
                if bname == "pelvis":
                    pb.location = loc
                    pb.keyframe_insert("location", frame=frame)
        # Root never moves: in-place clips, the character controller owns displacement.
        track = arm.animation_data.nla_tracks.new()
        track.name = name
        track.strips.new(name, 0, act)
        arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.rotation_euler = (0, 0, 0)
            pb.location = (0, 0, 0)
        made.append({"name": name, "frames": n, "seconds": round(n / cfg["fps"], 3), "loop": loop})
    return made


# ----------------------------------------------------------------------------- main

def _import(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"import_path not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)


def main(config=None):
    cfg = dict(CONFIG)
    cfg.update(config or {})
    log = []
    if cfg.get("clear_scene"):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    if cfg.get("import_path"):
        _import(os.path.abspath(os.path.expanduser(cfg["import_path"])))
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    mesh_obj = _pick_mesh(cfg.get("mesh_name"))
    if mesh_obj.parent:
        mw = mesh_obj.matrix_world.copy()
        mesh_obj.parent = None
        mesh_obj.matrix_world = mw
    old = bpy.data.objects.get(cfg["armature_name"])
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    # Meshes from build_lowpoly_creature.py carry their real joint positions; use them so the
    # bones bend where the mesh bends. Landmarks passed in CONFIG still win.
    baked = mesh_obj.get("quadruped_landmarks")
    if baked:
        cfg["landmarks"] = {**json.loads(baked), **(cfg.get("landmarks") or {})}
        log.append("using joint landmarks stored on the mesh")
        if cfg["head_direction"].upper() == "AUTO" and mesh_obj.get("quadruped_head_direction"):
            cfg["head_direction"] = str(mesh_obj["quadruped_head_direction"])

    lo, hi = _orient(mesh_obj, cfg, log)
    arm = _build_armature(cfg, lo, hi)
    method, unweighted = _skin(mesh_obj, arm, cfg, log)
    clips = _make_clips(arm, cfg, hi.z - lo.z, log)
    bpy.context.scene.frame_set(0)

    report = {
        "ok": unweighted == 0,
        "armature": arm.name, "mesh": mesh_obj.name,
        "bones": len(arm.data.bones), "deform_bones": sum(1 for b in arm.data.bones if b.use_deform),
        "skinning": method, "unweighted_verts": unweighted,
        "bounds_m": {"length": round(hi.y - lo.y, 3), "height": round(hi.z - lo.z, 3), "width": round(hi.x - lo.x, 3)},
        "clips": clips, "log": log,
    }

    if cfg.get("export_path"):
        path = os.path.abspath(os.path.expanduser(cfg["export_path"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for o in bpy.context.view_layer.objects:
            o.select_set(o in (arm, mesh_obj))
        bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True,
                                  export_animations=True, export_animation_mode='NLA_TRACKS',
                                  export_force_sampling=True, export_def_bones=False)
        report["export_path"] = path
    for line in log:
        print("[quadruped]", line)
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
