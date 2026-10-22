# Pictures program

The mosaic, color science, and drill-down plans, built together on the `pictures` branch and merged into `main` as one piece at the end.

- Combined roadmap: https://claude.ai/artifact/JNSTFbuBXUhTf96NgEhnso
- Background reports: [mosaic reliability](https://claude.ai/artifact/PnNQRzjpkpAix73DSsyKcx) (steps M), [color science](https://claude.ai/artifact/Jki2BixvT4uJHhqgB7KNK7) (steps C), [picture drill-down](https://claude.ai/artifact/4X8YAXCmDv2kDQEEYtKKgz) (steps D)
- Branch point: `main` at e6ed0fe (2026-10-22)

## How the work flows

1. Each phase is built in its own thread, on its own branch cut from `pictures`, and opens its PR **against `pictures`**, never `main`.
2. The program lead reviews each PR: runs the cloud tests, checks the evidence, checks the rules below, then merges it into `pictures` (merge commit).
3. `pictures` is kept folded with `main`: whenever `main` moves (PR #55, #60 or anything else), the lead merges `main` into `pictures` and every open phase branch folds `pictures` in.
4. A Mini worktree of `pictures` is served on the LAN so Sam can see the branch as a whole: http://192.168.68.52:8790/ (worktree `/Volumes/LaCie/claude_scratch_spk/wt-pictures`, its own frame cache on the LaCie). The live server on 8765 is never touched by this program.
5. `pictures` merges into `main` only when Sam says so.

## Rules every phase follows

- **Pipeline only.** Every picture goes through the existing pipeline (`stacking`, `calibration`, `color_image.calibrate` / `load_aligned`, SPICE centering, `mosaic.compose`, `obs_mosaic`). Change those functions; never re-implement them in the server or the browser.
- **General rules, no per-moment hacks.** A fix must hold for every pass, not the benchmark passes only.
- **Keep earlier features.** Separate NAC and WAC windows, per-body windows, mosaics, color composites, movie mode, export, flags and the dock keep working.
- **Settings.** Every new behavior that changes how pictures look is a `window.cassiniSettings` registry option, on by default, with a raw option.
- **Cache versions.** Every display change bumps the version of the cache it affects (`color-v*`, `proc-v*`, `obs-v*`) so stale pictures are rebuilt.
- **American spelling** in all user-facing text.
- **Rebuild `web/cassini-os/index.html`** (`python web/cassini-os/src/build.py`) and commit it whenever the viewer changes.
- **Disk rule.** Anything over 1 GB (worktrees, caches, scratch renders) lives on `/Volumes/LaCie/claude_scratch_spk/`; the Mini keeps 50 GB free; never `~/dev/scratch`.
- **Preview servers** run from a worktree on the LaCie with their own `--cache` on the LaCie, the same `CASSINI_DATA`, `CASSINI_KERNELS` and `CASSINI_GEOMETRY_CACHE` as live, in their own tmux session. Ports are listed per phase below.

## Preview recipe (every port)

1. Worktree on the LaCie: `git -C ~/dev/Cassini-Project worktree add /Volumes/LaCie/claude_scratch_spk/wt-<name> <branch>`.
2. **Replay data.** `web/replay/data` and the site's `data` are generated and not in git, so a fresh worktree has none and the page stops with "trajectory data could not be loaded". Symlink every untracked data file and folder from the live checkout (`~/dev/Cassini-Project/web/cassini-os/data` and `~/dev/Cassini-Project/web/replay/data`, whichever the site serves) into the worktree, keeping the branch's own tracked files (textures, models). Phase 5 writes its own rebuilt data folder instead.
3. Server in its own tmux session with the live environment, `--port <port> --cache /Volumes/LaCie/claude_scratch_spk/cache-<name>`.
4. **Check before posting a link:** `/health` answers ok; `/data/mission.json`, the tracks, attitude and month chunk for the linked `?t=` moment all return 200; a frame returns a real picture; and the page itself, opened at the exact link in headless Chromium on the Mini, shows the scene with no error overlay and no failed `data/` requests in the console. A link that has not passed this check is not posted.
5. After every push to the branch: check out the new head, restart the server if `frame_server.py` changed, and run the check again.

## Evidence every PR must carry

Every PR that changes anything a person can see carries both kinds:

1. **Cloud rig.** Before (branch point) and after stills plus a short side-by-side video, recorded with Playwright on the fake frame server (recipes in `/mnt/project-files/burst-limit/` and `/mnt/project-files/camera-feed/`). Saved under `/mnt/project-files/pictures/<phase>/` and embedded or linked in the PR.
2. **Real data on the Mini.** Before and after renders of the phase's benchmark passes (listed per phase) through the real pipeline, stills and a labeled video. Pictures cannot be uploaded from the Mini, so they go in the live site's static folder `~/dev/Cassini-Project/web/cassini-os/<phase-name>/` (git-excluded through `.git/info/exclude`) with an `index.html`, and are linked as `http://192.168.68.52:8765/<phase-name>/`.
3. **A preview server** of the phase branch on its port, with the exact URL (and `?t=` moment) that shows the change.
4. **Numbers where the phase promises numbers** (restarts left, movies reclassified, hue error against NASA, seconds per tile), measured with the investigation scripts (`mosaic-investigation/scan_passes.py`, `color-investigation/fit_matrix.py`) or their successors.

5. **Image quality pass (after checkpoint 2, 2026-10-22).** Every PR that changes how pictures look measures each before/after pair at a 100% crop of sky and body: sky noise (std in output levels), banding (distinct levels and histogram gaps over a smooth gradient) and scan lines (row-mean ripple). The after may not be worse than the before on any of them. The phase thread looks at every pair itself at 100% and writes one honest line per pair (better, worse, why). 100% crops of the hardest pairs go on an orphan `evidence/<phase>` branch so the lead can view them in the cloud, and the lead looks at them before Sam sees anything.

Phases with nothing visible (for example the tile map) carry test output and a sample of the new data instead.

## Checkpoints where work pauses for Sam

At each checkpoint the lead posts in the program thread what changed, the evidence links and the preview link, and waits for Sam's feedback before merging that phase into `pictures` and before starting any phase that builds on how it looks. Work on phases that do not depend on it continues.

| Checkpoint | When | What Sam judges |
|---|---|---|
| **1 · Mosaics stop jumping** | Phase 1 PR ready, again after the rework | No blank-and-restart; movies told apart; Mosaic / Movie switch |
| **M · Movies worth watching** | Phase M PR ready | How a pass looks played as a movie; filmstrip |
| **2 · Color looks right** | Phase 2a PR ready, then again for 2b | Composites and mosaics no longer dim, gray or tinted; then natural color against NASA |
| **A · Composite drill-down** | Phase A PR ready | Clicking channels, held window, save menu |
| **4 · Explore mosaics** | Phase 4 PR ready | Hover, click into pointings, pointing matches its spot |
| **5 · Sets and passes** | Phase 5 PR ready | "Open its mosaic" from a lone frame |
| **6 · Speed** | Phase 6 PRs ready | Faster tiles; whole-mosaic save; before the overnight pre-build starts |
| **7 · Movies** | Phase 7 PRs ready | Filmstrips; Build, Rolling, Time-lapse |
| **8 · Finishing** | Each finishing PR | Fringes, Phoebe day, science download |
| **Final** | All phases merged | Whole `pictures` branch on 8790, before any merge into `main` |

Checkpoints 1 and 2a together are the roadmap's "quickest visible win". Phase 3 has nothing visible except "the mosaic no longer shrinks when color begins", which is shown at checkpoint 4 with it.

## Phases in order

Effort comes from the reports. Phase A runs alongside 1 and 2; everything else follows the order below.

### Phase 1 · Mosaics stop jumping (M1, M2, M4) · ~1 day · port 8791
- **Goal.** Every pass shows its whole footprint, scaled to fit, so tiles never leave the picture; the tile label counts from the plan. `_judge` tells movies from mosaics by counting jumps between same-filter frames (a pass is a movie when fewer than 30% of its same-filter steps move at least 15% of a frame); movies play as frames. The page asks for a mosaic only in passes the server named as mosaics.
- **Files.** `web/frames/obs_mosaic.py` (`_judge`, `view_rect`, label), `web/frames/frame_server.py` / `reel.py` if the route changes, `web/cassini-os/src/head-quiet.html` (mosaic requests), `index.html`.
- **Done when.** The scan finds no follow-window restarts (was 329 of 352); the 945 movie passes are no longer mosaics; the gray stare is asked about once, not 36 times a minute; obs cache version bumped.
- **Benchmarks.** IOSIC_034RI_VERTULMP001_SI (2006-12-03, tile 12 W1543828177_1), ISS_034RI_SPKDKFORM001_PRIME, IOSIC_086RI_VTMPS70MP001_SI; movies ISS_109RI_LRHPENKMV001_PRIME, ISS_137RI_FMOVIE001_VIMS; stare ISS_028RG_HIPHASE002_VIMS; regression ISS_028RI_HIPHWAC001_PRIME (Saturn's Shadow).
- **Rework after checkpoint 1 (Sam, 2026-10-22 20:53Z).** Sam is not convinced movies and mosaics are told apart: the WAC ring pass building from about 2006-12-04 11:00 on the 8791 preview looks to him like a ring movie built as a mosaic. Mosaics and movies overlap (a mosaic can be a movie), so the call must be the person's too:
  - Re-check the detection on that pass and on a sample of the passes still called mosaics (contact sheets of the frames in time order next to the mosaic), and tighten the rule where it is wrong. Report how many passes change.
  - A per-window **Mosaic / Movie** switch (Auto by default, which follows the server's call). Movie plays the pass's frames in place; Mosaic builds it. The choice sticks for that pass while it plays and is a `cassiniSettings` default ("Mosaic passes: Auto / Always mosaic / Always movie"). The server builds a mosaic for any pass when asked, whatever `_judge` says.
  - Low mosaic resolution is noted and belongs to phase 6 (full-resolution mosaic); not in this PR.
- **Second round of feedback (Sam, 21:36Z).** Three kinds, not two: **mosaic** (places covered once), **movie** (one place, or a slow creep), and **mosaic movie** (the same set of places taken again and again, e.g. the Jupiter approach: a cycle of about 12 color frames repeated). The classifier names all three, and the switch offers Mosaic / Movie / Mosaic movie with Auto first. Known wrong or doubtful calls go into `pass_benchmarks.json` with Sam's verdict: ISS_064RI_AZSCAN001_PRIME NAC pass 1 (called mosaic, looks like a movie), ISS_222TI_REGMAP001_VIMS NAC pass 0 (debatable; possibly a movie of a few spots or a mosaic movie), the Jupiter approach (mosaic movie; Sam's canonical example, top of the list: JUPITER ISS_C23JU_6ATM2X2B115_PRIME NAC and the neighboring 2x2 ATM passes of late 2000). The rule is checked against every benchmark and the random sample before Sam sees it again.
- **Depends on.** Nothing. **Checkpoint 1** (shown again, together with phase M, as one "mosaic or movie" checkpoint).

### Phase M · Movies worth watching (D7 and the movie presentation, moved up) · ~2 days · port 8794
- **Why moved up.** Sam (checkpoint 1) does not love today's movie mode, and with the movie/mosaic switch more passes play as movies, so how a movie looks matters now, not after the speed work.
- **Goal.** A pass played as a movie looks like a movie: frames held steady in place (SPICE-centered through the pipeline, one display scale for the pass so brightness does not pump), smooth timing at the pass's own pace or the playback speed, a scrubbable filmstrip of the pass under the window (D7) that opens any frame or set, and an optional short Rolling trail. Starts with a short look at today's movie mode (#23, #40) and what Sam dislikes in it; the brief lists the faults found before building.
- **Files.** `head-quiet.html`, `movie.html`, `bodywin.html`, `web/frames/frame_server.py` / `reel.py` for the pass's shared scale.
- **Benchmarks.** The 2006-12-04 ring pass, ISS_137RI_FMOVIE001_VIMS, ISS_109RI_LRHPENKMV001_PRIME, ISS_235SA_SATSTARE001_PRIME, a spoke movie.
- **Mosaic movies (moved up from 7b, Sam 21:36Z).** A mosaic movie plays as a rolling mosaic that persists: the picture never resets to empty when a new cycle begins; each new tile replaces or fades over its own earlier copy (Rolling with a persistence slider, Time-lapse where a tile replaces its earlier self), and it exports through movie export (#43) looking the same. Speed work (phase 6) makes it faster later but is not a precondition.
- **Depends on.** Phase 1's pass kinds and switch; folds phase A in if A merges first. **Checkpoint M**, shown together with phase 1.

### Phase 2a · Color looks right (C1 to C5) · ~2 days · port 8792
- **Goal.** One display model on linear I/F: mosaic gains anchored (mean log gain held at 0, stronger pull to 1); one seam gain and offset per tile solved on linear luminance and applied to every filter; filled passes share one black and white across filters, sRGB curve instead of gamma 1.5, `detail()` on luminance only; composite white at the 99.5th percentile of the brightest channel over lit pixels with a soft shoulder; black per channel = sky median plus one shared noise margin.
- **Files.** `calibration.py` (`picture_scale`), `mosaic.py` (`compose`, `match_gains`, `match_offsets`), `web/frames/obs_mosaic.py` (shared scale, filled passes), settings entry, cache versions.
- **Done when.** No gain sits at the 0.909 clip in ISS_198SA or Saturn's Shadow; no offsets at the ±6 limit disagreeing between filters; no filter black above its white; channel brightness opened alone matches the composite (drill-down check); before/after hue and saturation table against the eight NASA references.
- **Benchmarks.** W1760119558 (Saturn 198 true-color pass), ISS_028RI_HIPHWAC001_PRIME tiles 21-35, Rhea 102 GEOLOG002, Rhea 049 HIGHRES, Saturn 003 WINDS, N1884017786 (Titan), PIA21889 Saturn limb; NASA references and scratch renders in `/Volumes/LaCie/claude_scratch_spk/color-investigation`.
- **Depends on.** Nothing in code; it touches `obs_mosaic.py` alongside phase 1, so whichever lands second folds the other in. **Checkpoint 2.**

### Phase 2b · Natural color (C6) · ~0.5 day · port 8792
- **Goal.** For true-color sets (RED/GRN/BL1 and RED/GRN/VIO), apply the fitted 3×3 filter-to-sRGB matrix on linear I/F, then the sRGB curve. "Natural color" setting, on by default, with "Raw filters" as the other option, in the cameras section of Settings. False-color and two-filter sets keep the direct mapping and stay labeled false color.
- **Files.** `calibration.py` / `color_image.py`, matrices from `/mnt/project-files/color-investigation/filter_to_srgb_matrices.json`, settings, cache version.
- **Per-filter-set rules for false color (Sam, 21:50Z).** False-color sets (methane and continuum bands, UV/IR, e.g. the Jupiter approach ISS_C23JU_6ATM2X2B115_PRIME NAC) look off and unpleasant today. Add a small table of rules per filter set (which filter goes to which channel, per-band weights and a balance that keeps the planet's neutral bands near gray), used for every set with those filters, not per moment. They stay labeled false color, and a Raw option keeps the direct mapping.
- **Done when.** Hue within about 1° of NASA on 6 of the 8 references, as in the report; the Jupiter approach and two other common false-color sets look balanced next to NASA's releases of the same sets where they exist, and pass the image quality checks.
- **Depends on.** 2a merged into `pictures` after Sam's feedback at checkpoint 2. **Checkpoint 2 (second half).**

### Phase A · Composite drill-down (D1) · ~2.5 days · port 8793
- **Goal.** The "held" window state (breadcrumb stack, Esc back to live, held badge, dock dot, exempt from linger and crowding, silent while held, flags record the path). The channel strip becomes clickable and opens a channel in the same window on the composite's shared scale. Server: `color.webp?…&channel=0|1|2` for a full-resolution channel cut from the composite; `size=full`, PNG and download on `/frames/processed/<ID>`; a named download for the archive PNG. A save menu offering each level.
- **Files.** `web/cassini-os/src/head-quiet.html` (window model, channel strip, full view, save), `bodywin.html`, `dock.html`, `flag.html`, `phone.html`, `web/frames/frame_server.py` (composite and processed routes), `index.html`.
- **Done when.** Click a channel under any composite, it opens in place; Esc returns to live; every level saves at full resolution; works in full view, body windows and on a phone; a channel opened alone matches its brightness in the composite.
- **Depends on.** Nothing; it does not touch mosaic or calibration code. If 2a lands first, the channel route uses the new scale through the same pipeline call. **Checkpoint A.**

### Phase 3 · Mosaics as placed tiles (M3 = C7, D2) · ~2 days
- **Goal.** A gray luminance base from every tile, drawn everywhere it exists, with color laid over it only where all three filters cover, feathered to gray at that edge; the gray filter fixed by the plan. The server writes the picture manifest (pointings with outline polygons as 0-1 fractions, center, set, tiles, `also`, and an L layer beside the color set) into the `.json` beside each cached mosaic and serves it at `/frames/mosaic/<ID>.json`; outlines backfilled from cached tile PNGs.
- **Files.** `web/frames/obs_mosaic.py` (`so_far`, `tile`, plan), `mosaic.py` if needed, `web/frames/frame_server.py` (manifest route).
- **Also.** Once the gray base draws every tile, `_judge` counts steps across filters for passes that never repeat a filter, so per-filter scans (LIMBSCAN011, CH4FLUOR001, GLOMAP001, RHEA003; 70 passes reclassified as movies in phase 1, see PR #61) come back as mosaics where they step.
- **Done when.** The mosaic never shrinks when color begins (19 cases) or when the gray filter changes (Titan ISS_181TI_TEA001_CIRS); the manifest validates for the benchmark passes.
- **Depends on.** Phases 1 and 2a merged into `pictures`. Shown to Sam with phase 4.

### Phase 4 · Explore mosaics (D3, D5) · ~2.5 days
- **Goal.** Hover a mosaic to outline the full frame under the mouse (quarter-second rest while playing), nearest-center hit test, tooltip, arrow keys, phone tap-tap; click opens the pointing in the held window, then its channels. `/frames/mosaic/<ID>/p/<n>.webp` draws a pointing from the pass's own tiles on its shared scale through `mosaic.compose`, with a toggle to "on its own".
- **Done when.** An opened pointing matches its spot in the mosaic; works in full view, body windows and on a phone.
- **Depends on.** Phases 3 and A. **Checkpoint 4.**

### Phase 5 · One rule for sets and passes (D6) · ~1.5 days plus a data rebuild
- **Goal.** One Python rule for sets and passes, used by `build_data.py` (set and pass ids in the month chunks) and `obs_mosaic`; the page uses the ids instead of its own rule. A lone frame offers "open its mosaic".
- **Data rebuild** on the Mini with the smithed attitude (command in project memory), written to a preview data folder; the live data is untouched until the final merge.
- **Depends on.** Phase 4. **Checkpoint 5.**

### Phase 6 · Speed (M5, M7, M6) · ~3 days plus one night · two PRs
- **6a.** Preview-size tiles, compose at the size sent, grow each pass's canvas in memory (`mosaic.compose` over the new tile and its overlaps only); "Whole mosaic, full resolution" in the save menu (capped canvas up to 4096 px, progress, feeds Save PNG and movie export).
- **6b.** Overnight pre-build of every real mosaic pass's plan and preview tiles on the LaCie (~108k tiles, 5-8 h, 10-25 GB), started only after every look change above has been accepted.
- **Done when.** New tiles 3-10× faster; cold jumps into Saturn's Shadow, Titan COMBINED and Dione under a second after the pre-build.
- **Depends on.** Phases 1-5 (all look changes) accepted. **Checkpoint 6** before the pre-build runs.

### Phase 7 · Movies (D7, M8) · ~5 days · two PRs
- **7a.** Moved up into phase M.
- **7b.** Moved up into phase M (mosaic movies). What remains here: speed-dependent polish of Build, Rolling (older tiles fade over the last N, persistence slider in Settings) and Time-lapse (a tile replaces its own earlier copy; the NPOLMOV_VIMS polar passes). The rolling persistence mosaic stays.
- **Depends on.** Phase 6. **Checkpoint 7.**

### Phase 8 · Finishing (C8, C9, D9, D8) · ~4 days · separate PRs
- C8 register filters to each other before composing (limb fringes, Dione's edge); C9 8LSB frames keep their good channels (Phoebe day 2004-06-11); D9 science download (calibrated I/F as 32-bit TIFF with its label); D8 rolling-mosaic tile map, or drop it if phase 7 folds rolling mosaics into `obs_mosaic`.
- **Depends on.** C8 and C9 only on phase 2; they can start once 2b is accepted. **Checkpoint 8** per PR.

## Parallel lanes

```
Lane 0 (movies):  Phase 1 ── Phase M
Lane 1 (mosaic):  Phase 1 ──┐
Lane 2 (color):   Phase 2a ─┴─ 2b ── Phase 3 ── Phase 4 ── Phase 5 ── Phase 6 ── Phase 7
Lane 3 (window):  Phase A ──────────────────────┘                          Phase 8 (C8, C9 after 2b)
```

First batch: phases 1, 2a and A at once. Second batch: 2b once checkpoint 2 is answered, and 3 once phases 1 and 2a are in `pictures`.

## Status

| Phase | Thread | PR | Preview | State |
|---|---|---|---|---|
| 1 | Mosaics stop jumping | | 8791 | building |
| 2a | Color display fixes | | 8792 | building |
| A | Composite drill-down | | 8793 | building |
| 2b, 3-8 | | | | waiting |
