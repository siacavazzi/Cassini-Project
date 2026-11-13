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
  page cannot even itself. Nothing is re-implemented.
- **The set** has two groups.
  - `hard` holds the cases recent changes fixed or broke: the Grand Finale ring mosaics HIPHASEFA and FB (#449, #456,
    #457), Day the Earth Smiled, the 2004 ring mosaic (#449), In Saturn's Shadow, 039RI's disk square, Jupiter
    ATMOS02A's gray panel (#455), Enceladus' crescent (#456), the SATELLORB002 centring (#450), the Daphnis A-ring
    movie (#400), a ring close-up and the G ring (#401), a CCD bloom frame, the approach and ring movies (#445,
    #402), and Telesto's colour frame.
  - `plain` holds pictures across 1999 to 2017 that must not change unless a change means to: the Moon, Venus,
    Masursky and Jupiter from cruise, then Saturn, its rings and the big and small moons. They come as stills, colour
    composites, movies and mosaics, including NAC and WAC, filled Titan passes, specks and dots.
- **Cost**, measured 2026-11-13 while other threads shared both Macs:
  - one commit takes 17.8 minutes on 12 MacBook processes, or 24.5 minutes on 8 of the Mini's;
  - the long pole is the 290-tile Grand Finale mosaic (about 10 minutes even with its tiles spread over the cores);
  - with `--hosts local,mini` the Mini takes a third of the items;
  - comparing two commits takes about 30 seconds. The base is built once per commit and kept (`~/cassini-build/image-bench/results`),
  so a PR usually waits only for its own build. The scratch cache is removed once the pictures are taken out.

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

1. **Every item is built on both commits.** An item the candidate cannot make is a regression.
2. **The target is better.**
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

The tool decides rules 1, 3 (the measures) and 4 by itself. Its verdict is `FAIL` when any of them breaks, and it
exits with status 1. Otherwise the verdict is `PASS (nothing changed)` or `NEEDS EYES`. `NEEDS EYES` means the
reviewer, and Sam for anything he flagged, looks at every changed item's sheet for rules 2, 3 (by eye) and 5. A
review approves only after looking, and says which sheets it looked at.

"Broad improvement" (Sam's words) is read this way:
- The target is the improvement, and must be visible.
- Everything else stays identical, or changes in a way that is explained and looks no worse.
- A change meant to touch everything (`--target all`) must show more items better than worse by eye, and none worse
  in the `plain` group.

## Keeping the set useful

- **A new defect becomes an item.** When a PR fixes a defect that is not in the set, it adds the frame to
  `image_bench_items.json` (group `hard`, `watch` saying what to look at), so later PRs guard it.
- **Every item stays.** The list is the memory of what broke before. An item is removed only when its frame leaves
  the archive.
- **The list's hash names the cached results.** Editing the list means every base is built again on its next run,
  which is automatic.
- **The noise floor is zero.** Building the same commit twice on the MacBook (12 items) and once on the Mini
  (14 items) gave byte-identical pictures on 2026-11-13 (`evidence/image_bench/noise-*.md`). So any change the
  report shows comes from the code. If a pipeline change ever breaks that, every run shows changes, and it must be
  fixed first.
