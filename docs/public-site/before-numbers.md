# Before numbers (WP0)

Measured 2026-11-11 by the zero-origin harness in `--mode before` against the sampler preview on the Mac Mini
(port 8955: frame_server.py at 8c121d5, cache `cache-diverse-8c121d5`), from the MacBook Pro, three minutes for the
playing sessions. Logs: `~/Documents/public-wp0/harness-before/` on the MacBook. Every later package compares its
sessions with these.

| Session | Requests | Origin | Refused | 404 | Marker | CDN | MB | Notes |
|---|---|---|---|---|---|---|---|---|
| S1 default play | 184 | 86 | 1 | 6 | 3 | 5 | 28.4 | |
| S2 movie mode | 518 | 341 | 1 | 7 | 3 | 5 | 33.1 | |
| S3 full view and lens | 351 | 154 | 3 | 6 | 9 | 10 | 28.8 | |
| S4 save menu | 160 | 62 | 1 | 1 | 2 | 5 | 27.9 | |
| S5 Movie Editor | 307 | 209 | 6 | 9 | 3 | 5 | 29.5 | the editor was still loading after 3 min; film steps left to WP7b |
| S6 shared links | 50 | 4 | 1 | 0 | 0 | 5 | 6.8 | not scripted yet (WP7b) |
| S7 Studio | 161 | 63 | 1 | 1 | 2 | 5 | 27.9 | looks and export left to WP7b |
| S8 phone | 482 | 274 | 1 | 6 | 2 | 5 | 21.0 | |
| S9 every setting | 680 | 528 | 205 | 24 | 5 | 5 | 33.4 | |

Requests to hosts other than the site and the CDNs: 0 in every session.

What they say:

- **Origin**: every frames request reaches the Mini today, 4 to 528 per session. On the public site these must all be
  answered by the Worker.
- **Refused**: the flag button's `/flags` request in every session (WP6 hides it); S5's film plan, server plan,
  Pre-process and exposure graph (WP7a, WP7b); S9's 165 `off=`, 29 `colors=` and 10 `look=` requests from the settings
  the public switch hides (WP6).
- **404**: all are `/frames/mosaic/<ID>.webp` answers for frames that are no mosaic tile, which the window asks for and
  reads as "keep the frame" (policy.json `probe_404`; the harness now counts them as `probe`), except S9's 17 movie and 4
  mosaic movie 404s from settings whose pictures are not pre-built (laps, trail and the like; WP6 hides them).
- **CDN**: three.js and the two fonts, 5 per page load (WP6 decides whether to host them on Pages).

## Report sizes as R2 metadata

From the same logs (`measure_headers.py`), each distinct URL once. Budget 2,048 bytes. **No report comes near it**, so
every picture keeps its report whole in metadata and no sidecar objects are needed on this sample.

| Route | Header | Pictures | p50 | p95 | Max | Trimmed max |
|---|---|---|---|---|---|---|
| color | X-Composite | 37 | 427 | 436 | 549 | 237 |
| processed | X-Composite | 326 | 372 | 375 | 387 | 188 |
| processed | X-Center (marker) | 28 | 65 | 238 | 238 | 141 |
| movie | X-Movie | 82 | 241 | 324 | 324 | 169 |
| mosaic_movie | X-Movie | 1 | 269 | 269 | 269 | 190 |
| mosaic | X-Reel | 200 | 242 | 242 | 242 | 203 |

The sample has few mosaic movies and long passes; WP3 re-measures on the rehearsal slice before upload.
