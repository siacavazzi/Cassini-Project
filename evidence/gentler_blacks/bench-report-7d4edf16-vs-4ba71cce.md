# Image benchmark: 4ba71ccea742 against 7d4edf1635b4

**NEEDS EYES**. 73 items: 35 identical, 38 changed (31 outside the target), 0 not built.

- target items with a measure worse (look at them): ringmovie04-movie, kiviuq-still, titanwac17-haze, saturn07-fullblack-movie, saturn08w-fullblack-movie, saturn13-fullblack-movie, saturn08-fullblack-movie

Built in 46 min (base) and 45 min (candidate). Targets: kiviuq-still, ringmovie04-movie, saturn07-fullblack-movie, saturn08-fullblack-movie, saturn08w-fullblack-movie, saturn13-fullblack-movie, titanwac17-haze.

| item | group | status | pictures changed | moved >8 levels (worst) | largest change (levels) | worse by measure | note |
|---|---|---|---|---|---|---|---|
| ringsFA-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| earthsmiled-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| ringmosaic04-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| shadow-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| photlit039-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| jupiter-atmos-mosaic | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-spol-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| satellorb-centre | hard | changed | 1/1 | 13.51% | 20 |  | Stills' black over the sky's grain: a smooth scattered-light halo shows round overexposed Saturn, cut where the frame ends (Fable: mixed). |
| daphnis09-movie | hard | changed | 46/70 | 1.40% | 255 |  | Hairline differences along ring edges and the frame border only; picture looks identical (Fable: same). |
| ringclose124-movie | hard | identical | 0/10 | 0.00% |  |  |  |
| gring-still | hard | changed | 1/1 | 0.11% | 15 | still.webp: lit area's centre moved 14 px; still.webp: lit share 42.8% -> 37.4% | Marginally darker sky; G ring band and column banding unchanged (Fable: same). Measures move with the black level. |
| plume279-movie | hard | changed | 167/288 | 47.38% | 132 | frame000.webp: 0.50% of the base's light now black; frame000.webp: lit area's centre moved 15 px; frame010.webp: lit share 17.5% -> 9.7% | Full keeps Processed's black sky: gray grainy footprint and column streaks gone, plume kept but its faint outer reach shorter (Fable: better). |
| plume-bloom-still | hard | changed | 1/1 | 8.54% | 19 | still.webp: detail 0.226 -> 0.286 (+27%) | Grain-based black: wider smooth glow round Enceladus and the plume, sky black (Fable: better). Detail/lit-share measures move with the glow. |
| approach-movie | hard | changed | 96/96 | 0.01% | 12 |  | No visible change (Fable: same). |
| ringmovie04-movie | target | changed | 44/44 | 83.42% | 255 | frame000.webp: 25.95% of the base's light now black; frame000.webp: detail 0.1032 -> 0.1496 (+45%); frame000.webp: lit area's centre moved 34 px; frame000.webp: lit share 60.7% -> 38.4% | Target. pointing_jitter 12 -> 15 was already failing on main: the lit-area centroid shifts as faint ring glow shows; black levels move no pixels. |
| telesto-composite | hard | changed | 1/1 | 0.26% | 14 |  | Slightly wider soft halo round the moon (Fable: same). |
| moon99-composite | plain | changed | 1/1 | 0.00% | 9 |  | Footprint lifted about 0.5 level, invisible unless brightened (Fable: mixed). |
| venus99-still | plain | identical | 0/1 | 0.00% |  |  |  |
| masursky-still | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | changed | 1/1 | 4.79% | 17 |  | Soft limb glow slightly wider, smooth (Fable: same). |
| approach-composite | plain | changed | 1/1 | 2.05% | 24 |  | Thin soft glow at the ring edge, sky black (Fable: same). |
| phoebe-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| titan04-composite | plain | changed | 1/1 | 0.96% | 15 | composite.webp: lit area's centre moved 15 px | Known: Titan's real scattered light over the set's frame footprint now shows faintly, about 7.5 levels vs 2.8 (Fable: worse; listed in the PR). |
| saturn05-movie | plain | changed | 27/27 | 0.21% | 70 | frame006.webp: clipped 12.94% -> 13.26% | Only a thin strip at the left frame edge changes; not noticeable (Fable: same). |
| rhea-glocol-composite | plain | changed | 1/1 | 1.08% | 17 |  | Faint smooth limb glow, cut straight at the frame's left edge (Fable: same). |
| hyperion-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| rhea-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| titan-globmap-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| equinox-shadow-still | plain | changed | 1/1 | 1.64% | 17 |  | Leftmost ringlet kept, gap clean black; glow test now net of the camera's banding (Fable: same). |
| kiviuq-still | target | changed | 1/1 | 89.66% | 41 | still.webp: 40.00% of the base's light now black; still.webp: detail 0.9397 -> 1.9598 (+109%); still.webp: lit area's centre moved 63 px; still.webp: lit share 89.8% -> 35.8% |  |
| prometheus-still | plain | changed | 1/1 | 1.29% | 18 |  | Slightly more smooth glow beside the F ring (Fable: same). |
| pan07-still | plain | changed | 1/1 | 2.15% | 19 |  | Hairline differences at ring edges (Fable: same). |
| iapetus-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| iapetus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus-composite | plain | changed | 1/1 | 3.81% | 20 |  | Smooth halo round the lit limb from the grain-based black (Fable: mixed, slightly glowy). |
| mimas-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| storm-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| methone-movie | plain | identical | 0/30 | 0.00% |  |  |  |
| hexagon-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| dione-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| enceladus15-movie | plain | changed | 74/74 | 2.79% | 57 |  | Slight surface contrast change, sky black (Fable: same). |
| telesto-movie | plain | changed | 36/36 | 0.14% | 20 |  | No visible change (Fable: same). |
| daphnis17-movie | plain | changed | 64/64 | 36.86% | 254 | evened000.webp: lit area's centre moved 8 px; evened001.webp: 0.41% of the base's light now black | Blacks unchanged; frames sit a few px differently as the registration's lit area takes in faint glow (Fable: mixed). Black levels move no pixels themselves. |
| pan17-movie | plain | changed | 38/38 | 0.08% | 196 |  | No visible change; frame-edge pixels only (Fable: same). |
| titan-cloud-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| earth-fb-still | plain | changed | 1/1 | 0.00% | 11 | still.webp: lit area's centre moved 13 px | Imperceptible change in rings and gap (Fable: same). |
| enceladus15-composite | plain | changed | 1/1 | 4.65% | 19 | composite.webp: lit area's centre moved 12 px | Night side faintly visible in Saturn-shine, soft limb glow, sky black (Fable: better). |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | identical | 0/62 | 0.00% |  |  |  |
| titan127-movie | hard | changed | 108/108 | 0.43% | 251 | evened047.webp: clipped 0.90% -> 1.71% | No visible change to Titan or sky (Fable: same). |
| june2004-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| saturn-limb-still | hard | changed | 1/1 | 8.55% | 21 |  | Smooth scattered-light glow below the limb fades into black (Fable: natural falloff). limb_halo can't judge rays where the sky is now lit: 0.03 -> 0.0001. |
| enceladus-eye-composite | hard | changed | 1/1 | 3.54% | 20 |  | Same smooth limb halo as enceladus-composite (Fable: mixed). |
| impact293-movie | hard | identical | 0/24 | 0.00% |  |  |  |
| mimas167-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| titanwac17-haze | target | changed | 1/1 | 0.65% | 15 | still.webp: detail 0.0691 -> 0.1222 (+77%) |  |
| saturn07-deck | hard | identical | 0/1 | 0.00% |  |  |  |
| saturn07-deck2 | hard | identical | 0/1 | 0.00% |  |  |  |
| titan08-mt1 | hard | identical | 0/1 | 0.00% |  |  |  |
| rings08-bright | hard | identical | 0/1 | 0.00% |  |  |  |
| mimas04-movie | hard | identical | 0/46 | 0.00% |  |  |  |
| saturn07-fullblack-movie | target | changed | 144/144 | 48.80% | 255 | frame000.webp: 14.84% of the base's light now black; frame000.webp: detail 0.1059 -> 0.1313 (+24%); frame000.webp: lit area's centre moved 26 px; frame000.webp: lit share 65.5% -> 53.0% |  |
| saturn08w-fullblack-movie | target | changed | 14/16 | 37.37% | 138 | frame000.webp: 42.09% of the base's light now black; frame000.webp: detail 0.08 -> 0.1006 (+26%); frame000.webp: lit area's centre moved 125 px; frame000.webp: lit share 33.5% -> 15.8%; frame002.webp: clipped 3.72% -> 4.10% |  |
| saturn13-fullblack-movie | target | changed | 61/61 | 33.11% | 221 | frame000.webp: 4.90% of the base's light now black; frame000.webp: lit area's centre moved 14 px; frame000.webp: lit share 72.3% -> 63.1% |  |
| saturn08-fullblack-movie | target | changed | 84/84 | 69.49% | 245 | evened000.webp: 21.21% of the base's light now black; evened000.webp: detail 0.0827 -> 0.0984 (+19%); evened000.webp: lit area's centre moved 28 px; evened000.webp: lit share 57.1% -> 39.9% |  |
| pan09-banding-movie | hard | identical | 0/16 | 0.00% |  |  |  |
| fring274-movie | hard | changed | 172/172 | 53.62% | 252 | frame000.webp: 4.82% of the base's light now black; frame000.webp: lit area's centre moved 29 px; frame000.webp: lit share 76.6% -> 66.9%; frame001.webp: detail 0.0841 -> 0.0978 (+16%) | Full keeps Processed's black sky (full_black 54 -> 18): veil gone, glow under the A ring fades (Fable: better). |
| npole0908-mosaicmovie | hard | identical | 0/1 | 0.00% |  |  |  |
| encset293-movie | hard | changed | 48/48 | 0.42% | 255 | frame009.webp: clipped 28.08% -> 28.45%; frame021.webp: detail 0.0094 -> 0.0252 (+168%) | Faint smooth glow line above the limb only (Fable: same). |
| daphnis257n1-movie | hard | identical | 0/34 | 0.00% |  |  |  |
| fring039-movie | hard | changed | 144/144 | 48.80% | 255 | frame000.webp: 14.84% of the base's light now black; frame000.webp: detail 0.1059 -> 0.1313 (+24%); frame000.webp: lit area's centre moved 26 px; frame000.webp: lit share 65.5% -> 53.0% | Full keeps Processed's black sky (full_black 49 -> 18): veil and ragged wedge gone, F ring glow fades smoothly (Fable: better). |
| fring183-movie | hard | changed | 61/61 | 33.11% | 221 | frame000.webp: 4.90% of the base's light now black; frame000.webp: lit area's centre moved 14 px; frame000.webp: lit share 72.3% -> 63.1% | Full keeps Processed's black sky (full_black 31 -> 10): veil between A and F rings gone (Fable: better). |
| titancloud264-movie | hard | changed | 104/104 | 0.91% | 125 | evened002.webp: clipped 3.65% -> 4.04%; evened018.webp: detail 0.0285 -> 0.0347 (+22%) | Tiny contrast change at cloud edges (Fable: same). |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

1 regressions, 3 fixed, 17 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| plume279-movie | full_black | known | 24.85 | 24.85 (limit 20.0) | black sky lost at Full: up to 25 points (40% of frame287.webp black at Processed, 15% at Full; 1 of 16 frames over 20) |
| plume279-movie | odd_frame | known | 14.7884 | 14.0524 (limit 4.0) | worst 14.1 at frame074.webp (100 of 286 frames over 4.0) |
| ringmovie04-movie | full_banding | fixed | 1.173 | 0.0 (limit 1.0) | Full sky banding up to 0.00 levels where Processed has black sky (0 of 16 frames over 1.0) |
| ringmovie04-movie | full_black | known | 61.32 | 25.29 (limit 20.0) | black sky lost at Full: up to 25 points (82% of frame006.webp black at Processed, 57% at Full; 5 of 16 frames over 20) |
| ringmovie04-movie | pointing_jitter | known | 11.9955 | 14.836 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 14.8 px, largest 23.6 px (33 pairs) |
| saturn05-movie | channel_registration | known | 10.438 | 10.31 (limit 4.0) | colour along edges past the picture's own: p90 10.31 levels, largest 10.70 (27 colour frames) |
| methone-movie | odd_frame | known | 4.1083 | 4.1083 (limit 4.0) | worst 4.1 at frame010.webp (1 of 1 frames over 4.0) |
| daphnis17-movie | odd_frame | known | 118.2115 | 118.1355 (limit 4.0) | worst 118.1 at frame008.webp (2 of 9 frames over 4.0) |
| saturn-limb-still | limb_halo | REGRESSION | 0.0307 | 0.0001 (limit 0.08) | 75% of 105 rays past the limb rise at most 0.000 of the body's level outward (1% over 0.08; 250 rays not judged, sky lit out there) |
| impact293-movie | odd_frame | known | 18.0219 | 18.0219 (limit 4.0) | worst 18.0 at frame007.webp (1 of 2 frames over 4.0) |
| mimas04-movie | channel_registration | known | 48.81 | 48.81 (limit 4.0) | colour along edges past the picture's own: p90 48.81 levels, largest 48.81 (23 colour frames) |
| mimas04-movie | odd_frame | known | 4.3576 | 4.3576 (limit 4.0) | worst 4.4 at frame018.webp (1 of 9 frames over 4.0) |
| saturn07-fullblack-movie | full_black | known | 49.49 | 30.05 (limit 20.0) | black sky lost at Full: up to 30 points (78% of frame029.webp black at Processed, 48% at Full; 16 of 16 frames over 20) |
| saturn08w-fullblack-movie | full_black | known | 35.86 | 22.01 (limit 20.0) | black sky lost at Full: up to 22 points (56% of frame002.webp black at Processed, 34% at Full; 2 of 16 frames over 20) |
| saturn13-fullblack-movie | full_black | fixed | 30.94 | 19.96 (limit 20.0) | black sky lost at Full: up to 20 points (55% of frame004.webp black at Processed, 35% at Full; 0 of 16 frames over 20) |
| saturn08-fullblack-movie | full_black | known | 53.71 | 21.9 (limit 20.0) | black sky lost at Full: up to 22 points (74% of frame025.webp black at Processed, 52% at Full; 3 of 16 frames over 20) |
| pan09-banding-movie | full_banding | known | 7.239 | 7.239 (limit 1.0) | Full sky banding up to 7.24 levels where Processed has black sky (5 of 5 frames over 1.0) |
| fring274-movie | full_black | known | 54.35 | 32.91 (limit 20.0) | black sky lost at Full: up to 33 points (64% of frame023.webp black at Processed, 31% at Full; 10 of 16 frames over 20) |
| fring274-movie | pointing_jitter | known | 5.8919 | 5.8112 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 5.8 px, largest 136.4 px (151 pairs) |
| fring039-movie | full_black | known | 49.49 | 30.05 (limit 20.0) | black sky lost at Full: up to 30 points (78% of frame029.webp black at Processed, 48% at Full; 16 of 16 frames over 20) |
| fring183-movie | full_black | fixed | 30.94 | 19.96 (limit 20.0) | black sky lost at Full: up to 20 points (55% of frame004.webp black at Processed, 35% at Full; 0 of 16 frames over 20) |
