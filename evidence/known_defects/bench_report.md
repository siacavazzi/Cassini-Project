# Image benchmark: 04aede6ca6df against 701fd40f5372

**NEEDS EYES**. 53 items: 45 identical, 8 changed (4 outside the target), 0 not built.

- target items with a measure worse (look at them): moon99-composite, hexagon-composite, titan127-movie

Built in 26 min (base) and 25 min (candidate). Targets: hexagon-composite, moon99-composite, storm-composite, titan127-movie.

| item | group | status | pictures changed | moved >8 levels (worst) | largest change (levels) | worse by measure | note |
|---|---|---|---|---|---|---|---|
| ringsFA-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| earthsmiled-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| ringmosaic04-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| shadow-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| photlit039-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| jupiter-atmos-mosaic | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-spol-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| satellorb-centre | hard | identical | 0/1 | 0.00% |  |  |  |
| daphnis09-movie | hard | identical | 0/70 | 0.00% |  |  |  |
| ringclose124-movie | hard | identical | 0/10 | 0.00% |  |  |  |
| gring-still | hard | identical | 0/1 | 0.00% |  |  |  |
| plume279-movie | hard | identical | 0/288 | 0.00% |  |  |  |
| plume-bloom-still | hard | identical | 0/1 | 0.00% |  |  |  |
| approach-movie | hard | identical | 0/96 | 0.00% |  |  |  |
| ringmovie04-movie | hard | identical | 0/44 | 0.00% |  |  |  |
| telesto-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| moon99-composite | target | changed | 1/1 | 1.59% | 69 | composite.webp: clipped 0.15% -> 0.36%; composite.webp: detail 0.2703 -> 0.3215 (+19%) |  |
| venus99-still | plain | identical | 0/1 | 0.00% |  |  |  |
| masursky-still | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| approach-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| phoebe-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| titan04-composite | plain | changed | 1/1 | 12.04% | 63 |  | HAL/GRN/BL1: HAL now stands in for RED (calibration.RED_STANDINS), so the set is true colour (natural matrix) instead of a false colour set balanced to Titan's tint: the high-phase crescent shows its blue outer haze and orange inside; needs Sam's eye |
| saturn05-movie | plain | identical | 0/27 | 0.00% |  |  |  |
| rhea-glocol-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| hyperion-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| rhea-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| titan-globmap-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| equinox-shadow-still | plain | identical | 0/1 | 0.00% |  |  |  |
| kiviuq-still | plain | identical | 0/1 | 0.00% |  |  |  |
| prometheus-still | plain | identical | 0/1 | 0.00% |  |  |  |
| pan07-still | plain | identical | 0/1 | 0.00% |  |  |  |
| iapetus-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| iapetus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| mimas-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| storm-composite | target | changed | 1/1 | 99.55% | 254 |  |  |
| methone-movie | plain | changed | 6/30 | 34.41% | 255 | evened011.webp: 75.81% of the base's light now black; evened011.webp: lit area's centre moved 32 px | frames 11-13 are polarized MT2 (P0/P60/P120) with no frame near to draw them through: drawn gray on main, now the colour picture before them (shown_of's held band rule); the evened copies and the black/centre measures move with that |
| hexagon-composite | target | changed | 1/1 | 99.99% | 249 | composite.webp: lit area's centre moved 11 px |  |
| dione-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| enceladus15-movie | plain | changed | 41/74 | 24.78% | 206 | evened011.webp: 6.69% of the base's light now black; evened011.webp: detail 0.2099 -> 0.2795 (+33%) | frame 11 is UV1 with nothing near: gray on main, now the colour picture before it (held band rule); evened frames rescale with it |
| telesto-movie | plain | identical | 0/36 | 0.00% |  |  | should be identical after the surface-window limit; listed only if a frame still differs |
| daphnis17-movie | plain | changed | 15/64 | 98.94% | 255 | evened024.webp: 1.91% of the base's light now black; evened024.webp: lit area's centre moved 14 px; evened025.webp: lit share 98.7% -> 83.0% | frame 24 is P60/UV3 with nothing near: gray on main, now the colour picture before it (held band rule); the two-view jumping stays (pointing thread) |
| pan17-movie | plain | identical | 0/38 | 0.00% |  |  |  |
| titan-cloud-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| earth-fb-still | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus15-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | identical | 0/62 | 0.00% |  |  |  |
| titan127-movie | target | changed | 31/108 | 31.04% | 163 | evened006.webp: clipped 0.00% -> 0.87%; evened021.webp: 0.20% of the base's light now black |  |
| june2004-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| saturn-limb-still | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-eye-composite | hard | identical | 0/1 | 0.00% |  |  |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

0 regressions, 4 fixed, 2 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| plume279-movie | odd_frame | known | 12.1826 | 12.1826 (limit 4.0) | worst 12.2 at frame250.webp (12 of 286 frames over 4.0) |
| moon99-composite | gray_colour | fixed | 1.0 | 0.0 (limit 0.0) | 0% of 1 pictures gray (median chroma 0.231) |
| storm-composite | gray_colour | fixed | 1.0 | 0.0 (limit 0.0) | 0% of 1 pictures gray (median chroma 0.088) |
| hexagon-composite | gray_colour | fixed | 1.0 | 0.0 (limit 0.0) | 0% of 1 pictures gray (median chroma 0.129) |
| daphnis17-movie | odd_frame | known | 118.2115 | 118.2115 (limit 4.0) | worst 118.2 at frame008.webp (2 of 9 frames over 4.0) |
| titan127-movie | odd_frame | fixed | 40.8719 | 0.9435 (limit 4.0) | worst 0.9 at frame017.webp (0 of 30 frames over 4.0) |
