# An idle frame server stays small: evidence

Measured 2026-11-17 on the MacBook Pro (M5, 48 GB), every run through the slot limiter and stopped by the tools
when its footprint passed 10 GB, so the runaway under test could not take the Mac's memory. "Footprint" is the
process's physical footprint (`proc_pid_rusage`), sampled every 2 s. No run was sent a request until it was idle.

## The preview's case (its passes are built)

The full-build preview (port 8996 on the Mini) runs code c7d77bc4 on the finished f9ab1b4 cache; both carry the same
versions (obs-v119, thumb-v23). Its twelve highlight mosaic passes, its `thumb-v23` folder (thumbnails 0 to 15 of 27)
and its geometry file were copied read-only to scratch, and c7d77bc4 itself was run on APFS clones of that copy.
"With the fix" is c7d77bc4 plus this branch's change to the two source files.

| | preview's code | the same code with the fix |
|---|---|---|
| idle server, no request | 2.2 GB at 8 s, 5.0 at 26 s, 9.6 at 50 s; **stopped at the 10 GB limit after 52 s, still climbing** | thumbnails done in 10 s, 12 CPU seconds in all, peak 2.0 GB, **flat at 1.53 GB** |
| thumbnail 16, the hexagon turning (193SA NPOLMOV001, mosaic movie, 728 frames) | 10 GB in 50 s, stopped; every stack sample in `_mosaic_at > _make_mosaic > so_far > filter_mosaic` | 2 s, +2 MB |
| thumbnail 19 (251SA NPOLMOV001, mosaic movie, 248 frames) | 181 s, peak 5.6 GB (two minutes of ring fits in `layout`, then the compose) | under a second, +1 MB |
| thumbnails 17, 18, 23, 25 (mosaic passes of 216, 48, 290, 60 frames) | 4 to 10 s each, about 1 GB each | under a second each |
| all 27 from a cache holding none | never finishes (16) | 23 s, peak 2.3 GB, none failed |

`footprint_preview_copy.png` (table: `footprint_preview_copy.md`) is the first row. The preview's cache held
thumbnails 0 to 15 and none after: the warm-up died at 16 on every start and began again at 16 on the next.

The same server with the first cut of this branch (a thumbnail of a pass the cache does not hold draws nothing)
reached the limit in the same 52 s (`runs/f9-after-run`): that cut was not this case.

Also measured, for the preview as it runs today: the old code with thumbnails 16 and 19 already in the cache
(`runs/f9-two-old-run`) makes the other nine itself in 26 s, peak 2.2 GB, flat at 1.80 GB; and what a camera window
asks for when one of the two movies is opened (its kept picture at the first, middle and last frame) is answered
in 0.01 to 1.6 s with the footprint unchanged (1,804 to 1,808 MB).

## A cache that holds no pass (main 02598865, empty cache)

| | main | this branch |
|---|---|---|
| idle server, no request | busy for all 15 minutes of the run: 1,300 CPU seconds, about 1.45 cores, 1.5 to 3.0 GB, planning highlight passes and drawing their tiles | thumbnails done in 37 s (27 made, 0 failed), 41 CPU seconds, peak 2.0 GB, **idle at 1.1 GB** |
| the thumbnails warm-up alone | 20 minutes, peak 3.1 GB; each mosaic highlight's thumbnail is a "mosaic" of the pass's first tile | not run alone; it is inside the 37 s of the row above |

`footprint_main_empty_cache.png` (table: `footprint_main_empty_cache.md`). Here main's cost is work, not memory.

The index warm-ups alone (zip index, `reel.target_of`, `obs_mosaic._observations` and `_row_of`, `warm_prebuild`,
`stacking.load_index`), run as `main` runs them: 1.14 GB in 7 s, then nothing more.

## What the page shows

`thumbnails_all_27.png` (table: `thumbnails_all_27.md`): every thumbnail as the old code made it beside the fix's,
at 256 px. 19 of 27 are the same file byte for byte (colour sets, frames, and passes whose 256 px picture the cache
already held). The other eight are pass pictures now shrunk from the picture the build kept at 512 px:

- 17, 18, 23, 25 (mosaic passes): the same mosaic so far, shrunk from the kept 512 instead of composed again;
- 1, 14, 19 (mosaic movies): the movie's own picture at that frame, the one a window opens on, instead of a mosaic
  of the whole pass composed by the server;
- 16: a thumbnail at all.

`thumbnails_16_19.png`: 16 and 19 before and with the fix, beside two neighbours.

## Page routes after each run

`runs/*/checks.txt`: `/`, `/health`, `/version.json`, `/data/mission.json`, `/data/highlights.json`, three
`/frames/thumb.webp` thumbnails and a frame, each asked once the server was idle: all 200.

## Files

- `runs/<name>/footprint.csv` (seconds, MB, CPU seconds, threads), `result.txt`, `checks.txt`: `f9-before-run`
  (preview's code), `f9-after-run` (first cut), `f9-after2-run` (the fix), `f9-two-old-run` (old code with 16 and 19
  in place, then a window), `before` (main, empty cache), `after-heavy` (first cut), `after-main2` (the fix).
- `runs/f9-parts-*.txt`: each missing thumbnail made alone by the preview's code, with the footprint and what every
  thread was in every 5 s; `f9-parts-after2.txt`: all 27 by the fix; `parts-thumbs*.txt`: main, empty cache.
- `runs/job1.log`, `job2.log`, `job3.log`: the three limiter jobs.
- `tools/`: `idle_watch.py` (starts a server, sends nothing, samples it, stops it at the limit), `idle_parts.py` (one
  warm-up alone, a thumbnail at a time), `idle_chart.py`, `thumb_sheet.py`, and the three job scripts as run.
