# WP7a · Page ports of the film plan and the exposure levels

Read `_common.md` first.

**Goal.** The Movie Editor's plan and exposure graph computed in the page, line for line with the Python.

**Owns.** New `src/plan-local.js`, `src/levels-local.js`, `web/test_plan_local.py`, `web/test_levels_local.py`.

**Read first.** `web/frames/export.py`: `options`, `plan`, `public_plan`, `timing`, `frames`, `boomerang`, `cut`,
`complete_mosaics`, `source`, `levels`, `brightness`, `stretches`, `exposures`; the page's existing `evened_gains` port
(steady-local.html) and the catalog it loads; `docs/compute-on-viewer.md`.

**Do.**
- `plan-local.js`: `export.plan` + `public_plan` with the options the editor sends (`from`, `until`, `cams`, `fps`, `size`
  up to 1024, `drop`, `targets`, `filters`, `pictures`, `sets`, `edit`, `fedit`, `levels`, `even`, `ctr`, `zoom`,
  `nudge`), reading the page's catalog and the pass tables (`/frames/movie/<ID>.json`, `.steady.json`) instead of the
  index. Each picture's `src` is a canonical public URL (`keys.mjs`).
- `levels-local.js`: brightness, stretches and exposures; Even out reuses the existing `evened_gains` port.
- The two files reach the page only once WP6's `build.py` inlines them (WP6's brief says so); ask the lead to
  relay to WP6 when your PR is up.
- Export an API object WP7b can stub now: `window.cassiniPlanLocal = { plan(options), levels(options, pictures) }`.

**Don't.** Touch `export.py`, other than importing it in the tests.

**Tests.** The two test files run the page code in node against the Python on sample stretches: a busy Saturn day, a
Titan flyby, a mosaic movie, a stretch across New Year. Outputs match exactly.
