#!/usr/bin/env bash
# forge.py end-to-end: procedural karambit, fixture wolf (quadruped rig), and a humanoid through
# the Mixamo manual gate (simulated with FBX files), all landing in a fresh Godot project.
#   BLENDER=... GODOT=... ./pipeline3d/tests/test_forge.sh [out_dir]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P3D="$(dirname "$HERE")"
OUT="${1:-${TMPDIR:-/tmp}/p3d_forge}"
rm -rf "$OUT" && mkdir -p "$OUT/manifests"
"$BLENDER" -b --factory-startup -P "$HERE/make_fixtures.py" -- "out_dir=$OUT/fixtures" >/dev/null 2>&1
cp -r "$P3D/godot_template" "$OUT/game"

cat > "$OUT/manifests/karambit.json" <<JSON
{"name": "karambit", "generate": {"procedural": "build_karambit.py"}, "cleanup": false,
 "rig": {"method": "none"}, "export": {"collision": "convex", "godot_project": "../game"}}
JSON
cat > "$OUT/manifests/wolf.json" <<JSON
{"name": "wolf", "generate": {"file": "../fixtures/quadruped_raw.glb"},
 "cleanup": {"target_tris": 4000, "target_height_m": 0.85, "remove_floaters_below": 0.02},
 "rig": {"method": "quadruped", "clip_prefix": "wolf_"}, "animations": {"method": "procedural"},
 "export": {"godot_project": "../game"}}
JSON
cat > "$OUT/manifests/fighter.json" <<JSON
{"name": "fighter", "generate": {"file": "../fixtures/quadruped_raw.glb"},
 "cleanup": {"target_tris": 4000, "target_height_m": 1.0},
 "rig": {"method": "mixamo"},
 "animations": {"method": "clips_dir", "expect": ["idle", "walk"], "rename": {"standing_idle": "idle", "walking": "walk"}},
 "export": {"godot_project": "../game"}}
JSON

cat > "$OUT/manifests/horse.json" <<JSON
{"name": "horse", "generate": {"procedural": "build_lowpoly_creature.py",
   "config": {"preset": "deer", "target_tris": 1200, "height_m": 1.6, "muscle": 0.6},
   "fit_reference": {"keypoints": "$P3D/manifests/horse_keypoints.json"}},
 "cleanup": false, "rig": {"method": "quadruped", "clip_prefix": "horse_"}, "animations": {"method": "procedural"},
 "export": {"godot_project": "../game"}}
JSON
cat > "$OUT/manifests/wolf_fit.json" <<JSON
{"name": "wolf_fit", "concept": {"tool": "banana", "subject": "grey wolf", "out": "wolf_side.png", "auto_approve": true},
 "generate": {"procedural": "build_lowpoly_creature.py", "config": {"preset": "wolf", "height_m": 0.85},
   "fit_reference": {"animal": "grey wolf"}},
 "cleanup": false, "rig": {"method": "quadruped", "clip_prefix": "wolffit_"}, "animations": {"method": "procedural"},
 "export": {"godot_project": "../game"}}
JSON

run() { python3 "$P3D/forge.py" "$@" || echo "exit=$?"; }
echo "== horse (fitted to a keypoints file, no key)"; run "$OUT/manifests/horse.json"
echo "== wolf_fit without GEMINI_API_KEY (expect the concept gate, then the fit gate)"
env -u GEMINI_API_KEY -u GOOGLE_API_KEY python3 "$P3D/forge.py" "$OUT/manifests/wolf_fit.json" | grep -E "WAITING|GEMINI_API_KEY" | head -2 || true
# the user supplies a side view by hand (a blank 1500x1000 PNG stands in for it) ...
python3 - "$OUT/build/wolf_fit/refs/wolf_side.png" <<'PY'
import struct, sys, zlib
w, h = 1500, 1000
raw = b"".join(b"\x00" + b"\xff" * (w * 3) for _ in range(h))
chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                              + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
PY
env -u GEMINI_API_KEY -u GOOGLE_API_KEY python3 "$P3D/forge.py" "$OUT/manifests/wolf_fit.json" | grep -E "WAITING|GEMINI_API_KEY" | head -2 || true
# ... and marks the joints by hand (handoff/fit_keypoints.json), then forge resumes to the end
cp "$P3D/manifests/horse_keypoints.json" "$OUT/build/wolf_fit/handoff/fit_keypoints.json"
echo "== wolf_fit after the manual keypoints"; env -u GEMINI_API_KEY -u GOOGLE_API_KEY python3 "$P3D/forge.py" "$OUT/manifests/wolf_fit.json" || echo "exit=$?"

echo "== karambit";  run "$OUT/manifests/karambit.json"
echo "== wolf";      run "$OUT/manifests/wolf.json"
echo "== fighter (expect a Mixamo gate)"; run "$OUT/manifests/fighter.json" | tail -8

# Simulate the Mixamo round trip with FBX: rig the handoff mesh ourselves, export clips without skin
FB="$OUT/build/fighter"
"$BLENDER" -b --factory-startup --python-expr "
import bpy, runpy
rig = runpy.run_path('$P3D/blender/quadruped_rig.py')['main']
rig({'import_path': '$FB/handoff/fighter_for_rigging.fbx', 'clear_scene': True, 'clips': ['idle', 'walk']})
arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
tracks = {t.name: t.strips[0].action for t in arm.animation_data.nla_tracks}
for t in list(arm.animation_data.nla_tracks): arm.animation_data.nla_tracks.remove(t)
bpy.ops.export_scene.fbx(filepath='$FB/incoming/fighter_rigged.fbx', add_leaf_bones=False, bake_anim=False)
for name, act in [('Standing Idle', tracks['idle']), ('Walking', tracks['walk'])]:
    arm.animation_data.action = act
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = [int(f) for f in act.frame_range]
    for o in bpy.data.objects: o.select_set(o == arm)
    bpy.ops.export_scene.fbx(filepath='$FB/incoming/clips/%s.fbx' % name, use_selection=True, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False)
" >/dev/null 2>&1
echo "== fighter (after the simulated Mixamo downloads)"; run "$OUT/manifests/fighter.json"
python3 "$P3D/forge.py" "$OUT/manifests/fighter.json" --status
python3 - "$OUT" <<'PY'
import json, sys
for n in ["karambit", "wolf", "fighter", "horse", "wolf_fit"]:
    audit = json.load(open(f"{sys.argv[1]}/build/{n}/forge_state.json"))["godot"]["report"]["audit"]
    for a in audit:
        print(f"[forge-test] {n}: tris={a['tris']} bones={a['bones']} collision={a['static_bodies']} "
              f"clips={[(c['name'], c['seconds'], c['loop']) for c in a['clips']]}")
PY
