# Wide-angle pixel scale in the km/px label, the movie editor and the coverage maps

2026-11-16, pipeline audit thread, on top of PR 500 (`claude/km-per-px`, 43736d06).

## Why 5.9715e-5 and not the kernel's value

A wide-angle frame is drawn after CISSCAL's geometric correction (`geometric_correction.py`, the "geom" step), which
resamples every filter's frame onto a pinhole camera of one focal length, `F_LINEAR` = 200.956 mm. A 12 micron pixel
over that is 5.9715e-5 rad. That is the scale `obs_mosaic.IFOV["W"]` has, and the one `bootleg_autonav.linear_ratio`
grows SPICE's shifts to (SPICE works them out at the instrument kernel's 200.77 mm, 5.9770e-5 rad, which is the
uncorrected frame's). The narrow-angle camera has no such correction, so the kernel's 2003.44 mm is right there.

The three places PR 500 touches had 5.9907e-5 (`export_tracks.py`, `movieedit.html`) and 59.9e-6
(`build_coverage.py`), 0.32% and 0.31% above the frames as drawn.

## What changes

No picture changes. The label and the editor's radius do, by 0.32%:

| frame (wide-angle) | km/px before | km/px after | body radius in the editor before, px | after, px |
|---|---|---|---|---|
| Titan, 24,031 km (PR 500's test case) | 1.285 | 1.281 | 1788.7 | 1794.4 |
| Rhea, 60,000 km | 3.549 | 3.537 | 212.5 | 213.2 |
| Saturn, 1,200,000 km | 68.400 | 68.181 | 810.0 | 812.6 |
| Saturn, 2,500,000 km, 2x2 summed | 292.558 | 291.620 | 388.8 | 390.1 |

(`export_tracks.ground_range` on the axis through the body's center; the page shows two decimals under 10 km/px and
whole numbers above.)

## A check on real limbs

`audit_limb_scale.py` measures the scale on whole-disk frames of Rhea and Dione as the pipeline draws them: the lit
limb found along rays to a fraction of a pixel, a circle fitted with its center free (so pointing does not matter),
against the limb's angular size from SPICE (the body's own radii seen from Cassini). `limb.jsonl` has every frame,
`audit_limb_fit.py` the fit, `wac_scale_on_limbs.png` the picture.

Wide-angle, 60 frames kept (limb radius 74 to 262 px), a line fitted to measured radius against angular size:

| scale | rad/px | from the fit (5.9762e-5 +- 0.0031e-5) |
|---|---|---|
| the label before | 5.9907e-5 | 4.7 sigma off |
| as drawn, F_LINEAR (this PR) | 5.9715e-5 | 1.5 sigma |
| kernel, uncorrected frame | 5.9770e-5 | 0.3 sigma |

So the old label value is ruled out by the frames themselves. The measurement cannot tell the other two apart (they
differ by 0.09%, a quarter of a pixel on the largest disk here), so the choice between them rests on the code: the
frames are resampled to F_LINEAR.

The same measurement on the narrow-angle camera (33 frames kept) scatters by 0.5 px and lands 0.3% from every
candidate, the calibrated focal length in the literature included, so it is not used as evidence for anything.
