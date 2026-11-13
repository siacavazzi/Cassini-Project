# Report sizes as R2 metadata (gate G2)

Measured by `web/public/measure_headers.py` from the gate G2 harness logs (WP9b, 2026-11-13). Every picture's X-* report
fits the 2,048-byte metadata budget whole (largest 549 bytes), so `headers.json` keeps every report whole and trims
none. The rig's publish found the same: largest 646 bytes over all 113,411 objects (rig.md, publish
20261113T035852Z-7f88cd3bd56e).

## The private frame server (before)

`node web/public/harness/zero_origin.mjs --mode before`, S1 to S9, the switch-off page on public-release (Mini 8912/off)
with the sampler cache's frame server (8c121d51, port 8955) answering.

| route | header | pictures | whole p50 | whole p95 | whole max | over budget whole | trimmed p95 | trimmed max | over budget trimmed | needs |
|---|---|---|---|---|---|---|---|---|---|---|
| color | x-composite | 51 | 427 | 445 | 549 | 0 | 245 | 245 | 0 | whole |
| mosaic | x-reel | 232 | 242 | 242 | 242 | 0 | 203 | 203 | 0 | whole |
| mosaic_movie | x-movie | 2 | 261 | 269 | 269 | 0 | 190 | 190 | 0 | whole |
| movie | x-movie | 148 | 243 | 357 | 358 | 0 | 170 | 170 | 0 | whole |
| native | x-native | 2 | 135 | 159 | 159 | 0 | 10 | 10 | 0 | whole |
| processed | x-center | 39 | 65 | 65 | 238 | 0 | 65 | 141 | 0 | whole |
| processed | x-composite | 388 | 372 | 375 | 387 | 0 | 173 | 188 | 0 | whole |

## The rehearsal rig's Worker (after)

`--mode public`, S1 to S9, the rig's public page (public-release 7f88cd3b) with the Worker on the published mirror
(8915). The Worker answers each report from the object's metadata, so these are the reports as R2 keeps them.

| route | header | pictures | whole p50 | whole p95 | whole max | over budget whole | trimmed p95 | trimmed max | over budget trimmed | needs |
|---|---|---|---|---|---|---|---|---|---|---|
| color | x-composite | 41 | 421 | 445 | 549 | 0 | 245 | 245 | 0 | whole |
| mosaic | x-reel | 125 | 242 | 242 | 242 | 0 | 203 | 203 | 0 | whole |
| movie | x-movie | 75 | 261 | 357 | 358 | 0 | 170 | 170 | 0 | whole |
| processed | x-composite | 332 | 372 | 375 | 386 | 0 | 173 | 173 | 0 | whole |
