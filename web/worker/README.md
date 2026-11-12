# The frames Worker (public site, WP4)

The public site's frames host. It answers every request the page sends to the frame server from R2 alone, by the
contracts in `web/public/` (brief: `docs/public-site/briefs/WP4.md`). It never forwards a request to an origin
(decision D1); the tests check that both by reading the source and by failing any outbound request.

| File | What it is |
|---|---|
| `src/index.mjs` | The Worker. Imports `web/public/keys.mjs` and the contract JSON as they are |
| `wrangler.toml` | Local template, no account and no secret. WP8's `web/deploy/` holds the deployed config |
| `tools/mirror.mjs` | Reads a publish mirror (`publish.py --to-dir`) into R2: in batches through a small loader Worker (one request per few hundred objects, so a 100,000-object mirror does not use up the ephemeral ports), retrying connection errors |
| `tools/dev.mjs` | Loads a mirror into wrangler's local R2 and starts `wrangler dev` on port 8911 |
| `tools/record_mirror.mjs` | A stand-in mirror until WP3: the frames requests of harness logs, asked of a frame server, written under their canonical keys |
| `test/fixture_mirror.mjs` | A hand-made mirror with an answer for each of the 232 key fixtures |
| `test/fixtures.test.mjs` | The bundled Worker in workerd (Miniflare) on that mirror |
| `test/unit.test.mjs` | Analytics Engine data points, 405s, sidecars, and D1 read from the source |

## How it answers

`keys.canonical(method, url, manifest.families)` names the store:

- **r2**: the object at the canonical key, then each `fallback` key in order. An object whose metadata holds
  `x-status` is a marker and is answered with that status, `X-Center` and body (Auto center's 404). The X-* report
  comes back from metadata (whole or trimmed) or from the sidecar `<key>.h.json` when `x-report-sidecar` is `1`.
  The Cache API sits in front of R2 (keyed by the R2 key, so a picture is cached once however it was asked).
  `download=1` adds `Content-Disposition` named per `headers.json` `download_names`. `If-None-Match` gets 304.
- **table**: the alias shard, then the pass-table part it names; `info` gets the alias's `n`. A frame in no pass gets
  the route's `no_alias_answer` (warm=1), or 404 `{"error": "not a mosaic pass"}` for the tile map, as the server does.
  `fade.json` with `w` or `h` 0 is `{"local": false}` without a read.
- **manifest**: `/version.json` and `/frames/slices.json` from the manifest named by `MANIFEST_KEY`, which is read once
  per isolate and kept a minute.
- **worker**: `GET /health` is `200 ok public` (with `X-Site-Env`); `POST /usage` is 204 and counts one of the page's
  words (`visit`, `visit-link`, `copy-link`).
- **refused**: 404, or 405 with `Allow` when the path is a route of another method.

Caching: pictures and table parts `public, max-age=31536000, immutable` (their keys change with their tags). The Cache
API sits in front of R2 for pictures and for the alias shards and pass-table parts a table answer reads, so a colo reads
each from R2 once; the isolate keeps its last 16 alias shards parsed. Manifest
answers and `no_alias_answer`s `public, max-age=60`, refusals, misses and markers `no-store`. No manifest: 503.

Bindings: `BUCKET` (R2), `MANIFEST_KEY`, `SITE_ENV` (local, staging, production), `USAGE` (Analytics Engine, optional),
`USAGE_SAMPLE` (optional; staging and production set 10).

## Counting

Analytics Engine data points (WP8's cost sheet and the gates). A point costs about as much as the Worker request, so
with `USAGE_SAMPLE` = N every Nth answer of an isolate that came back whole (below 400, outcome `ok` or `fallback`) is
written, weighing N, and the rest of those not at all; every refusal, miss, marker, `none`, error and POST /usage word
is written, weighing 1, so the gates count them exactly. Without `USAGE_SAMPLE`, one point per answer. Sum `double3`
(times `_sample_interval`) for answers. One point: `index1` the policy route id (`none` when
no route fits); `blob1` the store (`usage` for a counted word), `blob2` the status (the word for usage), `blob3` the
Cache API `hit` or `miss`, `blob4` the colo, `blob5` the outcome (`ok`, `fallback`, `marker`, `miss`, `none`,
`refused`, `error`); `double1` the response bytes, `double2` the R2 reads made, `double3` the answers it stands for.

## The mirror format

The mirror holds every object as a file at its R2 key and its metadata beside it as `<key>.meta.json`, in the shape of
R2's `put()` options (preferred):

```json
{"httpMetadata": {"contentType": "image/webp"}, "customMetadata": {"x-composite": "{\"observation\":\"...\"}"}}
```

A marker is an empty file with `{"httpMetadata": {"contentType": "application/json"}, "customMetadata":
{"x-status": "404", "x-center": "...", "x-body": "..."}}`. A flat map is read as `customMetadata` (with an optional
`contentType`), and a missing content type comes from the extension. Sidecars (`<key>.h.json`) are objects like any
other; the newest `manifest/<publish_id>.json` is the one served.

## Running it

```
cd web/worker && npm ci
npm test                                         # bundle with wrangler, then every test
node tools/dev.mjs --fixtures --fresh            # wrangler dev on :8911 with the fixture mirror
node tools/dev.mjs --mirror DIR --fresh          # ... with a publish mirror (WP3) or a recorded one
node tools/record_mirror.mjs --server http://127.0.0.1:8955 --out DIR harness-logs/S1.json harness-logs/S3.json
node ../public/harness/zero_origin.mjs --site http://127.0.0.1:8955 --frames http://127.0.0.1:8911 --mode public --sessions S1,S3 --out DIR
```

workerd in miniflare 4.20260730.0 takes compatibility dates up to 2026-08-06, so `compatibility_date` is 2026-08-01.
