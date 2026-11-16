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

## Heavy jobs go through the limiter; clean up after yourself

On 2026-11-16 the MacBook hard-crashed: more than 100 benchmark processes filled its 48 GB of memory, and with
the disk full there was no room left for swap. Since then:

- **Every heavy job runs through `~/agents/bin/heavy`**, on both Macs: renders, evidence batches, benchmarks,
  test sweeps and builds. Use `heavy -n <processes> --name "<thread>: <job>" -- <command>`, and `heavy --status`
  shows who holds what. The limiter sets the slot count and the per-thread cap (`~/agents/heavy.max`,
  `~/agents/heavy.cap`) and caps each job's worker counts at its slots. It also waits for disk and memory room: no
  job starts under 60 GB free on the MacBook (50 GB on the Mini) or without about 2.5 GB of memory per slot, and
  `heavy-guard` pauses running jobs when either gets low. A job gets its own `TMPDIR`, which is deleted when the
  job ends. Don't start parallel work outside it.
- **Each thread deletes what it created as soon as it is done with it**: experiment folders, scratch checkouts and
  clones, benchmark worktrees, caches and results, temp files and old evidence. That is approved in advance (Sam,
  2026-11-16), but for a thread's own files only. Never delete what another thread or Sam created. Never delete
  the mission zips, the 12-bit originals, `cisscal`, the full-build or live caches, sparsebundles, or Sam's own
  files. Push or bundle any unpushed commits first.
- **Evidence is kept only as small final files**: on the PR (committed under `evidence/`) or in the project's
  shared folder. Working renders and intermediate caches go once the evidence exists.
- **When a thread finishes, it says what it deleted and how much disk is free** on each Mac it used
  (`df -h /System/Volumes/Data`).
