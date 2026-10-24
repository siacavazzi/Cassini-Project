# Color investigation: composites and mosaics (2026-10-22)

Investigation only: no repo changes. I worked in a detached worktree of origin/main at fc0fecb (`/Volumes/LaCie/claude_scratch_spk/color-investigation/wt`). Every render goes through the pipeline's own calibration, stacking and alignment. The single composites are `frame_server.composite` with the pipeline's aligned I/F captured. The mosaics are `obs_mosaic.so_far` with `mosaic.match_gains`/`match_offsets` instrumented. Scratch caches are under `.../color-investigation/cache`. The live cache was read only.

## Bottom line

1. **Calibration is not the problem.** All 6,091 composites the live server has made are calibrated. In a mission-wide sample, 99.5% of color frames calibrate. The only failures are 8LSB frames, and when one channel fails the whole composite falls back to the min-max stretch (Phoebe 2004-06-11 NAC: every BL1 frame is 8LSB).
2. **Single composites have plausible ratios but are under-saturated and shifted toward yellow-green compared with NASA.** CURRENT hue is 52-72° against NASA's 40-44°, and saturation is 0.07-0.18 against 0.17-0.35. There are three causes:
   - **No color matrix.** RED/GRN/BL1 are not sRGB primaries. Adding the 3x3 matrix (V3/V4) moves the hue to within about 1° of NASA's on 6 of 8 references.
   - **White comes from one pixel.** White is the single brightest 3x3-median pixel, so one bright ring ansa or limb makes the whole body dim and grey. Example: PIA21889's Saturn limb, where CURRENT has saturation 0.08 and lightness 0.62 and V2 (white at p99.5) has 0.35 and 0.88. NASA's is 0.55 and 0.83.
   - **The "black" is the sky's noise width, not its offset.** The per-channel black is the sky's 98th percentile. Sky median I/F is only 0.1-1.3% of white, while p98 minus median is 1-3.4% of white. That width is largest in RED (exposure and noise), so CURRENT removes more red than blue. Gamma 1/2.2 magnifies this in dim areas, giving blue limbs and terminators and a desaturated body. Flagged Titan N1884017786: noise width is 3.4% of white in RED against 1.2% in BL1.
   - **A single common black (V1) is not the fix.** It tints the sky (Rhea PIA06578: red sky in V2, blue in V4) and shows tile outlines in mosaics. The per-channel sky offsets are real, so subtract each channel's sky median and then one shared noise margin.
3. **Mosaics have three serious color bugs, larger than anything in the single composites:**
   - **Gain collapse.** `mosaic.compose(calibrated=True, pin=None)`: with nothing pinned, the least-squares gain solve shrinks every gain until the 1/1.1 clip stops it (the 1e-4 prior toward 1 is too weak). The flagged Saturn pass ISS_198SA has 36 of 36 color-tile gains at 0.909. Saturn's Shadow has 49 of 75 clipped, and the rest sit at 0.92-1.1. Where filters at the same place land on different sides of the clip, the color shifts. In Saturn's Shadow the gains for one place differ by up to 0.19, which is the whole clip range.
   - **Offsets at their limit, solved per filter.** 9 of 75 offsets in Saturn's Shadow and 9 of 13 in Rhea HIGHRES are at the ±6-level clip. The offsets differ between filters (ISS_198SA: GRN +6, -3.4, +3.3 against RED within ±2), and gamma 3 shows them as colored rectangles in the faint sky. This is the flagged W1760119558 "some off colors".
   - **"Filled" passes stretch each filter on its own.** These use per-filter black = 1st percentile and white = 99.5th percentile, gamma 1.5, then `detail()` x2. In the live cache, 473 of 558 plans are filled. Where the body is bright and fills the frame, black/white goes above 1: Rhea 049 HIGHRES has IR1 1.51, GRN 1.44, UV3 0.91, and Saturn 003 WINDS has CB2 1.85. Each channel becomes its own contrast stretch, so the color is the difference between per-filter stretches. `detail()` then turns the filter-to-filter misregistration (tiles are placed by SPICE per filter, with no cross-filter registration) into rainbow texture. This is the "pixel range looks pretty stretched" look.
4. **Example of a single-pass color error.** In Rhea 102 GEOLOG002 (RED/GRN/BL1, filled), GRN's black is 0.001×white while RED's and BL1's are 0.035-0.040. Worse, GRN's 4 tiles are solved to gains 0.909-1.1 and offsets ±6, while RED and BL1 have one tile each at gain 1. The result is a pink Rhea (hue 354°). Forcing GRN's gains onto all filters gives hue 38°.

## 1. Census

**1a. Composite reports (live cache color-v4).** 6,091 unique composites: 1,857 three-channel and 4,234 two-channel. All have `calibrated: true`. None have alignment `failed`. Alignment methods: phase 4,370, edges 257, centroid 81, "not aligned" 3,240 (that is, a channel left unshifted). There are no uncalibrated ids to list.

**1b. Observation-mosaic plans (live obs-v9).** 558 plans: 473 filled (gamma 1.5) and 85 not (gamma 3.0).
- Color triplets: 396 grey (no color), RED/GRN/BL1 44, CB3/MT2/MT1 32, CB3/MT2/GRN 31, IR1/GRN/UV3 20, IR3/GRN/UV3 10, CB2/CB1/BL1 5, and others. 80 have GRN in the middle.
- Spread of the color filters' blacks as a fraction of white:

| Plans | n | Median | p90 | Max |
|---|---|---|---|---|
| All | 162 | 0.0074 | 0.229 | 1.40 |
| Filled | 123 | 0.009 | 0.251 | 1.40 |
| Not filled | 39 | 0.0017 | 0.036 | 0.45 |

- Worst cases: Saturn 003 WINDS004-006, Rhea 049 HIGHRES001 passes 0-3, Saturn 048 STRMOVIEC001, Saturn 045RG GPHOT5DEG001 (white only 1e-4). Full list: `1b_plans.json`.

**1c. Calibratability (3,000 random non-clear frames, seed 1).** 14 failures (0.47%), all `DATA_CONVERSION_TYPE 8LSB`. No missing filter pairs and no gain or mode failures. By conversion: TABLE 0/1653, 12BIT 0/1333, 8LSB 14/14. By camera: NAC 0.4%, WAC 0.6%. By year: failures only in 1999 (1/3), 2003 (1/35), 2005 (1/238), 2006 (6/268) and 2007 (5/397). Every other year is 0. Details: `1c_summary.json`.

**1d. Flags (`index.jsonl`, 6 entries).** Two mention color:
- 20261022-110608 N1575364115_1: NAC camera window, false-color composite, "color frames misaligned".
- 20261022-111109 W1760119558_1: WAC camera window, true-color pass mosaic ISS_198SA_SATURN001, "some off colors and slightly misaligned frame stacks".

Two more are relevant:
- 20261022-112845 N1884017786_1: Titan body window, true-color composite, "pixel range looks pretty stretched".
- 20261022-112717 W1884011258_5: Saturn body window, pass mosaic, "mosaic could use some improvements".

## 2. Single composites (task2/)

These are the I/F ratios of the body median. `pc` means after per-channel blacks and `1` means after one black. "Blk diff/w" is the largest difference between channel blacks over white. CURRENT and V4 are the mean displayed RGB of the body.

| Set | Blk diff/w | R/G | B/G | R/G pc | B/G pc | R/G 1 | B/G 1 | CURRENT RGB | V4 RGB |
|---|---|---|---|---|---|---|---|---|---|
| Saturn 2004 NAC (rings) | 0.010 | 1.110 | 0.680 | 1.105 | 0.679 | 1.115 | 0.664 | 184,175,146 | 193,174,143 |
| Saturn 2016 WAC (rings) | 0.014 | 1.069 | 0.685 | 1.052 | 0.674 | 1.075 | 0.660 | 184,178,148 | 196,179,144 |
| Saturn 2011 WAC | 0.008 | 1.077 | 0.699 | | | | | 191,186,158 | 200,185,153 |
| Titan 2010 NAC | 0.012 | 1.225 | 0.568 | | | | | 208,191,147 | 215,183,138 |
| Titan 2008 WAC | 0.003 | 1.141 | 0.683 | | | | | 199,187,157 | 206,185,152 |
| Titan flagged N1884017786 | 0.025 | 1.189 | 0.553 | 1.178 | 0.548 | 1.200 | 0.525 | 205,191,146 | 213,183,135 |
| Enceladus 2008 | 0.002 | 1.041 | 0.981 | | | | | 187,180,181 | 191,182,186 |
| Mimas 2008 | 0.006 | 1.040 | 0.921 | | | | | 180,176,169 | 190,185,178 |
| Dione 2007 | 0.004 | 1.007 | 0.959 | | | | | 204,203,199 | 223,221,216 |
| Rhea 2005 | 0.001 | 1.026 | 0.913 | | | | | 210,207,199 | 224,218,210 |
| Tethys 2015 | 0.009 | 1.021 | 0.970 | | | | | 211,207,204 | 217,211,211 |
| Iapetus 2004 (leading, dark) | 0.007 | 1.123 | 0.850 | | | | | 139,133,123 | 192,177,165 |
| Iapetus 2007 flyby | 0.004 | 1.046 | 0.917 | | | | | 170,166,159 | 183,177,171 |
| Hyperion 2011 | 0.003 | 1.104 | 0.863 | | | | | 193,183,172 | 205,190,180 |
| Phoebe 2004 WAC | 0.002 | 0.946 | 0.926 | | | | | | |
| Jupiter 2000 WAC BL1 | 0.002 | 0.987 | 0.803 | | | | | 198,201,186 | 203,202,183 |
| Jupiter 2000 WAC VIO | 0.005 | 0.988 | 0.704 | | | | | 198,199,174 | 204,201,180 |

Phoebe 2004 NAC: both sets fell back to stretched frames, because the BL1 frame is 8LSB. The full per-set numbers are in `task2_diagnostics.json`, including `sky_median`/`sky_p98` per channel, the blacks, V1/V2 white, and displayed HSL for every variant.

Observations:
- Over the bodies, the ratios barely depend on per-channel versus one black (under 2%). The black choice matters in dim areas (limb, terminator, haze, sky) through gamma, and that is where the blue rims come from.
- V2 brightens anything whose white was set by rings or a bright point.
- V3/V4 warm Saturn and Titan, and neutral moons stay neutral.
- The Iapetus leading face goes from muddy grey (CURRENT, lightness 0.52) to tan.
- WAC limbs of Saturn show cyan and red fringes from inter-filter parallax and misregistration (PIA14910 set).

## 3. NASA references (task3/)

Every caption and image was downloaded from photojournal / assets.science.nasa.gov. Body mean color is hue/saturation/lightness.

| PIA | Our frames | NASA note | NASA | CURRENT | V2 | V4 |
|---|---|---|---|---|---|---|
| PIA06081 Titan 2004-06-10 NAC | N1465568061/N1465567453/N1465568087 | natural | 40/0.35/0.43 | 45/0.18/0.55 | 44/0.18/0.55 | 37/0.24/0.55 |
| PIA14910 Titan+Dione 2011-05-21 NAC | N1684686374/408/443 (different framing) | natural | 43/0.33/0.56 | 56/0.09/0.50 | 54/0.18/0.65 | 44/0.24/0.65 |
| PIA14912 Titan+Dione 2011-11-06 WAC | W1699282076/109/142 | Titan brightened x1.6, contrast-enhanced | 44/0.11/0.56 | 72/0.10/0.60 | 73/0.11/0.61 | 58/0.12/0.60 |
| PIA09906 Saturn 2008-04-15 WAC | W1586957906/873/840 | natural | 43/0.17/0.52 | 52/0.07/0.48 | 53/0.15/0.62 | 44/0.21/0.64 |
| PIA21889 Saturn limb + Enceladus 2017-09-13 NAC | N1884015292/352/413 | natural | 54/0.55/0.83 | 54/0.08/0.62 | 53/0.35/0.88 | 44/0.46/0.88 |
| PIA06578 Rhea 2005-01-16 NAC | N1484528640/657/674 | contrast-enhanced | 11/0.02/0.60 | 47/0.09/0.74 | 12/0.13/0.78 (sky tint) | 355/0.13/0.79 (sky tint) |
| PIA10478 Mimas 2007-09-04 NAC | OPNAV N1567640113/149/186, aimed at Enceladus: an uncertain match | natural | 35/0.22/0.59 | 44/0.11/0.43 | 42/0.30/0.72 | 34/0.35/0.72 |
| PIA08938 Dione 2007-04-08 NAC | N1554736938/717/883 | natural | 43/0.02/0.52 | 43/0.04/0.61 | 48/0.04/0.66 | 35/0.06/0.67 |
| PIA08329 Saturn's Shadow 2006-09-15 WAC mosaic | ISS_028RI_HIPHWAC001 (task4) | UV/IR/clear "adjusted to resemble natural color" (also a greatly exaggerated version) | 14/0.08/0.29 | 249/0.015/0.21 | gamma 2.2: 78/0.03/0.19 | all three: 11/0.025/0.19 |

V4 has the closest hue in 6 of 8. Every CURRENT is less saturated than NASA's. The PIA08329 comparison is `task3/PIA08329_montage.jpg`. Our version shows tile-shaped tints in the sky and a greenish disk.

## 4. Mosaics (task4/)

Each render is `obs_mosaic.so_far` at the last tile. Variants: CURRENT; one black for all color filters (the mean); gamma 2.2; gains forced equal across filters (the middle filter's gain at the nearest place); and all three combined.

| Pass | Tiles | Color | Gamma | Black/white per filter | Gains clipped | Offsets at ±6 | Largest gain gap at one place |
|---|---|---|---|---|---|---|---|
| Saturn's Shadow 028RI HIPHWAC001 W | 75 | IR3/CL/VIO | 3.0 | .0037/.0008/.0035 | 49/75 | 9/75 | 0.19 |
| Titan 046TI MEDRES001 W (filled) | 26 (5 color placed) | IR1/GRN/BL1 | 1.5 | .0047/.0002/.0011 | 0/5 | 0/5 | 0.013 |
| Rhea 102RH GEOLOG002 N pass 1 (filled) | 21 (6 color placed) | RED/GRN/BL1 | 1.5 | .040/.001/.035 | 2/6 (GRN 0.909/1.1) | 3/6 | 0.091 |
| Rhea 049RH HIGHRES001 N pass 1 (filled) | 17 | IR1/GRN/UV3 | 1.5 | 1.51/1.44/0.91 | 9/13 | 9/13 | 0.14 |
| Saturn 198SA SATURN001 W (flagged) | 48 | RED/GRN/BL1 | 3.0 | .0016/.0011/.0008 | 36/36, all at 0.909 | 1/36 | 0 (all collapsed) |

Lit-area mean hue/saturation, CURRENT → equal gains → all three:

| Pass | CURRENT | Equal gains | All three |
|---|---|---|---|
| Saturn's Shadow | 250°/0.015 | 249°/0.015 | 11°/0.025 |
| Rhea 102 | 354°/0.10 (pink) | 38°/0.08 | 15°/0.08 |
| Rhea 049 HIGHRES | 66°/0.15 | 48°/0.14 | — |
| Titan | 45°/0.42 | 44°/0.42 | 44°/0.43 |
| Saturn 198 | 45°/0.07 | 45°/0.07 | 47°/0.10 |

- In Rhea 049 HIGHRES, one black wipes out UV3, because its black was set at 0.91×white and the others are higher.
- In the Titan and Saturn's Shadow passes, one black lifts one filter's sky and the tile outlines show. Per-filter sky offsets must stay.

## Suggested direction (for a later PR, not done here)

1. **Composites.** Black per channel = the sky median (the offset), plus one shared noise margin (for example, the largest channel's p98 minus median). White = p99.5 of the lit pixels of the brightest channel, not the single brightest pixel. Apply a per-camera RGB matrix (the NAC/WAC matrices tested here) for true-color sets, and use the sRGB curve. Leave false-color sets unmatrixed.
2. **Mosaics, gain solve.** Fix the gain collapse: pin the mean log-gain to 0 (a constraint, not a 1e-4 prior), or pin the best-connected tile. Solve gains and offsets once per place, on luminance or on the middle filter, and apply the same correction to every filter's tile at that place.
3. **Mosaics, filled passes.** Drop the per-filter 1st/99.5th percentile stretch. Use one black (the sky offset, or 0) and one white for all filters, a gentler gamma, and leave color to the matrix. Apply `detail()` to luminance only, after cross-filter registration of tiles at the same place, so misregistration is not amplified into color noise.
4. **8LSB fallback.** When one channel is 8LSB, calibrate the others and scale the 8LSB channel by matching its body median to an estimate, or drop it to two-filter color, rather than stretching every channel.

## Files

Everything is in `~/Documents/color-investigation/`. Originals and full-resolution PNGs are at `/Volumes/LaCie/claude_scratch_spk/color-investigation/out`.
- `task2/*_montage.jpg` (CURRENT | V1 | V2 | V3 | V4), `task2/*_{CURRENT,V1..V4}.jpg` (1024 px), `task2/task2_diagnostics.json`
- `task3/PIA*_montage.jpg` (NASA | CURRENT | V2 | V4), `task3/PIA*_variants.jpg`, `task3/task3_diagnostics.json`, `task3/PIA08329_stats.json`
- `task4/*_montage.jpg`, `task4/*_{variant}.jpg` (1024 px), `task4/*.json` (plan, gains and offsets per filter and tile, colour stats)
- `census_abd.json`, `1b_plans.json`, `1c_summary.json`, `sets_candidates.json`
