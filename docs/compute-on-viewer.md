# Compute on the viewer's computer

Sam, 2026-10-27: the site must keep running on the one Mac Mini plus Cloudflare storage. A handful of people
processing pictures in parallel would swamp the Mini, so **work that depends on a viewer's settings runs on the
viewer's computer**, not on the server. This is a design rule for every feature from now on.

## The rule

Every picture feature is split in two:

1. **Measure once, on the server, in the pre-build.** This is whatever needs the full tiles or the archive:
   SPICE centering, calibration, registration chains (`steady_chain`, `track_places`), brightness chains
   (`exposure_chain`), seam solves, mosaics. It is done once per pass, the same for every viewer, and kept in the
   cache. Its result is served as pictures (one default variant) plus small JSON next to them.
2. **Apply per viewer, in the page.** This is whatever turns a setting into a picture: smoothing a chain for a
   slider value, a gain, a whole-pixel move, a colour mix, a look, a trail, a fade. It runs in a worker or a WebGL
   pass, on pictures and JSON the cache already holds.

Neither half may become a second implementation (the prime directive). The page's half is a line-for-line port
of the Python function, with a test that runs the page's own code against the Python, and the test must match:
bit for bit for arithmetic, and pixel for pixel before WebP for pictures. The precedents are
`web/frames/studio_look.py` with `test_studio_look.py` (Studio look, WebGL), and `web/test_steady_local.py`
(stabilization, `src/steady-local.html`).

Checklist for a new feature or setting:

- Can each value of the setting be shown from pictures the cache already holds, plus page-side arithmetic? If so,
  build it that way.
- If not, does it have one value that everyone sees? Pre-build that value and nothing else.
- A setting whose every stop needs a picture drawn by the server does not go on the public site. It can stay
  behind a local-only flag for Sam.
- The server still draws a picture when no cached one exists (a cold pass), as a fallback, and for exports.
  The Worker in front of R2 caps how much of that reaches the Mini.

## Migration of what exists

Ordered by what it costs the Mini now. Each step ships as its own PR with before/after evidence.

| # | Feature | Today | Moves to | Status |
|---|---|---|---|---|
| 1 | Image stabilization, single-filter movie frames | server draws every frame per smoothing value (`_s<N>`) | page moves the pre-built steady-0 frame (`steady-local.html`) | PR #149 |
| 2 | Exposure normalization | server draws every frame per smoothing value (`_e<N>`) | page: port of `evened_gains`, then `_shade`'s lookup table per frame | PR #149 |
| 3 | Colour movie frames under 1 and 2 | server mixes each set's planes | page: the set's grey frames (`color=0`, pre-built) moved and gained, mixed by a WebGL port of `colour_picture` / `calibration.mix_display`, then `detail` for filled passes | PR #149, natural colour only (false-colour sets stay on the server); filled passes on on-machine: the page gains, mixes and trails their frames drawn without `detail` (`detail=0`, `_d0`) and runs `detail` itself on the GPU (`web/test_detail_local.py`) |
| 4 | Movie trail | server blends earlier frames per trail length | page: the same blend over grey frames it already has | PR #149 |
| 5 | Defaults switch | stabilization and exposure default on, drawn by the server | page does 1 to 4 by default; the pre-build keeps only base frames (steady 0, exposure 0), and #147's ~23 GB frame remake is no longer needed (its chains still are) | PR #149 turns the page path on by default; the pre-build change is the pre-build thread's |
| 6 | Film export "as in the movie" | Mini encodes (~10 pictures/s, one at a time) | page encodes from the pictures it shows (WebCodecs H.264), with the Studio look already applied there | on-machine: export.html makes films up to 1024 px a camera here by default (`web/test_export_here.py`); Full and "up to" sizes stay on the server |
| 7 | Mosaic movie fade / laps / persist | server draws each combination (`rolling_webp`) | fade: page dims the pre-built time-lapse picture (`fade_table`: each tile's alpha on the fade map, zlib) by a port of `_faded` (`web/test_fade_local.py`); laps above 1 change the composition and stay on the server | on-machine (fade) |
| 7b | Color smoothing (a color picture's palette moved toward its neighbours', Settings > Processing) | new | page: `colour-smooth.html`, a port of `web/frames/colour_smooth.py` (`web/test_colour_smooth.py`, byte for byte); measured on the pictures the window shows and looks ahead to, so nothing is pre-built; server films (`export.py cs=`) use the Python | on-machine |
| 7c | Additional stabilization of a film (the Movie Editor's Framing, under Auto center: for when SPICE's centering wobbles, a small moon in the NAC) | new | page: `film-steady.html`, a port of `web/frames/film_steady.py` (the pipeline's own `image_correction.find_shift` then `centroid_shift`, chained, within the part both pictures show so a centred picture's own edge stays out of the match, and `obs_mosaic.held_to_spice`; `web/test_film_steady.py`: the same matches, moves equal to 1/100,000 of the picture, as the page's DFT is in doubles and OpenCV's in floats); measured on the pictures the film shows, so nothing is pre-built; a server film is sent the moves (`export.py steadied=`, POST body) and only moves its pictures | this PR |
| 8 | Processing toggles, classic look, raw colours (`off=`, `look=`, `colors=`) | server redraws everything | stay on the server; local-only (Sam), not offered on the public site unless pre-built | rule only |
| 9 | Seam blend and level, full-resolution export, Pre-process | heavy, need tiles | stay on the server: seams pre-built as one variant; full-res and Pre-process off on the public site | rule only |

The pre-build (`prebuild.py` movies phase, `make_planes`) keeps every movie frame alone at 1024 (`color=0`), the
plane the page starts from, and for filled passes (Titan, Jupiter) their movie frames drawn without the detail filter too
(`/frames/movie/<ID>.webp?...&detail=0`, files `_d0`): the page's exposure, colour and trail start from those.

Steps 1 to 5 also need two shared pieces:

- **Pass tables.** `/frames/movie/<ID>.steady.json` (from #149) grows into one per-pass JSON holding every chain a
  page step needs: places, boxes, view, log brightness and gains. It is pre-built and goes to R2 next to the
  pictures (a few KB a pass).
- **A test per port**, in `web/test_*.py`, which runs the page's script in node or Playwright against the Python,
  in the style of `test_steady_local.py`.
