# Image benchmark: 61ad1ed83052 against 28ade30fb90e

**FAIL**. 80 items: 4 identical, 22 changed (21 outside the target), 54 not built.

- 54 items not built on both commits: satellorb-centre, daphnis09-movie, ringclose124-movie, gring-still, plume279-movie, plume-bloom-still, approach-movie, ringmovie04-movie, telesto-composite, moon99-composite, venus99-still, masursky-still, jupiter-portrait-composite, approach-composite, titan04-composite, saturn05-movie, rhea-glocol-composite, equinox-shadow-still, kiviuq-still, prometheus-still, pan07-still, iapetus-composite, enceladus-composite, storm-composite, methone-movie, hexagon-composite, enceladus15-movie, telesto-movie, daphnis17-movie, pan17-movie, earth-fb-still, enceladus15-composite, titan17-composite, titan127-movie, saturn-limb-still, enceladus-eye-composite, impact293-movie, titanwac17-haze, saturn07-deck, saturn07-deck2, titan08-mt1, rings08-bright, mimas04-movie, saturn07-fullblack-movie, saturn08w-fullblack-movie, saturn13-fullblack-movie, saturn08-fullblack-movie, pan09-banding-movie, fring274-movie, encset293-movie, daphnis257n1-movie, fring039-movie, fring183-movie, titancloud264-movie

Built in 23 min (base) and 23 min (candidate). Targets: dione139-mosaic.

| item | group | status | pictures changed | moved >8 levels (worst) | largest change (levels) | worse by measure | note |
|---|---|---|---|---|---|---|---|
| ringsFA-mosaic | hard | changed | 2/2 | 5.56% | 61 |  | rings about 6% brighter and a little creamier from the solved gains. The saturated block on the left stays white (clipped_white: 255/255/254 against the old 255; it went 255/255/247 cream before this fix). The pink ring patches move and change shape but are not new; the pink tile rectangles below the rings are in both (Fable 11-21: mixed, none worse) |
| earthsmiled-mosaic | hard | changed | 2/2 | 10.23% | 111 |  | main rings go from purple/blue-grey to a more neutral cream-tan, and the green cast in the faint outer ring is reduced; faint ring detail kept (Fable 11-21: better) |
| ringmosaic04-mosaic | hard | changed | 2/2 | 0.39% | 24 |  | rings very slightly brighter and clearer; the green smear by the planet and the blown planet are unchanged; no new clipping (Fable 11-21: same to slightly better) |
| shadow-mosaic | hard | changed | 2/2 | 0.45% | 90 |  | very small ring and halo level changes from the solved gains; faint halo detail kept (Fable 11-21: same) |
| photlit039-mosaic | hard | changed | 2/2 | 0.01% | 29 |  | rings a touch more even and a faint yellow-pink blotch on the globe weaker (Fable 11-21: slightly better) |
| jupiter-atmos-mosaic | hard | changed | 1/1 | 0.00% | 10 |  | sub-visible changes only (largest 10 levels) (Fable 11-21: same) |
| enceladus-spol-mosaic | hard | changed | 2/2 | 0.66% | 17 |  | the saturated crescent stays flat and gray (about 236 to 228; the bench's clipped_white check wants it gray, not white) and the night side is very slightly brighter; no clipping added (Fable 11-21: mixed, near same) |
| satellorb-centre | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| daphnis09-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| ringclose124-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| gring-still | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| plume279-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| plume-bloom-still | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| approach-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| ringmovie04-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| telesto-composite | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| moon99-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| venus99-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| masursky-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| approach-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| phoebe-mosaic | plain | changed | 2/2 | 0.00% | 10 |  | noise-level changes only (Fable 11-21: same) |
| titan04-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn05-movie | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| rhea-glocol-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| hyperion-mosaic | plain | changed | 2/2 | 0.01% | 13 |  | noise-level changes only (Fable 11-21: same) |
| rhea-mosaic | plain | changed | 2/2 | 0.21% | 169 |  | a small change at the top limb and faint tile-edge lines in the difference, not visible as seams; the largest change is a few pixels at that limb (Fable 11-21: same) |
| titan-globmap-mosaic | plain | changed | 2/2 | 0.31% | 46 |  | low-level changes from the solved gains, nothing visible; tile edges unchanged (Fable 11-21: same) |
| equinox-shadow-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| kiviuq-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| prometheus-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| pan07-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| iapetus-mosaic | plain | changed | 2/2 | 0.08% | 75 |  | noise-level changes plus a faint change along a tile outline in the sky (Fable 11-21: same) |
| iapetus-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| enceladus-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| mimas-mosaic | plain | changed | 2/2 | 0.01% | 96 |  | faint halo arcs left of the disc shift slightly, present in both; the disc is unchanged (Fable 11-21: same) |
| storm-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| methone-movie | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| hexagon-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| dione-mosaic | plain | changed | 2/2 | 0.26% | 153 |  | a couple of tiny specks near the limb change; no seam, tint or clipping change (Fable 11-21: same) |
| enceladus15-movie | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| telesto-movie | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| daphnis17-movie | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| pan17-movie | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| titan-cloud-mosaic | plain | changed | 2/2 | 7.26% | 255 | mosaic.webp: clipped 1.37% -> 1.59% | the upper-left tiles blend more evenly with their neighbours (the solved gains). One local loss: at the notch on the left edge about 95 px of the screen picture (a 13 x 9 px patch at x 157-165, y 447-459) that the grown mosaic covered are now uncovered (alpha 250 -> 51), so the notch's small dark hole is a larger hard-edged black block; that block is the clipped-share rise 1.37% -> 1.59%. Composed whole, the tile corner there is not drawn where the grown mosaic drew it; open (Fable 11-22: same, one local regression) |
| earth-fb-still | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| enceladus15-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| titan17-composite | plain | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | changed | 4/62 | 29.85% | 192 | mosaic_at029.webp: lit area's centre moved 8 px | one of 62 pictures (at029) changes in its lower-left strip, at noise level; the lit centre moves 8 px because that strip's faint levels changed, not the rings (Fable 11-21: same) |
| titan127-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| june2004-mosaic | hard | changed | 2/2 | 0.00% | 44 |  | small differences only (largest 44 levels, none over 8 levels on more than 0.01% of pixels); at 1:1 a tile at the upper left of the disc reads a touch darker with a soft vertical edge; its existing step and seam are unchanged (Fable 11-22: slightly worse, low confidence) |
| saturn-limb-still | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| enceladus-eye-composite | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| impact293-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| mimas167-mosaic | hard | changed | 2/2 | 1.04% | 145 |  | a tiny change on the lit disc and very faint contour streaks in the dark lower right; the clipped share rises 1.82% to 2.16% at the black end (dark sky), not at white (Fable 11-21: same) |
| titanwac17-haze | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn07-deck | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn07-deck2 | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| titan08-mt1 | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| rings08-bright | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| mimas04-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn07-fullblack-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn08w-fullblack-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn13-fullblack-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| saturn08-fullblack-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| pan09-banding-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| enceladus144-mosaic | hard | changed | 2/2 | 0.05% | 57 |  | the disc and crescent limb change by a few levels from the solved gains (one small spot on the bright limb, largest 57 levels); plume and tile frame unchanged (Fable 11-22: same) |
| dione139-mosaic | target | changed | 2/2 | 20.90% | 98 |  | the target: the mid-disc brightness step between the tile rows is clearly softer (a faint trace remains) and the lower step and the darker patch near the right notch are gone; tiles of a balanced mosaic are now solved together with the log gains (held_level), not grown one at a time (Fable 11-21: better, high confidence) |
| titan059-mosaic | hard | changed | 2/2 | 0.48% | 61 |  | thin changes along tile edges only; the tile tints are a different cause, not this PR's (Fable 11-21: same) |
| storm13-night-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| night-washout-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| night-dark-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| storm13-night-movie | hard | identical | 0/10 | 0.00% |  |  |  |
| fring274-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| npole0908-mosaicmovie | hard | changed | 1/1 | 0.00% | 9 |  | noise-level only (Fable 11-21: same) |
| encset293-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| daphnis257n1-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| fring039-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| fring183-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| titancloud264-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

0 regressions, 0 fixed, 1 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| night-dark-composite | gray_colour | known | 1.0 | 1.0 (limit 0.0) | 100% of 1 pictures gray (median chroma 0.000); the pipeline says: not aligned |
