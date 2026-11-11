# WP8 · Cloudflare setup, deploy and staging

Read `_common.md` first.

**Goal.** The site deploys from scripts, first to a locked staging host, and rolls back.

**Owns.** New `web/deploy/`.

**Read first.** `docs/public-site/README.md` (Cloudflare access), `manifest.schema.json`, `keys.json` (manifest),
WP4's `web/worker/` once it exists, `src/build.py` (WP6 adds `--public`).

**Do.**
- `wrangler.toml` for the Worker (R2 binding, Analytics Engine dataset, `MANIFEST_KEY` var) and the Pages project
  config, with no secret in the repo; a staging host behind Cloudflare Access.
- `deploy.sh`: builds the site with the public switch from a clean output (no evidence folders), deploys Pages and
  the Worker, switches `MANIFEST_KEY` to a given manifest, and rolls back to the previous one.
- `publish-run.sh`: runs WP2's phases and WP3's publisher year by year after the full cache build, on both Macs.
- Measure the Pages upload (files, largest file, total) against Pages' limits (20,000 files, 25 MiB a file).
- A cost sheet from Analytics Engine and R2 metrics: requests and bytes per viewer-minute, cost at 1,000 viewers.

**Needs from Sam, only for the live parts** (README "Cloudflare access"): Workers Paid, the domain on Cloudflare, one
private R2 bucket, one API token with the listed scopes, one R2 access key pair, the account ID, in
`~/.cassini-cloudflare.env` on the MacBook. Until then everything runs against WP3's mirror and `wrangler dev`.

**Done when.** A dry run against the mirror and `wrangler dev` deploys, switches and rolls back; with Sam's access, the
same against staging.
