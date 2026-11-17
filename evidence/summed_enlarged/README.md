# Summed frames enlarged smoothly (taste call 23, option C)

Evidence for the change on `claude/summed-smooth`, code at 45b0f4a9, against main 02598865.

## The change

181,430 frames were taken summed: the camera added its pixels 2x2 (122,936 frames) or 4x4 (58,494) before sending
them, so they arrive at 512 or 256 lines. The pipeline works at 1024, and until now drew each camera pixel as a 2x2
or 4x4 block. Now a summed frame's calibrated picture is enlarged smoothly (bicubic) from the camera's own pixels,
after calibration and before the geometric correction (`calibration.enlarged`, called in `calibrate`).

Only what the camera measured is enlarged:

- Nothing is sharpened and no detail is added. A flat frame stays flat to the bit.
- Pixels lost in downlink keep the values they had, block for block, so everything measured or filled downstream
  meets what it met before. So that they do not bleed into their neighbors when the frame is enlarged, they are
  bridged first from the kept pixels above and below, and a column with nothing kept (a summed frame's first and
  last column always count as lost) from the pixels beside it.
- What the camera saturated, and the 2 camera pixels round it, stay as blocks and fade into the smooth picture over
  one more pixel.
- The valid and saturated masks keep their block shape.
- A full-size frame is not touched, and neither is a summed frame asked for at its own size.

## Before and after stills

Nine summed frames as stills (`color_image.load_aligned`), from the branch's own code with the enlargement off and
on. Each sheet shows the whole picture, a part at actual size before and after, and its middle at twice the size.
They were rendered at bfc26929 and again at 0cff22a2, byte for byte the same; the last commit changes only frames
handed over with a lost-pixel mask, which the stills path does not do (the benchmark's six stills and composites
are also byte-identical between its last two runs).

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

All 53 items, 45b0f4a9 against main: **33 identical, 20 changed**, verdict NEEDS EYES (the harness's word for
targets that changed). Report: [`bench_report.md`](bench_report.md). Sheets: `bench_<item>.jpg` (base, candidate,
difference x4, then crops at actual size of the place that changed most).

I counted the summed frames in every item from the labels. The 20 changed items are the 20 that draw summed
frames, and no item without one changed. One more pass, `jupiter-atmos-mosaic`, has 23 summed frames among its 171,
but the benchmark draws only its last lap (12 tiles) and that picture is identical.

Main gives the same picture twice: `ringsFA-mosaic` and `ringsFB-mosaic` built a second time at main's commit,
seven hours after the first, are byte-identical to it. So every difference below is this change's.

| item | summed frames | moved >8 levels | brightness (mean, 0 to 255) | seam number | my read |
|---|---|---|---|---|---|
| [`ringsFB-mosaic`](./bench_ringsFB-mosaic.jpg) | 275 of 290 | 12.15% | 35.8 to 35.6 (-0.6%) | 0.983 to 0.980 | the same picture as main: brightness and patches as they were; ring edges smoother, and the tiles by Saturn's shadow on the rings sit a little differently |
| [`ringsFA-mosaic`](./bench_ringsFA-mosaic.jpg) | 157 of 174 | 10.09% | 28.3 to 28.4 (+0.6%) | 1.031 to 1.080 | the same picture as main: brightness, the white block and the patches as they were; ring edges smoother, some tiles sit a little differently |
| [`earthsmiled-mosaic`](./bench_earthsmiled-mosaic.jpg) | 176 of 216 | 3.70% | 18.0 to 18.5 (+2.7%) | 1.288 to 1.494 | the same picture to the eye; ring tiles right of Saturn sit a little differently. Seam number worse by measure; I see no new seam at actual size |
| [`ringmosaic04-mosaic`](./bench_ringmosaic04-mosaic.jpg) | 19 of 87 | 41.41% | 36.2 to 36.5 (+0.6%) | 1.007 to 0.998 | the same picture, placed about 7 and 9 px differently on its canvas, which is most of the pixels that move; as meant on the 19 summed tiles |
| `shadow-mosaic` | 50 of 75 | 0.02% | 20.5 to 20.6 (+0.2%) | 0.805 to 0.792 | nothing to see; 16 levels at most |
| [`gring-still`](./bench_gring-still.jpg) | 1 of 1 | 4.39% | 13.9 to 15.2 (+9.1%) |  | as meant: stars and cosmic ray hits are points, not blocks; the noise is finer and the faint ring a little brighter |
| `approach-movie` | 6 of 48 | 0.00% | -0.1% to +0.1% by frame |  | 6 of 48 frames summed; 12 levels at most |
| [`phoebe-mosaic`](./bench_phoebe-mosaic.jpg) | 25 of 25 | 2.54% | 125.4 to 125.4 (-0.0%) | 1.334 to 1.325 | as meant: the cratered right half was plainly blocky and is smooth now |
| [`hyperion-mosaic`](./bench_hyperion-mosaic.jpg) | 27 of 36 | 0.15% | 117.6 to 117.6 (+0.0%) | 1.007 to 1.008 | as meant, barely visible |
| [`rhea-mosaic`](./bench_rhea-mosaic.jpg) | 62 of 83 | 0.25% | 130.4 to 130.3 (-0.1%) | 0.948 to 0.954 | as meant, barely visible |
| `titan-globmap-mosaic` | 51 of 51 | 0.00% | 144.8 to 144.9 (+0.0%) | 0.677 to 0.676 | nothing to see; 11 levels at most |
| [`kiviuq-still`](./bench_kiviuq-still.jpg) | 1 of 1 | 10.27% | 30.2 to 32.9 (+9.2%) |  | the same on a near-empty sky frame |
| [`iapetus-mosaic`](./bench_iapetus-mosaic.jpg) | 46 of 115 | 14.95% | 104.9 to 104.9 (-0.0%) | 1.192 to 1.194 | as meant: fine texture over the disk, and no streak band from lost lines |
| [`iapetus-composite`](./bench_iapetus-composite.jpg) | 3 of 3 | 3.54% | 184.2 to 184.0 (-0.1%) |  | as meant: edges of the dark patches smoother |
| `storm-composite` | 1 of 3 | 0.00% | 210.7 to 210.7 (+0.0%) |  | one of three frames summed; 10 levels at most |
| `hexagon-composite` | 2 of 2 | 0.46% | 214.0 to 213.9 (-0.0%) |  | as meant, barely visible |
| [`dione-mosaic`](./bench_dione-mosaic.jpg) | 35 of 57 | 1.20% | 99.7 to 99.7 (+0.0%) | 0.808 to 0.823 | as meant: one summed tile at lower left reads smoother |
| `titan-cloud-mosaic` | 51 of 75 | 0.14% | 131.8 to 131.8 (+0.0%) | 0.931 to 0.935 | nothing to see but two short marks on one tile's edge |
| `titan17-composite` | 2 of 2 | 0.00% | 198.9 to 198.9 (+0.0%) |  | nothing to see; one hot pixel differs |
| [`tossup-enceladus-088en`](./bench_tossup-enceladus-088en.jpg) | 19 of 22 | 72.19% | -20.0% to -4.1% by frame |  | noisy frames of Enceladus in eclipse: 4 to 12% darker (one frame 20%), because fewer noise specks stand above black on the night side; the disk is as bright as before |

### How to read it

**Moons, Saturn and Titan (13 items): as meant.** They come out smoother where a tile was summed, and brightness
holds within 0.2%. Phoebe shows it best: all 25 of its frames are summed and the cratered half was plainly blocky.

**Dim, noisy pictures (3 items): finer noise.** On the G ring still and the Kiviuq still, stars and cosmic ray hits
become points instead of blocks and the grain is finer. The harness's "detail" number falls from 1.5 to about 1.0,
which is the block edges going away. Both come out a little brighter: 1.3 levels on the G ring still and 2.8 on
Kiviuq, about 9% of a very dark picture. The movie of Enceladus in eclipse goes the other way, 4 to 12% darker
(one frame 20%), because fewer noise specks stand above black on the night side; the disk itself is as bright as
before. My explanation for both, not measured separately: a picture's black is set just above its sky's noise, and
smoother noise is lower.

**Ring mosaics (4 items): the same pictures, with tiles sitting a little differently.** A mosaic's tiles are
registered on their pixels, so with smoother pixels some register differently. Brightness is within 0.6% on three
of them and 2.7% (half a level) on Earth Smiled.

- `ringsFB` and `ringsFA` (275 of 290 and 157 of 174 frames summed): the defect patches these two have on main,
  the pink patch and the white block, are where they were. Measured on plans kept from both builds: the pass's
  black is within 2.7% of main's on every filter, the white within 1.5%, the angle and footprint the same. Of the
  tiles registered in both builds (92 and 47), the registration moved by a median 0.27 and 0.40 px, more than 1 px
  on 21 and 17 tiles, and 11 and 20 tiles switch between registered and left where SPICE puts them. The rings'
  joint solve fits better: the share of misfit measures falls from 9.2% to 5.3% and from 11.2% to 1.2%. Seam
  number 0.983 to 0.980 and 1.031 to 1.080. Numbers: [`f_ring_plans.txt`](f_ring_plans.txt).
- `ringmosaic04`: the whole picture sits about 7 and 9 px differently on its canvas, which is most of the pixels
  that move (at full size, 20% over 8 levels as built and 8% once that shift is undone).
- Earth Smiled: the seam number is worse by measure (1.288 to 1.494). At actual size I see no new seam; the ring
  tiles right of Saturn sit a little differently.

## What review and the F ring mosaics turned up

Two defects in earlier versions of this branch, both fixed and both in the test now:

1. **Edge columns (review).** A summed frame's first and last column always count as lost. They were bridged from
   the frame's median, which then bled into the two camera pixels beside each edge: a band down both sides of a
   tile wherever a ring or limb crosses its edge. Now a column with nothing kept takes the pixels beside it
   (0cff22a2).
2. **Lost pixels left bridged (found on the F ring mosaics).** With that fixed, `ringsFB` still drew 14% brighter
   than main. A pass's black sits above its sky's fine structure, and that measure counts the lost pixels. With the
   bridge left in their place it fell by a quarter to a half on the 4x4 filters (all 128 IR3 and VIO frames of
   `ringsFB`, measured as `pass_scale` does: VIO 3.42e-4 to 1.52e-4, IR3 2.78e-4 to 2.07e-4). Now the lost pixels
   get their own values back after the enlargement, and the same measure is 3.43e-4 and 2.75e-4 (45b0f4a9).

## Tests and versions

- `web/test_summed_enlarged.py`: bicubic from the camera's pixels at 512 and 256 lines, no stair steps, block means
  kept, small overshoot, a flat frame unchanged to the bit, lost pixels bridged without bleeding and left with
  their own values, edge columns taking the pixels beside them, saturated pixels and their neighbors kept as
  blocks, full-size and own-size frames left alone.
- 19 related tests pass on 45b0f4a9, among them `test_lost_lines`, `test_hot_lost`, `test_black_lost_pixels`,
  `test_summed_white`, `test_full_depth` and the three `test_saturated_*`.
- Bumped: obs, reel, native, export, levels, color, proc, thumb and the centring version, since every picture made
  from a summed frame changes.

Two more looks: [`earthsmiled_right_ansa.jpg`](earthsmiled_right_ansa.jpg) (Earth Smiled's right ansa at actual
size, main left and this branch right; the lower pair is the same with the dark end lifted) and
[`enceladus_eclipse_frames.jpg`](enceladus_eclipse_frames.jpg) (three frames of the eclipse movie at half size: main,
this branch, difference x4).
