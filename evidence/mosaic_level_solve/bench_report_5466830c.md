# Image benchmark: b80611643989 against 5466830c990c

**NEEDS EYES**. 80 items: 58 identical, 22 changed (21 outside the target), 0 not built.


Built in 52 min (base) and 47 min (candidate). Targets: dione139-mosaic.

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
| titan-cloud-mosaic | plain | changed | 2/2 | 7.26% | 255 | mosaic.webp: clipped 1.37% -> 1.59% | the upper-left tiles blend more evenly with their neighbours (the solved gains). One local loss: at the notch on the left edge about 95 px of the screen picture (a 13 x 9 px patch at x 157-165, y 447-459) that the grown mosaic covered are now uncovered (alpha 250 -> 51), so the notch's small dark hole is a larger hard-edged black block; that block is the clipped-share rise 1.37% -> 1.59%. Composed whole, the tile corner there is not drawn where the grown mosaic drew it; open (Fable 11-22: same, one local regression) |
| earth-fb-still | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus15-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | changed | 4/62 | 29.85% | 192 | mosaic_at029.webp: lit area's centre moved 8 px | one of 62 pictures (at029) changes in its lower-left strip, at noise level; the lit centre moves 8 px because that strip's faint levels changed, not the rings (Fable 11-21: same) |
| titan127-movie | hard | identical | 0/108 | 0.00% |  |  |  |
| june2004-mosaic | hard | changed | 2/2 | 0.00% | 44 |  | small differences only (largest 44 levels, none over 8 levels on more than 0.01% of pixels); at 1:1 a tile at the upper left of the disc reads a touch darker with a soft vertical edge; its existing step and seam are unchanged (Fable 11-22: slightly worse, low confidence) |
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
| enceladus144-mosaic | hard | changed | 2/2 | 0.95% | 20 |  | the disc and crescent limb change by a few levels from the solved gains (one small spot on the bright limb, largest 57 levels); plume and tile frame unchanged (Fable 11-22: same) |
| dione139-mosaic | target | changed | 2/2 | 20.89% | 93 |  | the target: the mid-disc brightness step between the tile rows is clearly softer (a faint trace remains) and the lower step and the darker patch near the right notch are gone; tiles of a balanced mosaic are now solved together with the log gains (held_level), not grown one at a time (Fable 11-21: better, high confidence) |
| titan059-mosaic | hard | changed | 2/2 | 0.48% | 61 |  | thin changes along tile edges only; the tile tints are a different cause, not this PR's (Fable 11-21: same) |
| storm13-night-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| night-washout-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| night-dark-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| storm13-night-movie | hard | identical | 0/10 | 0.00% |  |  |  |
| fring274-movie | hard | identical | 0/172 | 0.00% |  |  |  |
| npole0908-mosaicmovie | hard | changed | 1/1 | 0.00% | 9 |  | noise-level only (Fable 11-21: same) |
| encset293-movie | hard | identical | 0/48 | 0.00% |  |  |  |
| daphnis257n1-movie | hard | identical | 0/34 | 0.00% |  |  |  |
| fring039-movie | hard | identical | 0/144 | 0.00% |  |  |  |
| fring183-movie | hard | identical | 0/61 | 0.00% |  |  |  |
| titancloud264-movie | hard | identical | 0/104 | 0.00% |  |  |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

0 regressions, 0 fixed, 16 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| plume279-movie | odd_frame | known | 12.1826 | 12.1826 (limit 4.0) | worst 12.2 at frame250.webp (10 of 286 frames over 4.0) |
| ringmovie04-movie | full_black | known | 25.18 | 25.18 (limit 20.0) | black sky lost at Full: up to 25 points (82% of frame006.webp black at Processed, 57% at Full; 5 of 16 frames over 20) |
| ringmovie04-movie | pointing_jitter | known | 6.3178 | 6.3178 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 6.3 px, largest 8.7 px (33 pairs) |
| daphnis17-movie | odd_frame | known | 118.1355 | 118.1355 (limit 4.0) | worst 118.1 at frame008.webp (2 of 9 frames over 4.0) |
| impact293-movie | odd_frame | known | 18.4491 | 18.4491 (limit 4.0) | worst 18.4 at frame007.webp (1 of 2 frames over 4.0) |
| mimas04-movie | channel_registration | known | 1.29 | 1.29 (limit 0.7) | red or blue channel off green: p90 1.29 px, largest 1.97 px (23 colour frames) |
| mimas04-movie | full_black | known | 25.17 | 25.17 (limit 20.0) | black sky lost at Full: up to 25 points (98% of frame000.webp black at Processed, 73% at Full; 7 of 16 frames over 20) |
| saturn07-fullblack-movie | full_black | known | 30.05 | 30.05 (limit 20.0) | black sky lost at Full: up to 30 points (78% of frame029.webp black at Processed, 48% at Full; 16 of 16 frames over 20) |
| saturn08w-fullblack-movie | full_black | known | 22.01 | 22.01 (limit 20.0) | black sky lost at Full: up to 22 points (56% of frame002.webp black at Processed, 34% at Full; 2 of 16 frames over 20) |
| saturn08-fullblack-movie | full_black | known | 21.9 | 21.9 (limit 20.0) | black sky lost at Full: up to 22 points (74% of frame025.webp black at Processed, 52% at Full; 3 of 16 frames over 20) |
| pan09-banding-movie | full_banding | known | 7.239 | 7.239 (limit 1.0) | Full sky banding up to 7.24 levels where Processed has black sky (5 of 5 frames over 1.0) |
| night-dark-composite | gray_colour | known | 1.0 | 1.0 (limit 0.0) | 100% of 1 pictures gray (median chroma 0.000); the pipeline says: not aligned |
| fring274-movie | full_black | known | 32.91 | 32.91 (limit 20.0) | black sky lost at Full: up to 33 points (64% of frame023.webp black at Processed, 31% at Full; 10 of 16 frames over 20) |
| fring274-movie | pointing_jitter | known | 5.8112 | 5.8112 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 5.8 px, largest 136.4 px (151 pairs) |
| fring039-movie | full_black | known | 30.05 | 30.05 (limit 20.0) | black sky lost at Full: up to 30 points (78% of frame029.webp black at Processed, 48% at Full; 16 of 16 frames over 20) |
| titancloud264-movie | channel_registration | known | 1.36 | 1.36 (limit 0.7) | red or blue channel off green: p90 1.36 px, largest 1.38 px (52 colour frames) |
