#!/usr/bin/env bash
# Pre-flight for pipeline3d. Required: Blender 4.2+, Godot 4.3+, Python 3.10+.
# Optional: uv, Node.js (Godot MCP), API keys.
set -u
ok=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1 -> $2"; ok=1; }
warn() { echo "  [WARN] $1 -> $2"; }

BLENDER="${BLENDER:-$(command -v blender || true)}"
GODOT="${GODOT:-$(command -v godot || command -v godot4 || true)}"

if [ -n "$BLENDER" ] && V=$("$BLENDER" -b --factory-startup --python-expr "import bpy;print('BV',bpy.app.version_string)" 2>/dev/null | grep '^BV' | cut -d' ' -f2); then
  case "$V" in 4.[2-9]*|4.1[0-9]*|[5-9].*) pass "Blender $V ($BLENDER)";; *) fail "Blender $V" "install Blender 4.2 LTS or newer";; esac
else fail "Blender not found" "install it, then export BLENDER=/path/to/blender"; fi

if [ -n "$GODOT" ] && V=$("$GODOT" --headless --version 2>/dev/null | head -1); then
  case "$V" in 4.[3-9]*|4.1[0-9]*) pass "Godot $V ($GODOT)";; *) fail "Godot $V" "install Godot 4.3+ (standard build)";; esac
else fail "Godot not found" "install it, then export GODOT=/path/to/godot"; fi

if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
  pass "$(python3 --version)"; else fail "Python 3.10+ missing" "install Python 3.10+"; fi
command -v uv >/dev/null && pass "uv $(uv --version | cut -d' ' -f2)" || warn "uv missing" "needed for Blender MCP (uvx) and banana.py"
command -v node >/dev/null && pass "Node $(node --version) (Godot MCP)" || warn "Node.js missing" "only needed for Godot MCP"
for k in TRIPO_API_KEY MESHY_API_KEY RODIN_API_KEY; do
  [ -n "${!k:-}" ] && pass "$k set" || warn "$k not set" "only needed for that provider"
done
exit $ok
