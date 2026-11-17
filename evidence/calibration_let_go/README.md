# The calibration's kept tables let go once a pass's tiles are made: evidence

Made 2026-11-16 on the M5 MacBook, full inputs.

## What was held (`held_while_composing.txt`, `memplan.py --tm --whole`)

A WAC color mosaic pass (009SA 1X2WPH, 41 tiles, 12 filters) with #520 in, tracemalloc's snapshot at the highest
point of composing its mosaics: of 1,499 MB allocated, 294 MB is the WAC distortion correction's kept plans
(`geometric_correction.py` 187/188), 117 MB the dark model's tables and darks, 88 MB the flat fields: about 0.5 GB
that nothing after the tiles reads.

## This branch alone against main (`passes_this_branch.md`, `by_step_this_branch.log`)

Ten passes (455 frames), each built by `prebuild.py <its phase> --only <its frames> --threads 1` in a process of its
own (`build_each.sh`), into empty caches:

- **5,255 files, all byte-identical** (`summary2.py`).
- Work the same: 16,303 and 16,281 billion instructions (what is made again for the next pass does not show).
- Peak memory of a pass's process: the WAC color mosaic 2,879 to 2,528 MB; the other nine unchanged, because on
  main their highest point is the dark tables' moment in the first second (#520), before any tile.
- The same mosaic by build step (`memtrace.py`): the whole-pass solve peaks at 2,277 MB and composing at 2,048 MB,
  where with #520 alone they peaked at 2,862 and 2,561 MB (`by_step_with_520_only.log`).

## The memory changes together (`passes_memory_set.md`, `peaks.md`, `by_step_memory_set.log`)

`claude/memory-set-union` (84a5b655): main 5d600b52 with #520 (dark tables), this branch and #522 (ring grids, which
brings #496 and #515) merged in, nothing else. The same ten passes:

- **5,255 files, all byte-identical** to main's.
- Peak memory of a pass's process:

| | main | this branch alone | #520 alone | together |
|---|---|---|---|---|
| mean of the ten passes | 2,448 MB | 2,447 | 2,114 | **1,922** |
| highest of the ten | 2,879 MB | 2,642 | 2,948 | **2,107** |

  Every pass is lower than on main, by 117 to 795 MB (`peaks.md`). The mosaic passes, which #520 alone left at up to
  2.9 GB, come down to the movie passes' level: the highest of the ten is 2.1 GB.
- (Work is 17.1% less there, which is #496 and #515, not this.)

## Image benchmark

Queued on the shared MacBook when this was written (51 pictures against 1a35acb4, `web/frames/image_bench.py`). The
report is added to this folder when it finishes.
