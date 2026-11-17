# Notes for agents working on this repo

## Showing Sam a moment: send a link

When you want to show Sam something at a specific moment of the mission (a picture, a flyby, a bug, a before/after),
send a Cassini OS link that opens on that moment and view, not just a date. The page keeps these query
parameters in its address bar at all times (`web/cassini-os/src/link.html`; README section "Shareable links"):

```
http://192.168.68.52:8765/?t=2005-02-17T05:46:09&view=enceladus&speed=3600&play=0
```

| parameter | value |
|---|---|
| `t` | mission time, UTC, to the second (`2005-02-17T05:46:09`; no `Z`) |
| `view` | `follow` (Cassini with the follow camera), `cassini` (Cassini, free camera) or a body in lower case (`saturn`, `titan`, `enceladus`, ...) |
| `cam` | optional free-camera position `x,y,z` around the view's target; only copy it from a real address bar, leave it out otherwise |
| `speed` | mission seconds per second of playback (`60`, `600`, `3600`, `86400`) |
| `play=0` | open paused, which is usually what you want for showing a single picture |
| `movie=1` | open in movie mode |
| `ambient=1` | open in ambient mode (or a mode: `live`, `60`, `600`, `3600`, `pictures`, `highlights`); `live` ignores `t` and runs ten years behind today |

Other parameters keep working alongside them (`?finale`, `?frames=`, `?tex=`).

- The host is the live site, `http://192.168.68.52:8765/` (or a preview port when the change is not merged yet).
  When Sam is away from home Wi-Fi, use the Tailscale address `http://100.76.189.126:<port>/` instead. Never link
  `/replay/`.
- Use a frame's own time for `t` (from the catalog, `web/replay/data/catalog`, or the frame's label) and pause it,
  so the camera windows show that picture when the page opens.
- To share a link you got from the page itself (a Playwright run, a flag in `/flags/`), copy `location.href` as it
  is: it already holds the time, view, camera and speed. In page code, `window.cassiniLink.href()` returns the same
  link.
- Put the link in the message next to the screenshot or video, so Sam can open the same moment and look around.

## Compute on the viewer's computer

Sam's rule (2026-10-27): the site must stay runnable on the one Mac Mini plus Cloudflare storage. So work that
depends on a viewer's settings (slider values, looks, smoothing, gains, mixes) runs in the page, on pictures and
small JSON the pre-build already holds. The server measures once per pass in the pre-build, draws only the one
default variant, and handles cold passes and exports. A page-side step is a line-for-line port with a test against
the Python (`web/test_steady_local.py`, `web/frames/test_studio_look.py`), never a second implementation. Read
`docs/compute-on-viewer.md` before adding a setting that changes pictures.

## Use every free core

Sam's rule (2026-11-09): there is no one-core limit and no cap on parallel renders. Before a render, an
evidence batch, a test sweep or a check, look at what is already running on each machine (`uptime`, `ps`,
the farm dashboard) and size the job to the free cores: the MacBook Pro (M5, 18 cores) and the Mac Mini
(10 cores), split across both when the job divides. When several threads need compute at once, share the
cores between them rather than each taking one. Background cache builds give way to thread work.

`OPENBLAS_NUM_THREADS=1` / `OMP_NUM_THREADS=1` are still right where the parallelism comes from many
processes (prebuild workers, the farm, long-running frame servers), so they don't oversubscribe; a
one-off job run as a single process should leave BLAS threads at their default or start one process per
free core.

## Image changes need the benchmark report

Sam's rule (2026-11-13): a pull request that can change a served picture (a picture version bump, or a change to the
pipeline, calibration, `obs_mosaic`, `reel`, `color_image`, `mosaic`, `stacking` or `frame_server`'s makers) runs the
image regression benchmark against the `main` it merges into, and attaches its report: the verdict, the table and the
sheet of every changed item.

```
python web/frames/image_bench.py run --base origin/main --candidate HEAD --target <items it means to change> \
    --notes notes.json --hosts local,mini
```

It merges only when every item builds on both commits, the target items look better, and nothing outside the target
is worse, by the measures (clipped, crushed, lit, detail, seams, centre) or by eye. Every change outside the target
must be explained in `--notes`, and the report must show no new over-processing. A `FAIL` verdict blocks the merge.
`NEEDS EYES` means the reviewer looks at every changed sheet before approving. A defect a PR fixes that is not in the
set goes into `web/frames/image_bench_items.json` in the same PR. The full rule and how the measures work are in
`docs/image-benchmark.md`.
