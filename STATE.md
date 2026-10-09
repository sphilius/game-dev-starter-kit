# STATE — Switchback (updated S00)

Milestone: S00 specs written, awaiting owner approval. No game code exists.
Branch: bmx-downhill-demo (from main @ 31004c8)

## Works
- Spec set drafted: ARCHITECTURE, COURSE, PALETTE, QUALITY (BMX-CRITIC v1 verbatim), RISKS (+ session roadmap).
- three pin 0.186.1 confirmed on owner machine and agent sandbox.
- Numbers computed, not guessed: course sums (1690 m / 110.2 s / 126.8 m drop), jump minimum speeds, hairpin balance speed, palette contrast and derived ramps, plan-view layout (no self-crossing, 30 m closest approach).

## Broken / missing
- No package.json, no src/, no `npm run dev|check|shots` yet (all S01).
- Zero frames exist, so there are no rubric scores. No perf data (agent numbers would be NON-TARGET anyway).
- Agent sandbox has Chromium only (no Chrome, no GPU): `channel:'chrome'` fails here; shots will be software GL. See DEC-016.
- Every three.js API reference in ARCHITECTURE is UNVERIFIED until checked against node_modules/three in S01.
- All PROPOSED numbers (physics constants, flow economy, GPU pass budgets) are starting values, not measurements.

## Open items for owner
1. Approve or redirect the specs (ARCHITECTURE, COURSE, PALETTE, QUALITY, RISKS).
2. Confirm placeholder values: name "Switchback", DPR_MIN 1.25, draw-call cap 250 (all passes summed).
3. Confirm docs live at repo root beside the Go workshop README (else move to bmx/).
4. Confirm the sweeper turns right (a left sweeper self-crosses in plan view; heightfield cannot represent it).

## Next action
S01: Vite/TS/three@0.186.1 skeleton, 120 Hz loop, ToonMaterial, 5-pass toon pipeline on a test scene, `?perf=1`, `npm run check|shots`. Owner runs `?perf=1` once and returns the JSON. Exit gate in RISKS.md.
