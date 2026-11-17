# Summed frames enlarged smoothly (taste call 23, option C)

Evidence for the change on `claude/summed-smooth`, head bfc26929, against main 02598865.

## The change

181,430 frames were taken summed: the camera added its pixels 2x2 (122,936 frames) or 4x4 (58,494) before sending
them, so they arrive at 512 or 256 lines. The pipeline works at 1024, and until now drew each camera pixel as a 2x2
or 4x4 block. Now a summed frame's calibrated picture is enlarged smoothly (bicubic) from the camera's own pixels,
after calibration and before the geometric correction (`calibration.enlarged`, called in `calibrate`).

- Nothing is sharpened and no detail is added. A flat frame stays flat to the bit.
- Pixels lost in downlink are bridged from the kept pixels above and below before the frame is enlarged, so a lost
  line does not bleed into its neighbors. They are filled afterward as before.
- What the camera saturated, and the 2 camera pixels round it, stay as blocks and fade into the smooth picture over
  one more pixel. The saturation tests and fills downstream see what they saw before.
- The valid and saturated masks keep their block shape.
- A full-size frame is not touched, and neither is a summed frame asked for at its own size.

## Before and after stills

Nine summed frames as stills (`color_image.load_aligned`), from the branch's own code with the enlargement off and
on. Each sheet shows the whole picture, a part at actual size before and after, and its middle at twice the size.

| | frame | taken at | mean before to after |
|---|---|---|---|
| [01](summed_01_N1604167689_2.jpg) | Enceladus N1604167689 | 512 | 71.3 to 71.5 (+0.3%) |
| [02](summed_02_N1521604790_1.jpg) | Rhea N1521604790 | 512 | 40.3 to 40.4 (+0.3%) |
| [03](summed_03_N1568157829_2.jpg) | Iapetus N1568157829 | 512 | 190.9 to 190.6 (-0.1%) |
| [04](summed_04_N1569827764_1.jpg) | Dione N1569827764 | 512 | 185.6 to 185.5 (0.0%) |
| [05](summed_05_N1506391373_2.jpg) | Hyperion N1506391373 | 512 | 161.8 to 152.2 (-5.9%) |
| [06](summed_06_N1354395644_1.jpg) | Jupiter N1354395644 | 512 | 56.8 to 57.0 (+0.4%) |
| [07](summed_07_W1750920394_1.jpg) | Saturn, wide-angle W1750920394 | 256 | 136.4 to 136.4 (0.0%) |
| [08](summed_08_N1589183710_1.jpg) | Saturn's rings N1589183710 | 256 | 227.1 to 226.5 (-0.2%) |
| [09](summed_09_N1565075555_1.jpg) | Saturn N1565075555 | 512 | 157.0 to 156.7 (-0.2%) |

Brightness holds within half a percent on eight of the nine. Hyperion is the exception at 5.9% darker: that frame
sits on the line of the test that decides whether a picture has sky to measure, and the smoother pixels tip it the
other way. The numbers are in `summed.jsonl`.

## Image benchmark

All 53 items: **33 identical, 20 changed**, verdict NEEDS EYES (the harness's word for targets that changed).
Report: [`bench_report.md`](bench_report.md). Sheets: `bench_<item>.jpg` (base, candidate, difference x4, then
crops at actual size of the place that changed most).

I counted the summed frames in every item from the labels. The 20 changed items are the 20 that draw summed
frames, and no item without one changed. One more pass, `jupiter-atmos-mosaic`, has 23 summed frames among its 171,
but the benchmark draws only its last lap (12 tiles) and that picture is identical.

| item | summed frames | moved >8 levels | brightness (mean, 0 to 255) | seam number | my read |
|---|---|---|---|---|---|
| [`ringsFB-mosaic`](./bench_ringsFB-mosaic.jpg) | 275 of 290 | 50.24% | 35.8 to 40.4 (+12.9%) | 0.983 to 1.063 | **not only smoothing**: brighter all over, most in the faint outer rings; the pink patch moved from the left ansa to the right; one more tile is placed (162, main 161) |
| [`ringsFA-mosaic`](./bench_ringsFA-mosaic.jpg) | 157 of 174 | 16.56% | 28.3 to 28.1 (-0.7%) | 1.031 to 0.964 | **not only smoothing**: the white block at the left (a saturated tile, a defect on main) is gray; one more tile is placed (114, main 113) |
| [`earthsmiled-mosaic`](./bench_earthsmiled-mosaic.jpg) | 176 of 216 | 5.79% | 18.0 to 18.5 (+2.8%) | 1.288 to 1.327 | ring edges on the summed tiles smoother; one tile left of Saturn sits a little differently |
| [`ringmosaic04-mosaic`](./bench_ringmosaic04-mosaic.jpg) | 19 of 87 | 22.44% | 36.2 to 36.2 (-0.1%) | 1.007 to 0.990 | as meant on the 19 summed tiles; tiles sit up to 3 px differently, which is what the 'now black' measure sees at the outline |
| `shadow-mosaic` | 50 of 75 | 0.02% | 20.5 to 20.4 (-0.5%) | 0.805 to 0.790 | nothing to see; 16 levels at most |
| [`gring-still`](./bench_gring-still.jpg) | 1 of 1 | 4.39% | 13.9 to 15.2 (+9.1%) |  | as meant: stars and cosmic ray hits are points, not blocks; the noise is finer and the faint ring a little brighter |
| `approach-movie` | 6 of 48 | 0.00% | -0.1% to +0.1% by frame |  | 6 of 48 frames summed; 12 levels at most |
| [`phoebe-mosaic`](./bench_phoebe-mosaic.jpg) | 25 of 25 | 2.74% | 125.4 to 125.4 (+0.0%) | 1.334 to 1.330 | as meant: the cratered right half was plainly blocky and is smooth now |
| [`hyperion-mosaic`](./bench_hyperion-mosaic.jpg) | 27 of 36 | 0.34% | 117.6 to 118.6 (+0.9%) | 1.007 to 1.017 | as meant, barely visible |
| [`rhea-mosaic`](./bench_rhea-mosaic.jpg) | 62 of 83 | 2.51% | 130.4 to 128.9 (-1.2%) | 0.948 to 0.952 | as meant; 1.2% darker all over (the white moved 1%) |
| `titan-globmap-mosaic` | 51 of 51 | 0.01% | 144.8 to 145.1 (+0.2%) | 0.677 to 0.678 | nothing to see; 11 levels at most |
| [`kiviuq-still`](./bench_kiviuq-still.jpg) | 1 of 1 | 10.27% | 30.2 to 32.9 (+9.2%) |  | the same on a near-empty sky frame |
| [`iapetus-mosaic`](./bench_iapetus-mosaic.jpg) | 46 of 115 | 15.03% | 104.9 to 104.9 (+0.0%) | 1.192 to 1.193 | as meant: fine texture over the disk, no streak band (the lost-line fix) |
| [`iapetus-composite`](./bench_iapetus-composite.jpg) | 3 of 3 | 3.54% | 184.2 to 184.0 (-0.1%) |  | as meant: edges of the dark patches smoother |
| `storm-composite` | 1 of 3 | 0.00% | 210.7 to 210.7 (+0.0%) |  | one of three frames summed; 10 levels at most |
| `hexagon-composite` | 2 of 2 | 0.46% | 214.0 to 213.9 (-0.0%) |  | as meant, barely visible |
| [`dione-mosaic`](./bench_dione-mosaic.jpg) | 35 of 57 | 1.42% | 99.7 to 99.6 (-0.1%) | 0.808 to 0.813 | as meant: one summed tile at lower left reads smoother |
| `titan-cloud-mosaic` | 51 of 75 | 0.14% | 131.8 to 131.9 (+0.1%) | 0.931 to 0.913 | nothing to see but two short marks on one tile's edge |
| `titan17-composite` | 2 of 2 | 0.00% | 198.9 to 198.9 (+0.0%) |  | nothing to see; one hot pixel differs |
| [`tossup-enceladus-088en`](./bench_tossup-enceladus-088en.jpg) | 19 of 22 | 31.80% | -7.9% to +4.1% by frame |  | noisy frames of Enceladus in eclipse: the noise is finer; brightness moves a few percent either way by frame |

### How to read it

**Moons, Saturn and Titan (13 items): as meant.** They come out smoother where a tile was summed, with brightness
within about 1% (Rhea is 1.2% darker, evenly over the disk). Phoebe shows it best: 25 of its 25 frames
are summed and the cratered half was plainly blocky. On Iapetus the streak band an earlier version of this branch
drew (lost lines bleeding) is gone.

**Dim, noisy pictures (3 items): finer noise and a little brighter.** On the G ring still, the Kiviuq still and
Enceladus in eclipse, stars and cosmic ray hits become points instead of blocks and the grain is finer. The
harness's "detail" number falls from 1.5 to about 1.0 on the two stills, which is the block edges going away. These
pictures also come out brighter: 1.3 levels on the G ring still and 2.8 on Kiviuq, about 9% of a very dark picture.
My explanation, which I did not measure separately: the levels are taken from the picture as it will be drawn, the
sky's floor is its noise at the 98th percentile, and smoother noise has a lower 98th percentile, so less is cut off.

**Ring mosaics (4 items).** `ringmosaic04` and Earth Smiled read as meant on their summed tiles. Tiles are
registered on their pixels, so with smoother pixels some sit up to 3 px differently; that is what the "light now
black" and seam numbers see.

**The two F ring mosaics are not only smoothing, and I do not call them better.** 275 of 290 frames in `ringsFB`
and 157 of 174 in `ringsFA` are summed, so nearly every tile changes, and each mosaic places one more tile than on
main (162 against 161, 114 against 113). Both pictures have known defect patches on main, and the patches change:

- `ringsFB`: brighter all over (35.8 to 40.4, lit share 61% to 69%), by 3 to 7% in the main rings and by 30 to 80%
  in the faint outer rings, where a few levels are a large share. The pink patch moves from the left ansa to the
  right. Seam number 0.983 to 1.063 (worse).
- `ringsFA`: the white block at the left edge, a saturated tile, is gray (clipped pixels 3.43% to 0.01%). Seam
  number 1.031 to 0.964 (better).

A second build of these two items at main's own commit is queued, to confirm that main gives the same picture twice
and the differences above are this change. Its result will be added here.

## Tests and versions

- `web/test_summed_enlarged.py`: bicubic from the camera's pixels at 512 and 256 lines, no stair steps, block means
  kept, small overshoot, a flat frame unchanged to the bit, lost pixels bridged, saturated pixels and their
  neighbors kept as blocks, full-size and own-size frames left alone.
- 19 related tests pass on bfc26929, among them `test_lost_lines`, `test_hot_lost`, `test_black_lost_pixels`,
  `test_summed_white`, `test_full_depth` and the three `test_saturated_*`.
- Bumped: obs, reel, native, export, levels, color, proc, thumb and the centring version, since every picture made
  from a summed frame changes.
