# Ring passes redrawn as at the pass's epoch

Saturn ring mosaic ISS_00ARI_COMPHIDRK001_VIMS (WAC, 7 pointings × 13 filters, 2004-10-28 14:31–15:50, at periapsis).
In the overnight cache (main 5f655bc), its tiles stepped 10–30 px at every seam. Cassini's view of the ring plane
changed so fast that the ellipse SPICE draws for the last pointing is a quarter flatter than the one for the first
(`00ARI_spice_ring_shapes.jpg`: red = first, green = middle, blue = last pointing). No shift lines up two neighbours:
an affine fit of tile against tile needs a 4–5% squash (ECC 0.99), and the best shift lines up the ansa but leaves the
arms apart (`00ARI_tiles26-39_anaglyph.jpg`).

## Measured: seam lags, overnight cache passes (79 mosaics with rings), main vs this branch

`tools/ring_metric.py`: for every overlapping same-filter pair of tiles in different pointings, the radial lag of
their ring profiles as drawn (px); "within" is the same between filters of one pointing.

| pass | main: pairs, median, p90 | branch: pairs, median, p90 | within p90 main → branch |
|---|---|---|---|
| 00ARI COMPHIDRK001 W | 45, 2.82, **19.48** | 31, 1.29, **4.29** | 0.61 → 0.80 |
| 00ARI RADCOLOR001 N | 57, 0.71, **8.20** | 85, 0.77, **2.17** | 0.23 → 0.27 |
| 008RI RDCOLSCNA001 N | (one strip) | | **22.89 → 0.39** |
| 007RI RDCOLSCNA001 N | (one strip) | | 0.87 → 0.47 |
| 00ARI COMPLODRK001 W | 20, 0.59, 1.53 | 46, 1.89, 2.56 | 0.30 → 0.36 |
| 00ARI RNGPHOTMA/MC 001/002, 000RI RINGPHOTM001, 00ASA SATSYSTEM001, 00BRI RADCOLOR001 | within ±0.3 px | | |
| the other 67 | identical | | |

COMPLODRK001: the seam step across the A ring at the middle is gone, but the A ring's tip at the right ansa now steps,
where the last pointing (it shows the disk, so it stays as taken) meets its redrawn neighbour.

`tools/predict.py` (SPICE only, no pictures) gives how far each pass's ring plane changes shape, the part no shift
takes out: 16 of the 136 ring passes in the overnight cache change 2 px or more (6 still mosaics, the rest ring-strip
movies). Renders: `tools/full.py`-style 2048 px through `obs_mosaic.so_far` with the full kernels (galign harness).
