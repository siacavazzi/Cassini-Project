# Gate G2: the nine sessions through the Worker (WP9b)

**Result: pass.** On the rehearsal rig (WP9a, rig.md: public-release 7f88cd3b, publish 20261113T035852Z-7f88cd3bd56e,
113,411 objects), every session S1 to S9 runs every step with **origin 0, refused 0, miss 0**.

- **Before:** `zero_origin.mjs --mode before`, the switch-off page on public-release with the sampler cache's private
  frame server (8955).
- **After:** `--mode public`, the rig's public page (`build.py --public`, frames http://192.168.68.60:8915) served on
  localhost, with the Worker on the published mirror.

| Session | before: requests / origin / refused / miss | rig: requests / origin / refused / miss | rig: probe / cancelled / pending | MB before → rig |
|---|---|---|---|---|
| S1 Default play from a Moment, both cameras | 924 / 498 / 1 / 0 | 840 / **0** / **0** / **0** | 67 / 0 / 0 | 41.7 → 41.5 |
| S2 Movie mode at high speed through a movie pass and a mosaic movie | 690 / 416 / 1 / 0 | 613 / **0** / **0** / **0** | 4 / 0 / 0 | 41.1 → 41.0 |
| S3 Full view and the lens over a mosaic and a colour picture | 451 / 152 / 5 / 0 | 422 / **0** / **0** / **0** | 0 / 4 / 0 | 45.8 → 46.1 |
| S4 The save menu: PNG, archive frame, science link | 429 / 126 / 10 / 0 | 370 / **0** / **0** / **0** | 0 / 1 / 0 | 49.9 → 60.5 |
| S5 Movie Editor on a two-hour stretch | 321 / 220 / 19 / 7 | 879 / **0** / **0** / **0** | 227 / 0 / 0 | 37.0 → 45.6 |
| S6 A shared film link and a shared Studio edit in a fresh browser | 519 / 215 / 7 / 0 | 461 / **0** / **0** / **0** | 0 / 14 / 0 | 37.1 → 40.0 |
| S7 Studio: open a mosaic, change its looks, export | 371 / 71 / 3 / 0 | 124 / **0** / **0** / **0** | 0 / 0 / 0 | 54.1 → 35.2 |
| S8 Phone viewport, default play | 295 / 97 / 1 / 0 | 358 / **0** / **0** / **0** | 16 / 0 / 0 | 26.5 → 27.5 |
| S9 Every visible setting toggled in turn | 695 / 523 / 219 / 12 | 293 / **0** / **0** / **0** | 0 / 0 / 0 | 42.1 → 36.8 |

The before column's refusals were the flag button, native full view, `format=png` saves, the `.tif` and `.lbl`
downloads, the server film plan, levels and export, and S9's look and colour options. Its misses were mosaics the
private server had not made yet (S5) and movie frames and steady tables of passes the sampler cache had not built (S9).

**Every step ran** on the rig, S7 included: it now opens a real mosaic of The Day the Earth Smiled (W1752967401_1)
in Studio.

## What the counts mean

- **probe:** a 404 on `/frames/mosaic`, which the page reads as "keep the frame" (policy.json probe_404). They are no
  miss, but each is a Class B read. Most of S1's and S8's came from frames a mosaic pass's list leaves out (second
  exposures at a pointing). The camera windows now stop asking for those: S1 67 → 4 and S8 16 → 2 on this branch, with
  every mosaic still shown. S5's 227 come from the film plan's tries (`plan-local.js`, a port of `export.py`'s plan),
  which asks a mosaic of every frame of a mosaic pass. That is WP7a's rule to change on both sides together.
- **cancelled:** requests the page dropped itself (the mosaic lane's AbortController, a film the page finished).
- **pending:** none. The harness now counts a request with no answer by the end, so a hang cannot hide a missing
  picture.

## How to run it on the rig

The rig's own page server is `python -m http.server`. Its listen backlog of 5 resets connections when a page asks
many files at once, so three page opens timed out. The rig's address 192.168.68.60 is also not a secure context, so
the browser offers no WebCodecs and the page cannot make films (S5, S6). Neither applies on Pages over https. Run the
gate against the same files on localhost with a larger backlog:

    python3 web/public/harness/serve.py 8921 ~/cassini-build/public/wp9a/site-rig     # ThreadingHTTPServer, request_queue_size 128
    node web/public/harness/zero_origin.mjs --site http://127.0.0.1:8921 --frames http://192.168.68.60:8915 \
      --mode public --sessions S1,S2,S3 --channel chrome --out DIR

The M5 carried an overnight cache build at load 30 to 90 throughout. S1 in fixed steps took 12 minutes under it.
