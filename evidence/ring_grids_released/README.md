# Ring fit: a tile's radius grid let go as soon as its bins are made: evidence

Made 2026-11-16 on the M5 MacBook, full inputs.

`obs_mosaic.ring_places` sampled every ring tile of the pass first and only then turned each tile's radius grid (a
float64 grid of the tile and the search's margin, 9.5 MB) into its bins (2.4 MB), so while the tiles were sampled
the grids of the whole pass were held at once.

## Measured (`ring_fit_time.py --mem`)

The whole-pass ring fit of 108RI MNRNGSHAD005 (29 tiles) on a clone of its built cache, tracemalloc's highest size
inside `ring_places` over what was held before it (`CASSINI_RING_PROFILES_MB=0`, so #515's kept profiles are not in
the number):

| checkout | most held inside `ring_places` | digest of the answers and the reference |
|---|---|---|
| main 1a35acb4 | 647 MB | f5411ffcdfbd |
| #515 (82d50064) | 647 MB | f5411ffcdfbd |
| this branch | **401 MB** | f5411ffcdfbd |

246 MB less for 29 tiles, 8.5 MB a tile (the grid and its mask, less the bins). What is left is one tile's geometry
being worked out (the transient) and about 4 MB a tile kept for the fit. By the same count a 132 tile pass (116RI
EQXSHADOW018) holds about 1.1 GB less while it is sampled, a 316 tile one (033RI AZSCNLOPH001) about 2.7 GB less.

## Tests

`web/test_ring_fit_once.py` (the old function copied in, as in #515): the answers and reference still equal to the
last digit; and the radius grids alive while a pass's tiles are sampled, counted with weak references: every one
sampled so far before, one now.
