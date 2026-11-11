# WP4 · The Worker

Read `_common.md` first.

**Goal.** Answer every public frames-host request from R2 only.

**Owns.** New `web/worker/` (its code, `wrangler.toml` template without secrets, tests). Port 8911 for `wrangler dev`.

**Read first.** `web/public/policy.json`, `keys.json`, `keys.mjs` (import it; do not re-implement), `headers.json`,
`tables.schema.json`, `manifest.schema.json`.

**Do.**
- Read the manifest named by `MANIFEST_KEY` (cache it per isolate for a minute); tags come from it.
- `keys.canonical(method, url, manifest.families)`, then by store: `r2` (object, then each `fallback` key in order),
  markers (`x-status` in metadata: that status, `x-center` as X-Center, `x-body` as body), `table` (alias shard, then
  the part; for `info` add the alias's `n`; `answer` and `no_alias_answer` from the canonical result when given),
  `manifest` (`version`, `slices` fields), `worker` (`/health` 200 `ok public`; `POST /usage` counted in Workers
  Analytics Engine, 204), `refused` (404, 405 for a method; counted).
- The Cache API in front of R2; CORS and caching per `headers.json` `worker_adds`; X-* headers restored from metadata
  (whole or trimmed) or the sidecar; `Content-Disposition` only for `download=1`, named per `download_names`.
- No `fetch` to any origin anywhere in the code (D1). A test greps for it.

**Don't.** Transform a picture or a table.

**Tests.** Miniflare or `wrangler dev` tests on `key_fixtures.json` (every fixture answered per its store) and on WP3's
mirror (once it exists; a hand-made mirror of a few objects until then).

**Done when.** The harness sessions S1 and S3 pass against `wrangler dev` serving the mirror (`--mode public`).
