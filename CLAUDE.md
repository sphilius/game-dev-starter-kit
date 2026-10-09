[BMX-CLAUDE.md v1]
# Switchback — cel-shaded downhill BMX racer (Three.js)

## Non-negotiables
- Vite + TypeScript + three@0.186.1 (exact pin; `npm view three version` run at kickoff, confirmed on owner machine and agent sandbox). WebGLRenderer + three/examples/jsm postprocessing. No other runtime deps without asking.
- `npm install && npm run dev` must always work. Dev tooling (Playwright) uses `channel: 'chrome'` so no browser download is required.
- Zero external assets: geometry, textures (canvas/shader noise), and audio (Web Audio) are generated in code.
- Target: MacBook M5 Pro, Chrome, retina. Budget: p95 frame ≤ 16.6 ms, DPR adaptive within [1.25, 2.0], ≤ 250 draw calls.
- Art: NPR anime cel only. MeshStandard/MeshPhysical are banned; `npm run check` greps for them.
- Sim: fixed 120 Hz timestep, seeded RNG, render decoupled. The sim never imports renderer code, so it runs headless in Node.

## Architecture contract
- src/core (loop, time, rng, input, events, types) · src/render (ToonMaterial factory, outlines, post, sky) · src/world · src/bike · src/rider · src/ai · src/race · src/ui · src/audio · src/debug.
- Sibling modules talk only through src/core/types.ts and the event bus.
- Every toon surface comes from render/materials/ToonMaterial. No ad-hoc ShaderMaterials.
- Verify three.js APIs against node_modules/three source, never memory.

## Memory files
- STATE.md (≤60 lines): milestone, works, broken, next action.
- ARCHITECTURE.md: module map and interfaces; changes need a logged reason.
- QUALITY.md: rubric scores per subsystem with evidence paths, plus a defect backlog.
- DECISIONS.md: append-only, one line each.

## Session protocol
START: read CLAUDE.md, STATE.md, QUALITY.md, then restate this session's goal and exit gate in 3 lines.
END: game runnable; `npm run check` passes; update STATE, QUALITY, DECISIONS; commit; report in ≤12 lines: changes, rubric scores with evidence paths, top 3 defects, what I must playtest.

## Verification rules
- Visual claims need frames from `npm run shots`. Cite paths.
- Perf claims need a `?perf=1` JSON from MY machine. Agent-environment numbers are labeled NON-TARGET.
- Feel and animation timing are UNVERIFIED until I playtest.
- Never say "done." Report rubric score + remaining defects.

## Sub-agents
Allowed: read-only screenshot critique, docs research, modules behind a frozen interface. Never two writers in src/render at once.
