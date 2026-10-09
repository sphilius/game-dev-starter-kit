# DECISIONS (append-only, one line each: ID | session | decision | reason)

DEC-001 | S00 | Branch is `bmx-downhill-demo`, not `/bmx-downhill-demo` | a git ref cannot start with "/".
DEC-002 | S00 | Project root is the repo root; docs live there; Go/Godot workshop content untouched | CLAUDE.md memory-file contract assumes project root.
DEC-003 | S00 | three pinned to exactly 0.186.1 | `npm view three version` = 0.186.1 on owner machine and agent sandbox.
DEC-004 | S00 | GAME_NAME=Switchback (working title), DPR_MIN=1.25, DRAW_CALL_BUDGET=250 summed over all passes per frame | proposals to fill CLAUDE.md placeholders; owner may change.
DEC-005 | S00 | Add core/math.ts (plain-object vec/quat, no three) to the core list | sim must run in Node without importing renderer code.
DEC-006 | S00 | Modules split into sim/ and view/ folders; ai, race, core are sim-only; render, ui, audio, rider are view-only | makes the headless boundary greppable in `npm run check`.
DEC-007 | S00 | Only compose.ts, main.ts, headless.ts may import across sibling modules | siblings otherwise talk via core/types.ts interfaces and the event bus.
DEC-008 | S00 | Ink single-owner rule: hulls own CHARACTER/HERO silhouettes, Sobel owns everything else and is masked where hull ink exists | BMX-CRITIC "no doubled lines".
DEC-009 | S00 | Terrain Sobel uses depth+ID and normal creases ≥60° only | BMX-CRITIC "no noise lines on terrain".
DEC-010 | S00 | Dust/roost/ribbons are opaque inked cel shapes; no dither or alpha-noise fades | BMX-CRITIC "effects stay graphic".
DEC-011 | S00 | No shadow-map pass; contact-shadow decals only | requested pass order has no shadow pass; cel look.
DEC-012 | S00 | HUD is a DOM overlay after composite (the UI pass) | zero GPU cost, unaffected by Sobel/grade.
DEC-013 | S00 | Palette = 9 anchor hexes; all other tones derived by formula; ROCK = mix(VIOLET,PAPER,0.42) | 7–9 colour commitment; hard bands come free.
DEC-014 | S00 | Pumping Plan A = rider-on-rail point mass; Plan B = authored per-roller impulse; chosen at S02 gate | pump gain must be testable headless either way.
DEC-015 | S00 | Course: 9 sections, 1690 m timed + 60 m runout, par 110 s, 150 s hard cap; sweeper turns right | fits 90–150 s; left sweeper self-crosses (heightfield cannot overlap).
DEC-016 | S00 | Playwright config tries channel:'chrome', falls back to executablePath from SHOTS_CHROMIUM | agent sandbox has Chromium only; owner machine has Chrome.
DEC-017 | S00 | RISKS.md added as an 8th file (not in the CLAUDE.md memory list) | holds the risk list and session roadmap; fold into ARCHITECTURE if owner prefers four.
DEC-018 | S00 | BMX-CRITIC v1 copied verbatim into QUALITY.md; anchors added beneath it, never inside it | critic text is the owner's; anchors calibrate scores.
