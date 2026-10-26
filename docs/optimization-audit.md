# Optimization audit

Sam, 2026-10-26 02:48Z: "Optimize everything everywhere... find optimizations wherever possible... even if it's a
small boost, that's a win", without redoing what is already planned or in flight. Thread: optimization
(cmsg_01VihZrurbK5NUCdmG37hHXsNKE6CKwYf4uMynqwQr35nM), reviewed by the pictures lead.

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
  `sky_stats_equiv.py` (O33): `sky_levels` and `sky_blacks`, old against new, the way each caller asks (each frame
  and set on the sky `_sky` finds, with the floor; `black_of`'s quarter-size frame; the sample's frames grouped as
  passes) and on 600 made-up skies; `web/test_sky_stats.py` (in the repo): the shared partition against the separate
  numpy calls. `mix_layout_equiv.py` (O34): `mix_display` and `apply_mix`, old against new, on the sample's colour
  pictures as the passes draw them, on made-up pictures and mixes, and on made-up float pictures in both layouts
  (`mix_lprof.py` is the line profile it came from). `pct_equiv.py` and `pct_nan2.py` show why order statistics
  shared between numpy calls must stay the same call on the same array unless the pixels are checked first (O33):
  with both signs of zero in it the zero found can change with the partition, and with a NaN even the result's type.
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
| O33 | sky statistics | a sky's median, 20th percentile and (in a balanced scale) 98th percentile were three numpy calls, each copying the sky's pixels (~836 k of a 1024 px frame) and partitioning the copy. `_median_percentiles` takes both percentiles in one call and then the median, in place on the array `sky_levels` has already made. A value at a rank does not depend on which partition finds it unless the pixels hold a NaN or both signs of zero, so a sky with either (checked first) goes to the separate calls as before | 15.2 to 9.6 ms a channel, the check included (the sample's 34 skies, cloud, `sky_stats_time.py`): every channel of a balanced composite or processed frame, each tile's own scale, a pass's sky levels; the pre-build's processed phase 199 to 190 ms a frame; 4,528 results the same (`sky_stats_equiv.py`, `sky_share_equiv.py`), `web/test_sky_stats.py` 1,570 checks | this audit | #121 |
| O34 | colour mix layout | `mix_display` hands `apply_mix` its picture channels first in shape but channels last in memory (a moveaxis of the RGB picture), where numpy's mean, min and max over the three bands run one tiny loop per pixel, 10 to 45 times as long as on a channels-first copy. A false-colour mix's band mean, band minimum and the straight picture's saturation now work on such a copy: numpy's sum starts from 0 and adds the bands in order in either layout, and max and min pick the same values, so the same results; the weighted sums (`tensordot`) keep the layout they had, for BLAS. `tone`'s channels were already channels first. The picture's brightness for the detail step is taken once instead of twice | a colour pass's colour picture 510 to 409 ms a 1024 px movie frame, 3.1 to 2.6 s a 2048 px mosaic picture (cloud, `mix_layout_equiv.py`); 4,103 outputs the same (the sample's colour pictures, 1,100 made-up pictures through `mix_display`, 3,000 `apply_mix` calls with NaN, inf, negative values and signed zeros in both layouts) | this audit | #121 |

O27 to O32 together, the sample's passes on the build tree (016249b without and with them), medians of three
alternating runs on a quiet cloud machine, fresh caches, no tiles made ahead (as the pre-build runs): a movie pass
30.7 to 25.4 s (17% less), a mosaic pass 37.2 to 32.6 s (12% less). A movie played cold on the live server, each
frame's tile made just before it is drawn (`time_live_movie.py`): 22.3 to 17.3 s (23% less), since there the kept
tile also saves its read-back. On `pictures` (ef8a5c3 without, 8ab6e04 with): the pre-build's processed phase 201 to
195 ms a frame (3% less, 5-6 ms in each round); the composites item the same within its noise (runs vary by ~140 ms a
set, more than the ~20 ms O30 should take off a three-filter set). With both rounds of #121, a movie pass takes about
31% less and a mosaic pass about 24% less than before it (36.8 and 43.0 s, timed the same way: O25, O26).

O33 on its own, timed the same way (8ab6e04 without and f5db4e8 with on `pictures`; the build tree without and with
it): the pre-build's processed phase 199 to 190 ms a frame (6 to 9 ms less in each round). The composites item and the
movie and mosaic passes are the same within their noise: O33 takes ~17 ms off a three-filter set, and the passes' runs
vary by ~3 s. O34 is timed on the colour pictures alone: the sample's passes hold two colour movie frames
and one colour mosaic picture, inside the passes' noise.

## For the owners
Ideas in another thread's area, sent to that thread; this audit does not make them.

| Owner | Idea | Why |
|---|---|---|
| phase 8 (#107) | calibrate a set's frames once in load_aligned | adopted (ff55095) |
| processing toggles (#117) | on `pictures` the background threads (`tiles_ahead`, `warm_movie`, `movie_footprint`'s pool) re-set only the look, so a raw-colors request also made natural-look tiles behind it; and `tiles_ahead` kept one thread per pass whatever the mode, so after a toggle it went on making the old mode's tiles to the end of the pass | fixed in #117 (`calibration.in_mode` in those threads; 29808de keys the tiles ahead by mode) |
| phase 4 (explore mosaics) | the pre-build's `all_passes` (72 s on the build head, cloud) spends 28 s in `units`' `itertuples` (a namedtuple class made per observation, 4.5 s of it) and 25 s in `_judge`, mostly matching each frame to its nearest place (6.2 million lambda calls); column arrays and a vectorised nearest place would about halve it | sent through the lead for when phase 4 starts |
| #115 (WebP quality 95) and the pictures lead | WebP's encoder effort (`method`, Pillow's default 4) for the pictures the pipeline sends. On the sample (`webp_method.py`, cloud): method 3 gives the same size and fidelity (PSNR within 0.02 dB) in 79-86% of the encode time for 1024 px RGBA pictures (colour composites, movie frames, mosaics) and 95-100% for gray frames and singles; method 1 takes 39-62% of the time for 5-10% more bytes; 6 takes 2 to 23 times as long for 3-7% fewer (all at 1024 px). Not the same bytes, so a cache version bump and a look by eye | a movie frame's two encodes are ~240 ms of it (cloud); method 3 would take ~27 ms off a 1024 px movie frame and ~45 ms off a mosaic picture. Results: project files `opt-audit/results/webp_method.txt`. For after tonight's build |
| phase 8 (#107) and processing toggles (#117) | in `load_aligned` the classic guide's `load_channels` (`picture_scale`) measures the sky again on the channels `load_linear` has just measured it on (`_sky`: a 99.9th percentile of every pixel of each channel); `load_linear`'s sky passed on to the guide is the same sky, so the same guide and alignment | ~27 ms a balanced colour composite (cloud) |

## Next (second pass)
- `color_webp` encodes the other window sizes before replying. Since O24 a composite up to 1024 px gets its full for
  free, so encoding the rest after the reply would only help a composite larger than 1024 px (and prebuild.py relies
  on those side files being written when color_webp returns).
- A frame's .lbl, .png and .prefix.gz sit next to each other in the sample zip; if the Mini's archive is laid out the
  same, reading the label and the PNG after it in one read would save a seek per frame of a composite (check the
  layout first).
- Color tone steps (`tone`, `apply_mix`, `_flatten_broad`, `picture_scale`): O30, O31 and O33 took out the repeated
  partitions and shared the sky's. What is left in a balanced composite of three channels is 31 partitions of 100 k
  pixels or more (`prof_partition.py` on f5db4e8), each of its own pixels (a channel, its sky, its residuals, its lit
  part), except the classic guide's sky (for the owners, above). One partition for a sky's median and percentiles
  (the percentiles' call also placing the median's two middle values) would take ~1 ms more off a channel, but it
  would redo `np.median`'s last step outside numpy, so it is not done.
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
- Count the summed frames in the Mini's archive, for O24's share of the frames phase.
