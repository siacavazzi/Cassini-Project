# Exact speed-ups: evidence

Made 2026-11-16 on the M5 MacBook, main 1a35acb4 against this branch, full inputs (lut8 archive, JAN05 kernels,
cisscal, SPICE and geometry caches).

## The same files, less work (`passes.md`)

Ten passes (455 frames: six movies, two mosaic movies, two mosaics; NAC and WAC, color and grey, a small moon, a ring
pass, a toss-up), each built by `prebuild.py <its phase> --only <the pass's frames> --threads 1` in a process of its
own (`build_each.sh`), once on main and once on this branch, into empty caches. `summary2.py` compares every file the
pass left (tiles, plans, solves, chains, pictures, reports, recovery maps) byte for byte.

- **5,255 files, all identical.**
- Work done, as instructions retired (`/usr/bin/time -l`; CPU seconds move 10 to 20% with the load on a shared Mac,
  this count does not): **13.2% less over the ten passes**, 4.6% to 20.5% per pass. CPU seconds: 1,280 to 1,141.
- Most on the ring mosaic (282RI HIRESAFRG, 20.5%: the ring fit's bins), the small moon's movie (Tarqeq, 18.1%: the
  saturated patches' medians) and the toss-up ring pass (16.1%).

## Each change on its own

Timed alone on a 1,024 px frame (a 3,072 px tile canvas for the channel maximum):

| change | before | after |
|---|---|---|
| `saturated_code`: 529 saturated patches' medians | 542 ms | 0.6 ms |
| `_brightest` against `max(axis=2)` | 72 ms | 8 ms |

`web/test_pass_speedups.py` holds each old form and checks the new one against it to the bit.

## Where these were found

A CPU-time profile of 18 passes on main (2026-11-16): `saturated_code`'s median was 3.7% of movie-pass CPU (14% of the
small moon's), `hdr_map`'s second resampling 4.7%, `_tile_made`'s channel maximum 2 to 3%, and the ring fit's
binning 54% of the ring mosaic.

## With the two other exact fixes (`all_three_together.md`)

This branch, the plan's merges handed on in files and movie pictures read from their twins, merged on one branch
and built the same way: the same 5,255 files, all identical, and **22.8% less work** over the ten passes (10.1% to
35.4% per pass; CPU seconds 1,280 to 952).

## Image benchmark

**PASS (nothing changed): 51 of 51 items identical** to main 1a35acb4 (`image_benchmark_union/report.md`, `summary.json`), run 2026-11-16 on `claude/exact-set-union` (795a49db = main 5d600b52 with the heads of #496 (58502adf), #501 (b487154d) and #502 (01915082) merged in and nothing else), with `CASSINI_HDR_HANDED_DIR` set so #502's files are used.
One run for the three exact PRs.
