# Ring movies stabilized on their ring profiles

Left: PR 543. Right: this branch. Shake = the change of the frame-to-frame shift (phase correlation), px on the 1024
movie frame; the chain's links come from the steady file (linked / of the movie's frames).

| movie | before median / p90 | after median / p90 | linked before -> after |
|---|---|---|---|
| D ring 179RI DRHPMOV001 (rings-drhp179.webp) | 8.8 / 21.5 | 4.7 / 15.3 | 7 (17 past reach) -> 25 of 26 |
| F ring 030RF FMOVIE001 (rings-fmovie030.webp) | 6.1 / 14.3 | 4.0 / 11.6 | 27 -> 31 of 32 |
| 2005-04-13 ring movie 006RI LPHRLFMOV001 (rings-ring2005.webp) | 1.2 / 2.4 | 0.8 / 2.0 | 212 -> 1,161 of 1,334 |
| Daphnis 09, F ring 166RI, ring close-up 124 | unchanged | unchanged | |
| 2004 high-phase F ring 00ARF HIPHLFMOV001 (rings-rings2004.webp) | 10.0 / 16.0 | unchanged | 10 of 44 |

The 2004 F ring movie stays as it is. The F ring is eccentric, so its radius on SPICE's circular ring plane changes
across the frame and the radial profiles of two frames do not agree (best correlation 0.26 to 0.47, under the 0.6 the
match needs). Its frames also change shape from one to the next, so the pictures do not match either. Neither match is
believed, and the movie keeps SPICE's places.

Image benchmark, all 51 items built on both sides (base 443d88ad = PR 543): 51 identical (bench_report.md).
