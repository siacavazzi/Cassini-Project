# Image benchmark: 412b12cc2d4d against 387019fa8ab7

**FAIL**. 31 items: 2 identical, 23 changed (12 outside the target), 6 not built.

- 6 items not built on both commits: fring274-movie, npole0908-mosaicmovie, daphnis257n1-movie, fring039-movie, fring183-movie, titancloud264-movie
- target items with a measure worse (look at them): saturn05-movie, rz-enceladus15-still, adj-rz-enceladus15-still-obs, adj-rz-titan10-movie4-obs, t36-titan028, t36-enc215, t36-enc243, t36-enc136ecl, t36-enc136lr, t36-tethys, t36-jupiter

Built in 23 min (base) and 23 min (candidate). Targets: adj-rz-enceladus15-still-obs, adj-rz-titan10-movie4-obs, rz-enceladus15-still, saturn05-movie, t36-enc136ecl, t36-enc136lr, t36-enc215, t36-enc243, t36-jupiter, t36-tethys, t36-titan028.

| item | group | status | pictures changed | moved >8 levels (worst) | largest change (levels) | worse by measure | note |
|---|---|---|---|---|---|---|---|
| saturn05-movie | target | changed | 54/54 | 5.06% | 240 | evened009.webp: clipped 11.97% -> 12.28%; evened009.webp: 0.58% of the base's light now black |  |
| approach04-movie | hard | changed | 134/140 | 0.02% | 17 |  | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| saturn16-uv2-movie | hard | identical | 0/52 | 0.00% |  |  | clouded body cross-filter links weigh 0.1, and its pictures disagree by 9 px (res_p90), so the sequence plays whole on SPICE's smoothed path; jitter 3.6 -> 6.4, Fable on frames 39-44: SAME |
| skathi11-veil-movie | hard | changed | 134/134 | 15.18% | 255 | frame000.webp: 97.76% of the base's light now black; frame000.webp: lit area's centre moved 25 px; frame030.webp: clipped 0.99% -> 1.23% | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path); pictures disagree by 40 px: whole on SPICE's smoothed path; jitter 26 -> 16; odd_frame at the near-blank frame 84 (Fable: SAME, the hop across it 17 -> 10 px) |
| rx-saturn14-movie | hard | changed | 108/144 | 0.00% | 11 |  | clouded body cross-filter links weigh 0.1; channel_registration 0.48 -> 0.82 by the measure, Fable at 1:1: no visible fringe |
| m-mundilfari07-pass | hard | changed | 22/22 | 10.58% | 255 | evened000.webp: 97.67% of the base's light now black; evened006.webp: lit area's centre moved 13 px | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| m-pallene17-pass | hard | changed | 30/30 | 10.11% | 193 | evened000.webp: 0.77% of the base's light now black | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| rx-sun02-cruise | hard | changed | 22/22 | 50.58% | 255 | evened000.webp: 0.92% of the base's light now black; evened000.webp: lit area's centre moved 13 px | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| ry-methone12-movie | hard | changed | 47/47 | 0.07% | 253 | frame002.webp: clipped 0.44% -> 0.96%; frame022.webp: 0.34% of the base's light now black | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| rz-enceladus13-movie | hard | changed | 62/62 | 23.36% | 255 | frame000.webp: 8.93% of the base's light now black; frame000.webp: lit area's centre moved 25 px; frame005.webp: clipped 66.01% -> 66.37%; frame045.webp: detail 0.0914 -> 0.1065 (+17%) | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| m-janus10-pass | hard | changed | 48/48 | 3.06% | 201 | evened020.webp: 0.47% of the base's light now black | pointing: its unmatched red frame 21 takes the median of its colour set's placed frames (the pictures place frames 0-20 and 22-26 as two runs 80 px apart); jitter 30.8 -> 30.4, odd_frame 2.77 -> 2.71; Fable on frames 19-24: SAME colour and position as main |
| adj-m-io00-pass-yr | hard | changed | 246/246 | 10.41% | 255 | evened000.webp: 1.24% of the base's light now black; evened046.webp: lit area's centre moved 14 px | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path) |
| rx-saturn05-movie | hard | changed | 54/54 | 10.30% | 254 | evened000.webp: 0.37% of the base's light now black; evened000.webp: detail 0.148 -> 0.1725 (+17%); evened012.webp: clipped 10.00% -> 10.21% | pointing: one source per sequence (frames the pictures do not place go between the pictures' places by time; a sequence the pictures place under half of, or whose links disagree past 5 px, whole on SPICE's smoothed path); jitter 0.43 -> 3.06 by the measure, Fable on frames 21-26: SAME, 0 px from main |
| rz-enceladus15-still | target | changed | 1/1 | 99.85% | 255 | still.webp: 96.95% of the base's light now black; still.webp: detail 0.2947 -> 0.34 (+15%); still.webp: lit area's centre moved 510 px; still.webp: lit share 96.0% -> 48.2% |  |
| adj-rz-enceladus15-still-obs | target | changed | 1/1 | 99.99% | 255 | still.webp: 14.70% of the base's light now black; still.webp: detail 0.1362 -> 0.578 (+324%); still.webp: lit area's centre moved 402 px; still.webp: lit share 100.0% -> 86.7% |  |
| adj-rz-titan10-movie4-obs | target | changed | 48/48 | 1.13% | 247 | evened006.webp: clipped 2.72% -> 2.95% |  |
| t36-titan028 | target | changed | 1/1 | 66.22% | 255 | still.webp: 99.98% of the base's light now black; still.webp: lit area's centre moved 500 px; still.webp: lit share 8.3% -> 3.9% |  |
| t36-titan125 | plain | identical | 0/1 | 0.00% |  |  |  |
| t36-enc215 | target | changed | 1/1 | 98.23% | 255 | still.webp: 88.59% of the base's light now black; still.webp: lit area's centre moved 494 px; still.webp: lit share 89.9% -> 46.7% |  |
| t36-enc243 | target | changed | 1/1 | 67.97% | 255 | still.webp: detail 0.2253 -> 0.6613 (+194%); still.webp: lit area's centre moved 292 px |  |
| t36-enc136ecl | target | changed | 1/1 | 75.26% | 255 | still.webp: lit area's centre moved 361 px; still.webp: lit share 97.1% -> 94.5% |  |
| t36-enc136lr | target | changed | 1/1 | 74.32% | 255 | still.webp: detail 0.0937 -> 0.2803 (+199%); still.webp: lit area's centre moved 328 px |  |
| t36-tethys | target | changed | 1/1 | 65.98% | 255 | still.webp: 99.17% of the base's light now black; still.webp: lit area's centre moved 545 px |  |
| t36-jupiter | target | changed | 1/1 | 98.83% | 255 | still.webp: detail 0.038 -> 0.0483 (+27%); still.webp: lit area's centre moved 561 px; still.webp: lit share 99.9% -> 59.6% |  |
| fring274-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| npole0908-mosaicmovie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| encset293-movie | hard | changed | 37/48 | 5.45% | 255 | frame019.webp: detail 0.0106 -> 0.0261 (+146%); frame038.webp: clipped 76.54% -> 76.75% | pointing: one source per sequence (its 7 unmatched frames go between the pictures' places, not on SPICE's step); jitter 0.29 -> 0.40, pointing_sources fixed |
| daphnis257n1-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| fring039-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| fring183-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |
| titancloud264-movie | hard | not built (base: not built; candidate: not built) | 0/0 | 0.00% |  |  |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).

## Checks

2 regressions, 13 fixed, 15 known (failing on the base too), 0 errors. A known failure is a defect already on the base; it does not fail this run, and a fix should turn it into fixed.

| item | check | verdict | base | candidate | what |
|---|---|---|---|---|---|
| saturn05-movie | odd_frame | known | 5.1307 | 5.3405 (limit 4.0) | worst 5.3 at frame003.webp (5 of 7 frames over 4.0) |
| approach04-movie | odd_frame | known | 27.6188 | 27.3111 (limit 4.0) | worst 27.3 at frame027.webp (1 of 12 frames over 4.0) |
| approach04-movie | pointing_sources | fixed | 1.0 | 0.0 (limit 0) | 0 of 70 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 69 placed by the pictures, 1 on the smoothed path (stabilized by defa |
| saturn16-uv2-movie | full_banding | known | 1.303 | 1.303 (limit 1.0) | Full sky banding up to 1.30 levels where Processed has black sky (1 of 16 frames over 1.0) |
| skathi11-veil-movie | odd_frame | REGRESSION | 2.8443 | 6.0996 (limit 4.0) | worst 6.1 at frame084.webp (1 of 97 frames over 4.0) |
| skathi11-veil-movie | pointing_jitter | known | 26.2062 | 15.9921 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 16.0 px, largest 35.2 px (109 pairs) |
| skathi11-veil-movie | pointing_sources | fixed | 53.0 | 0.0 (limit 0) | 0 of 134 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 0 placed by the pictures, 0 on the smoothed path (stabilized by defa |
| rx-saturn14-movie | channel_registration | REGRESSION | 0.48 | 0.82 (limit 0.7) | red or blue channel off green: p90 0.82 px, largest 0.82 px (72 colour frames) |
| m-mundilfari07-pass | pointing_sources | fixed | 3.0 | 0.0 (limit 0) | 0 of 11 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 0 placed by the pictures, 0 on the smoothed path (stabilized by defau |
| m-pallene17-pass | pointing_jitter | known | 28.2952 | 28.6615 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 28.7 px, largest 111.5 px (12 pairs) |
| m-pallene17-pass | pointing_sources | fixed | 1.0 | 0.0 (limit 0) | 0 of 15 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 14 placed by the pictures, 1 on the smoothed path (stabilized by defa |
| rx-sun02-cruise | odd_frame | known | 79.0499 | 78.9782 (limit 4.0) | worst 79.0 at frame003.webp (3 of 5 frames over 4.0) |
| rx-sun02-cruise | pointing_jitter | fixed | 6.3895 | 0.2946 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 0.3 px, largest 0.4 px (7 pairs) |
| rx-sun02-cruise | pointing_sources | fixed | 4.0 | 0.0 (limit 0) | 0 of 11 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 7 placed by the pictures, 4 on the smoothed path (stabilized by defau |
| ry-methone12-movie | full_black | known | 77.33 | 77.09 (limit 20.0) | black sky lost at Full: up to 77 points (100% of frame028.webp black at Processed, 23% at Full; 2 of 16 frames over 20) |
| ry-methone12-movie | odd_frame | known | 21.7011 | 21.6886 (limit 4.0) | worst 21.7 at frame028.webp (9 of 37 frames over 4.0) |
| ry-methone12-movie | pointing_sources | fixed | 4.0 | 0.0 (limit 0) | 0 of 47 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 43 placed by the pictures, 4 on the smoothed path (stabilized by defa |
| rz-enceladus13-movie | odd_frame | known | 32.1055 | 23.7825 (limit 4.0) | worst 23.8 at frame008.webp (20 of 54 frames over 4.0) |
| rz-enceladus13-movie | pointing_jitter | known | 20.9301 | 7.2667 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 7.3 px, largest 8.6 px (15 pairs) |
| rz-enceladus13-movie | pointing_sources | fixed | 5.0 | 0.0 (limit 0) | 0 of 62 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 0 placed by the pictures, 0 on the smoothed path (stabilized by defau |
| m-janus10-pass | pointing_jitter | known | 30.758 | 30.3857 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 30.4 px, largest 136.0 px (23 pairs) |
| m-janus10-pass | pointing_sources | fixed | 1.0 | 0.0 (limit 0) | 0 of 27 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 23 placed by the pictures, 1 on the smoothed path (stabilized by defa |
| adj-m-io00-pass-yr | odd_frame | known | 16.5817 | 18.4507 (limit 4.0) | worst 18.5 at frame055.webp (61 of 83 frames over 4.0) |
| adj-m-io00-pass-yr | pointing_jitter | known | 28.148 | 29.7141 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 29.7 px, largest 31.8 px (92 pairs) |
| adj-m-io00-pass-yr | pointing_sources | fixed | 25.0 | 0.0 (limit 0) | 0 of 123 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 98 placed by the pictures, 25 on the smoothed path (stabilized by de |
| rx-saturn05-movie | odd_frame | known | 5.6011 | 6.1035 (limit 4.0) | worst 6.1 at frame003.webp (5 of 7 frames over 4.0) |
| rx-saturn05-movie | pointing_sources | fixed | 1.0 | 0.0 (limit 0) | 0 of 27 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 27 placed by the pictures, 0 on the smoothed path (stabilized by defa |
| adj-rz-titan10-movie4-obs | channel_registration | known | 1.295 | 1.114 (limit 0.7) | red or blue channel off green: p90 1.11 px, largest 1.26 px (24 colour frames) |
| adj-rz-titan10-movie4-obs | pointing_jitter | fixed | 17.7088 | 0.4999 (limit 3.0) | frame-to-frame jump past the movie's own motion: p90 0.5 px, largest 0.6 px (19 pairs) |
| encset293-movie | pointing_sources | fixed | 7.0 | 0.0 (limit 0) | 0 of 48 frames at SPICE's raw pointing, 0 on SPICE's step among frames the pictures place; 41 placed by the pictures, 7 on the smoothed path (stabilized by defa |
