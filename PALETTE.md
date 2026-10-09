# PALETTE — nine anchors, everything else derived

| # | Name | Hex | Role |
|---|---|---|---|
| 1 | INK | `#1D1B34` | outlines, hull colour, UI panels, deepest shade (never pure black) |
| 2 | PAPER | `#FFF4DF` | highlights, snow, clouds, helmets, UI text (never pure white) |
| 3 | SKY | `#4FA8F0` | sky bands, water, distant air |
| 4 | DIRT | `#D9A066` | the track surface, dust |
| 5 | MEADOW | `#8CC46E` | mid terrain, valley floor |
| 6 | PINE | `#2B6F5C` | foliage, low terrain, deep shade |
| 7 | VIOLET | `#6A4FCB` | shadow tint, rock source, Rival B |
| 8 | CORAL | `#F23B5C` | player, HUD hot accent |
| 9 | SUN | `#FFD03A` | sun disc, Rival A, HUD full-flow accent |

## Why these nine (3 lines)

Cool world (SKY, VIOLET, PINE, INK) against warm ground and riders (DIRT, PAPER, SUN, CORAL), so track and rider separate by hue even where luminance is close.
Only nine anchors; every other tone is a formula (shade pulled toward VIOLET then INK, light pulled toward PAPER), so three hard bands per surface come free and nothing drifts off-palette.
INK is an indigo, not black, so linework reads as anime ink on every band and doubles as UI panel colour; CORAL and SUN double as hero and HUD accents so the player and the interface read as one system.

## Derived tones (generated, never hand-picked)

Formulas: `shade = mix(mix(base, VIOLET, 0.15), INK, 0.35)`; `light = mix(base, PAPER, 0.30)`, except SUN `0.55`; `ROCK = mix(VIOLET, PAPER, 0.42)`; `haze = mix(SKY, PAPER, 0.65)`.

| Name | Shade | Base | Light | Step ratio shade→base / base→light |
|---|---|---|---|---|
| SKY | `#406EAA` | `#4FA8F0` | `#84BFEB` | 2.03 / 1.30 |
| DIRT | `#8C6A5E` | `#D9A066` | `#E4B98A` | 2.11 / 1.27 |
| MEADOW | `#627D63` | `#8CC46E` | `#AFD290` | 2.21 / 1.22 |
| PINE | `#2C4E59` | `#2B6F5C` | `#6B9783` | 1.51 / 1.81 |
| VIOLET | `#4F3D96` | `#6A4FCB` | `#9781D1` | 1.47 / 1.77 |
| CORAL | `#9A3259` | `#F23B5C` | `#F67283` | 1.87 / 1.38 |
| SUN | `#A28446` | `#FFD03A` | `#FFE495` | 2.42 / 1.17 |
| ROCK (derived) | `#72639B` | `#A994D3` | `#C3B1D7` | 1.98 / 1.35 |
| haze | — | `#C1D9E5` | — | — |

Rule: every band step must be >= 1.15 contrast ratio so the three bands stay hard. The S01 palette test asserts this (SUN's light mix was raised from 0.30 to 0.55 because 0.30 gave 1.09).

## Usage

- **Sky:** four hard bands, top to bottom: SKY shade, SKY, SKY light, haze. Sun disc SUN. Clouds PAPER with VIOLET-shade undersides. No smooth gradient.
- **Terrain by altitude:** start ridge ROCK + PAPER snow + DIRT track; slopes MEADOW; forest PINE (shade band) set back from the line; ravine ROCK with VIOLET shade; valley MEADOW + DIRT. Distance fog lifts toward haze in <= 4 steps.
- **Ink:** INK for all hulls and Sobel lines. Constant screen width.
- **Riders (jersey / helmet / frame; tyres and gloves INK, rims PAPER):**
  - Player: CORAL / PAPER / SUN
  - Rival A: SUN / CORAL / VIOLET
  - Rival B: VIOLET / SUN / PAPER
  - Rival C: PAPER / VIOLET / CORAL
- **UI:** INK panels (85%), PAPER text, CORAL player marker and hot meter, SUN at full flow, rival markers in their jersey colour.
- **Never:** pure black, pure white, a tenth hue, gradients other than quantised sky/fog bands.

## Contrast reality (WCAG luminance ratio, fill only)

| Rider fill vs | DIRT | MEADOW | PINE | SKY | ROCK |
|---|---|---|---|---|---|
| CORAL | 1.65 | 1.84 | 1.57 | 1.47 | 1.42 |
| SUN | 1.56 | 1.40 | 4.06 | 1.75 | 1.82 |
| VIOLET | 2.55 | 2.85 | **1.02** | 2.28 | 2.19 |
| PAPER | 2.10 | 1.88 | 5.45 | 2.35 | 2.45 |

INK outline against backgrounds: DIRT 7.3, MEADOW 8.1, SKY 6.5, ROCK 6.2, PINE **2.8**. UI: PAPER on INK 15.3, SUN on INK 11.4, CORAL on INK 4.4, VIOLET on INK 2.9 (never used for small text).

Reading: fill contrast is low by design in a mid-value anime palette. Silhouette read is carried by the hull ink and by hue. The weak spots are VIOLET on PINE and ink on PINE, handled by the backdrop rule in COURSE.md and checked in the berm-apex and pack-close shots.
