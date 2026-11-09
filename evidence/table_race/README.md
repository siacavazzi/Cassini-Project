# Mini and MacBook builds of one pass differed: a thread race in calibration's tables

**Symptom (2026-11-08 farm build, regression-2017).** The two machines built `obs-v89-q95/SATURN_ISS_269RI_HIPHASEFB001_PIE_W_0_g3` differently. The MacBook's `plan4.json` had RED and IR3 blacks and the IR3 luminance gain differ in the 5th digit (IR3 gain 0.3829 vs 0.3831), with IR3 last in the blacks' key order. Every tile drawn on that plan differed by 1 to 3 codes out of 255, on 142 of 2.7 M pixels (max 3, mean 4e-5 in `filters-level/RED-3`). That isn't visible: `sidebyside_269RI_RED.png` shows Mini | MacBook | difference x85.

The other flagged files (`under1-*.json`, `edges4-panels2-plan4.json` in all three passes) are side caches that fill in as frames are asked for. Every key the two copies share has the same value; one copy simply has more keys. On the current `obs-v91` build, 268TI and 271SA are byte-identical, and 269RI differs only in those side caches.

**Cause.** `replay_plan.py` recomputes the pass's display scale on the Mini at 65dad65b. With every frame, it gives the Mini's plan bit for bit. With the pass's first IR3 frame `W1870759038_1` left out, it gives the MacBook's plan bit for bit, including the key order (`replay.txt`). So the code is deterministic, and the MacBook's run lost that frame.

`calibration.filter_table()` publishes its dict before filling it. `obs_mosaic.pass_scale` calibrates a pass's first frames on a thread pool. In a fresh process, the thread calibrating the IR3 frame read the table while the VIO thread was still filling it. `ISSWA IR3CL2` sits 13 rows after `CL1VIO` in `filter_calibration.csv`, so it wasn't there yet. `calibrate` returned None, and `load_hdr` treated the frame as no picture. The plan was cached without it.

**Fix.** `filter_table`, `band_wavelength`, `body_level`, `false_gains` and `eye_tint` now fill a local dict and publish it in one assignment.

**Before / after** (`web/test_table_race.py`; 300 cold starts, two threads, switch interval 1 us):

| | a thread got no factor |
|---|---|
| regression-2017 (7590e76) | 299 of 300 |
| this branch | 0 of 300 |
