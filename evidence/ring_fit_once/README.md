# Ring fit: a tile's profiles made once for both rounds: evidence

Made 2026-11-16 on the M5 MacBook (shared with other threads' jobs: CPU seconds of the process), full inputs.

## The same fits, a third of the time (`ring_fit_time.py`)

The whole-pass ring fit of a built ring pass, 108RI MNRNGSHAD005 (29 tiles, all with rings; a toss-up that plays as a
movie): its kept ring and solve files removed from a clone of its cache, the pass's last layout asked as
`solve_places` asks it, `obs_mosaic.ring_places` timed where it is called. The same clone source for each checkout.

| checkout | `ring_places`, CPU s | a tile | fitted / no match | digest of the answers and the reference |
|---|---|---|---|---|
| main 1a35acb4 | 109.1 | 3.76 s | 12 / 5 | f5411ffcdfbd |
| #496 (58502adf) | 72.0 | 2.48 s | 12 / 5 | f5411ffcdfbd |
| this branch (on #496) | 38.5 | 1.33 s | 12 / 5 | f5411ffcdfbd |

The digest is over every tile's answer (move, scores, place found, accepted) and the reference profile's bytes: the
three checkouts give the same fit.

Where it goes: the fit's two rounds try the same ~1,100 places of every tile; the second round now reads the first
round's profiles back (in the unit test, 39,676 `bincount` calls for a 9 tile pass become 19,820).

## What that means for a rebuild (estimates from the per-tile times above)

Tiles counted from the finished cache's kept ring files (the movie-speed thread's survey, 2026-11-16); a tile with too
little ring to try costs nothing, so these are upper bounds.

| passes | tiles | the fit today on main | with #496 | with this too |
|---|---|---|---|---|
| 543 mosaics (solved whole, two rounds a tile) | 15,092 | about 15.8 CPU-hours | 10.4 | 5.6 |
| 293 toss-ups that play as movies, as main builds them (a tile at a time, one round a tile) | 12,592 | about 6.6 | 4.3 | 4.3 |
| the same solved whole, as #503 builds them (two rounds a tile) | 12,592 | about 13.2 | 8.7 | 4.7 |

So #503's whole-pass fit, which on main alone costs about 6.6 CPU-hours more over a rebuild, costs less than the
tile-at-a-time fits do today once #496 and this are in; and the mosaics' fits fall from about 16 CPU-hours to 6.

A scan along one ring radius (a reference of under 30 bins, which can match nothing) is answered without a search:
033RI AZSCNLOPH001's 316 tiles, 096RI AZSCANLIT001's 241, 064RI AZSCAN001's 226 and 013RI AZSCNHIPH001's 105 in the
survey kept "no match" for every tile after searching each.

## Whole passes

Three ring passes built by `prebuild.py` in a process of its own each, on main and on this branch, compared file by
file: PASSES
