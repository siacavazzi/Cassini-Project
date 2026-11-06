# Every movie in the Cassini ISS data

Catalog: `movie_catalog.csv` (2,833 rows, one per movie sequence, sorted by time). Built 2026-11-06 from the full image
index (443,177 frames) on main 1825d67, with the pipeline's own passes (`obs_mosaic.units`, the geometry cache for
pointing). No movies were rendered.

## The rule

A **movie sequence** is one camera taking the same view of one target again and again: at least **10 time steps**.
A time step is one picture through the sequence's main filter, so a color movie counts one step per color set and a
mosaic movie one step per lap. "Same view" means one of:

- the pipeline already plays the pass as a movie or a mosaic movie (its stare, creep and track rules);
- the main filter's pictures stay put: each step under 0.3 of a frame and the whole run within 1 frame;
- the camera steps on at an even pace (a ring movie riding along with the ring), or keeps coming back to one of at most
  four places (a spoke movie swinging between two patches of ring).

Passes of the same target and camera join into one sequence across pauses and across observation IDs when the next one
shares a filter, is within 16 hours, the distance changed by less than 1.4x, and its pictures sit where the earlier ones
did (within half a frame) or both keep the target's disk in frame (Auto center holds them). That joins the 2004 Saturn
approach movie, whose 100+ observations of a few frames each are one film.

**Flagged in metadata** means an observation name has MOV or MV in it (MOVIE, NPOLMOV, APPRMV, SPKMV, FNTRNGMV; LAMVELOC
is left out). The PDS labels have no other movie flag: SEQUENCE_TITLE is just the observation name.

Nothing is hard-coded per sequence. Thresholds are in `catalog.py`.

## Threshold

Real targets (sky and star stares left out), sequences with at least N steps:

| N | sequences | flagged | not flagged |
|---|---|---|---|
| 5 | 3,868 | 425 | 3,443 |
| 8 | 2,953 | 407 | 2,546 |
| **10** | **2,651** | **403** | **2,248** |
| 15 | 1,981 | 374 | 1,607 |
| 20 | 1,621 | 334 | 1,287 |
| 30 | 1,222 | 292 | 930 |
| 50 | 803 | 234 | 569 |

I kept Sam's floor of 10. Flagged movies barely change between 8 and 15 steps, so 10 isn't cutting real movies. By
length: 987 have 10-19 steps, 848 have 20-49, 403 have 50-99, and 413 have 100 or more. Filter on `time_steps` for a
stricter list.

## What it found (2,651 on real targets, plus 182 sky/star stares)

- **403 flagged, 2,248 not flagged.** Most movies aren't named as movies.
- Unflagged movies include night-side lightning watches (NALGTNG), aurora stares (AURSTARE), Titan cloud monitors (TEA,
  CLOUD, LRMONITOR), the Jupiter atmosphere series of 2000-01 (6ATM, 17ATM: rotation movies), mutual events between moons
  (MUTUALEVE), propeller retargets (PROPRETRG), Saturn polarization stares (PLRNC) and the Titan wind movies (WIND5HR).
- **By target size:** 2,147 show a disk 100 px or more across, 197 a small moon (10-100 px), and 288 are distant
  irregular moons under 10 px. Those are light-curve stares at a dot (`target_class` = point).
- 1,082 are color, 1,569 single filter. 1,694 are NAC, 957 WAC.

## Against what we play today

`movie_on_main_now` uses current main's passes. `movie_on_live_site` uses the live site's `web/replay/data` (8765).
"split" means it plays, but as several shorter movies.

| | plays as one movie | split into shorter movies | not a movie |
|---|---|---|---|
| main now | 1,384 | 1,007 | 260 |
| live site (8765) | 1,226 | 973 | 452 |
| main + this PR | 1,454 | 917 | 260 (+20 nearly whole) |

So **1,267 sequences don't play as one movie today, 1,117 of them unflagged.** Most are films cut by pauses or by
observation-ID changes.

Movie Spot Check 4 looked at 40 observations, and 26 of them are in the catalog. The other 14 play as movies today but
have fewer than 10 time steps of one view. Some are filter or polarizer surveys that the spot check already said "play as
a near-still or as a grey filter strobe" (020TI, 080EN, 223EN). Others are a handful of color sets (126MI, 141EN, 153SA,
159TI, 195RI Earth, 200SA, 257DA, 264PN, 039IA, 009OT) or two frames (033RI). By this rule they're stills or short
clips, not movies.

## Flagged observations that aren't in the catalog (37 of 812)

Most are under 10 steps: Titan MOVIEVV/WW/ZZ (9 steps each), 00ASA 2X2MOVI*A01x mosaic-movie legs (8-9 laps each),
049SA STRMOVIB/STRMOVIEA (one 6-frame set each), and small aurora movies (5-6 steps). Two kinds are real movies that our
pointing can't follow:

- **Spoke movies** (116RI SPKMVDFHP, 55-69 frames) go back and forth between two ring patches. The pipeline gives them no
  kind. The catalog picks most up as "view revisited", but these four still fall short because each patch's step is
  under 10.
- **F ring movies** (191RF/262RF FMOVIE001, 057RI LPMRLFMOV) follow the ring as it moves, so in Saturn-centered pointing
  they slide across the canvas. They need ring-frame pointing, which is a bigger change than tonight's.

## The PR

Within one observation, a movie pass taken up again on the same view after a pause longer than 30 minutes (and within
2 hours) now plays as one movie (`obs_mosaic._restare`). On the whole index that joins 3,928 movie passes into 871, in
634 observations. No pass changes kind. For example, 048SA STRMOVIEC001's WAC goes from 12 films of 37 pictures to one
of 444, and the 175TI CLOUD001 monitor gets its last 4 frames back. Cross-observation series (the approach movie, the
Jupiter series) stay split. Joining those would mean passes spanning observations, which the page and caches don't
support yet.

## Files

- `movie_catalog.csv`: the catalog. `link` opens the start of each sequence in movie mode on 8765 (Tailscale address).
- Scripts (on the Mini, `~/dev/scratch/moviecat/`): `dump2.py` (passes from main), `catalog.py` (the rule),
  `final.py` and `write_csv.py` (comparisons and the CSV).
