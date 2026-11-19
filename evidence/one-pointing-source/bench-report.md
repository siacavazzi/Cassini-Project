# Image benchmark: 099f13ba444c against 16b3f6c43ca0

**NEEDS EYES**. 55 items: 49 identical, 6 changed (4 outside the target), 0 not built.

- target items with a measure worse (look at them): encset293-movie, titancloud264-movie

Built in 29 min (base) and 30 min (candidate). Targets: encset293-movie, titancloud264-movie.

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
| ringclose124-movie | hard | changed | 10/10 | 50.20% | 236 | evened000.webp: lit area's centre moved 12 px | now played stabilized by default (one pointing source): 2 frames placed by the pictures, 3 on SPICE's smoothed path; the frames move by the stabilization, no tone change |
| gring-still | hard | identical | 0/1 | 0.00% |  |  |  |
| plume279-movie | hard | identical | 0/288 | 0.00% |  |  |  |
| plume-bloom-still | hard | identical | 0/1 | 0.00% |  |  |  |
| approach-movie | hard | changed | 96/96 | 9.14% | 180 | frame032.webp: 0.21% of the base's light now black | now played stabilized by default: all 48 frames placed by the pictures instead of SPICE's raw places; the frames move by a few px, 'light now black' is the moved edge |
| ringmovie04-movie | hard | changed | 44/44 | 41.05% | 254 | frame003.webp: 0.58% of the base's light now black; frame019.webp: lit area's centre moved 11 px | now played stabilized by default: 13 frames placed by the pictures, 31 on SPICE's smoothed path; pointing_jitter known on both (10.4 -> 12.9 px): its picture links between ring frames are short isolated pairs that disagree with each other by up to 15 px (ringlets repeat along the ring); a ring-movie follow-up, not this PR's rule |
| telesto-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| moon99-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| venus99-still | plain | identical | 0/1 | 0.00% |  |  |  |
| masursky-still | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| approach-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| phoebe-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| titan04-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| saturn05-movie | plain | changed | 27/27 | 1.71% | 232 | frame000.webp: detail 0.1549 -> 0.1802 (+16%) | now played stabilized by default: all 27 frames placed by the pictures; the frames move by the stabilization (detail +16% on frame000 is the moved limb against the frame edge) |
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
| methone-movie | plain | identical | 0/30 | 0.00% |  |  |  |
| hexagon-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| dione-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| enceladus15-movie | plain | identical | 0/74 | 0.00% |  |  |  |
| telesto-movie | plain | identical | 0/36 | 0.00% |  |  |  |
| daphnis17-movie | plain | identical | 0/64 | 0.00% |  |  |  |
| pan17-movie | plain | identical | 0/38 | 0.00% |  |  |  |
| titan-cloud-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| earth-fb-still | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus15-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | identical | 0/62 | 0.00% |  |  |  |
| titan127-movie | hard | identical | 0/108 | 0.00% |  |  |  |
| june2004-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| saturn-limb-still | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-eye-composite | hard | identical | 0/1 | 0.00% |  |  |  |
| encset293-movie | target | changed | 48/48 | 17.46% | 255 | frame000.webp: 7.84% of the base's light now black; frame000.webp: lit area's centre moved 30 px; frame019.webp: detail 0.0105 -> 0.0262 (+150%); frame037.webp: clipped 77.06% -> 77.30% |  |
| titancloud264-movie | target | changed | 104/104 | 0.60% | 70 | evened000.webp: clipped 3.84% -> 4.17%; evened019.webp: detail 0.0451 -> 0.0519 (+15%) |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

0 regressions, 5 fixed, 9 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| ringclose124-movie | pointing_sources | fixed | 5.0 | 0.0 (limit 0) | 0 of 5 frames at SPICE's raw pointing; 2 placed by the pictures, 3 on the smoothed path (stabilized by default) |
| plume279-movie | odd_frame | known | 12.1826 | 12.1826 (limit 4.0) | worst 12.2 at frame250.webp (12 of 286 frames over 4.0) |
| approach-movie | pointing_sources | fixed | 48.0 | 0.0 (limit 0) | 0 of 48 frames at SPICE's raw pointing; 48 placed by the pictures, 0 on the smoothed path (stabilized by default) |
| ringmovie04-movie | pointing_jitter | known | 10.4331 | 12.8906 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 12.9 px, largest 23.7 px (42 pairs) |
| ringmovie04-movie | pointing_sources | fixed | 44.0 | 0.0 (limit 0) | 0 of 44 frames at SPICE's raw pointing; 13 placed by the pictures, 31 on the smoothed path (stabilized by default) |
| moon99-composite | gray_colour | known | 1.0 | 1.0 (limit 0.0) | 100% of 1 pictures gray (median chroma 0.000) |
| saturn05-movie | pointing_sources | fixed | 27.0 | 0.0 (limit 0) | 0 of 27 frames at SPICE's raw pointing; 27 placed by the pictures, 0 on the smoothed path (stabilized by default) |
| storm-composite | gray_colour | known | 1.0 | 1.0 (limit 0.0) | 100% of 1 pictures gray (median chroma 0.000); the pipeline says: not aligned |
| hexagon-composite | gray_colour | known | 1.0 | 1.0 (limit 0.0) | 100% of 1 pictures gray (median chroma 0.000); the pipeline says: not aligned |
| daphnis17-movie | odd_frame | known | 118.2115 | 118.2115 (limit 4.0) | worst 118.2 at frame008.webp (2 of 11 frames over 4.0) |
| daphnis17-movie | pointing_jitter | known | 19.489 | 19.489 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 19.5 px, largest 30.9 px (27 pairs) |
| tossup-ring-108ri | pointing_jitter | known | 172.4451 | 172.4451 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 172.4 px, largest 297.6 px (14 pairs) |
| titan127-movie | odd_frame | known | 40.8719 | 40.8719 (limit 4.0) | worst 40.9 at frame006.webp (3 of 40 frames over 4.0) |
| encset293-movie | pointing_sources | fixed | 48.0 | 0.0 (limit 0) | 0 of 48 frames at SPICE's raw pointing; 41 placed by the pictures, 7 on the smoothed path (stabilized by default) |
