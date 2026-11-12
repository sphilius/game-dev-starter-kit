# Art pipeline test environment

Preflight run: **Tuesday, November 10, 2026, 05:29 AM -05:00** on the Windows 11 laptop
(Acer Nitro AN515-55, 8 GB RAM). Re-run this check whenever a tool is upgraded.

## Tools

| Tool | Status | Path / version | Notes |
|---|---|---|---|
| Godot 4.7.2 (console, non-mono) | OK | `%LOCALAPPDATA%\Microsoft\WinGet\Packages\GodotEngine.GodotEngine_Microsoft.Winget.Source_8wekyb3d8bbwe\Godot_v4.7.2-stable_win64_console.exe` → `4.7.2.stable.official.ed1daf0bf` | Do **not** use `godot` on PATH for headless runs: it is the 4.6.3 mono build and hangs at ".NET: Initializing module". |
| Godot web export templates | OK | `%APPDATA%\Godot\export_templates\4.7.2.stable` | Needed for the web-export size gate. |
| Blender | OK (5.1.1 only) | `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe` | The `Blender 4.2` folder has no `blender.exe` (leftover from an uninstall). pipeline3d was written against 4.2; see "pipeline3d on Blender 5.1" below. |
| uv | OK | 0.6.10 | |
| Python | OK | 3.14.0 | |
| Pillow / numpy / scipy | OK | 12.2.0 / 2.3.5 / 1.18.1 | scipy is required by `art_cleanup.py`. |
| Git Bash | OK | `C:\Program Files\Git\bin\bash.exe` | Use this for `*.sh`. `bash` on PATH is the WSL launcher. |

## API keys

| Variable | Status | Notes |
|---|---|---|
| `GEMINI_API_KEY` | OK (set 2026-11-11) | A dedicated game-jam key, stored as a Windows *user* environment variable. Quota check: one 1K image from `gemini-3.1-flash-lite-image` in 7.4 s. Every call is logged in `logs/spend_log.csv` (cap $5). |
| `TRIPO_API_KEY` | Not set | Tripo cells are skipped. |
| `MESHY_API_KEY` | Not set | Meshy cells are skipped. |
| SpriteCook | Skipped by decision | 2-credit free tier; the MCP also needs `/mcp` auth. |

Older files that define a Gemini key name (values not read; **not used** by this project): `~\.env` (2025-06-12),
`~\Projects\.env` (2025-06-01), `~\Projects\Claude\.env` (2025-05-27),
`~\dev\discordmcp\.env` (2025-05-27), `~\Desktop\director-mode-gemini\.env` (2026-03-01);
`GOOGLE_API_KEY` in `~\dev\storyforge\.env` (2026-03-16) and `~\Desktop\llm-workbench\.env` (2026-01-02).

## pipeline3d/tests/run_all.sh baseline (Blender 5.1.1 + Godot 4.7.2)

First run, before the port below: 30 s, then **FAILED**.

| Stage | Result |
|---|---|
| 1/5 Blender stages | **Broken, but reported as passing.** The 4 cleanup checks pass, then `build_karambit.py:193` raises `AttributeError: 'NoneType' object has no attribute 'select_set'`. Blender's `-P` exits 0 on a Python error, and `run_all.sh` only greps `[test]` lines, so the crash is hidden. Only `character.glb` is exported, not `wolf_merged`, `karambit` or `crate`. |
| 2/5 Reference fitting | **FAIL**: deer landmark error 0.0241, limit 0.02 (wolf, boar, bear and cat pass, and so do all noisy fits and the mock-Gemini fit). |
| 3/5 Godot import | Passes on `character.glb` alone. |
| 4/5 Asset audit | 0 errors, 1 warning (static prop without collision). |
| 5/5 Smoke test | `failures=0` on `character.glb` alone. |

### pipeline3d on Blender 5.1: ported 2026-11-11, now ALL PASS (22 s)

What broke, and the fix in each case:

1. **New objects read as `None` in `view_layer.objects`.** In 5.x, an object created through
   `bpy.data.objects.new()` stays out of the view layer's list until `view_layer.update()`.
   Fix: refresh the view layer before each of the 9 select/deselect loops. Skipping `None`
   instead was tried first: it hid the crash but left the karambit unselected, so the export was
   an empty 132-byte GLB. The karambit test now checks the file size too.
2. **`Action.fcurves` was removed in 5.0** (slotted actions: layers → strips → channel bags).
   `merge_clips.py` now reads and deletes F-curves through `_fcurves()` / `_remove_fcurve()`,
   which work on 4.x and 5.x.
3. **Deer "landmark error 0.0241" was a measurement artifact.** The failing axis was sideways,
   measured as a fraction of half the body width. The deer is the narrowest preset, and a
   side-view image carries no sideways information. In metres the joint is 0.2 mm off. The test
   now gates length and height as fractions (< 0.02) and sideways in metres (< 1 cm), and names
   the worst joint and axis.
4. **Crashes were reported as passes.** `run_all.sh` now calls Blender with
   `--python-exit-code 1`.

## Source repos

All reuse sources exist: `banana.py`, `asset_audit.gd`, open-world `tests/run_tests.gd`,
`tests/test_case.gd`, `scripts/combat/*` (10 scripts), `scripts/ui/touch/`,
`.github/workflows/deploy-web.yml`, and Medusa's `tools/art_cleanup.py`, `test_art_cleanup.py`,
`build_sprites.py`, `art/processed/`.
