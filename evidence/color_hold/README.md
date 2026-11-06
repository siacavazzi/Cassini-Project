# Movies: every frame plays its own moment

Before: base c31dfe38 (main). After: this branch. Both drawn by the tree's own pipeline (`render.py`: `obs_mosaic.movie_webp`,
the `/frames/movie` route, the page's defaults: color on, centered, exposure 8), each into a cache of its own.
Each sheet: 10 frames spread over the run, before on top, after below; the label says what each frame shows
(SET: a held color set; OWN+COLOR: its own moment in the set's color; OWN: gray on its own).

| Movie | Frames | Distinct pictures before | after |
| --- | --- | --- | --- |
| Titan in front of Saturn (165TI LRMONITOR001 WAC) | 29 | 2 | 28 |
| First close Titan flyby (00ATI MOVIEA001 NAC) | 40 | 3 | 23 |
| Enceladus plume watch (221EN PLMHPMR003 NAC) | 30 | 1 | 30 |
| Hyperion (153HY HYPERION001 NAC) | 40 | 25 | 38 |

Whole mission (`scan_before.py` on main, `scan_after.py` on the branch; movie passes of 10+ frames, every frame taken as fit):
a lost moment is a frame whose picture was taken more than 5 minutes (SET_GAP) from it.

| | Frames | Lost moments before | after | Distinct pictures before | after |
| --- | --- | --- | --- | --- | --- |
| Movies playing in color (3,083) | 95,350 | 30,129 | 1,335 | 15,946 | 39,909 |
| Movies playing gray (2,101) | 152,008 | 3,926 | 0 | 142,233 | 144,937 |

The 1,335 left are frames inside a color set's own span (a set's frames can be up to 10 minutes apart).
