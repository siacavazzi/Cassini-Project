# Image benchmark: 3db47a1e5f58 against 3f85fc7394f7

**NEEDS EYES**. 80 items: 60 identical, 20 changed (13 outside the target), 0 not built.

- target items with a measure worse (look at them): mimas04-movie, aurstare289-movie, wind170-movie, albiorix129-movie, aurora101-movie, approach04-movie

Built in 43 min (base) and 56 min (candidate). Targets: albiorix129-movie, approach04-movie, aurora101-movie, aurstare289-movie, jupiter-tint-movie, mimas04-movie, wind170-movie.

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
| moon99-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| venus99-still | plain | identical | 0/1 | 0.00% |  |  |  |
| masursky-still | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| approach-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| phoebe-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| titan04-composite | plain | identical | 0/1 | 0.00% |  |  |  |
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
| storm-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| methone-movie | plain | changed | 30/30 | 1.64% | 85 | evened000.webp: clipped 0.00% -> 3.83%; evened000.webp: lit area's centre moved 11 px | tinted frames' brightness now matched on the lit moon, not on sky noise (the Jupiter W_10 bug): the moon is drawn ~12% brighter (lit median 74 -> 84), and the core where the clear frames themselves saturated (294 px clipped on the frame's own scale) now shows white; before, the sky-noise match drew the whole moon darker |
| hexagon-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| dione-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| enceladus15-movie | plain | changed | 74/74 | 9.40% | 38 | evened018.webp: clipped 0.00% -> 0.74% | WHITE_EACH / tint match on lit pixels; small uniform change on the lit side |
| telesto-movie | plain | changed | 12/36 | 0.00% | 11 |  | tint match on lit pixels; at most 10 levels |
| daphnis17-movie | plain | changed | 37/64 | 88.95% | 255 | evened008.webp: 37.67% of the base's light now black; evened008.webp: lit area's centre moved 79 px; evened008.webp: lit share 84.7% -> 55.3% | unfit frames hold their own moment, not their filter's frame a cycle back: odd_frame 111 -> 2.6 (fixed); a frame at a new view keeps playing as it is |
| pan17-movie | plain | identical | 0/38 | 0.00% |  |  |  |
| titan-cloud-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| earth-fb-still | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus15-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | identical | 0/62 | 0.00% |  |  |  |
| titan127-movie | hard | changed | 108/108 | 0.07% | 14 | evened002.webp: clipped 0.35% -> 0.58% | tint hue read on Titan's disk; at most 15 levels |
| june2004-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| saturn-limb-still | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-eye-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| impact293-movie | hard | changed | 24/24 | 98.27% | 224 | evened000.webp: detail 0.6438 -> 0.808 (+26%) | held band frames with no gray frame near show the frame before them (MT3 frame 7): odd_frame 18.0 -> 15.8; WHITE_EACH 99.5 |
| mimas167-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| titanwac17-haze | hard | identical | 0/1 | 0.00% |  |  |  |
| saturn07-deck | hard | identical | 0/1 | 0.00% |  |  |  |
| saturn07-deck2 | hard | identical | 0/1 | 0.00% |  |  |  |
| titan08-mt1 | hard | identical | 0/1 | 0.00% |  |  |  |
| rings08-bright | hard | identical | 0/1 | 0.00% |  |  |  |
| mimas04-movie | target | changed | 46/46 | 50.05% | 232 | evened000.webp: detail 2.1289 -> 2.916 (+37%); evened000.webp: lit area's centre moved 51 px |  |
| aurstare289-movie | target | changed | 88/88 | 99.86% | 255 | evened000.webp: 94.98% of the base's light now black; evened000.webp: detail 0.0265 -> 1.5365 (+5698%); evened000.webp: lit area's centre moved 380 px; evened000.webp: lit share 99.9% -> 3.7%; evened001.webp: clipped 0.00% -> 0.65%; evened042.webp: the candidate makes no such picture | target. The stare brightens as it goes (its frames' floor rises from 0 to ~95 of 255 in the raw-calibrated tiles: night-side glow), so later frames are lighter; frame 0 is mid-gray vs frame 1 near-black in the tiles too (floor 34 vs 0). Before, a stray lit-limb frame set the white and hid this. |
| jupiter-tint-movie | target | changed | 40/40 | 0.44% | 103 |  |  |
| wind170-movie | target | changed | 32/32 | 87.59% | 255 | evened014.webp: 1.64% of the base's light now black; evened014.webp: lit area's centre moved 86 px |  |
| albiorix129-movie | target | changed | 39/39 | 13.23% | 255 | frame000.webp: clipped 0.93% -> 1.35%; frame000.webp: 96.47% of the base's light now black; frame000.webp: lit area's centre moved 29 px |  |
| aurora101-movie | target | changed | 84/84 | 86.60% | 255 | evened008.webp: 0.22% of the base's light now black; evened008.webp: lit area's centre moved 150 px; evened008.webp: lit share 64.0% -> 39.7%; evened009.webp: detail 0.1475 -> 0.1994 (+35%) | target. Frame 8 (unfit MT3) now holds frame 7's picture (its own moment) instead of jumping ahead to frame 9's bigger view (W1611761878): the size change now happens at frame 9, when the new pointing's frames start; the narrower slice and black right third are that same view as frames 0-7 |
| approach04-movie | target | changed | 124/140 | 87.40% | 255 | evened026.webp: 0.93% of the base's light now black; evened026.webp: lit area's centre moved 115 px |  |
| saturn07-fullblack-movie | hard | changed | 144/144 | 20.74% | 255 |  | #609's full-black items: WHITE_EACH (no frame of the movie clips) and the tint/hold rules; full_black known on both (24.1 -> 23.5 on saturn07), Fable-judged |
| saturn08w-fullblack-movie | hard | changed | 16/16 | 0.00% | 98 |  | #609's full-black items: WHITE_EACH (no frame of the movie clips) and the tint/hold rules; full_black known on both (24.1 -> 23.5 on saturn07), Fable-judged |
| saturn13-fullblack-movie | hard | identical | 0/61 | 0.00% |  |  |  |
| saturn08-fullblack-movie | hard | changed | 84/84 | 1.71% | 178 |  | #609's full-black items: WHITE_EACH (no frame of the movie clips) and the tint/hold rules; full_black known on both (24.1 -> 23.5 on saturn07), Fable-judged |
| pan09-banding-movie | hard | identical | 0/16 | 0.00% |  |  |  |
| himalia00-movie | hard | changed | 24/40 | 26.88% | 255 | frame005.webp: clipped 0.15% -> 0.41%; frame005.webp: 92.19% of the base's light now black; frame005.webp: lit area's centre moved 75 px | new item guarding STEADY_SEEN_PAD: the moon's square is matched on the moon again (8 px pad lost it to SPICE's few-px error and the stars took over); frames placed on Himalia, pointing_jitter passes on both |
| fring274-movie | hard | identical | 0/172 | 0.00% |  |  |  |
| npole0908-mosaicmovie | hard | identical | 0/1 | 0.00% |  |  |  |
| encset293-movie | hard | identical | 0/48 | 0.00% |  |  |  |
| daphnis257n1-movie | hard | changed | 4/34 | 0.00% | 8 |  | tint hue on the body; at most 8 levels |
| fring039-movie | hard | changed | 144/144 | 20.74% | 255 |  | WHITE_EACH: the A ring keeps tone where it neared white |
| fring183-movie | hard | identical | 0/61 | 0.00% |  |  |  |
| titancloud264-movie | hard | changed | 104/104 | 1.80% | 227 | evened002.webp: clipped 2.61% -> 4.92%; evened014.webp: detail 0.0524 -> 0.0656 (+25%) | WHITE_EACH: the brightening movie's bright cloud patch keeps texture |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

0 regressions, 8 fixed, 19 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| plume279-movie | full_black | known | 24.85 | 24.85 (limit 20.0) | black sky lost at Full: up to 25 points (40% of frame287.webp black at Processed, 15% at Full; 1 of 16 frames over 20) |
| plume279-movie | odd_frame | known | 13.9092 | 13.9092 (limit 4.0) | worst 13.9 at frame088.webp (100 of 286 frames over 4.0) |
| ringmovie04-movie | pointing_jitter | known | 15.2414 | 15.2414 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 15.2 px, largest 19.1 px (36 pairs) |
| saturn05-movie | channel_registration | known | 10.572 | 10.572 (limit 4.0) | colour along edges past the picture's own: p90 10.57 levels, largest 11.10 (27 colour frames) |
| methone-movie | odd_frame | fixed | 4.1083 | 3.9439 (limit 4.0) | worst 3.9 at frame010.webp (0 of 1 frames over 4.0) |
| daphnis17-movie | odd_frame | fixed | 118.1757 | 2.7082 (limit 4.0) | worst 2.7 at frame007.webp (0 of 7 frames over 4.0) |
| impact293-movie | odd_frame | known | 18.0219 | 17.108 (limit 4.0) | worst 17.1 at frame007.webp (1 of 2 frames over 4.0) |
| mimas04-movie | channel_registration | fixed | 48.81 | 3.96 (limit 4.0) | colour along edges past the picture's own: p90 3.96 levels, largest 5.90 (23 colour frames) |
| mimas04-movie | odd_frame | known | 4.3576 | 5.3286 (limit 4.0) | worst 5.3 at frame018.webp (1 of 9 frames over 4.0) |
| aurstare289-movie | full_banding | known | 2.429 | 2.732 (limit 1.0) | Full sky banding up to 2.73 levels where Processed has black sky (9 of 16 frames over 1.0) |
| aurstare289-movie | full_black | known | 69.14 | 69.36 (limit 20.0) | black sky lost at Full: up to 69 points (71% of frame022.webp black at Processed, 1% at Full; 11 of 16 frames over 20) |
| jupiter-tint-movie | channel_registration | fixed | 7.35 | -7.73 (limit 4.0) | colour along edges past the picture's own: p90 -7.73 levels, largest -7.73 (20 colour frames) |
| jupiter-tint-movie | odd_frame | fixed | 5.0647 | 0.7654 (limit 4.0) | worst 0.8 at frame014.webp (0 of 5 frames over 4.0) |
| wind170-movie | odd_frame | fixed | 5.8505 | 1.1318 (limit 4.0) | worst 1.1 at frame008.webp (0 of 2 frames over 4.0) |
| wind170-movie | pointing_jitter | known | 14.97 | 14.633 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 14.6 px, largest 75.1 px (13 pairs) |
| albiorix129-movie | pointing_jitter | fixed | 18.3826 | 1.0978 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 1.1 px, largest 2.9 px (37 pairs) |
| aurora101-movie | channel_registration | known | 8.94 | 9.2 (limit 4.0) | colour along edges past the picture's own: p90 9.20 levels, largest 9.92 (42 colour frames) |
| aurora101-movie | odd_frame | fixed | 87.996 | 0.9877 (limit 4.0) | worst 1.0 at frame011.webp (0 of 6 frames over 4.0) |
| approach04-movie | odd_frame | known | 43.9003 | 27.4303 (limit 4.0) | worst 27.4 at frame027.webp (1 of 12 frames over 4.0) |
| saturn07-fullblack-movie | full_black | known | 24.14 | 23.46 (limit 20.0) | black sky lost at Full: up to 23 points (77% of frame029.webp black at Processed, 53% at Full; 10 of 16 frames over 20) |
| pan09-banding-movie | full_banding | known | 7.141 | 7.141 (limit 1.0) | Full sky banding up to 7.14 levels where Processed has black sky (5 of 5 frames over 1.0) |
| himalia00-movie | full_banding | known | 4.049 | 4.049 (limit 1.0) | Full sky banding up to 4.05 levels where Processed has black sky (3 of 10 frames over 1.0) |
| himalia00-movie | full_black | known | 89.65 | 89.65 (limit 20.0) | black sky lost at Full: up to 90 points (92% of frame000.webp black at Processed, 3% at Full; 3 of 16 frames over 20) |
| himalia00-movie | odd_frame | known | 40.8583 | 40.8583 (limit 4.0) | worst 40.9 at frame003.webp (2 of 14 frames over 4.0) |
| fring274-movie | full_black | known | 22.09 | 22.09 (limit 20.0) | black sky lost at Full: up to 22 points (58% of frame000.webp black at Processed, 36% at Full; 4 of 16 frames over 20) |
| fring274-movie | pointing_jitter | known | 5.8858 | 5.8858 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 5.9 px, largest 137.6 px (152 pairs) |
| fring039-movie | full_black | known | 24.14 | 23.46 (limit 20.0) | black sky lost at Full: up to 23 points (77% of frame029.webp black at Processed, 53% at Full; 10 of 16 frames over 20) |
