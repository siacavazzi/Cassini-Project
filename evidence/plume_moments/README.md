# Enceladus plume Moments: evidence

`plume-candidates-sheet.jpg`: the 62 passes scoring 5 or more, ranked by plume score. Left of each pair is the
picture the site shows (the pipeline's processed frame from the full-build preview, normal tone); right is the same
frame as archived, stretched hard. Green passes are at or over the cut (8), red under it. The plumes show at the
normal tone in nearly every green pass, so no tone change is needed.

`passes.csv`: every pass with judged pictures, its score (75th percentile jet score of its judged pictures), the
best frame and its geometry, and whether it became a moment (some green passes on the sheet were already Moments,
and passes with Enceladus under 15 px radius are left out).

How it was made (MacBook, mission kernels, geometry cache `geometry-usgs.sqlite`, archive `cassini_lut8.zip`):

    python web/replay/plume_scan.py --out plume_geometry.jsonl          # ~1 min, 27,316 frames
    python web/replay/plume_measure.py plume_geometry.jsonl --out plume_measured.jsonl --jobs 6   # ~2 min
    python web/replay/plume_moments.py plume_measured.jsonl            # writes web/replay/plume_moments.csv
