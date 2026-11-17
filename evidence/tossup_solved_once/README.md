# Toss-up movie passes solved once: evidence

Made 2026-11-16, main 1a35acb4 against this branch (4903d669; the commits after it change a comment, a test and
this folder), full inputs. Two toss-up passes that play as movies, each built by
`prebuild.py movies --only <its frames> --threads 1` in a process of its own (`scripts/build_each.sh`), once on main
and once on this branch, into empty caches:

- a ring pass, 108RI MNRNGSHAD005 (`SATURN_ISS_108RI_MNRNGSHAD005_PRIME_N_0`, 29 frames), on the Mac Mini and again
  on the MacBook (the same names and numbers on both);
- a moon, Enceladus 088EN SECLNX001 (`ENCELADUS_ISS_088EN_SECLNX001_CIRS_N_1`, 22 frames), on the MacBook.

## What a server finds (`served_*.txt`, `scripts/tossup_check.py`)

A fresh process, as a server is, asked at each frame which mosaic-so-far picture it wants and whether the build made
it:

| pass | main: found pre-built | this branch |
|---|---|---|
| 108RI ring pass | 10 of 29 (19 drawn on request) | **29 of 29** |
| Enceladus 088EN | 8 of 22 (14 drawn on request) | **22 of 22** |

## Why the views change, the finished one too

Confirmed from the two builds' files and by replaying main's order; nothing here is a guess.

**The growing mosaic keeps each tile where it was first drawn.** `obs_mosaic._grown` makes a filter's mosaic of N
tiles from its mosaic of N - 1 "as it was drawn, with the newest composed over it ... what is drawn stays as it was
drawn". Those grown pictures are kept by tile count (`filters-level/<filter>-<N>-<view>-<tags>.png`), not by the
solve they were drawn under. On main a toss-up's mosaic grows a frame at a time, each frame solved on the tiles so
far, so each tile is baked into the picture where *that* solve put it. Later solves move it in the layout (and in
the picture's name), never in the picture.

**Enceladus 088EN** (`enceladus_088en/`):

- The two builds' solve files are identical (`solve_diff.txt`: `surface7-global2-panels2-plan4.json`, 22 tiles, the
  same 14 moves), and a fresh server lays every tile out at the same place in both, to 0.00 px, at frame 11 and at
  frame 22. Their mosaic pictures have the same names. So nothing moves in the solve.
- `replay_main_order.txt`: main's frame-by-frame order replayed on a clone of its cache (its kept solves and mosaics
  removed, its tiles kept). The replay gives the very picture names main's build left (22 of 22). In it, 14 of the 22
  tiles are first drawn somewhere else than the whole pass's solve puts them, up to 13.8 px of a frame, **5.1 px of
  the 1,024 px view** (tile 7: +4.46, +2.47 px; tile 9: +4.19, +1.32; tile 8: -3.02, -0.83).
- So main's finished mosaic view is not drawn where its own kept solve says: 14 tiles sit where 14 earlier, smaller
  solves put them. On this branch every tile is drawn where the kept solve puts it.
- The frames of this pass are full of single black pixels (lost in compression), so a tile drawn a few pixels
  elsewhere changes a large share of pixels by a lot while the picture looks the same.

**108RI ring pass** (`ring_108ri/`):

- The same baking: in the replay 18 of 29 tiles are first drawn off the whole pass's place, here by at most 0.59 px
  of the 1,024 px view (the view is 0.06 px a frame pixel). (The ring replay reproduces 22 of main's 29 picture
  names; the Enceladus one all of them.)
- And the ring registration. `ring_moves` makes its reference ring profile once, from the first tiles it sees, and
  keeps each tile's answer. Grown a frame at a time, the reference comes from the first few tiles (167 radius bins);
  this pass scans across the rings, so 25 of 29 tiles share too few bins to be matched (kept as "no match", score
  -1) and one is moved. Solved first, the reference is made from all tiles (427 bins): 24 of 29 are matched (0.89
  to 1.0) and 12 moved, by up to 31 px of a frame (about 2 px of the view). Each tile's rings are redrawn by its fit,
  which is where most of this pass's pixel change comes from; the solve's own moves differ by at most 0.43 px of the
  view (`solve_diff.txt`).

## Which is right

The new views: each tile is drawn where the pass's kept solve puts it, which is also where everything else that
reads the layout (the picture's name, the tile map under the cursor) takes it to be, and where a mosaic pass's tiles
have been drawn since #459 solved those first. The old views mix the places of as many partial solves as the pass
has frames, and depend on the order of building.

By eye the two are the same picture (`before_after.png` of each pass, `closeup.png`, the full-size crops). By the
repo's own seam measure (`web/frames/seam_bench.py`: the brightness step across the tiles' edges against the same
away from them, on the full-size view; near 1 = seams no more visible than the picture's texture;
`scripts/seam_views.py`, `seams.json`) they are equal within 3%, but for Enceladus' frame 11, 8% better:

| view | seam95 / flat95, main | this branch |
|---|---|---|
| ring, frame 12 | 2.098 | 2.128 |
| ring, frame 18 | 0.979 | 0.997 |
| ring, frame 24 | 0.885 | 0.904 |
| ring, frame 29 (finished) | 0.914 | 0.921 |
| Enceladus, frame 11 | 1.142 | 1.047 |
| Enceladus, frame 22 (finished) | 1.168 | 1.201 |

So this is a change for the picture agreeing with its solve and for the server finding it made, not one that makes
seams visibly better or worse.

## The benchmark's "light now black" guard

With the toss-up items of #509 the image benchmark flags four of the six changed views: light in main's picture
that is black in this branch's (0.2 to 2.1% of the lit area). Counted both ways on the full-size views
(`seams.json`: pixels above level 8 in one build and not in the other), it is the same light landing a few pixels
elsewhere, not light lost:

| view | lit pixels, main | this branch | lit only in main | lit only in this branch |
|---|---|---|---|---|
| ring, frame 12 | 30,241 | 30,081 | 989 | 829 |
| ring, frame 18 | 99,139 | 99,099 | 1,065 | 1,025 |
| ring, frame 24 | 163,748 | 163,643 | 1,236 | 1,131 |
| ring, frame 29 | 215,826 | 215,740 | 1,439 | 1,353 |
| Enceladus, frame 11 | 778,897 | 781,579 | 44,822 | 47,504 |
| Enceladus, frame 22 | 959,234 | 963,276 | 85,316 | 89,358 |

On the ring pass it is the tiles' edges; on Enceladus mostly the frames' own black pixels, which move with their
tile. `benchmark_items/` has that run's rows and sheets (main 1a35acb4 against 65ff83eb, #509's tool in a root of
its own): every movie frame and evened frame of both passes identical (58 of 62 and 22 of 24 pictures), the six
mosaic views changed.

## How far the pixels move (`before_after.json`, at 1,024 px)

| view | pixels that differ | by more than 8 levels | mean difference, levels |
|---|---|---|---|
| ring, frame 12 (of 770,048 px) | 8,286 | 3,356 | 0.13 |
| ring, frame 18 | 24,370 | 5,649 | 0.24 |
| ring, frame 24 | 38,521 | 6,104 | 0.29 |
| ring, frame 29 (finished) | 49,774 | 6,679 | 0.34 |
| Enceladus, frame 5 (of 862,208 px) | 0 | 0 | 0 |
| Enceladus, frame 11 | 214,150 | 111,982 | 5.49 |
| Enceladus, frame 17 | 284,035 | 126,258 | 4.87 |
| Enceladus, frame 22 (finished) | 315,706 | 114,321 | 4.12 |

## Everything else of the pass is the same

Compared file by file, the two builds' movie frames (435 files on the ring pass, 264 on Enceladus), tiles (145 and
95, the redrawn ones among them), plan, movie footprint, stabilization chain and exposure chain are byte-identical.
What differs is the mosaic pictures, the grown filter mosaics they are drawn from, on the ring pass the solve and
ring files, and on Enceladus `under1-CL1_CL2.json` (each tile's brightness against the picture before it, measured
where the tile was at the time; no tile changes sides of its threshold).

## Build time

Not a speed-up. Instructions retired for the ring pass (`/usr/bin/time -l`): 2,104 billion on main, 2,218 billion on
this branch (+5.4%): the partial solves at every frame are gone, one whole solve with every tile's ring fit takes
their place.

## How many passes

605 passes are toss-ups that play as a movie (21,851 frames; counted from the pass list, 2026-11-16): 454 of
Saturn, 100 of Titan, 17 of Jupiter, 16 of Enceladus, 18 of other moons and the Sun.

## Image benchmark

The 51-picture set (`web/frames/image_bench.py`): **PASS (nothing changed): 51 of 51 items identical** to main 1a35acb4 on this branch at 721736e1 (`image_benchmark/report.md`, `summary.json`; run 2026-11-16). As expected, since the set holds no toss-up's mosaic view: it shows nothing else moved. The views this change does move are #509's two items, run above.
