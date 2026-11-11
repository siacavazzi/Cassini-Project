# Deploying the public site (WP8)

Scripts that put Cassini OS on Cloudflare: the page and its replay data on **Pages**, the frames **Worker** (WP4,
`web/worker/`) in front of the private **R2** bucket, a **switch** of the Worker to a finished publish, and a
**rollback**. Staging comes first, at `staging.<domain>`, locked behind Cloudflare Access. Production is the same
commands with `--env production --sams-go`, used only after Sam's go (G4 in `docs/public-site/README.md`).

```
viewer ──► staging.cassinios.com ──► Access (staging only: listed emails, one-time PIN)
                 │
                 ├─ /frames*, /reel*, /export*, /prebuild*, /flags*, /stats*, /debug*,
                 │  /version.json, /usage, /health, /jumplog ──► Worker routes ──► R2 (private), Analytics Engine
                 └─ everything else ──► Pages (index.html, about/, how/, icons/, models/, vendor/, data/)
```

The Worker sits on the **same host** as Pages through Worker routes, so the page asks its own origin for pictures
exactly as it asks the frame server today: no `?frames=`, no CORS, and one Access app covers both. The route list is
made from `web/public/policy.json` (`cf.py routes`), every policy route included, so a refused request reaches the
Worker, gets its 404 and is counted, rather than falling through to Pages. WP6's public build puts nothing under
those prefixes, and `cf.py build` refuses a build that would.

## Files

| File | What it does |
|---|---|
| `deploy.sh` | the commands below, for `--local`, `--env staging` or `--env production --sams-go` |
| `cf.py` | the helpers: routes, wrangler.toml, the clean site build, the Pages measurement, manifest check, switch history, the Access app, the Pages domain, rollback, the lock check |
| `wrangler.template.toml` | the Worker's config (bindings `BUCKET`, `USAGE`, vars `MANIFEST_KEY`, `SITE_ENV`; no workers.dev, no preview URLs); rendered per run with names from `site.env` |
| `site.env` | names only: domain, hosts, Pages projects, Worker, bucket, datasets, wrangler version, local ports |
| `cloudflare.env.example` | the credentials file Sam fills on the MacBook as `~/.cassini-cloudflare.env`, mode 600 |
| `publish-run.sh` | WP2's tables and fullview phases and WP3's publisher, year by year across the Macs, then one whole-range run that writes the manifest |
| `cost.py`, `pricing.json` | the cost sheet: requests and bytes per viewer-minute, and a month at 1,000 viewers |
| `before-counts.json` | WP0's measured frames requests per session, for a first cost sheet until real harness logs are copied |
| `dry_run.sh` | the local dry run: build, serve, deploy publish A, switch to B, roll back to A, each step checked |
| `make_test_mirror.py`, `local_r2.mjs` | a two-publish test mirror, and the loader that puts a mirror into wrangler dev's local R2 |
| `stub/worker.mjs` | a stand-in Worker for the local dry run only, until WP4 merges; deploy.sh refuses it anywhere else |
| `test_deploy.py` | tests, no network needed |

## Commands

```
web/deploy/deploy.sh --local|--env staging COMMAND
  preflight                      tools; credentials file mode 600; token works; bucket private (no r2.dev URL, no
                                 custom domain); staging's Access app
  build --data DIR [--out DIR]   the site from a clean git worktree at HEAD: the replay data from DIR put in the
                                 worktree's web/replay/data, then WP6's `build.py --public --out DIR`, which writes the
                                 whole static site; measured against Pages' limits; staging and local get robots
                                 "Disallow: /" and noindex; no hidden file inside, the build record beside it
                                 (DIR.build.json). Before WP6 merges, --local only: the private page and its files
  pages --site DIR               staging: make the Pages project if needed, put the Access app on, upload, attach
                                 the host and its DNS record, then check every name answers with the Access sign-in
  switch --manifest KEY          check KEY is in the bucket and valid (publishes upload the manifest last), deploy the
                                 Worker with MANIFEST_KEY=KEY, check the lock, add the step to the history
  rollback [--pages]             the Worker back to the version before the last switch (its code and MANIFEST_KEY
                                 together, `wrangler rollback`); --pages also rolls the site back
  status                         the history and what answers now
  all --data DIR --manifest KEY  preflight, build, pages, switch
```

The switch history is a JSON list kept in the bucket at `deploy/<env>/history.json` (no Worker route can read it:
every public key starts with a family, `manifest/` or `table/`), so either Mac can roll back. Every Cloudflare step
that changes something says what it does first; `cf.py` changes nothing without `--apply`.

## Staging, step by step (once Sam has given access)

1. Sam fills `~/.cassini-cloudflare.env` from `cloudflare.env.example` (token, account ID, R2 key pair, staging
   viewers' emails) and sets it to mode 600. In Zero Trust, Settings > Authentication must list **One-time PIN** (it
   is there on a new account): it is how the listed emails sign in. Without it staging stays locked, but to everyone. A thread copies it to the Mini over SSH if the Mini deploys.
2. `deploy.sh --env staging preflight`.
3. `deploy.sh --env staging build --data <replay data built at this commit>`; the measurement must say FITS.
4. `deploy.sh --env staging pages`: the Access app goes on **before** the upload and before `staging.<domain>` has a
   DNS record, so staging is never open; the lock check covers the host, a data file and `<project>.pages.dev`.
5. WP3 publishes the rehearsal slice (`publish-run.sh` or `publish.py`), which prints a manifest key.
6. `deploy.sh --env staging switch --manifest <key>`; then WP9 runs the nine harness sessions against staging.
7. A second publish and `switch`, then `rollback`, prove both on the real thing.

Nothing is public at any step: the bucket stays private, the Worker has no workers.dev name, staging and its
pages.dev names sit behind Access, and production refuses to run without `--sams-go`.

## What Sam gives (docs/public-site/README.md, "Cloudflare access")

1. A Cloudflare account on Workers Paid ($5 a month).
2. The domain on Cloudflare (cassinios.com was the pick; Cloudflare Registrar sells it at cost).
3. Zero Trust turned on, free plan (it asks for a team name): this is what Access needs.
4. One R2 bucket, `cassini-os`, private (no public access, no r2.dev URL).
5. One API token, that account and that zone only. Account: Workers Scripts Edit, Workers R2 Storage Edit,
   Cloudflare Pages Edit, Account Analytics Read, Access: Apps and Policies Edit. Zone: Workers Routes Edit, DNS Edit,
   Zone Read (wrangler looks the zone up by name for the routes).
6. One R2 access key pair, Object Read and Write on `cassini-os` only (the publisher).
7. The account ID.

All of it goes only into `~/.cassini-cloudflare.env`; never into the repo, a thread or memory.

## Local dry run

```
web/deploy/dry_run.sh --data web/replay/data      # needs node and npm; installs wrangler (site.env) once
```

It builds the site, serves it with `wrangler pages dev` (port 8918), loads a mirror into the local R2, runs the
Worker with `wrangler dev` (port 8917), and checks after each step which publish `/health`, `/version.json` and a
picture come from: deploy A, switch to B, rollback to A. `--mirror DIR --a KEY --b KEY` runs it on WP3's real mirror
instead of the test cards. Until WP4 merges it runs the stand-in Worker; set `WORKER_MAIN` to try another.

## Pages limits

Pages takes at most 20,000 files and 25 MiB a file. `deploy.sh build` measures every build and stops when it does
not fit. Measured on the Mini at df204dd with the whole-mission replay and coverage data (main e56c1f4's build, the
private page since WP6's `--public` has not merged): **1,357 files, 505.2 MiB, largest file 10.6 MiB (the 8k sky);
fits**, with 18,643 files and about 14.4 MiB per file to spare. The biggest folders are data/months (480 files,
227 MiB), data/tracks (561, 119 MiB), data/attitude (19, 57 MiB) and data/catalog (21, 50 MiB, largest 2007.json at
5.4 MiB, growing a little with WP7a's catalog fields).

## Costs

`cost.py --harness <zero_origin --out folders>` turns the harness's request logs into frames requests and bytes per
viewer-minute and prices a month at 1,000 viewers; `cost.py --ae --since ...` reads the live Worker's Analytics
Engine points (WP4: one per answer; blob1 store, blob3 cache, blob5 outcome, double1 bytes, double2 R2 reads).
Only the Worker side costs money: Pages and bytes out are free.
