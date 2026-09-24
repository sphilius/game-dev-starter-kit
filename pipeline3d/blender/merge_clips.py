"""
merge_clips.py - combine a rigged character with separately downloaded animation files.

Typical sources (all share one skeleton per source):
  * Mixamo: download the character once "With Skin" (T-pose), then each animation
    "Without Skin", FBX Binary, 30 fps, "In Place" ticked for locomotion.
  * ActorCore / AccuRIG, Meshy animation API, Tripo retarget, Rokoko / DeepMotion video
    mocap exports - as long as the bone names match the character's armature.

Each clip file's action is renamed to its clip name, moved onto the character's armature
as its own NLA track, and the clip's extra armature/meshes are deleted. Export with
export_for_godot.py (or set export_path here) to get one GLB with N named animations.

Clip names come from the file names: "Idle.fbx" -> "idle", "Sword And Shield Slash.fbx"
-> "sword_and_shield_slash". Provide "rename" to map them to game names.
"""

import bpy
import json
import os
import re
import sys

CONFIG = {
    "character_path": "~/game/incoming/character_rigged.fbx",   # None = use the armature already in the scene
    "clips_dir": "~/game/incoming/clips",                        # every .fbx/.glb in here is a clip
    "clear_scene": True,
    "rename": {},                    # {"standing_idle": "idle", ...}
    "keep_existing_clips": False,    # keep animations that came inside character_path
    "loop_clips": ["idle", "walk", "run"],   # recorded in the report; Godot import sets loop by name
    "strip_root_motion": [],         # clip names whose hips horizontal motion should be removed
    "hips_bone": "mixamorig:Hips",
    "fps": 30,
    "export_path": None,
}


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _import(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False, ignore_leaf_bones=False)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise ValueError(f"unsupported clip format {ext}")
    return [o for o in bpy.data.objects if o not in before]


def _strip_root_motion(action, hips):
    """Zero the hips' horizontal translation. Mixamo hips: bone-local Y is up, X/Z horizontal."""
    removed = 0
    for fc in action.fcurves:
        if fc.data_path == f'pose.bones["{hips}"].location' and fc.array_index in (0, 2):
            first = fc.keyframe_points[0].co.y if fc.keyframe_points else 0.0
            for kp in fc.keyframe_points:
                kp.co.y = first
                kp.handle_left.y = first
                kp.handle_right.y = first
            removed += 1
    return removed


def main(config=None):
    c = dict(CONFIG)
    c.update(config or {})
    if c.get("clear_scene"):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for a in list(bpy.data.actions):
            bpy.data.actions.remove(a)
    bpy.context.scene.render.fps = int(c["fps"])

    if c.get("character_path"):
        imported = _import(os.path.abspath(os.path.expanduser(c["character_path"])))
        arm = next((o for o in imported if o.type == 'ARMATURE'), None)
    else:
        arm = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
    if arm is None:
        return {"ok": False, "error": "no armature found for the character"}
    arm.animation_data_create()
    # The character file may carry its own clips (Mixamo "with skin" idle, glTF NLA tracks).
    if not c.get("keep_existing_clips"):
        arm.animation_data.action = None
        for t in list(arm.animation_data.nla_tracks):
            arm.animation_data.nla_tracks.remove(t)

    clips_dir = os.path.abspath(os.path.expanduser(c["clips_dir"]))
    files = sorted(f for f in os.listdir(clips_dir) if f.lower().endswith((".fbx", ".glb", ".gltf")))
    bone_names = {b.name for b in arm.data.bones}
    clips, warnings = [], []
    for fname in files:
        new_objs = _import(os.path.join(clips_dir, fname))
        src_arm = next((o for o in new_objs if o.type == 'ARMATURE'), None)
        act = src_arm.animation_data.action if src_arm and src_arm.animation_data else None
        if act is None:
            warnings.append(f"{fname}: no action found")
        else:
            name = c["rename"].get(_slug(os.path.splitext(fname)[0]), _slug(os.path.splitext(fname)[0]))
            act.name = name
            act.use_fake_user = True
            missing = {m for m in re.findall(r'pose\.bones\["([^"]+)"\]', " ".join(fc.data_path for fc in act.fcurves))
                       if m not in bone_names}
            if missing:
                warnings.append(f"{fname}: {len(missing)} bones not on the character (e.g. {sorted(missing)[:3]})")
            stripped = _strip_root_motion(act, c["hips_bone"]) if name in c["strip_root_motion"] else 0
            track = arm.animation_data.nla_tracks.new()
            track.name = name
            # Importers start clips at frame 1 (glTF) or 0/1 (FBX); strips always start at 0
            # so every exported clip begins at t=0 and lasts exactly its length.
            track.strips.new(name, 0, act)
            clips.append({"name": name, "file": fname, "frames": [round(x, 2) for x in act.frame_range],
                          "loop": name in c["loop_clips"], "root_motion_stripped": bool(stripped)})
        for o in new_objs:
            bpy.data.objects.remove(o, do_unlink=True)

    report = {"ok": bool(clips), "armature": arm.name, "clips": clips, "warnings": warnings}
    if c.get("export_path"):
        path = os.path.abspath(os.path.expanduser(c["export_path"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        keep = [arm] + [o for o in bpy.context.scene.objects if o.parent == arm or o.find_armature() == arm]
        for o in bpy.context.scene.objects:
            o.select_set(o in keep)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True,
                                  export_animations=True, export_animation_mode='NLA_TRACKS')
        report["export_path"] = path
    print("[clips]", json.dumps(report, indent=1))
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
