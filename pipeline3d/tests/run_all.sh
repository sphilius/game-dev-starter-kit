#!/usr/bin/env bash
# End-to-end pipeline test: Blender stages -> reference fitting -> Godot import -> audit -> controller smoke test.
# No API keys or credits needed (uses procedural fixtures).
#
#   BLENDER=/path/to/blender GODOT=/path/to/godot ./pipeline3d/tests/run_all.sh [out_dir]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P3D="$(dirname "$HERE")"
OUT="${1:-${TMPDIR:-/tmp}/p3d_test}"
BLENDER="${BLENDER:-blender}"
GODOT="${GODOT:-godot}"

echo "== 1/5 Blender stages -> $OUT"
rm -rf "$OUT"
"$BLENDER" -b --factory-startup -P "$HERE/test_blender_stages.py" -- "out_dir=$OUT" 2>&1 | grep -E "^\[test\]"

echo "== 2/5 Reference fitting (keypoints -> creature, mock Gemini)"
"$BLENDER" -b --factory-startup -P "$HERE/test_fit_reference.py" -- "$OUT/fit" > "$OUT/fit.log" 2>&1 || true
grep -E "^\[test\]" "$OUT/fit.log"
grep -q "FIT TESTS PASSED" "$OUT/fit.log" || { echo "reference fitting failed: $OUT/fit.log"; exit 1; }

echo "== 3/5 Godot headless import"
PROJ="$OUT/godot_project"
cp -r "$P3D/godot_template" "$PROJ"
cp "$OUT"/export/{wolf_merged,karambit,crate,character}.glb "$PROJ/assets/"
# texture_2d_get errors from the headless dummy renderer (thumbnails) are harmless.
"$GODOT" --headless --path "$PROJ" --import 2>&1 | grep -E "^\[pipeline_import\]|SCRIPT ERROR" || true

echo "== 4/5 Asset audit"
"$GODOT" --headless --path "$PROJ" -s res://tools/asset_audit.gd -- res://assets "--out=$OUT/audit.json" >/dev/null 2>&1 \
  && echo "audit: no errors ($OUT/audit.json)" || { echo "audit reported errors: $OUT/audit.json"; exit 1; }

echo "== 5/5 Character controller smoke test"
"$GODOT" --headless --path "$PROJ" -s res://tools/smoke_test.gd 2>&1 | grep -E "^\[smoke\]"
echo "ALL PIPELINE TESTS PASSED"
