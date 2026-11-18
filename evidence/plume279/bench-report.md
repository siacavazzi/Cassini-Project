# Image benchmark: 4e7691aac6e3 against e755fd897a66

**NEEDS EYES**. 54 items: 35 identical, 19 changed (18 outside the target), 0 not built.

- target items with a measure worse (look at them): plume279-movie

Built in 7 min (base) and 39 min (candidate). Targets: plume279-movie.

| item | group | status | pictures changed | moved >8 levels (worst) | largest change (levels) | worse by measure | note |
|---|---|---|---|---|---|---|---|
| ringsFB-mosaic | hard | changed | 2/2 | 13.44% | 237 |  | half-pixel matcher fix: the ring tiles' registration moves by up to a pixel (difference only along ringlet and limb edges); no new seams or steps by the seam measure or by eye |
| ringsFA-mosaic | hard | changed | 2/2 | 8.82% | 241 |  | half-pixel matcher fix: ring tiles registered up to a pixel differently (edge-only difference); no new seams or steps |
| earthsmiled-mosaic | hard | changed | 2/2 | 0.24% | 128 |  | half-pixel matcher fix: 0.24% of pixels, sub-pixel tile placement along ring edges |
| ringmosaic04-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| shadow-mosaic | hard | changed | 2/2 | 0.00% | 10 |  | half-pixel matcher fix: at most 10 levels, sub-pixel placement |
| photlit039-mosaic | hard | changed | 2/2 | 0.15% | 151 |  | half-pixel matcher fix: 0.15% of pixels, sub-pixel tile placement at edges |
| jupiter-atmos-mosaic | hard | identical | 0/1 | 0.00% |  |  |  |
| enceladus-spol-mosaic | hard | identical | 0/2 | 0.00% |  |  |  |
| satellorb-centre | hard | identical | 0/1 | 0.00% |  |  |  |
| daphnis09-movie | hard | identical | 0/70 | 0.00% |  |  |  |
| ringclose124-movie | hard | identical | 0/10 | 0.00% |  |  |  |
| gring-still | hard | identical | 0/1 | 0.00% |  |  |  |
| plume279-movie | target | changed | 193/288 | 23.03% | 255 | frame000.webp: 12.10% of the base's light now black; frame000.webp: lit area's centre moved 17 px; frame263.webp: detail 0.2657 -> 0.3078 (+16%) |  |
| plume-bloom-still | hard | identical | 0/1 | 0.00% |  |  |  |
| approach-movie | hard | identical | 0/96 | 0.00% |  |  |  |
| ringmovie04-movie | hard | identical | 0/44 | 0.00% |  |  |  |
| telesto-composite | hard | changed | 1/1 | 1.38% | 253 |  | half-pixel matcher fix: the composite sits up to a pixel over (difference on the limb and the frame edge only), colour unchanged |
| moon99-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| venus99-still | plain | identical | 0/1 | 0.00% |  |  |  |
| masursky-still | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-portrait-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| jupiter-rmov-movie | plain | changed | 12/142 | 0.00% | 9 | evened000.webp: clipped 0.43% -> 0.88% | half-pixel matcher fix: 12 of 142 frames at most 9 levels; the clipped share of evened000 rises 0.43 to 0.88% from a sub-pixel move of a bright limb, not a tone change |
| approach-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| phoebe-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| phoebe-movie | plain | changed | 44/44 | 0.44% | 55 | evened001.webp: 0.66% of the base's light now black; frame011.webp: clipped 7.66% -> 7.92% | half-pixel matcher fix: frames steadied up to a pixel differently; 'light now black' and clipped changes are the limb moved, not tone |
| titan04-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| saturn05-movie | plain | identical | 0/27 | 0.00% |  |  |  |
| rhea-glocol-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| hyperion-mosaic | plain | changed | 2/2 | 0.53% | 64 |  | half-pixel matcher fix: sub-pixel tile placement, 0.53% of pixels |
| rhea-mosaic | plain | changed | 2/2 | 0.04% | 77 |  | half-pixel matcher fix: 0.04% of pixels, sub-pixel placement |
| titan-globmap-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| equinox-shadow-still | plain | identical | 0/1 | 0.00% |  |  |  |
| kiviuq-still | plain | identical | 0/1 | 0.00% |  |  |  |
| prometheus-still | plain | identical | 0/1 | 0.00% |  |  |  |
| pan07-still | plain | identical | 0/1 | 0.00% |  |  |  |
| iapetus-mosaic | plain | changed | 2/2 | 0.11% | 32 |  | half-pixel matcher fix: 0.11% of pixels, sub-pixel placement |
| iapetus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| mimas-mosaic | plain | identical | 0/2 | 0.00% |  |  |  |
| storm-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| helene-movie | plain | changed | 64/64 | 13.53% | 151 | evened011.webp: 0.52% of the base's light now black | half-pixel matcher fix: each frame steadied up to two pixels differently (the steady chain no longer drifts half a pixel a link); difference on edges only, no tone change |
| methone-movie | plain | changed | 30/30 | 5.70% | 197 | evened000.webp: 11.84% of the base's light now black | half-pixel matcher fix: the whole frame moved about a pixel (steady chain); 'light now black' is the speckled cosmic-ray field shifted, not darkened |
| hexagon-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| dione-mosaic | plain | changed | 2/2 | 0.74% | 82 |  | half-pixel matcher fix: 0.74% of pixels, sub-pixel placement |
| enceladus15-movie | plain | changed | 74/74 | 2.98% | 80 |  | half-pixel matcher fix: frames steadied up to a pixel differently |
| telesto-movie | plain | changed | 36/36 | 0.79% | 54 |  | half-pixel matcher fix: frames steadied up to a pixel differently |
| daphnis17-movie | plain | identical | 0/64 | 0.00% |  |  |  |
| pan17-movie | plain | identical | 0/38 | 0.00% |  |  |  |
| titan-cloud-mosaic | plain | changed | 2/2 | 0.15% | 91 |  | half-pixel matcher fix: 0.15% of pixels, sub-pixel placement |
| earth-fb-still | plain | identical | 0/1 | 0.00% |  |  |  |
| enceladus15-composite | plain | changed | 1/1 | 1.96% | 61 |  | half-pixel matcher fix: the colour set's channels lined up up to half a pixel differently (1.96% of pixels, on edges) |
| titan17-composite | plain | identical | 0/1 | 0.00% |  |  |  |
| tossup-ring-108ri | hard | identical | 0/62 | 0.00% |  |  |  |
| tossup-enceladus-088en | plain | identical | 0/24 | 0.00% |  |  |  |

Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).
