# Image benchmark: 7efaef0b954d against 3f85fc7394f7

**NEEDS EYES**. 75 items: 54 identical, 21 changed (20 outside the target), 0 not built.


Built in 42 min (base) and 46 min (candidate). Targets: dione139-mosaic.

| item | group | status | pictures changed | moved >8 levels (worst) | largest change (levels) | worse by measure | note |
|---|---|---|---|---|---|---|---|
| ringsFA-mosaic | hard | changed | 2/2 | 5.56% | 61 |  | rings about 6% brighter and a little creamier from the solved gains. The saturated block on the left stays white (clipped_white: 255/255/254 against the old 255; it went 255/255/247 cream before this fix). The pink ring patches move and change shape but are not new; the pink tile rectangles below the rings are in both (Fable 11-21: mixed, none worse) |
| earthsmiled-mosaic | hard | changed | 2/2 | 10.23% | 111 |  | main rings go from purple/blue-grey to a more neutral cream-tan, and the green cast in the faint outer ring is reduced; faint ring detail kept (Fable 11-21: better) |
| ringmosaic04-mosaic | hard | changed | 2/2 | 0.39% | 24 |  | rings very slightly brighter and clearer; the green smear by the planet and the blown planet are unchanged; no new clipping (Fable 11-21: same to slightly better) |
| shadow-mosaic | hard | changed | 2/2 | 0.45% | 90 |  | very small ring and halo level changes from the solved gains; faint halo detail kept (Fable 11-21: same) |
| photlit039-mosaic | hard | changed | 2/2 | 0.01% | 29 |  | rings a touch more even and a faint yellow-pink blotch on the globe weaker (Fable 11-21: slightly better) |
| jupiter-atmos-mosaic | hard | changed | 1/1 | 0.00% | 10 |  | sub-visible changes only (largest 10 levels) (Fable 11-21: same) |
| enceladus-spol-mosaic | hard | changed | 2/2 | 0.39% | 17 |  | the saturated crescent stays flat and gray (about 236 to 228; the bench's clipped_white check wants it gray, not white) and the night side is very slightly brighter; no clipping added (Fable 11-21: mixed, near same) |
| satellorb-centre | hard | identical | 0/1 | 0.00% |  |  |  |
| daphnis09-movie | hard | identical | 0/70 | 0.00% |  |  |  |
| ringclose124-movie | hard | identical | 0/10 | 0.00% |  |  |  |
| gring-still | hard | identical | 0/1 | 0.00% |  |  |  |
| plume279-movie | hard | identical | 0/288 | 0.00% |  |  |  |
| plume-bloom-still | hard | identical | 0/1 | 0.00% |  |  |  |
| approach-movie | hard | identical | 0/96 | 0.00% |  |  |  |
| ringmovie04-movie | hard | identical | 0/44 | 0.00% |  |  |  |
| telesto-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| moon99-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| venus99-still | plain | identical | 0/1 | 0.00% |  |  |  |
| masursky-still | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| approach-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| phoebe-mosaic | plain | changed | 2/2 | 0.00% | 10 |  | noise-level changes only (Fable 11-21: same) |
| titan04-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| saturn05-movie | plain | identical | 0/27 | 0.00% |  |  |  |
| rhea-glocol-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| hyperion-mosaic | plain | changed | 2/2 | 0.01% | 13 |  | noise-level changes only (Fable 11-21: same) |
| rhea-mosaic | plain | changed | 2/2 | 0.20% | 169 |  | a small change at the top limb and faint tile-edge lines in the difference, not visible as seams; the largest change is a few pixels at that limb (Fable 11-21: same) |
| titan-globmap-mosaic | plain | changed | 2/2 | 0.31% | 46 |  | low-level changes from the solved gains, nothing visible; tile edges unchanged (Fable 11-21: same) |
| equinox-shadow-still | plain | identical | 0/1 | 0.00% |  |  |  |
| kiviuq-still | plain | identical | 0/1 | 0.00% |  |  |  |
| prometheus-still | plain | identical | 0/1 | 0.00% |  |  |  |
| pan07-still | plain | identical | 0/1 | 0.00% |  |  |  |
| iapetus-mosaic | plain | changed | 2/2 | 0.08% | 75 |  | noise-level changes plus a faint change along a tile outline in the sky (Fable 11-21: same) |
| iapetus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| mimas-mosaic | plain | changed | 2/2 | 0.07% | 133 |  | faint halo arcs left of the disc shift slightly, present in both; the disc is unchanged (Fable 11-21: same) |
| storm-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| methone-movie | plain | identical | 0/30 | 0.00% |  |  |  |
| hexagon-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| dione-mosaic | plain | changed | 2/2 | 0.29% | 154 |  | a couple of tiny specks near the limb change; no seam, tint or clipping change (Fable 11-21: same) |
| enceladus15-movie | plain | identical | 0/74 | 0.00% |  |  |  |
| telesto-movie | plain | identical | 0/36 | 0.00% |  |  |  |
| daphnis17-movie | plain | identical | 0/64 | 0.00% |  |  |  |
| pan17-movie | plain | identical | 0/38 | 0.00% |  |  |  |
| titan-cloud-mosaic | plain | changed | 2/2 | 7.26% | 255 | mosaic.webp: clipped 1.37% -> 1.59% | the upper-left tiles now blend more evenly with their neighbours (the solved gains); the clipped share rises 1.37% to 1.59% from one small spot at the left notch, where a tiny dark hole is slightly more defined; cloud detail kept (Fable 11-21: slightly better) |
| earth-fb-still | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus15-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | changed | 4/62 | 29.85% | 192 | mosaic_at029.webp: lit area's centre moved 8 px | one of 62 pictures (at029) changes in its lower-left strip, at noise level; the lit centre moves 8 px because that strip's faint levels changed, not the rings (Fable 11-21: same) |
| titan127-movie | hard | identical | 0/108 | 0.00% |  |  |  |
| june2004-mosaic | hard | changed | 2/2 | 0.00% | 44 |  | tiny differences only (largest 44 levels on a few pixels); its existing step and seam are unchanged (Fable 11-21: same) |
| saturn-limb-still | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-eye-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| impact293-movie | hard | identical | 0/24 | 0.00% |  |  |  |
| mimas167-mosaic | hard | changed | 2/2 | 0.03% | 64 | mosaic.webp: clipped 1.82% -> 2.16% | a tiny change on the lit disc and very faint contour streaks in the dark lower right; the clipped share rises 1.82% to 2.16% at the black end (dark sky), not at white (Fable 11-21: same) |
| titanwac17-haze | hard | identical | 0/1 | 0.00% |  |  |  |
| saturn07-deck | hard | identical | 0/1 | 0.00% |  |  |  |
| saturn07-deck2 | hard | identical | 0/1 | 0.00% |  |  |  |
| titan08-mt1 | hard | identical | 0/1 | 0.00% |  |  |  |
| rings08-bright | hard | identical | 0/1 | 0.00% |  |  |  |
| mimas04-movie | hard | identical | 0/46 | 0.00% |  |  |  |
| saturn07-fullblack-movie | hard | identical | 0/144 | 0.00% |  |  |  |
| saturn08w-fullblack-movie | hard | identical | 0/16 | 0.00% |  |  |  |
| saturn13-fullblack-movie | hard | identical | 0/61 | 0.00% |  |  |  |
| saturn08-fullblack-movie | hard | identical | 0/84 | 0.00% |  |  |  |
| pan09-banding-movie | hard | identical | 0/16 | 0.00% |  |  |  |
| dione139-mosaic | target | changed | 2/2 | 20.89% | 93 |  | the target: the mid-disc brightness step between the tile rows is clearly softer (a faint trace remains) and the lower step and the darker patch near the right notch are gone; tiles of a balanced mosaic are now solved together with the log gains (held_level), not grown one at a time (Fable 11-21: better, high confidence) |
| titan059-mosaic | hard | changed | 2/2 | 0.48% | 61 |  | thin changes along tile edges only; the tile tints are a different cause, not this PR's (Fable 11-21: same) |
| fring274-movie | hard | identical | 0/172 | 0.00% |  |  |  |
| npole0908-mosaicmovie | hard | changed | 1/1 | 0.00% | 9 |  | noise-level only (Fable 11-21: same) |
| encset293-movie | hard | identical | 0/48 | 0.00% |  |  |  |
| daphnis257n1-movie | hard | identical | 0/34 | 0.00% |  |  |  |
| fring039-movie | hard | identical | 0/144 | 0.00% |  |  |  |
| fring183-movie | hard | identical | 0/61 | 0.00% |  |  |  |
| titancloud264-movie | hard | identical | 0/104 | 0.00% |  |  |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

0 regressions, 0 fixed, 12 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| plume279-movie | odd_frame | known | 12.1826 | 12.1826 (limit 4.0) | worst 12.2 at frame250.webp (12 of 286 frames over 4.0) |
| ringmovie04-movie | pointing_jitter | known | 15.2414 | 15.2414 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 15.2 px, largest 19.1 px (36 pairs) |
| saturn05-movie | channel_registration | known | 10.572 | 10.572 (limit 4.0) | colour along edges past the picture's own: p90 10.57 levels, largest 11.10 (27 colour frames) |
| daphnis17-movie | odd_frame | known | 118.1757 | 118.1757 (limit 4.0) | worst 118.2 at frame008.webp (2 of 9 frames over 4.0) |
| impact293-movie | odd_frame | known | 18.4491 | 18.4491 (limit 4.0) | worst 18.4 at frame007.webp (1 of 2 frames over 4.0) |
| mimas04-movie | channel_registration | known | 54.34 | 54.34 (limit 4.0) | colour along edges past the picture's own: p90 54.34 levels, largest 54.34 (23 colour frames) |
| mimas04-movie | full_black | known | 25.19 | 25.19 (limit 20.0) | black sky lost at Full: up to 25 points (98% of frame000.webp black at Processed, 73% at Full; 7 of 16 frames over 20) |
| saturn07-fullblack-movie | full_black | known | 24.14 | 24.14 (limit 20.0) | black sky lost at Full: up to 24 points (77% of frame029.webp black at Processed, 53% at Full; 12 of 16 frames over 20) |
| pan09-banding-movie | full_banding | known | 7.141 | 7.141 (limit 1.0) | Full sky banding up to 7.14 levels where Processed has black sky (5 of 5 frames over 1.0) |
| fring274-movie | full_black | known | 22.09 | 22.09 (limit 20.0) | black sky lost at Full: up to 22 points (58% of frame000.webp black at Processed, 36% at Full; 4 of 16 frames over 20) |
| fring274-movie | pointing_jitter | known | 5.8858 | 5.8858 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 5.9 px, largest 137.6 px (152 pairs) |
| fring039-movie | full_black | known | 24.14 | 24.14 (limit 20.0) | black sky lost at Full: up to 24 points (77% of frame029.webp black at Processed, 53% at Full; 12 of 16 frames over 20) |
