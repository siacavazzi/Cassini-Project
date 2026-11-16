# Wide-angle filter offsets (pipeline audit, finding 7)

Measured 2026-11-16 on the full cache `cache-full-f9ab1b4` by the pipeline audit thread. Handed over: the table and
its use in `color_image.spice_offsets` are on this branch, with the version bumps. **No before/after renders, no
test and no image benchmark have been run yet.**

## What was measured

For every channel of a centered color set that the pipeline matched by phase correlation, the match (the report's
`phase dx,dy`) less SPICE's offset between the two frames (geometry cache `target.x, y` of the reference minus the
channel's, a WAC frame's grown by its geometric correction). One offset per filter fitted to them all.

| file | what |
|---|---|
| `colour_sets_f9ab1b4.json.gz` | every centered color set's report from the cache (34,311 sets: name, grey, grey_moved, aligned, calibrated, dropped, centred, stacked), made on the Mini by `list_colour_sets.py` |
| `fit.py`, `fit.txt` | the fit on full resolution WAC frames (14,894 matches), the held-out check and the fit by era; `table.json` holds the offsets |
| `fit_all_modes.py`, `fit_all_modes.txt` | the same with summed frames in: SUM4 gives another pattern, because of the next line |
| `summed_lock.py`, `summed_lock.txt` | SUM4 sets' channel shifts lock to whole camera pixels (90% within a tenth of one; 20% if evenly spread): the frames are enlarged by repeating pixels before they are matched |
| `by_filter_pair.py`, `by_filter_pair.txt` | the raw medians per filter pair, WAC and NAC (NAC between JPL-corrected frames only) |
| `spice_vs_match.py`, `spice_vs_match.txt` | SPICE against the picture match by camera and pointing source |
| `audit_labels_scan.py`, `audit_labels_sqlite.py` | make `labels.sqlite` (every label of the archive), which the scripts read |
| `audit_smithed_list.py` | lists the frames with JPL's per-image pointing (`*_ISS.bc` coverage) |

The scripts read their inputs from `~/cassini-build/audit/out/` on the M5 MacBook (`labels.sqlite`,
`geometry-audit.sqlite` = a copy of `inputs/geometry-usgs.sqlite`, `smithed_frames.txt`, `cache_colour_sets.json`).

## Result

Offsets relative to CL1/GRN, in full resolution px of the frame as drawn (x, y):

| filter | offset | matches |
|---|---|---|
| RED | (+2.03, +1.16) | 6,301 |
| BL1 | (+2.10, -1.35) | 3,301 |
| VIO | (+2.16, -1.75) | 1,588 |
| IR1 | (+2.13, +1.35) | 519 |
| CB2 | (+2.42, -0.85) | 5,667 |
| MT2 | (+2.51, -0.32) | 2,717 |
| CB3 | (+2.79, -0.65) | 1,069 |
| MT3 | (+3.08, -0.11) | 1,010 |
| IR2/IR1 | (+0.44, -0.06) | 244 |

Held-out sets: SPICE's offset is a median 2.36 px from the picture match without the table and 1.25 px with it;
0.37 px on the 2000-2001 Jupiter frames, whose pointing JPL corrected. RED and BL1 hold to 0.3 px from 2000 to 2017.
Refitted by era on full resolution frames only (`era_full_frames.py`, `era_full_frames.txt`; the era rows in
`fit.txt` mixed in summed frames, whose matches lock to whole camera pixels): RED and BL1 stay within 0.2 px of the
table in every era. CB2, MT2, MT3 and CB3 differ by 0.5 to 0.7 px in 2009-2017 (CB3 1.5 px on 122 matches), but a
table fitted to each era lines SPICE up only 0.04 to 0.07 px better (median) than the one table, so there is one table.

## Open points for whoever takes this on

- Mosaic and movie tiles of different filters are also placed by SPICE before they are registered
  (`obs_mosaic._register`); the same table belongs there.
- SUM4 color sets are registered only to whole camera pixels (`summed_lock.txt`). Enlarging summed frames smoothly
  for the alignment guide, or matching at the camera's own size, would fix that; it is a separate change.
- The offsets with the "geom" step off were not measured (the shift at the frame's middle differs by under 0.1 px).
- The version numbers taken here (color-v59/v42/v37, thumb-v24, reel-v97/v80/v74, export-v104, levels-v66) are
  numbered past PRs 480 to 484 as they stood at 06:15Z on 11-16; check them against main when this lands.
