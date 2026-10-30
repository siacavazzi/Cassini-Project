# Optimization audit

Sam, 2026-10-26 02:48Z: "Optimize everything everywhere... find optimizations wherever possible... even if it's a
small boost, that's a win", without redoing what is already planned or in flight. Thread: optimization
(cmsg_01VihZrurbK5NUCdmG37hHXsNKE6CKwYf4uMynqwQr35nM), reviewed by the pictures lead.

Sam, 2026-10-30 04:32Z: "optimize anything that has been recently introduced... everything can always be faster":
O39 to O47, over what #181 and #185 to #210 brought into the pre-build and the frame server (thread
cmsg_01VihZrurbK5NUCdmG37hHXsLvNmw69mpn56wLSTM3KyCR). The same rules, those steps included by that ask.

Rules this audit keeps:
- **Same pictures to the bit** unless a row says otherwise. A speedup that changes pixels needs a cache version bump and
  Sam's look, so it is written down here for the owner instead of being made.
- Nothing in another thread's area (see "Who works where" in docs/pictures-program.md). Ideas for those go to the owner
  and are listed under "For the owners".
- A measured number for every claim: where it was measured, before and after.

## How a speedup is proven identical
Rigs in the project files, `opt-audit/rigs/` (cloud, 34 real lean-archive frames in `sample.zip`, geometry cache copy):
- `equiv.py`: the old and new modules side by side, every changed function on the real frames, label variants and
  synthetic edge cases, comparing dtype, shape and bytes (or the exception raised).
- `golden.py OUT.json` then `compare_golden.py A.json B.json`: hashes of 671 route outputs (composites, each channel,
  `load_aligned` HDR, `processed_frame`, `color_webp`, centred pictures, singles, `processed_webp`, `load_hdr`, WebP 512,
  mosaics, movies, rolling) in the three display styles. References: `golden_pictures_17ca6fd.json` (pictures before
  #112) and `golden_pictures-next_fde48ed.json`.
- `web/test_per_code.py` (in the repo): the per-code calibration steps against the per-pixel arithmetic.
- `reel_equiv_env.py`: `reel.load_index` (the type of every value too), the color sets, `bodies()` and `reel.shots`
  old against new for every reel (keys, values and value types, `_shot_of`).
- `units_rows_equiv.py`: `obs_mosaic.units`' rows, old selection against new, for all 20,681 observations.
- `frame_memo_equiv.py`: `frame_server.webp` against the old per-size decode (sizes, formats, orders, threads).
- `pass_memo_equiv.py`: the sample's passes through `make_pass`, drawn as mosaics and as mosaic movies, at 1024 then 512
  in the three looks and 512 then 1024: a hash of every file and report. `corners_equiv.py`: a tile's outline from
  each row's ends against every pixel, on edge cases, synthetic frames and real tiles.
- `proc_memo_equiv.py`: `processed_webp` at 512 then 1024 (the segment pre-render's order), plain and centred, in the
  three looks: a hash of every picture, report and file written.
- `encode_equiv.py`: `encode` on a grid of pictures (4 modes, 6 sides, 7 sizes, WebP and PNG, 3 qualities) and on the
  sample's frames and composites at every size. `prebuild_composites_equiv.py`: the pre-build's composites item
  (`color_webp` at 1024 then 512, which writes full too) in the three looks: a hash of every file written.
- `resize_equiv.py`: `_lit_resize` (O25) against PIL's resize of the whole canvas on random canvases (lit nowhere, at
  a pixel, everywhere, in a box, a disk, a turned frame, with holes, at an edge; down and up) and 3072 px movie-tile
  canvases. For `_lit_crop` (O28), `web/test_lit_resize.py` in the repo does the same against the whole canvas's
  resize cut to its lit rows and columns, and `crop_equiv.py` checks the sample's movie-tile canvases (saved by
  `capture_canvases.py`) against the old resize and cut. `proc_place_equiv.py`: `processed_frame` on the sample's
  frames and sets, plain and hdr, and the reel pictures made of them, in the three looks: a hash of every picture,
  report and file, and of the label's placement.
- `made_equiv.py` (O27): every part drawn from a tile kept in memory against the same tile read from its PNG, over
  the sample's passes as movies, mosaics and mosaic movies. `web/test_detail_mean.py` (O29, in the repo): the
  channels' sum over 3 against numpy's mean for every 8-bit colour.
- `sky_share_equiv.py` (O30, O31): `_balanced_scale` and `picture_scale` in both looks, old against new, on the
  sample's frames and sets and on 1,200 made-up skies (ties, signed zeros, NaN, inf, constant). `shoulder_equiv.py`
  (O32): `roll_off`, `tone`, `mix_display` and `display`, old against new, on made-up pictures (NaN, inf, signed
  zeros, values at the knee; float32 and float64; views) and `tone` on the sample's frames and sets.
  `sky_stats_equiv.py` (O33): `sky_levels` and `sky_blacks`, old against new, the way each caller asks (each frame and
  set on the sky `_sky` finds, with the floor; `black_of`'s quarter-size frame; the sample's frames grouped as passes)
  and on 600 made-up skies; `web/test_sky_stats.py` (in the repo): numpy's own calls in place on one working array
  against each on its own copy. `mix_layout_equiv.py` (O34): `mix_display` and `apply_mix`, old against new, on the
  sample's colour pictures as the passes draw them, on made-up pictures and mixes, and on made-up float pictures in
  both layouts (`mix_lprof.py` is the line profile it came from). `pct_equiv.py` and `pct_nan2.py` show why order
  statistics shared between numpy calls must stay the same call on the same array unless the pixels are checked first
  (O33): with both signs of zero in it the zero found can change with the partition, and with a NaN even the result's
  type. And on numpy 2 a list of percentiles has another type than a single one (O33's fix).
- Timings: `time_make_pass.py` (a pass maker run on the sample's passes, fresh cache and geometry, no profiler, no
  tiles made ahead as the pre-build runs), `time_composites.py` (the composites item, with its encodes counted and
  timed), `time_proc.py` (`processed_frame` alone, with the time it holds `spice_lock`), `time_processed.py` (the
  pre-build's processed phase, `processed_webp` at 1024) and `time_live_movie.py` (a movie played cold on the
  live server with no tiles made ahead: each frame's tile made just before it is drawn), alternating with and
  without.
- For the overnight build, the same checks on the integration branch with and without the change (`git apply -R`
  of its code diff). How to run them: `opt-audit/rigs/README.md`.
- `zip_equiv_env.py`: every member of the sample zip and of synthetic zips (stored, deflated, empty, long local extra
  fields) read by the old and new zip reader, at several chunk sizes.
- numpy versions: the rigs run in a venv matching the Mini (numpy 1.26.4, pandas 1.5.3, cv2 4.11.0, Pillow 13.0.0).
  Since 2026-10-26 18:30Z the function rigs (`sky_stats_equiv.py`, `sky_share_equiv.py`, `shoulder_equiv.py`,
  `mix_layout_equiv.py`), every `web/test_*.py` and the route hashes also run on numpy 2.5.3 (Python 3.12, pandas 3.1,
  cv2 5.0), what `requirements.txt` installed before it was pinned: numpy 2 types some results otherwise (NEP 50), and
  O33 as first written was the same only on numpy 1 (O38).
- O39 to O43 (2026-10-30), rigs in the project files, `opt-audit-2/rigs/`: `test_garbled_repo.py`, `test_dark.py`,
  `test_stack.py`, `test_lines.py` and `test_floor.py` run d0777e6's module and the new one side by side on every frame
  of the sample (with its prefix mask, its repeats and its readout key) and on made-up inputs (lost tails and blocks,
  pasted garbage, clipped stars, NaN, infinities, signed zeros, ties), comparing dtype, shape and bytes: 1,128
  garbled-line cases (424 with garbled lines), 390 darks (282 on numpy 2), 890 stacks, 975 line fills (459 with
  something filled) and 1,598 floors, 0 differ on numpy 1.26.4 and 2.5.3. `run_phases.sh TREE OUT` runs every
  pre-build phase on the sample (one process, one thread, a fresh geometry cache), `tree_hash.py A B` compares two
  caches file by file and `timing_rounds.sh N` runs two trees side by side, the start order swapped each round.
  `web/test_exact_speedups.py` (in the repo): each new form against the old one copied in, on made-up inputs.

## Baseline
### Mini, real archive (2026-10-26 03:40Z, wt-pictures at 7ffcf90)
The Mini was busy: load 5.8 to 7.2 during the run (4 to 11.6 before it), previews :8821 (170-256% CPU), :8817 and :8819
busy, Spotlight (spotlightknowledged) near 100% CPU. Read the times as a cost breakdown, not as speeds. Files:
project files `opt-audit/mini-baseline-20261026/`.

Start-up of one frame server process:

| Step | Time | RSS after |
|---|---|---|
| numpy, cv2, PIL | 0.85 s | 62 MB |
| import frame_server | 0.69 s | 154 MB |
| reel.load_index | 3.11 s | 524 MB |
| stacking.load_index | 0.43 s | 760 MB |
| obs_mosaic._row_of | 0.04 s | 774 MB |

Pictures, cold (archive bytes not read yet) / warm (same picture again, new cache), mean of n:

| Kind | n | Cold | Warm | Largest costs (cold) |
|---|---|---|---|---|
| natural color composite | 6 | 1.58 s | 1.15 s | load_stacked 501 ms, archive reads 460 ms (15 a picture), label text 388 ms |
| false color composite | 4 | 1.87 s | 0.82 s | load_aligned 1011 ms, archive reads 383 ms, label text 334 ms, load_linear 238 ms, tone 203 ms, apply_mix 174 ms |
| centred composite | 10 | 1.11 s | 0.94 s | processed_frame 613 ms, centre_view 181 ms, WebP 165 ms |
| processed single | 12 | 0.94 s | 0.56 s | label text 479 ms (51%), archive reads 566 ms |
| WebP 512 frame | 40 | 0.81 s | 0.33 s | archive read 383 ms for 0.15 MB (47%) |

On the busy Mini a cold picture spends a quarter to a half of its time reading the LaCie (each zip read is two
`pread`s, 9 ms each on average; a 5 KB label took about 100 ms). The CPU work is the rest.

### Cloud (4 vCPU, sample archive, venv matching the Mini: numpy 1.26.4, pandas 1.5.3, cv2 4.11.0)

| | Before (fde48ed) | After (#112) |
|---|---|---|
| three-filter composite | 1.23-1.87 s | 0.84-1.25 s |
| calibrate, 34 frames | 760 ms | 227 ms |
| display_stretch, 34 frames | 1289 ms | 67 ms |
| saturated, 34 frames | 69 ms | 10 ms |
| three reads of a frame, 34 frames | 769 ms | 245 ms |
| find_repeats, a call | 1.45 ms | 36 µs |
| stack_frames of a lone frame, 34 | 283 ms | 0 |
| import frame_server | 0.93 s, 133 MB | 0.49 s, 91 MB |

| | Before (pictures 759c260) | After (#114) |
|---|---|---|
| reel.load_index (every server start) | 3.13 s | 1.85 s |
| reel.shots("SATURN") | 29.0 s | 2.8 s |
| reel.shots("ENCELADUS") | 1.44 s | 0.13 s |
| reel.shots, every body (77) | 51.0 s | 6.4 s |
| obs_mosaic.units' rows, first visit to an observation | 55 ms | 0.17 ms |
| the first centred picture after a server start (centre_view) | 282 ms | 5 ms |
| centre_view, cold, the 34 sample frames | 494-597 ms | 13 ms |
| zip reads per member | 2 | 1 |

## Findings

| # | Area | Finding | Gain (measured) | Owner | Status |
|---|---|---|---|---|---|
| O1 | calibrate | per pixel float64 work on 8-bit codes; now worked out per code and looked up (`cv2.LUT`), constants applied in place in the same order | 3.3x | this audit | #112 |
| O2 | display_stretch | the stretch of every pixel in float64; now per code | 19x | this audit | #112 |
| O3 | saturated | a frame's top found by converting every pixel; now from its largest code | 6.8x | this audit | #112 |
| O4 | load_linear | the sky mask made twice per composite, the luminance twice in false color | one `_sky` (~36 ms on the Mini) | this audit | #112 |
| O5 | data_source.imread | each frame's PNG read from the zip and inflated three times per composite; now once (16 kept, plain gray PNGs only) | 3 reads 3.1x; 6 fewer LaCie reads per composite | this audit | #112 |
| O6 | find_repeats | a DataFrame built and sorted per call | 40x | this audit | #112 |
| O7 | imports | scikit-image and matplotlib loaded by every server, never used there | -0.44 s, -42 MB per process | this audit | #112 |
| O8 | stack_frames | the reference work done for a lone frame | 8 ms a frame | this audit | #112 |
| O9 | reel.shots | Saturn's reel is 25 of its 26-29 s in per-row `idx.loc`; `mosaic_of(wait=False)` answers None (no mosaics for that body) until it is done after each server start | Saturn 29.0 s to 2.8 s; every body 51 s to 6.4 s | this audit | #114 |
| O10 | load_aligned | a two-filter set calibrated each frame twice | one calibration per frame | phase 8 | **adopted in #107 (ff55095)** |
| O11 | memory | every server process holds ~760 MB before serving: the reel index ~370 MB, the stacking index ~236 MB, imports ~110 MB (after O7). At 04:00Z the Mini had 23 of 24 GB in use, 8.4 GB in the compressor and 226 MB free, with ~20 frame servers (8765 and 8790 among them) squeezed to ~25 MB resident; a squeezed server answers slowly for its first seconds back (#105's thread) | a shared or lazily loaded index, and fewer idle previews, would let more previews run and keep 8765 resident | pictures lead | finding, lead to schedule |
| O12 | Mini disk | the archive, the preview worktrees (wt-*), and their caches share the LaCie (USB spinning disk): on the busy Mini, importing two modules took ~1.8 s (0.003 s in the cloud) and each zip read ~9 ms a seek | worktrees and their caches on the SSD would take seeks off the archive's disk | ops (lead) | finding |
| O13 | Mini CPU | Spotlight (spotlightknowledged) at ~100% CPU through the whole run | one core back | ops (lead) | finding: check what it indexes and keep it off the LaCie and the caches |
| O14 | reel.load_index | the frame ids made with pandas' per-element string methods, `colour_filter` called for each of 443,000 frames | 3.13 s to 1.85 s per server start | this audit | #114 |
| O15 | zip reader | each member read as its 30-byte local header, then its data: two reads, on the busy Mini often two seeks | one read per member | this audit | #114 |
| O16 | obs_mosaic.units | three string comparisons over the whole index for each observation, the first time a server meets it, on request threads (centre_view, kind_of, warm_frame; several at once on a first visit) | 55 ms to 0.2 ms per observation; the pre-build's `all_passes` (20,681 observations) about 19 minutes less (cloud) | this audit (handed over by #105) | #114 |
| O17 | first request | the reel index was consolidated by the first selection from it (a tenth of a second on a request thread, and two at once could both start it) and `_row_of`'s map (0.16 s) was made by the first centred picture | the first centred picture after a start 282 ms to 5 ms; the two maps hold 17 MB per server, made as it starts instead of on its first centred picture | this audit | #114 |
| O18 | rolling mosaic movies | cold, they make only 2-3 pictures a second: NPOLMOV cold runs the clock at 14-29%; a rolling picture's median 1.3 s, p90 3.9 s (phase 7's measurement) | to profile: a color rolling picture, cold, in a morning Mini slot | phase 7 with this audit | finding |
| O19 | frames (pre-build) | each plain frame's PNG read from the archive and decoded again for each of the sizes the pre-build makes in turn (1024, 512, 128); now decoded once, the last 16 kept, each size encoded from a copy | 10% less time per frame (median 159.6 to 143.1 ms, cloud) | this audit | #116 |
| O20 | encode | `thumbnail` shrinks the picture it is given, and on `pictures` (since #62) that can be a composite kept for its other sizes (`_recent_composite`): after a 512 view, the full PNG save and the channel views came out 512 px (`pictures` only; main has no kept composites) | a bug, found by the audit: no pre-built file changed (the pre-build makes 512 last) | this audit | #119 |
| O21 | processed_webp | the segment pre-render (#102's `single()`) asks for each single frame at 512, then 1024, and each size made the frame again (`load_stacked`, calibration, tone; for Auto center `processed_frame` and SPICE); now kept like a composite (`_recent_composite`), the second size only an encode | 30% less per single frame (cloud medians: plain 325 to 213 ms, centred 706 to 486 ms); 4 segment threads made 34 frames for 34, not 68 | this audit | #120 |
| O22 | pass pictures (pre-build) | `make_pass` (the pre-build's mosaic and movie passes, and the segment pre-render) asks each frame's mosaic so far, mosaic movie picture or movie frame at 1024 and 512, and both sizes were made at OUT and shrunk after: the colour mix, the luminance base, detail's blur and the movie frame's placing done twice; now `so_far` and `movie_frame` keep their last picture on the thread (named as the cache names it, up to OUT, a copy per call) | the sample's passes as mosaics: `so_far` 8 times for 4 pictures (37 of 61 s); as movies: `movie_frame` 48 times for 24 (17 of 47 s). Timed on a quiet cloud machine with O23 (medians of three alternating runs, fresh caches): a mosaic pass 66.7 to 45.1 s (32% less), a movie pass 50.1 to 38.8 s (22% less) | this audit | #120 (follow-up merged as 7754fda) |
| O23 | tile outline | `_corners` handed `minAreaRect` every set pixel of a tile (about a million) to hull; each row's first and last set pixel have the same hull | 190 ms to 8 ms a tile (a tile ~0.9 s), same to the bit on 3,995 masks | this audit | #120 (follow-up merged as 7754fda) |
| O24 | encode | encode's plan for a size (the side the picture is shrunk to, the saver's format and arguments) is now worked out on its own (`_encoding`), and a picture asked for at sizes with the same plan is encoded once. At quality 95 (#115) a composite up to 1024 px is saved the same way at 1024 and full, so `color_webp`'s 1024 and full were the same bytes encoded twice (the pre-build's composites item, and every cold window composite); a summed frame (512 or 256 px) is not shrunk for 1024 or 512, so `webp`'s 1024 and 512 (asked in turn by the pre-build) were too | the pre-build's composites item (`color_webp` at 1024, then 512): 3 encodes a set to 2, its encodes 229-255 to 133-137 ms a set, the item ~15% less (cloud; a 1024 q95 composite encode is ~100 ms here, 31 ms on the Mini per #115); a cold window composite waits one encode less; a summed frame's three sizes 3 encodes to 2 | this audit | #121 |
| O25 | tile resize | a tile's frame sits on a canvas three frames wide (3072 px for a movie tile, ~1400 px of it lit), and the whole canvas was resized to the pass's reference distance (LANCZOS): half of making a tile. PIL resizes RGBA premultiplied, across then down, each row and then each column on its own, and an unlit pixel is 0 premultiplied: `_lit_resize` resizes only the lit rows across and the columns they leave lit down, through PIL's own resize | a movie tile's resize ~430 to ~250 ms (cloud). The sample's passes on the build tree (medians of three alternating runs, no tiles made ahead, with O24): a movie pass 36.8 to 32.8 s (11% less), a mosaic pass 43.0 to 38.9 s (10% less). The same bytes on 9,300 random canvases and on every tile of the sample's passes | this audit | #121 |
| O26 | processed_frame | every frame was drawn twice onto its 3072 px canvas: shifted and turned (`auto_center`) only to learn where SPICE puts it (the label's placement and the canvas's shape), then north up at the canvas's middle, the picture returned. Now the first is not drawn (`translate(draw=False)`): the same placement, worked out from the canvas's shape. Every tile, reel picture and Auto center view goes through it | a frame's `processed_frame` as a tile is made 233 to 197 ms (cloud medians), `spice_lock` held 41 to 0.8 ms of it: the drawing skipped was inside the lock, which every thread of the pre-build takes in turn (6-9 threads tonight). A movie pass 32.8 to 31.0 s more (16% less with O25); a mosaic pass the same within its noise (~3 s) | this audit | #121 |
| O27 | tile read-back | a tile's PNG was read back right after it was written: by `_part` when its movie frame or mosaic draws it (~35 ms a 1400 px movie tile), and on the build branch by `_register` when the other filters' tiles at that pointing are registered to it. The newest tiles' pictures, as written, are now kept in memory (`_keep_made`, up to `CASSINI_MOSAIC_MADE_MB`, 64 MB, about 8 movie tiles) and used instead: the PNG is lossless, so the same pixels | ~35 ms each time. The pre-build's `make_pass` makes all of a pass's tiles before drawing its frames, so there `_part` gains only on a pass's last tiles, and `_register` whenever the tile it registers to is still kept (it was made a few tiles before); on the live server a tile made for the frame being drawn gains both. 26 of the sample's parts drawn from kept pictures, each the same bytes as from its PNG (`made_equiv.py`) | this audit | #121 |
| O28 | tile cut | `_lit_resize` (O25) still made the whole resized canvas (~3000 px square, mostly empty), and the tile code scanned it with numpy for the crop, after scanning the 3072 px canvas twice (`any` over rows and over columns). `_lit_crop` returns the cut and its place: the lit boxes from PIL's `getbbox` (one pass in C), and only the lit part of the resized canvas is made | a movie tile's resize and cut 261 to 182 ms (30% less), and 17 to 6 ms for a tile at the reference distance, which is only cut (cloud medians over the sample's 21 movie-tile canvases, `crop_time.py`); the same bytes and place (`crop_equiv.py`); `web/test_lit_resize.py` 323 checks | this audit | #121 |
| O29 | detail | the luminance `detail` sharpens with was numpy's `mean(axis=2)` over the three channels (its reduce over a short axis is slow); the channels are 8-bit values as float32, so their sum over 3 is exact and the same to the bit (`web/test_detail_mean.py` checks all 2^24 colours) | ~19 to ~4 ms a 1024 px picture: each size of each movie frame and mosaic of a filled pass | this audit | #121 |
| O30 | balanced scale | a balanced scale picked each channel's sky pixels and took their median twice, in `sky_levels` and again in `noise_floor` (a boolean pick and a median of every sky pixel). `sky_levels(floor_pct=)` takes the floor from the same pixels and median: each percentile and median the same numpy call on the same pixels in the same order, so the same values, signed zeros and NaN included | ~7 ms a 1024 px channel of every balanced composite and processed frame (cloud); 1,317 scales the same (`sky_share_equiv.py`) | this audit | #121 |
| O31 | picture_scale | in the balanced look `picture_scale` measured each picture's sky (`_sky`, a 99.9th percentile of every pixel of each channel), then `_balanced_scale` measured it again; it now passes it on, as `load_linear` already did | ~8 ms a channel of each tile's own scale in the reel's mosaics (`tiles_scale`; cloud); the same scales (`sky_share_equiv.py`) | this audit | #121 |
| O32 | tone shoulder | `tone` and `mix_display` multiplied every pixel by a factor that is 1 below the shoulder, and `roll_off` worked `tanh` out over the whole picture before choosing; both now work only on the pixels past the knee (~5% of the sample's pictures), each value the same elementwise expression on the same input | `display`'s roll-off 3.8 to 1.3 ms a channel (each channel `load_channels` draws in the balanced look: every tile); the shoulder step of `tone` 8.0 to 6.8 ms (one channel), 10.8 to 10.6 ms (three; cloud, `shoulder_time.py`); 3,985 outputs the same (`shoulder_equiv.py`) | this audit | #121 |
| O33 | sky statistics | a sky's median, 20th percentile and (in a balanced scale) 98th percentile were three numpy calls, each copying the sky's pixels (~836 k of a 1024 px frame) and partitioning the copy. `_median_percentiles` makes the same calls in place on the array `sky_levels` has already made (`overwrite_input`): no copies, and each partition starts from the order the one before left. A value at a rank does not depend on that order unless the pixels hold a NaN or both signs of zero, so a sky with either (checked first) goes to the separate calls as before. First written as one call for both percentiles: numpy 2 works that out in float64 where a single percentile of float32 pixels stays float32, so it was the same only on numpy 1 (found by the pictures lead running `web/test_sky_stats.py` on numpy 2.5.3; 758 of 3,211 sky results differ there). Fixed in 2a6ad72: each value numpy's own call, with the arguments it had | 15.0 to 12.3 ms a channel, the check included (9.4 ms as first written; the sample's 34 skies, medians of three runs, cloud, `sky_stats_time2.py`): every channel of a balanced composite or processed frame, each tile's own scale, a pass's sky levels; the pre-build's processed phase 177 to 174 ms a frame, within its noise (168 ms as first written); 4,528 results the same on numpy 1.26.4 and 2.5.3 (`sky_stats_equiv.py`, `sky_share_equiv.py`), `web/test_sky_stats.py` 1,570 checks on both | this audit | #121 |
| O34 | colour mix layout | `mix_display` hands `apply_mix` its picture channels first in shape but channels last in memory (a moveaxis of the RGB picture), where numpy's mean, min and max over the three bands run one tiny loop per pixel, 10 to 45 times as long as on a channels-first copy. A false-colour mix's band mean, band minimum and the straight picture's saturation now work on such a copy: numpy's sum starts from 0 and adds the bands in order in either layout, and max and min pick the same values, so the same results; the weighted sums (`tensordot`) keep the layout they had, for BLAS. `tone`'s channels were already channels first. The picture's brightness for the detail step is taken once instead of twice | a colour pass's colour picture 510 to 409 ms a 1024 px movie frame, 3.1 to 2.6 s a 2048 px mosaic picture (cloud, `mix_layout_equiv.py`); 4,103 outputs the same (the sample's colour pictures, 1,100 made-up pictures through `mix_display`, 3,000 `apply_mix` calls with NaN, inf, negative values and signed zeros in both layouts) | this audit | #121 |
| O35 | mosaic movies made at once | a mosaic movie's picture grows from its last one (`_roll`, kept in `_rolled`) or, when that is gone, is drawn whole (every place's newest tile composed with its seam gains): different pictures by design. `_rolled` keeps 6 mosaic movie filters for the whole process ("two passes of three"), and the pre-build's `--threads` and the segment pre-render's 4 threads outrun it with three or more colour mosaic movies at once (section "filters-level", below) | not a speedup: a threaded build's mosaic movies differ from a one-at-a-time build's and from run to run (120 of 272 pictures with four colour movies at once, 0 with room for 12 filters; a disk up to 16% brighter where a picture is drawn whole); at 6 threads about 149 of the 347 mosaic movies are in stretches at risk. Drawn whole is also slower | pictures lead, phase 7, pre-build | **fixed in 11c01ad** (phase 7: `_rolled` evicts whole passes, least recently used, keeping at least `ROLLED_PASSES`, env, default 4, and `prebuild.run` raises it to threads + 1; `web/test_rolling_threads.py`), in `pictures` with #106 (a26a2e6) and in `pictures-build` as 60a7513; checked: six at once with the pre-build's room match one at a time (0 of 264 files differ). The segment pre-render's 4 threads had the default 4 too: phase 7 raised it in 1507f78 (`rolled_room(SEGMENT_THREADS + 2)`, in `pictures` with #106). Movies built before it: `fl_rolled_check.py` lists the ones with pictures drawn whole |
| O36 | a pass's first gray | until a pass's grey filter and all of its colour filters have a tile, `layout` draws the luminance base's filter taken most so far, `max(set(base), key=base.count)`: a tie goes by the set's order, which changes from process to process (string hashing is randomized unless `PYTHONHASHSEED` is set) | 28 frames at the start of 8 of the 2,352 mosaic passes can be drawn in another filter, under another name, on the live server than in the pre-build (a miss of the pre-built picture) | pictures lead | **fixed in #108 (3cad10f)**, in `pictures` (a26a2e6) and `pictures-build` 6dcf062; the 8 passes to make again are in project files `opt-audit/results/filters-level/o36_passes.txt` |
| O37 | grown mosaics made at once | `_grown_last` keeps the 6 filter mosaics grown last (`GROWN_KEEP`) for the whole process, the same shape as `_rolled` (O35): a pass past 16 tiles of a filter grows each frame's mosaic from the one before, and at 6 threads of colour passes (four filters each, with the luminance base) the others push it out. Time only: every count is written to filters-level before the next is grown, and a PNG reads back the same pixels | 6 passes at once against one at a time: the 904 served files the same, filter mosaics read back 65 times instead of 52 (~80 ms each here). In the catalog 20,960 of the mosaic passes' 59,125 filter steps are grown ones; at most one read back per filter and frame, up to ~5% of a big colour frame (cloud). With filters-level written only at checkpoints (its option 4b) a mosaic pushed out would be grown again instead, so that option needs this first | pictures lead | finding: 11c01ad's whole-pass eviction would fit it too |
| O38 | library versions | `requirements.txt` names pandas, numpy, spiceypy, opencv-python, pillow, matplotlib and scikit-image without versions, so a machine set up from it today gets numpy 2.5.3, pandas 3.1 and opencv 5.0, where the Mini runs numpy 1.26.4, pandas 1.5.3, cv2 4.11.0 and Pillow 13.0.0 (its `.venv`, read 2026-10-26 18:20Z). numpy 2 types some steps otherwise (NEP 50: a percentile of float32 pixels is a float32 there, a float64 on 1.26) | not a speedup: `pictures` 58162a8 on today's versions (Python 3.12) against the Mini's makes 288 of the 671 route hashes differently: every composite, centred picture, colour WebP, aligned load and processed frame, most channels, and 72 of the 108 mosaic, movie and rolling routes; singles, processed WebPs, `load_hdr` and the 512 WebPs are the same. 0.3 to 0.7% of a composite's pixels differ, by 1 level (at most 4): invisible, but pictures made elsewhere, or after the Mini's venv is set up again, are not the cache's to the bit, and a byte-identical check on today's versions is not one on the Mini's (#121 is checked on both) | this audit (the pictures lead's ask) | **pinned in d333522**: `requirements.txt` holds the Mini's `pip freeze` (read 2026-10-26 19:00Z), the seven packages and the 14 they install, Python 3.11 (scipy 1.17.1 and scikit-image 0.26.0 need 3.11 or newer, and pandas 1.5.3 has no wheels past 3.11); not playwright, which only the page tests use. A fresh Python 3.11 venv from it installs exactly those versions and makes the 671 route hashes as the rigs' Mini-matching venv, 0 differ (project files `opt-audit/results/o38/pinned/`). Not checked: the same versions on another kind of machine (the cloud's x86-64 against the Mini's arm64) |
| O39 | garbled_lines | the garbled-line check (#192, #201) runs on every frame with lost packets each time its valid mask is made (`load_stacked`, `load_aligned`, `load_hdr`), ~0.5 s a 1024 px frame: numpy's `maximum`/`minimum.accumulate` down the columns took 54% of it (it steps across memory), then a median of every row step at 8 distances and two looks at every line. Now the nearest good rows are found a row at a time, the 8-bit codes' median comes from their histogram (`cv2.calcHist` over the same pixels: the middle value, or the mean of the middle two, as `np.median`), the gathers are flat on 32-bit rows (64-bit past 2**31 pixels), the start search runs only on lines with a run that jumps, and a second look that would see what the first did is skipped (most flagged frames have no garbled line) | 510 to 94 ms a flagged 1024 px frame (cloud medians, `test_garbled.py`) | this audit (2026-10-30) | this PR |
| O40 | dark current | `_dark` (2026-10-27) runs for every calibration (the compression ratio in its readout key gives nearly every frame its own dark), ~150 ms a 1024 px frame: half of it the 5-line median, `np.median` of a stack (a sort of five at every pixel down axis 0), and a fifth numpy copying the spectrum across twice for the inverse FFT down axis 0. Now `_median5` (five minimum and maximum passes: the middle of five is the middle of the fifth and the two of the other four that are neither their least nor their greatest; a dark holding a NaN or a negative zero keeps `np.median`, whose pick among equal values is its partition's: none of the sample's 228 darks holds either, `probe_dark_zeros.py`), the inverse FFT along the rows of `summed.T` (einsum's own layout: the same transforms of the same numbers) put back by `cv2.transpose`, and the lift and saturation in place | 151 to 51 ms a dark (numpy 1.26.4), 89 to 48 ms (numpy 2.5.3) | this audit (2026-10-30) | this PR |
| O41 | stack_frames | `agreeing_median` sorted the stack with `np.sort` down axis 0, a sort of 2 to 5 values at every pixel; the per-pixel judgement round clipped stars (#201) worked out its blur and two full-frame medians for every repeat, also with no clipped star (its result or-ed in under an empty mask). Now `_sorted` sinks each frame into the sorted ones before it with minimum and maximum passes (numpy's sort past 8 frames or with a NaN, which it sorts last), and the clipped-star work runs only when a star is clipped | the sort ~70 to 4-24 ms a 1024 px stack of 2 to 6 frames; ~25 ms less a repeat with no clipped star | this audit (2026-10-30) | this PR |
| O42 | line fills | `fill_lines` and `line_fills` (#201) found each pixel's nearest valid row above and below, and its nearest lost row above and below (the one above never used), with numpy's accumulate down the columns, ~16 ms each on a 1024 px frame: every summed frame (its edge columns count as lost) and every frame with lost lines goes through `line_fills` in `load_aligned`. Now `rows_above` and `rows_below`, a row at a time | ~16 to ~1.5 ms a search (two in `fill_lines`, three in `line_fills` instead of four) | this audit (2026-10-30) | this PR |
| O43 | floor black | `_floor` without sky (9f505eb) measured every picture's fine structure (two Gaussian blurs and a percentile) for a glow share that multiplies a dim factor of 0 in every picture brighter than lit sky (median I/F at or over `GLOW_IOF[1]`, most of them). With every pixel under 1e30 in size the blurs cannot overflow and the share is finite, so the result is the black plus a zero of the same sign: the measure is skipped there; a NaN, an infinity or a pixel near the float32 limit (where the full path gives a NaN) still takes the full path | ~35 ms a frame without sky (cloud) | this audit (2026-10-30) | this PR |
| O44 | WebP encoding | after O39 to O43 the pre-build's processed phase is 39% WebP encoding (three encodes a frame at quality 95, ~100 ms each, cloud) and the composites phase about a quarter | the "WebP method" row under "For the owners" stands; not the same bytes | pictures lead | finding |
| O45 | pass listing | `all_passes` took 27 s on #183's tree and 42 s on 2c09bdc (cloud, no profiler; 96 s profiled on d0777e6): `units`' `_judge` (the pass-kind rules of #192 to #210) about half, pandas' `itertuples` a quarter | once per build process (each `--procs` child): under a minute of a 2 to 3 day build; on the live server ~2 to 5 ms per observation on its first visit. Not worth it now | pictures lead | finding |
| O46 | hot pixel maps | `hot_map` merges its frame's month and band maps (up to 3 months by 4 bands) with `np.unique(axis=0)` at every calibration: 2.5 ms for six maps of 1,000 defects to 50 ms for twelve of 7,000 (cloud, made-up maps; the Mini's `hot_maps.npz` is not in the cloud). Kept per (camera, mode, month, band), bounded, it would be worked out once per month | 0 to tens of ms a calibration, by the Mini's map sizes | pictures lead | finding: count the Mini's map sizes first |
| O47 | colour registration | `align_with_masks` works out `edges` of the reference up to four times for each channel that phase correlation misses (`guided_shift`, the edges fallback, `spice_shift`'s two `_agreement` calls) and `centroid_shift(reference, frame)` twice | ~1 s of the sample's 48 s composites phase | pictures lead | finding |

O27 to O32 together, the sample's passes on the build tree (016249b without and with them), medians of three
alternating runs on a quiet cloud machine, fresh caches, no tiles made ahead (as the pre-build runs): a movie pass
30.7 to 25.4 s (17% less), a mosaic pass 37.2 to 32.6 s (12% less). A movie played cold on the live server, each
frame's tile made just before it is drawn (`time_live_movie.py`): 22.3 to 17.3 s (23% less), since there the kept
tile also saves its read-back. On `pictures` (ef8a5c3 without, 8ab6e04 with): the pre-build's processed phase 201 to
195 ms a frame (3% less, 5-6 ms in each round); the composites item the same within its noise (runs vary by ~140 ms a
set, more than the ~20 ms O30 should take off a three-filter set). With both rounds of #121, a movie pass takes about
31% less and a mosaic pass about 24% less than before it (36.8 and 43.0 s, timed the same way: O25, O26).

O33 on its own, timed the same way (8ab6e04 without and f5db4e8 with on `pictures`; the build tree without and with
it), as first written: the pre-build's processed phase 199 to 190 ms a frame (6 to 9 ms less in each round). As fixed
(2a6ad72), timed again on a quieter machine, the three alternating (without, as first written, fixed): 177.4, 167.9
and 174.4 ms a frame, the fixed one inside the noise of the one without (its rounds 170 to 178 ms against 173 to 178).
The composites item and the movie and mosaic passes are the same within their noise: O33 as fixed takes ~8 ms off a
three-filter set (~17 ms as first written), and the passes' runs vary by ~3 s. O34 is timed on the colour pictures
alone: the sample's passes hold two colour movie frames and one colour mosaic picture, inside the passes' noise.

O39 to O43 together, the sample's whole pre-build on d0777e6 and on this branch (`timing_rounds.sh 3`: every phase,
frames to chains, the two trees side by side on a 4 vCPU cloud machine, one process and one thread each, fresh caches
and geometry, the start order swapped each round), medians of three rounds: processed 239.6 to 187.3 s (22% less),
composites 93.5 to 73.5 s (21% less), mosaics 380.8 to 338.4 s (11% less), movies 172.9 to 167.4 s (3% less); frames
the same, strips and chains (mostly each process's `all_passes`, O45) inside their noise; all phases 1,091 to 962 s
(12% less). Each round's two caches are the same file for file (`tree_hash.py`: 2,588 files, 0 differ), as were the
two of a first run on the machine before the cloud container was moved to another host. Between the two hosts one
file differs, for both trees alike (a 512 px colour WebP): the same libraries on another x86 machine (O38's last note).

## For the owners
Ideas in another thread's area, sent to that thread; this audit does not make them.

| Owner | Idea | Why |
|---|---|---|
| phase 8 (#107) | calibrate a set's frames once in load_aligned | adopted (ff55095) |
| processing toggles (#117) | on `pictures` the background threads (`tiles_ahead`, `warm_movie`, `movie_footprint`'s pool) re-set only the look, so a raw-colors request also made natural-look tiles behind it; and `tiles_ahead` kept one thread per pass whatever the mode, so after a toggle it went on making the old mode's tiles to the end of the pass | fixed in #117 (`calibration.in_mode` in those threads; 29808de keys the tiles ahead by mode) |
| phase 4 (explore mosaics) | the pre-build's `all_passes` (72 s on the build head, cloud) spends 28 s in `units`' `itertuples` (a namedtuple class made per observation, 4.5 s of it) and 25 s in `_judge`, mostly matching each frame to its nearest place (6.2 million lambda calls); column arrays and a vectorised nearest place would about halve it | sent through the lead for when phase 4 starts |
| #115 (WebP quality 95) and the pictures lead | WebP's encoder effort (`method`, Pillow's default 4) for the pictures the pipeline sends. On the sample (`webp_method.py`, cloud): method 3 gives the same size and fidelity (PSNR within 0.02 dB) in 79-86% of the encode time for 1024 px RGBA pictures (colour composites, movie frames, mosaics) and 95-100% for gray frames and singles; method 1 takes 39-62% of the time for 5-10% more bytes; 6 takes 2 to 23 times as long for 3-7% fewer (all at 1024 px). Not the same bytes, so a cache version bump and a look by eye | a movie frame's two encodes are ~240 ms of it (cloud); method 3 would take ~27 ms off a 1024 px movie frame and ~45 ms off a mosaic picture. Results: project files `opt-audit/results/webp_method.txt`. For after tonight's build |
| phase 8 (#107) and processing toggles (#117) | in `load_aligned` the classic guide's `load_channels` (`picture_scale`) measures the sky again on the channels `load_linear` has just measured it on (`_sky`: a 99.9th percentile of every pixel of each channel); `load_linear`'s sky passed on to the guide is the same sky, so the same guide and alignment | ~27 ms a balanced colour composite (cloud) |
| pictures lead | a picture several frames share (a frame whose tile is of a filter not drawn yet makes the same picture) keeps the report of the frame that made it first, and the window's label shows its count ("MOSAIC · n OF m TILES"): in the build's frame order a colour pass's frame 1 (its first GRN tile, still drawn in UV3) says 1 where it has taken 2 of the colour filters' tiles, and made in the other order both frames say 2 | labels only; seen when served pictures were made again in another order (filters-level proof) |

## filters-level: what a mosaic pass keeps of each filter's mosaic (asked by the pre-build)

The pre-build thread, for the lead (2026-10-26 11:27Z): on obs-v46-q95 a pass's served files come to ~2.1 MB and its
`filters-level/` to ~131 MB (20 passes measured on the Mini), ~270-440 GB over the 2,352 mosaic passes. Can it keep
only each filter's last mosaic, or none once the pass's pictures are made, without changing pixels?

**Answer: yes, any of it, at any time.** Every picture made from a pass is the same to the bit whether its
filters-level holds every count, each filter's last, a few counts or nothing, and whether it is thinned after the
build or while the build runs. What deleting costs is time later on the Mini's live server, the first time a full view,
a pointing, a PNG export or a remade picture needs a count that is gone (Costs). None of it is served, so none of it
goes to Cloudflare either way. The tile PNGs (`tiles-*/`, the other ~57 MB a pass) are what all of it is drawn from,
and stay.

**What it holds.** Each filter's mosaic of the pass's first c tiles, for every c the pass reaches, one file a count
(`_filter_path`: `{filter}-{c}-{view}.png`, PNG level 1, ~0.8 MB on the 2048 px canvas). Up to 16 tiles (`GROW_FROM`)
a filter's mosaic is composed whole from its first c tiles (the gains solved over all of them); past 16 it is the
mosaic of c - 1 tiles with tile c drawn over it (`_grown`, `_over`).

**What reads it.**
- The build, only each filter's newest: the next frame draws its tile over it, and a frame that adds nothing to a
  filter draws it again. It is found in memory (`_grown_last`, the 6 grown mosaics made last, shared by the process's
  threads) or on disk. An older count is never read.
- After the build, whatever needs a filter's mosaic at a frame's counts and finds no picture made: the full view
  (`size=full`), a pointing opened from the mosaic (`pointing_picture` fits each tile's seam against its filter's
  mosaic, `_seam_of`), a PNG or another size (the film export), and a served picture made again after its file is
  gone. A mosaic movie's pictures do not: they draw their own tiles' mosaics, under names of their own (`-{ids}`),
  which every rule below keeps.

**Why no pixel changes.** A missing count is made again when it is asked for (`reel._cached`) the way the build made
it: up to 16 tiles composed whole from the same tiles; past 16 grown from the nearest count kept below it, the same
chain of steps from the 16-tile mosaic on, each tile resized from its PNG (lossless). Each count made on the way is
written back.

**Proof** (`filters_level_equiv.py` on the build tree 24ff217, the same files as 016249b; cloud). The sample's passes
have one tile of each filter, so the test passes are made of its frames: GRAY (its 24 frames as one filter), COLOUR
(COLR003's four frames taken 18 times: 18 tiles of each of three colour filters, every tile covering the whole view),
RASTER (GRAY's tiles moved onto a 5 by 5 grid 0.85 of a frame apart and the view made to hold them, each tile about a
quarter of the canvas across) and the sample's three passes as mosaics, with `GROW_FROM` 16 and 4.
- Built as the pre-build builds them (`make_pass`), once keeping everything and once deleting each filter's older
  mosaics as soon as a newer one was written: every other file the same (569 files at 16 and at 4, 145 for RASTER).
- Read back after the build in a shuffled order, with all of filters-level kept, each filter's last only, every 4th
  (at 4) or 16th (at 16) count and the last, counts 1-16 with every 4th and the last (RASTER), and none: every filter
  mosaic `so_far` draws at every frame, the full view and a PNG at 1024 (every frame; COLOUR's every 8th and its
  last), the served 1024 and 512, and the seam fit of each frame's newest pointing. 740 answers for each rule at 16
  and at 4, and 145 on RASTER: 0 differ, and every count made again is the same bytes as the file deleted (166 and 48
  files compared).
- With the served pictures deleted as well and made again in the shuffled order, the pixels are again the same; two
  reports differ in their tile count (the label row under "For the owners").
- Six passes made at once (6 threads, as `--threads 6` runs them) and one at a time: the 904 served files the same.
  The filter mosaics were read back from disk 65 times instead of 52 (`_grown_last` outrun, ~80 ms each). Mosaic movies
  are another matter: O35, below.

**Costs** (cloud; the Mini is faster).
- In the build: a count's PNG encode 140-160 ms, reading one back ~80 ms, one or two encodes a frame: ~8% of a gray
  frame of RASTER (1.8 s here), ~3% of a colour frame (~7 s). Deleting as the build goes saves none of that time (the
  newest is still written); only writing fewer counts would (option 4b).
- What deleting costs later, when a full view, pointing, PNG or remake needs a count that is gone: up to 16 tiles, a
  whole compose of the first c tiles (~30 ms a tile on RASTER, ~600 ms when every tile covers the whole view); past
  16, a step a tile from the nearest count kept (~70 ms on RASTER, ~1 s on the whole view), and in a fresh process
  each tile it draws is first resized from its PNG. A cold full view of RASTER at tile 22 (medians of three): 2.0 s
  with all kept, 2.6 s with every 4th count and the last, 5.5 s with only the last or none (the 16 whole, then 6
  steps). It grows with the count: at tile 100 with none kept it is ~84 steps more. Cold full views with every tile
  covering the view (`GROW_FROM` 16, medians of three, nothing else running): GRAY at tile 22 3.8 s with all kept,
  5.3-5.6 s with every 4th count (2 steps), 9.3 s with every 16th (6 steps) and 20 s with only the last or none (16
  composed whole, then 6 steps); COLOUR at its 17th tile of each colour filter 7.6 s with all kept, 10.3-10.5 s with
  any of the checkpoint rules (a step a filter) and 43 s with only the last or none. The worst case here, COLOUR's
  last frame at `GROW_FROM` 4 with none kept: 65 s (6.8 s with all kept).

**Options** (none changes a picture).
1. Keep it all, out of the way: tonight's sweeper moves idle passes' intermediates to the LaCie image (1.8 TB free).
   Nothing gets slower than a read from the LaCie.
2. Thin it after the build to count 16, every 16th count and each filter's last: a later full view, pointing or
   export is at most a whole compose of 16 tiles or 15 steps away (~1-2 s on a raster pass here, ~15 s when every tile
   covers the view). Counts 1-16, every 4th and the last keeps more (at most 3 steps). `fl_keep_plan.py` (read-only)
   prints what each rule keeps and frees on the Mini's cache, from its own counts.
3. Delete it all: everything freed. A full view, pointing or export deep in a big pass then remakes the filter's chain
   from its 16-tile mosaic (seconds on a raster pass, a minute when every tile covers the view) and writes the counts
   back, so filters-level grows again where people look.
4. For the next full build (code, the lead's call): (a) delete each filter's previous count as the next one is
   written, unless it is a checkpoint (option 2's rule): the same pictures (proved above, deleting as it went), the
   same time, and filters-level a small part of its size; (b) write only the checkpoints: this also saves the encodes
   (3-8% of a mosaic frame), but only if each pass's newest filter mosaics stay in memory while it is made (~70 MB a
   thread, ~0.6 GB at 9 threads, against ~100 MB for `_grown_last` now). Without that, threads outrun the 6 kept and
   a frame regrows up to 15 steps, more than the encode saved.

**Recommendation.** Nothing needs to change tonight: the sweeper's moves are safe, and deleting would be too.
Cloudflare's size is the served set (~5 GB), filters-level and tiles left out. After the build, option 2 if the
LaCie's space is wanted, and 4a in the code before the next full build, so filters-level never grows to hundreds of
GB.

### O35: mosaic movies made at once (found while checking the threaded build)

A mosaic movie's picture is grown from its last one (`_roll`: the new tiles drawn over it, match=False) when that
picture is still in `_rolled`, and drawn whole otherwise (every place's newest tile composed with its seam gains):
two different pictures by design. `_rolled` keeps the last pictures of 6 mosaic movie filters (`ROLLED_KEEP`, "two
passes of three", a NAC and a WAC window), shared by every thread of the process. The pre-build's mosaics phase makes
`--threads` passes at once in one process, mosaic movies among them, and the segment pre-render makes up to 4 at once
on the live server (`SEGMENT_THREADS`). With more than 6 mosaic movie filters in flight, a movie's last picture is
gone from `_rolled` by the time its next frame is drawn, and the next is drawn whole.
- Four copies of a colour mosaic movie (COLOUR's frames at one place, six tiles of each filter), made one after another
  and four at once (`fl_threads.py`, `BASE=movies`): one at a time 12 pictures drawn whole (each movie's first of each
  filter) and 60 grown; four at once 186 drawn whole and 4 grown, and 120 of the 272 served files differ (all of them
  mosaic movie pictures, 30 a movie). With `_rolled` sized for 12 filters (`ROLLED_KEEP=12`) the four at once came out
  as one at a time: 12 drawn whole, 60 grown, 0 of 272 differ.
- With real pointings (LAPS: GRAY's 24 frames as three laps of three places, gray), two at once with `_rolled` holding
  one filter (`ROLLED_KEEP=1`, the same outrun with fewer movies): 82 of 144 pictures drawn whole instead of 2, and 282
  of the 576 files differ. Where a picture differs, a median of 37% of its covered pixels differ, mostly by less than a
  level (median PSNR 47 dB); in the worst, ~10% of its pixels by more than 8 levels (PSNR 30 dB): the disk 16%
  brighter (144 to 168 levels on average) where it was drawn whole with its seam gains, and the limb and a few pixels
  where an older lap's tile lies under the newest in one picture and not the other
  (project files `opt-audit/results/rolled/worst_lap_picture.jpg`). Among grown pictures, ones drawn whole would show
  as a flicker of the disk's brightness.
- In the catalog (`fl_rolled_scan.py`, frames and geometry only): 347 mosaic movies, 187 of them in colour (3 filters
  each) and 160 gray (1). At 6 threads in time order, 18 stretches have more than 6 mosaic movie filters among the 6
  passes in flight, about 149 movies in all: the Jupiter approach (ISS_C23JU_6ATM2X2A...), Saturn's approach
  (ISS_C44SA_APPRMOV...), 2004's 2X2 and 3X3 movies, the 048 and 052 storm movies, NPOLMOV (192-195), WIND5HR
  (159-160) and others. An estimate: how long each pass holds its thread decides what is really in flight.
- Fixed in 11c01ad (phase 7), in `pictures-build` as 60a7513 (head 6dcf062): `_rolled` lets go of whole passes, the
  least recently drawn first, keeping at least `ROLLED_PASSES` (4), and `prebuild.run` raises that to its threads + 1
  (`rolled_room`; `web/test_rolling_threads.py`). Checked with `fl_threads.py` on 6dcf062: six colour mosaic movies at
  once with `rolled_room(7)`, as `prebuild.run` asks for 6 threads, came out as one at a time (18 pictures drawn
  whole, each movie's first of each filter, and 54 grown; all 264 served files the same). Five at once with the
  default 4 did not (83 drawn whole against 15; 86 of 220 files differ). The segment pre-render (Pre-process) did not
  raise it, with `SEGMENT_THREADS` 4 on the Mini: each mosaic movie in a stretch holds a thread for all its frames
  there, so a stretch with four of them and a camera window playing a fifth (the same process) outran the 4 kept.
  Phase 7 added `rolled_room(SEGMENT_THREADS + 2)` where the segment runner opens its pool (1507f78); at most it holds
  ~0.2 GB more (a colour movie keeps 3 filters, 2 pictures each, up to 16 MB a canvas).
- A movie built before the fix with pictures drawn whole keeps them (a made file is not made again). A picture drawn
  whole writes its filter mosaics to filters-level under the picture's tag and a grown one does not, so
  `fl_rolled_check.py` (read-only) lists the movie folders with more such files than a one-at-a-time build makes (it
  draws whole only each filter's first picture: at most ~4). Remove their `rolling-level/` and those tagged files (a
  tagged file left would be read instead of grown), then make the pass again. Before the fix, `--procs` (#115: one
  thread a process) avoided it: each process made one pass at a time.

### O36: a tie at a pass's start, broken at random

Until a pass's grey filter has a tile, and before every colour filter has one, `layout` draws the luminance base's
filter taken most so far: `max(set(base), key=base.count)`. When two are taken equally often the set's order picks
one, and that order changes from process to process (Python randomizes string hashing unless `PYTHONHASHSEED` is set;
eight seeds picked GRN six times and RED twice). In the catalog (`fl_tie_scan.py`, frames and geometry only, every
tile taken as placed) that is 28 frames at the start of 8 of the 2,352 mosaic passes: ISS_082SA_NPOLECAM002_UVIS and
ISS_165TI_LRMONITOR001_PRIME frames 1-6, ISS_143RH_RHEA001_PIE frames 1-7, and five more passes' first one to three.
The pre-build and the live server can draw those frames in different filters, under different names, so the server
misses the pre-built picture and makes its own. `max(dict.fromkeys(base), key=base.count)` gives a tie to the filter
taken first, the same in every process; it changes those frames' pictures wherever the hash picked the other filter.
Fixed in #108 (3cad10f), in `pictures-build` 6dcf062; the 8 passes and their frames: project files
`opt-audit/results/filters-level/o36_passes.txt` (made again, a pass's frames whose name changes are made, the rest
are found).

## Next (second pass)
- `color_webp` encodes the other window sizes before replying. Since O24 a composite up to 1024 px gets its full for
  free, so encoding the rest after the reply would only help a composite larger than 1024 px (and prebuild.py relies
  on those side files being written when color_webp returns).
- A frame's .lbl, .png and .prefix.gz sit next to each other in the sample zip; if the Mini's archive is laid out the
  same, reading the label and the PNG after it in one read would save a seek per frame of a composite (check the
  layout first).
- Color tone steps (`tone`, `apply_mix`, `_flatten_broad`, `picture_scale`): O30 and O31 took out the repeated
  partitions and shared the sky's, and O33 the sky's copies. What is left in a balanced composite of three channels is
  31 partitions of 100 k pixels or more (`prof_partition.py` on f5db4e8; since O33's fix a sky's two percentiles
  partition on their own again, one more for a sky with the floor), each of its own pixels (a channel, its sky, its
  residuals, its lit part), except the classic guide's sky (for the owners, above). Sharing partitions between a sky's
  median and percentiles (O33 as first written: one call for both percentiles, then the median) took ~3 ms more off a
  channel, but numpy 2 types a list of percentiles otherwise than a single one; only numpy's own call for each value,
  with its own arguments, is the same on every numpy, so it is not done.
- The page's render loop and fetches (the frame-rate thread's seven rounds came first: project files `frame-rate/results.md`), `build_data.py` (phase 5 rebuilds the data: coordinate first). Label parsing was checked: 0.08 ms of CPU a label (cloud), so the label time on the Mini is its disk.
- What is left of a movie frame (cloud, with O22 to O32): the frame's processing (`processed_frame`: stacking,
  calibration, the north-up warp onto its canvas, ~200 ms), registering it to its pointing's first frame on the
  build branch (~150 ms, nearly all the pipeline's alignment), writing the tile's PNG (~90 ms), `detail`'s blur
  (~190 ms) and the two WebP encodes (~240 ms; see the WebP row under "For the owners"). The canvas warps are
  already only where the frame lands (`warp_into`); OpenCV's fixed-point coordinates depend on where the part
  warped starts, so cutting that part any smaller would not be the same to the bit. Blurring only the lit part for
  `detail` is not provably the same either (OpenCV's vector code and its scalar tails meet at different columns).
- A colour pass's colour picture (`colour_picture`: `mix_display` and `apply_mix`'s false-colour path), each movie
  frame and mosaic picture of a colour pass: ~0.5 s a 1024 px movie frame timed alone in the cloud before O34,
  ~0.4 s with it. Line by line (`mix_lprof.py`, the build tree, before O34), the two saturations and the reverting
  weight took ~40% of `apply_mix` (O34 took most of that out), `_flatten_broad` a quarter (its logs, exps and broad
  blurs), and the detail step's six 5 px blurs and the full-size temporaries most of the rest. Decoding the 8-bit
  picture (`decode`, a power of every value, ~50 ms a 1024 px picture) could look its 256 values up in a table
  instead, exact only if the table is worked out on the numpy path used now (a channels-last array; check on the
  Mini that both give the same 256 values). Changes to the steps themselves belong with the colour sets' rule
  (phase 5).
- Whole composes of a filter's first 16 tiles (`GROW_FROM`): each frame of a filter's first 16 composes all of its
  tiles so far again, so in the catalog (`fl_whole_scan.py`) the 2,005 mosaic passes' 4,686 filter mosaics (the
  luminance base counted as one) compose 245,678 tiles whole for their 59,125 tiles, besides 20,960 grown steps. In the
  filters-level test builds at 16 they took 360 of the 887 s (every tile covering the view; ~30 ms a tile on RASTER).
  In a 16-tile compose (`fl_prof_whole.py`, 14.5 s) `prepare` (each frame's box, float colours, alpha and feathered
  alpha) took 37% and `_window` (each tile put on a full canvas) 28%. Both depend only on the tile, so keeping them
  from one count to the next would take about half of the whole composes' time with the same arrays, so the same
  pixels; the gains and the drawing depend on all the tiles. The cost is memory (a 2048 px canvas is 16.8 MB a tile,
  its prepared floats up to 84 MB), so only under a cap like `_parts`'. First measure their share of the mosaics phase
  on the Mini, where a tile is a part of the view.
- Count the summed frames in the Mini's archive, for O24's share of the frames phase.
