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
- `proc_memo_equiv.py`: `processed_webp` at 512 then 1024 (the segment pre-render's order), plain and centred, in the
  three looks: a hash of every picture, report and file written.
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
| O21 | processed_webp | the segment pre-render (#102's `single()`) asks for each single frame at 512, then 1024, and each size made the frame again (`load_stacked`, calibration, tone; for Auto center `processed_frame` and SPICE); now kept like a composite (`_recent_composite`), the second size only an encode | 30% less per single frame (cloud medians: plain 325 to 213 ms, centred 706 to 486 ms); 4 segment threads made 34 frames for 34, not 68 | this audit | fifth PR |

## For the owners
Ideas in another thread's area, sent to that thread; this audit does not make them.

| Owner | Idea | Why |
|---|---|---|
| phase 8 (#107) | calibrate a set's frames once in load_aligned | adopted (ff55095) |

## Next (second pass)
- `color_webp` encodes the other window sizes before replying; encoding them after the reply would take one WebP
  encode (~40 ms on the Mini) off every composite's wait, but prebuild.py relies on those side files being written
  when color_webp returns, so it needs a request-only switch and a word with the pre-build thread.
- A frame's .lbl, .png and .prefix.gz sit next to each other in the sample zip; if the Mini's archive is laid out the
  same, reading the label and the PNG after it in one read would save a seek per frame of a composite (check the
  layout first).
- Color tone steps (`tone`, `apply_mix`, `_flatten_broad`, `picture_scale`): ~30 percentile/median partitions of whole
  pictures per composite (~146 ms on the Mini); several are of the same array and can share one partition exactly.
- The page's render loop and fetches (the frame-rate thread's seven rounds came first: project files `frame-rate/results.md`), `build_data.py` (phase 5 rebuilds the data: coordinate first). Label parsing was checked: 0.08 ms of CPU a label (cloud), so the label time on the Mini is its disk.
- Once #115 (quality 95) is in: a composite up to 1024 px comes out the same at 1024 and full (no shrink, the same quality), so `color_webp` encodes the same bytes twice. A plan for each size (the side it is shrunk to and the save arguments), with one encode per plan, would take one of the pre-build's three encodes per set (a 1024 WebP is ~70-90 ms, cloud) and one of a cold window composite's two.
- The pre-build's `all_passes` (72 s on the build head, cloud) spends 28 s in `units`' `itertuples` (a namedtuple class made per observation, 4.5 s of it) and 25 s in `_judge`, mostly matching each frame to its nearest place (6.2 million lambda calls); column arrays and a vectorised nearest place would about halve it (phase 3/4's code: for the owners).
- A summed frame (512 or 256 px) is not shrunk for 1024 or 512, so its two WebPs are the same bytes, encoded twice by the pre-build; one encode could serve both (count the summed frames in the Mini's archive first).
