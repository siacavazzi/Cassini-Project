# Image regression benchmark

Sam's rule (2026-11-13): a change to how pictures are made must show that it improves what it set out to fix and
makes nothing else worse. Earlier fixes went one step forward and two steps back: a fix for one mosaic put steps in
another (#449, fixed by #457), and rules aimed at glow made other pictures look over-processed (#267, #279). Minor
defects are acceptable. A change that makes pictures look over-processed is not.

So every pull request that can change a served picture attaches this benchmark's report, and the merge rule below
decides from it.

## What it is

`web/frames/image_bench.py` makes a fixed set of about 50 pictures (`web/frames/image_bench_items.json`) on two
commits, the base (usually `origin/main`) and the candidate (the PR's head). Then it compares them picture by picture.

- **The pictures are the site's own.** Each item is made by the pre-build's makers in that commit's code, with the
  full inputs (the lut8 archive, the JAN05 SPICE kernels, cisscal, the SPICE and geometry caches). A still is
  `frame_server.processed_webp` centred as Auto center asks. A composite is the camera window's filter set through
  `frame_server.color_webp`. A pass goes through `prebuild.make_pass`, then gives up the finished mosaic (1024 and
  full size), a mosaic movie's last rolling picture, or every frame of a movie, plus the evened frames for a pass the
  page cannot even itself. A toss-up pass that plays as a movie can also give its Mosaic view at chosen frames (the
  item's `mosaic_views`, through `obs_mosaic.mosaic_webp` as the window's Mosaic choice asks). Nothing is
  re-implemented.
- **Each commit is built alone**: its own worktree, its own scratch cache and its own copy of the geometry cache
  (the pipeline writes rows into that file, so two commits sharing it would overwrite each other's). A commit is built
  as committed: the tool refuses a checkout with uncommitted changes rather than quietly testing the old code.
- **The set** has two groups.
  - `hard` holds the cases recent changes fixed or broke: the Grand Finale ring mosaics HIPHASEFA and FB (#449, #456,
    #457), Day the Earth Smiled, the 2004 ring mosaic (#449), In Saturn's Shadow, 039RI's disk square, Jupiter
    ATMOS02A's gray panel (#455), Enceladus' crescent (#456), the SATELLORB002 centring (#450), the Daphnis A-ring
    movie (#400), a ring close-up and the G ring (#401), a CCD bloom frame, the approach and ring movies (#445,
    #402), Telesto's colour frame, and a toss-up ring pass's Mosaic view on the way and finished (#503).
  - `plain` holds pictures across 1999 to 2017 that must not change unless a change means to: the Moon, Venus,
    Masursky and Jupiter from cruise, then Saturn, its rings and the big and small moons. They come as stills, colour
    composites, movies and mosaics, including NAC and WAC, filled Titan passes, specks and dots.
- **Cost**, measured 2026-11-19 on main 701fd40f with 3 MacBook slots (a thread's cap under `~/agents/bin/heavy`),
  another thread's 3-slot job running beside it both times:
  - one commit takes 26.1 minutes for today's 53 items, against 33.8 minutes for the 54 items before (23% less);
  - the largest items are Earth Smiled, the backlit plume movie, Jupiter ATMOS and Grand Finale FA (7 to 10 minutes
    of one process each);
  - with `--hosts local,mini` the Mini takes a third of the items;
  - comparing two commits takes about 30 seconds, and the checks add about 15 seconds. The base is built once per commit and kept (`~/cassini-build/image-bench/results`),
  so a PR usually waits only for its own build. The scratch cache is removed once the pictures are taken out. The commit's
  worktree and the tool copy go too when a build ends (`--keep-worktree` keeps the worktree), so only results and
  reports stay on disk, and a build will not start with less than 60 GB free on its drive (`CASSINI_BENCH_MIN_FREE_GB`):
  a Mac needs that room for swap (the MacBook went down on 2026-11-16 with a full disk and no room to swap).

## Running it

From the PR's worktree (its code is the candidate; `~/.cassini-bench.json` names each machine's inputs, as in
`web/frames/image_bench.example.json`):

```bash
python web/frames/image_bench.py run --base origin/main --candidate HEAD --target ringsFB-mosaic,ringsFA-mosaic --notes bench-notes.json --hosts local,mini
```

- `--target` names the items the change means to change. A change that should touch everything (a new tone curve)
  passes `--target all` and says so in the PR.
- `--notes` is a JSON file `{"item": "why it changed"}` for every change outside the target. It is written after
  looking at the sheets, never before.
- The report lands in `~/cassini-build/image-bench/reports/<base>-<candidate>/`: `index.html` (every item, its
  numbers and its sheet), `report.md` (the table for the PR body), `summary.json`, and `sheets/<item>.jpg`. Each
  sheet shows base, candidate and the difference x4, with 1:1 crops where the picture changed most.

## Defect checks

The comparison says what changed between two commits. It cannot see a defect present on both sides, and most of what
Sam found by eye in cache builds was exactly that: a movie repeating frames, a Titan sequence in black and white, a
colour composite drawn gray in every build. So each item's pictures are also judged on their own by cheap, objective
checks (`web/frames/bench_checks/`), on the base and on the candidate:

| check | runs on | catches | proof (fails on, passes on) |
|---|---|---|---|
| `repeat_frames` | every movie | a played frame identical to the one before (Sam 11-17, #577); "played" is the commit's own `obs_mosaic.movie_shown` | daphnis17-movie: 19 repeats on 02598865, 0 on main |
| `odd_frame` | every movie | a frame unlike both neighbours while they agree, after moving them onto it (a doubled limb, a flash, a jump to another place) | saturn05-movie frame014 doubled Saturn: 5.6 on 5d600b52, 1.7 after #525 (limit 4) |
| `gray_colour` | every composite; passes that name it | a colour picture or sequence drawn gray | titan127-movie: 54 of 54 frames gray on f9ab1b49, 5 of 42 on main (limit 20%); june2004-mosaic gray on 5d600b52, chroma 0.46 on main |
| `body_tint` | items that name it | a colour cast on a near-neutral body | enceladus-eye-composite: R:G:B 1.04:1:0.89 (0.122) on 02598865, 1.01:1:0.99 (0.009) on main (limit 0.06) |
| `clipped_white` | items that name it, with their own limit | white blown out | ringmosaic04 13% at white on 1dcd9027, 0.08% after |
| `limb_halo` | items that name it | a black gap then a glow past a lit limb on black sky | saturn-limb-still: 0.185 on e755fd89, 0.031 on main (limit 0.08) |

`odd_frame`'s limit is the tight one: a good movie that pans (saturn05, a 3x3 movie whose played frames are each
a different crop) scores up to 3.3 on today's main, the doubled frame 5.6, the gray flash and the jump between views
40 and over. A fainter ghost scoring between 3.3 and 4 would pass; lower the limit only with every movie item's score
on main checked against it (`image_bench.py check`).

Each check gives a number (higher is worse), its limit and a line saying what it measured. Against the base it is:
**pass**; **fixed** (the base failed); **known** (both fail, the candidate no worse: a defect already on `main`,
listed in the report but not a failure by itself); **REGRESSION** (the candidate fails where the base passed, or fails
clearly worse), which makes the verdict `FAIL` unless the item is a target or `--notes` explains it; **error** (the
check broke on these pictures).

A check that breaks on the candidate, finds nothing to judge there, or judges far less of it (`Result.judged`, under
half the base's: a glow that lights the sky past a limb leaves few rays to judge), where the base was judged, is a
**REGRESSION** too: a blank or hidden picture never reads as a pass.

`python web/frames/image_bench.py check RESULTS_FOLDER [--items a,b]` judges one commit's results alone, with no base.
That is how a new check is proven: it must fail on a result of the old, bad commit and pass on a good one.

Adding a check: one module of your own in `web/frames/bench_checks/` (no shared file to edit, so threads never
collide); the module's notes give the whole interface: `@check(name, kinds, default)`, a function of the item's
pictures returning `Result(value, limit, ok, detail)`, an optional `collect` hook that runs inside the build with the
commit's own code (its data is kept in the item's `meta.json`), and optional `ITEMS` (the module's own targets).
Changing a collect hook rebuilds every base once; changing how a check judges does not.

## Known defects on main the benchmark sees

Listed so a fix can turn them from known to fixed (main 701fd40f, 2026-11-19):
- titan127-movie: a gray P60 polarizer frame (frame 6) and a lone GRN haze frame (frame 46) flash in a colour Titan
  movie (odd_frame).
- daphnis17-movie (257DA): the movie jumps back and forth between two views (odd_frame 118; the pointing thread's).
- plume279-movie: frame 250 and others drawn with another sky and footprint (odd_frame 12).
- storm-composite and hexagon-composite: drawn gray, their channels never aligned; moon99-composite (HAL/GRN/BL1)
  drawn exactly gray (gray_colour).
- june2004-mosaic: a green square background round Saturn (by eye; no check yet).
- phoebe-movie (out of the set): not deterministic, two builds of one commit differ, against the zero noise floor
  this benchmark relies on. A pipeline defect, not fixed.

## What the report says about each item

- **identical**: the same bytes. **same**: pixels differ by at most 2 levels (encoder rounding), counted as identical.
  **changed**: anything more. For a changed picture, the share of its pixels that moved by more than 8 levels.
- **Measures**, taken the same way on both sides:
  - `clipped`: the share of the lit picture at white.
  - `crushed`: the share of the base's light that is now black.
  - `lit`: the share of the picture with light in it. It drops when holes or black squares appear.
  - `mean`, `p99`, `chroma`: brightness and colour.
  - `detail`: mean |Laplacian| over mean brightness. It rises when a picture is sharpened, over-stretched or has its
    noise pulled up, which is the over-processed look.
  - `centre`: the lit area's centre, which moves when centring changes.
  - On full-size mosaics, `seam`: the step across the tiles' edges over the picture's own texture (seam95 / flat95,
    `seam_bench.measure`).
- **Worse by measure** (the guards in `image_bench.GUARDS`):
  - clipped up by 0.2 points
  - crushed over 0.2%
  - detail up by 15%
  - seam up by 10%
  - centre moved by more than 8 px
  - lit down by 2 points

## The merge rule

A PR that can change a picture (it bumps a picture version, or touches the pipeline, calibration, `obs_mosaic`,
`reel`, `frame_server`'s makers, `color_image`, `mosaic`, `stacking`) cannot merge without this report, run against the
`main` it will merge into. The report's verdict line, its table, and the sheets of every changed item go in the PR
body or as attached evidence.

It merges only when all of these hold.

1. **Every item is built on both commits.** An item the candidate cannot make is a regression, and so is a picture
   the base makes and the candidate no longer does.
2. **The target is better.** A named target that did not change at all fails: the change did not do what it says.
   - Each target item changed, and its sheet shows the defect gone or clearly smaller.
   - Where a measure covers the defect (seams, centring, clipping, holes), it moved the right way.
   - A target item that trips a guard is explained in the PR.
3. **Nothing outside the target is worse.**
   - No item outside the target trips a guard. One that does is a fail unless the PR explains why the number is
     misleading and Sam agrees.
   - By eye, each changed item outside the target looks the same or better on its sheet. One that looks worse is a
     fail, however much the target improves. That is the one-step-forward, two-steps-back case this rule exists for.
4. **Every change outside the target is explained.** It needs one line in `--notes`, which the report prints next to
   the sheet. "Encoder noise" is not an explanation for a picture that moved by more than 2 levels.
5. **No new over-processing.**
   - A change that raises `detail` or `clipped` on plain items fails, even under the guard, unless that is its stated
     target and the sheets show it looks better.
   - No sharpening, ever.

The tool decides rules 1, 2 (a target that did not change), 3 (the measures) and 4 by itself. It refuses `--target`
and `--notes` names that are not in the list. When a mosaic's tiles' edges could not be worked out, the report says
the seam guard is off for it. Its verdict is `FAIL` when any of them breaks, and it
exits with status 1. Otherwise the verdict is `PASS (nothing changed)` or `NEEDS EYES`. `NEEDS EYES` means the
reviewer, and Sam for anything he flagged, looks at every changed item's sheet for rules 2, 3 (by eye) and 5. A
review approves only after looking, and says which sheets it looked at.

"Broad improvement" (Sam's words) is read this way:
- The target is the improvement, and must be visible.
- Everything else stays identical, or changes in a way that is explained and looks no worse.
- A change meant to touch everything (`--target all`) must show more items better than worse by eye, and none worse
  in the `plain` group.

## Keeping the set useful

- **A new defect becomes an item and, where it can be measured, a check.** When a PR fixes a defect that is not in
  the set, it adds a small frame that shows it to `image_bench_items.json` (group `hard`, `watch` saying what to look
  at, `checks` naming the check that catches it), so later PRs guard it.
- **An item earns its time.** The list is the memory of what broke before, but a slow item that never caught
  anything, or that another item covers, goes (11-19, on Sam's ask for a fast run: the 290-tile Grand Finale FB
  mosaic, covered by FA, Earth Smiled and the 2004 ring mosaic; the Helene and 088EN toss-up movies, which never
  changed in 39 reports; the Phoebe movie, which is not deterministic; the 71-frame Jupiter WAC movie, whose evened
  frames approach-movie also covers). Prefer a small pass or a still that shows the
  defect to a long one. What the removed items watched: FB's cyan blob under Saturn (#456) is the saturated-glow
  rule (calibration.saturated_code) that FA's green and pink tiles still guard; tinted movie frames are now guarded
  on the NAC by titan127-movie (every frame drawn in its set's colour), and there is no tinted WAC movie in the set
  since jupiter-rmov-movie left (a gap, accepted for its 6 minutes).
- **The list's hash names the cached results.** Editing the list means every base is built again on its next run,
  which is automatic.
- **The noise floor is zero.** Building the same commit twice on the MacBook (12 items) and once on the Mini
  (14 items) gave byte-identical pictures on 2026-11-13 (`evidence/image_bench/noise-*.md`). So any change the
  report shows comes from the code. If a pipeline change ever breaks that, every run shows changes, and it must be
  fixed first.
