# Pass frames merged once (merges handed on in files): evidence

Made 2026-11-16 on the M5 MacBook, main 1a35acb4 against this branch, full inputs (lut8 archive, JAN05 kernels,
cisscal, SPICE and geometry caches).

## The same files, less work (`passes.md`)

Ten passes (455 frames: six movies, two mosaic movies, two mosaics; NAC and WAC, color and grey), each built by
`prebuild.py <its phase> --only <the pass's frames> --threads 1` in a process of its own (`build_each.sh`), once on
main and once on this branch, into empty caches. On this branch the pre-build's own default applies: merges past the
memory's room wait in `<cache>.handed`. `summary2.py` compares every file the pass left byte for byte.

- **5,255 files, all identical.**
- Work done, as instructions retired (`/usr/bin/time -l`; CPU seconds move 10 to 20% with the load on a shared Mac,
  this count does not): **4.9% less over the ten passes**, up to 13.5% (a Jupiter WAC movie: 50 frames, each
  through the WAC's distortion correction twice before). CPU seconds: 1,280 to 1,198.
- Nothing on a pass of 21 frames or fewer (Titan FIRNADCMP, 19 frames: its merges all fit in memory before) and
  little on a pass whose time is elsewhere (the ring mosaic's ring fits, the toss-up's mosaic side).
- `<cache>.handed` is gone when the run ends: each process removes its files as its tiles take them and its folder
  as it ends.

An earlier run of six of these passes, made while the MacBook was swapping, measured 7.5 to 23.5% fewer CPU seconds
(17.7% together). CPU seconds under swap are not a sound measure, so the instruction counts above are the ones to go
by.

## How many frames this reaches (`plan_frames.py`)

Counted over the mission's 12,260 passes with the plan's own rule (every frame of a filter, or `SCALE_FRAMES` spread
over it) and the in-memory hand-over's room (`HANDED_MB` = 128 at 6 MB a 1,024 px frame: a pass's first 21 frames):

| passes | frames | frames their plans read | of those, past the first 21 of their pass |
|---|---|---|---|
| 9,616 movies | 269,131 | 201,344 | 88,273 |
| 2,644 mosaics and mosaic movies | 93,384 | 89,948 | 54,006 |
| all | 362,515 | 291,292 | **142,279** |

So a full build read, calibrated and merged 142,279 frames twice; on this branch it does so once.

## Rebase check

The branch is on main 1a35acb4. It merges with today's main (5d600b52) and with the full-depth calibration
branch (`claude/full-depth-calibration`, 6c3f8a6f) without a conflict (`git merge-tree`), and
`web/test_hdr_hand_on.py` passes on the earlier head of that branch (3529ab73) with this one on top: the change is
in `hand_on` and beside `load_hdr`, not in how a frame is read or calibrated.

## With the two other exact fixes (`all_three_together.md`)

This branch, the six exact speed-ups and movie pictures read from their twins, merged on one branch
and built the same way: the same 5,255 files, all identical, and **22.8% less work** over the ten passes (10.1% to
35.4% per pass; CPU seconds 1,280 to 952).

## Image benchmark

**PASS (nothing changed): 51 of 51 items identical** to main 1a35acb4 (`image_benchmark_union/report.md`, `summary.json`), run 2026-11-16 on `claude/exact-set-union` (795a49db = main 5d600b52 with the heads of #496 (58502adf), #501 (b487154d) and #502 (01915082) merged in and nothing else), with `CASSINI_HDR_HANDED_DIR` set so #502's files are used.
One run for the three exact PRs.
