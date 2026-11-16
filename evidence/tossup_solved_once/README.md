# Toss-up movie passes solved once: evidence

Made 2026-11-16 on the Mac Mini, main 1a35acb4 against this branch's first commit (4903d669; the commit after it
changes a comment and a test), full inputs. One toss-up pass that plays as a movie, a ring pass of 29 frames
(108RI MNRNGSHAD005, `SATURN_ISS_108RI_MNRNGSHAD005_PRIME_N_0`), built by
`prebuild.py movies --only <its frames> --threads 1` in a process of its own (`build_each.sh`), once on main and once
on this branch, into empty caches.

## What a server finds (`served_main.txt`, `served_fix.txt`, `tossup_check.py`)

A fresh process, as a server is, asked at each frame which mosaic-so-far picture it wants and whether the build made
it:

| build | pictures the server asks for that the build made | not made (drawn on request) |
|---|---|---|
| main | 10 of 29 | 19 |
| this branch | **29 of 29** | 0 |

Main's build did make 22 mosaic pictures at 1,024 px for this pass, but named after the partial solves they were
drawn from, so only 10 of the 29 frames find theirs.

## The pictures change slightly (`before_after.png`, `before_after.json`, `tossup_sheet.py`)

`before_after.png`: the mosaic view at four frames. Left, what a server shows today on main's cache (drawn on request
where the build's picture is not the one asked for); middle, what this branch pre-built; right, the difference times
eight.

| frame | pixels that differ (of 770,048) | by more than 8 levels | mean difference, levels |
|---|---|---|---|
| 12 | 8,286 | 3,356 | 0.13 |
| 18 | 24,370 | 5,649 | 0.24 |
| 24 | 38,521 | 6,104 | 0.29 |
| 29 (the whole pass) | 49,774 | 6,679 | 0.34 |

Why they differ at all, the last frame too: on main the ring registration fits each tile as the mosaic grows, against
a reference made from the first tiles, and keeps those fits; with the pass solved first, the fits are made on all its
tiles at once, as a mosaic pass's are. Tiles land up to about 6 px from where they were; the difference is mostly
in the upper right tiles of the strip.

Only the mosaic view of the pass changes. Compared file by file, the two builds' movie frames (435 files), tiles
(145), plan, movie footprint, stabilization chain and exposure chain are byte-identical; what differs is the mosaic
pictures, the filter mosaics they are drawn from and the solve and ring files.

## Build time

Not a speed-up. Instructions retired for the pass (`/usr/bin/time -l`): 2,104 billion on main, 2,218 billion on this
branch (+5.4%): the partial solves at every frame are gone, one whole solve with every tile's ring fit takes their
place.

## How many passes

605 passes are toss-ups that play as a movie (21,851 frames; counted from the pass list, 2026-11-16).

## Image benchmark

Queued behind other threads' runs on the shared Macs when this was written (51 pictures against 1a35acb4,
`web/frames/image_bench.py`). The report is added to this folder when it finishes.
