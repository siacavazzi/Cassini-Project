# Dark-current tables made once, a map at a time: evidence

Made 2026-11-16 on the M5 MacBook, main against this branch, full inputs.

## Where the peak was (`plan_memory_main.log`, `plan_memory_main_traced.log`, `memplan.py`)

A movie pass's plan alone (030RI HIPHAMOVE, 70 frames), the process's physical footprint sampled every 20 ms beside
what every thread is running. On main the footprint goes from 893 MB to 2,158 MB in the plan's first 1.2 seconds, with
both of the plan's reading threads in `dark_current._parameters` at once (`plan_memory_main.log`: "_parameters:334 |
_parameters:334"). tracemalloc at the highest traced point (`plan_memory_main_traced.log`): 537 MB allocated in
`numpy.fft` under `_parameters` line 334 for the spectra, 268 MB for the padded maps, 134 MB each for two whole-cube
copies, all of it twice over (two threads).

## The plan step with the fix (`plan_memory_this_branch.log`)

| | footprint before the plan | highest during the plan |
|---|---|---|
| main | 893 MB | 2,453 MB |
| this branch | 895 MB | **1,792 MB** |

Making the 1,024 line maps on its own (the unit test, tracemalloc): 537 MB at the highest point before, 185 MB now.

## Ten whole passes (`passes.md`, `peaks.md`)

Ten passes (455 frames: six movies, two mosaic movies, two mosaics), each built by
`prebuild.py <its phase> --only <its frames> --threads 1` in a process of its own (`build_each.sh`), on main and on
this branch, into empty caches:

- **5,255 files, all byte-identical** (`summary2.py`).
- Work unchanged: 16,303 and 16,305 billion instructions.
- **Peak memory of a pass's process** (`/usr/bin/time -l`, peak memory footprint): 2,448 MB on average on main,
  **2,114 MB** on this branch, 334 MB less. Eight of the ten passes peak 91 to 760 MB lower. Two do not (030RI
  HIPHAMOVE -76 MB, 009SA 1X2WPH +69 MB, both inside the run-to-run spread): with the tables' moment gone, their
  highest point is at another step, which this does not touch.
- For the spread: the same passes built on three other branches that do not touch this code (`peaks.md`) average
  2,445 to 2,505 MB, and one pass's peak moves by up to 500 MB between such runs, since on main it depends on whether
  the two threads happen to make the tables at the same moment.

## Image benchmark

Queued on the shared MacBook when this was written (51 pictures against 1a35acb4, `web/frames/image_bench.py`). The
report is added to this folder when it finishes.
