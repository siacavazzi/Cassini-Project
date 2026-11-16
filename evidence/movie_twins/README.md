# Movie pictures read from their twins: evidence

Made 2026-11-16 on the M5 MacBook, main 1a35acb4 against this branch, full inputs (lut8 archive, JAN05 kernels,
cisscal, SPICE and geometry caches).

## The same files, less work (`passes.md`)

Six movie passes (260 frames: a small moon, Jupiter WAC, Iapetus in color, a ring movie, Titan, a toss-up ring pass),
each built by `prebuild.py movies --only <the pass's frames> --threads 1` in a process of its own
(`build_each.sh`), once on main and once on this branch, into empty caches. `summary2.py` compares every file the pass
left (tiles, plans, chains, movie frames, planes, evened frames, reports, recovery maps) byte for byte.

- **3,877 files, all identical.**
- Work done, as instructions retired (`/usr/bin/time -l`; CPU seconds move 10 to 20% with the load on a shared Mac,
  this count does not): **9.7% less over the six passes**, 0.1% to 16.7% per pass. The pass with nothing to copy
  (Titan FIRNADCMP: every frame tinted, no gain of 1) costs the same.

## How many pictures are twins (`twin_survey.txt`, `twin_survey.py`)

In main's build of those six passes:

- 180 evened frames have their plain frame kept; 48 have an exposure gain of exactly 1, and all 48 are the plain
  frame's picture, report (with the gain noted) and recovery map to the bit.
- 260 planes have their color frame kept; 192 follow a color frame drawn grey of the same held frame, and all 192 are
  that frame's picture, report and recovery map to the bit.
- No picture that meets a rule differs. (4 evened frames are the plain picture at another gain, by rounding; those
  are drawn as before.)

A wider look before the fix, at nine passes of the profile sample: 100 of 276 evened pictures and 192 of 365 planes.

## With the two other exact fixes (`all_three_together.md`)

This branch, the plan's merges handed on in files and the six exact speed-ups, merged on one branch
and built the same way: the same 5,255 files, all identical, and **22.8% less work** over the ten passes (10.1% to
35.4% per pass; CPU seconds 1,280 to 952).

## Image benchmark

**PASS (nothing changed): 51 of 51 items identical** to main 1a35acb4 (`image_benchmark_union/report.md`, `summary.json`), run 2026-11-16 on `claude/exact-set-union` (795a49db = main 5d600b52 with the heads of #496 (58502adf), #501 (b487154d) and #502 (01915082) merged in and nothing else), with `CASSINI_HDR_HANDED_DIR` set so #502's files are used.
One run for the three exact PRs.
