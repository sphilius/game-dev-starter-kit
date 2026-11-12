#!/usr/bin/env bash
# Runs every gate test. Set GODOT (and BLENDER for the 3D tests) first; see ../ENV.md.
#   bash run_tests.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PYTHON:-python}"
for t in test_art_cleanup.py test_runlog.py test_gate2d.py test_gate3d.py; do
  echo "== $t"
  "$PY" "$t" | grep -vE "frame\(s\), cell|feet at"      # hide art_cleanup's per-sheet chatter
done
echo "ALL GATE TESTS PASSED"
