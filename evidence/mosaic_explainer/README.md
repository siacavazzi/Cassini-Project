# Mosaic explainer animation

An 82 second film that shows everything the pipeline does to turn 60 raw exposures into one mosaic, on
`ISS_293SA_FAREWELL001_PRIME` (wide-angle camera, 13 September 2017: the Farewell to Saturn mosaic, 12 pointings in
clear, red, green and blue).

![stills](stills_sheet.jpg)

The video itself is not in the repo (project folder: `mosaic_explainer_draft2.mp4`).

## Nothing is re-implemented

`capture.py` saves each stage from the pipeline's own calls; `animate.py` only crops, resizes, cross-fades and labels
those files.

| Chapter | Call | How it is captured |
|---|---|---|
| opening, finished | `obs_mosaic.so_far(..., out=CANVAS)` | the finished mosaic; the outline is the followed frame's own tile outline |
| 01 one raw frame | `label_handler.label(...).export()` read by `data_source.imread` | the archive codes as stored |
| 02 calibrate | `color_image.processed_frame` | run once per step inside `calibration.stepping`, the steps turned on one at a time (fill, calibrate, twohz, dark, pairs, flat, hotpix, skysmooth, stack/hdr, geom); steps that change nothing on this frame are not shown |
| 03 colour | `obs_mosaic.tuned_layout` + `so_far` | the mosaic's own layout with every other pointing hidden (the path Cassini Studio's hidden tiles take): `filter_mosaic` of red, green, blue saved as they return, then the colour picture with `align`, `panels`, `surface` off (SPICE places only) and with everything on |
| 04 all 60 | `color_image.processed_frame` | every frame alone, all steps on; the frame the mosaic leaves out is the one its tile report calls saturated |
| 05 mosaic | `tuned_layout` + `so_far` | the other pointings un-hidden one at a time |
| 06 register | `so_far` inside `calibration.stepping(["panels", "surface", "blend", "level"])` against `["blend", "level"]` | SPICE places only, then registered |
| 07 blend and level | `so_far` with `blend`, `level` off, then `level` off, then everything on | |

`capture.py` also saves the mosaic after each single tile (`grow`) and the whole mosaic's colour steps
(`variants/final_steps`); the film does not use those at the moment.

## Rerun

Private cache and a private copy of the geometry database; through the job limiter. About 5 minutes of one core on the
MacBook from an empty cache (tiles and the 60 growing mosaics 4 min, the rest under a minute), then 2 minutes to draw
the film.

```
python evidence/mosaic_explainer/capture.py W1884003566_6 OUT --cache CACHE \
    --hero W1884008564_1
python evidence/mosaic_explainer/animate.py OUT film.mp4
python evidence/mosaic_explainer/animate.py OUT "still_%s.jpg" --still 40 --still 80    # single frames
```

Made on main e755fd89.
