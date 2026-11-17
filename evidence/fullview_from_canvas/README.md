# Full views from the canvas the mosaics phase already drew: evidence

Made 2026-11-16 on the M5 MacBook, full inputs: PR #482's newest commit (d0490078, one full size per pass) against
this branch merged up to it (d6a06f10).

Four mosaic passes (two mosaic movies, a WAC color mosaic, a one-filter ring mosaic; 195 frames), each built by
`prebuild.py <phase> --only <its frames> --threads 1` in a process of its own (`build_each.sh`, `run_all.sh`):

1. the mosaics phase on main, then #482's fullview phase on a copy of that cache;
2. the mosaics phase on this branch (which makes each frame's full view as it goes) into an empty cache.

## The same files (`files_compared.txt`, `cmp_items.py`)

Every file of the four passes in the two caches, the full views among them: **1,660 files, all byte-identical**,
none only in one.

## The work (`work.md`, instructions retired, billions)

| pass | full views | fullview phase (#482) | added to the mosaics phase by making them there | change |
|---|---|---|---|---|
| 003SA 3X3MOVIEA (mosaic movie, 3 filters) | 11 | 281 | 93 | -67% |
| 024SA HALOSRCHE (mosaic movie, 2 filters) | 37 | 773 | 305 | -60% |
| 009SA 1X2WPH (WAC color mosaic, 12 filters) | 33 | 661 | 206 | -69% |
| 282RI HIRESAFRG (ring mosaic, 1 filter) | 24 | 261 | 181 | -31% |
| **all four** | | **1,976** | **786** | **-60%** |

Both phases together: 8,785 on #482, 7,594 on this branch (13.6% less). The saving follows how much composing a
full view took: most where the mosaic is drawn of several filters, least on the one-filter ring mosaic, where most
of what is left is the 2,048 px WebP itself.

Running #482's fullview phase after this branch's mosaics phase finds every picture made: 238 billion instructions
for the four passes, which is four processes starting up (60 billion each).

## Earlier, on #482's first commit

The same pair on the Mac Mini before #482's second commit (a7a0f9ca against 0828280e): 1,660 files identical,
2,013 against 820 billion (-59%).

## Image benchmark

Queued on the shared MacBook when this was written (51 pictures against 1a35acb4, `web/frames/image_bench.py`). The
report is added to this folder when it finishes. The benchmark's own full-size mosaic pictures go through
`obs_mosaic.mosaic_webp`, the same `so_far` this changes.
