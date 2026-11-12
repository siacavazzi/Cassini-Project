# The public site: contracts, packages and gates

This folder is the working copy of the plan [Public site build plan for parallel agents](https://claude.ai/artifact/HsnpHVbnS1kQEqFd9v6HjD)
(Nov 5), brought up to date with the code at regression-2017 `8c121d5`, now merged into main (`e56c1f4`, Nov 11), by its contracts package, WP0. The goal is the
one Sam set: the site carries on the order of 1,000 viewers because a viewer's browser talks only to Cloudflare. Pages
serves the viewer and its replay data, a Worker answers every picture and table from R2 (or answers 404), and nothing
reaches an origin. The Mini builds the cache, then publishes it.

Everything a package builds against is in `web/public/`. Each package's brief is in `briefs/`. A package owns only
the files its row in [Work packages](#work-packages) lists, so the nine Wave 1 packages can be built at the same time by
agents that never talk to each other.

## What changed since the Nov 5 plan

The plan was written against `main` at 5609624. Since then regression-2017 took 107 merges (nine on Nov 11) and was merged into main on Nov 11. Most
change pictures, not routes, but a few change what the public site has to answer. Each item says which package or brief
it changed.

| # | What changed | Effect on the plan |
|---|---|---|
| 1 | regression-2017 was merged into **main** on Nov 11 (main `e56c1f4`). | Every branch is cut from main and every PR targets it (Rules). |
| 2 | Picture versions bump almost daily (several times on Nov 11 alone). | The plan's single version prefix is replaced by **per-family tags** computed from `frame_server.picture_versions()` at publish time, recorded in a publish **manifest** (`keys.json` families, `manifest.schema.json`). No contract names a version, and a test enforces that. A bump of the mosaic maker re-publishes the pass pictures and tables, not every frame. WP3, WP4, WP8 changed. |
| 3 | **HDR highlights** (#361 to #364): on an HDR screen the page asks `hdr=1` and the server makes an AVIF on demand. Prebuild makes none. | New decision **D8**: HDR is off on the public site by default, `hdr` is dropped from keys, and the setting is hidden. WP6 changed. |
| 4 | **Pointings opened on their own** (`/frames/mosaic/<ID>/p/<n>.webp`) are made on demand at full size; prebuild makes none. | New decision **D9**: not published; the drill-down opens the pointing's frame or colour picture instead. WP5 changed. |
| 5 | Page features from #399: "What Cassini is doing" (`activity.html`), "Seen so far" and "Pictures of a place" (`coverage.html`, data from `web/replay/build_coverage.py`), plus `orbit.html` and `surface-sites.html`. | They read static replay data (Pages) and frame thumbnails at `size=128`, which the frames phase builds. No new package; WP6's static build must include `data/coverage/`, and WP8 must re-measure the Pages upload (the plan's 572 MB and 1,721 files predate coverage data). |
| 6 | Steady movies on this computer (#149 onwards) ask for movie planes (`color=0`) and, for filled passes, planes before detail (`detail=0`); prebuild makes both at 1024. Movies with `exposure=8` are prebuilt only for passes the page cannot even itself. | Policy allows exactly those (`policy.json` movie). WP5's brief says how to tell a miss from a refusal. |
| 7 | Films up to 1024 px per camera are already made in the page (`export.html`, compute-on-viewer row 6), with film stabilization (`film-steady.html`) and colour smoothing (`colour-smooth.html`) ported. | WP7b is smaller: it removes the server fallbacks under the public switch rather than building the page path. |
| 8 | Square camera windows (#338) merged, so the plan's risk about #287 rebasing is gone. `head-quiet.html` still changes often (HDR, colour smoothing). | WP5 rebases daily and keeps every change behind the switch, as before. |
| 9 | Tile maps are kept per layout (`MAPS_DIR/<layout>.json`), steady and fade tables are per pass, and pass_info's only per-frame field is `n`. | One alias per frame is replaced by **alias shards** (one JSON per camera per 100,000 s of spacecraft clock), each frame naming its pass, index and tile map. Several hundred thousand fewer R2 objects. WP2, WP4 changed (`tables.schema.json`). |
| 10 | `resolve()` needs the cache folder. | Signature is `resolve(path, query, cache) -> Answer` (`web/frames/resolve.py`). WP1, WP3 changed. |
| 11 | Sam's rule of Nov 9: use every free core on both Macs, no cap on parallel renders. | Rules updated; the plan's one-LaCie-job rule stays for disk, not CPU. |
| 12 | The test baseline the plan quotes (8 failing scripts on main, Nov 5) is stale. | Each package records the failing scripts on main at its branch point and adds none (Rules). WP0 could not run the suite in the cloud (no archive data there). |
| 13 | three.js and the fonts load from jsDelivr and Google Fonts. | The harness counts them apart (`cdn`). WP6 decides whether to bring them onto Pages; the gate counts them only if Sam wants zero third-party hosts. |

The plan's design, packages, waves and gates otherwise stand.

## Contracts (`web/public/`)

| File | What it fixes | Who reads it |
|---|---|---|
| `policy.json` | Every route the frame server answers, in its own order, and what the public site does with it: the store that answers (`r2`, `table`, `manifest`, `worker`, `refused`) and every parameter value allowed. Decisions D1 to D9 are written into it. | WP1 (`--public`), WP3, WP4, WP5 to WP7b |
| `keys.json` | How a URL becomes an R2 key: `{family}/{tag}/{path}~{sorted query}`, defaults and no-op parameters dropped, sizes snapped to built sizes, the family tags, the manifest and the table keys. | WP3, WP4 |
| `keys.py`, `keys.mjs` | The two implementations of the above (Python for the publisher, JavaScript for the Worker and the page), line for line. | WP3 imports keys.py; WP4 and WP5 import keys.mjs |
| `key_fixtures.json` | 232 URL-to-answer pairs covering every route, every refusal and every no-op parameter. Both implementations reproduce all of them. | `test_contracts.py` (keys.py), `test_keys.mjs` (keys.mjs) |
| `headers.json` | The X-* reports, the fields the page reads, how they are kept as R2 metadata (whole, trimmed, or a sidecar object, under a 2 KB budget), markers for Auto center's 404, what the Worker adds (CORS, caching, download names). | WP3, WP4 |
| `tables.schema.json` | Alias shards and pass-table parts (info, kind, steady, fade, maps): exactly what the routes answer, once per pass. | WP2 writes, WP3 uploads, WP4 reads |
| `manifest.schema.json` | The one object a publish uploads last: family tags, the versions behind them, slices and version.json. | WP3 writes, WP4 reads, WP8 switches |
| `web/frames/resolve.py` | `resolve(path, query, cache) -> Answer` (file, negative or none) as a signature; raises until WP1 fills it. | WP1 fills, WP3 calls |
| `harness/` | The zero-origin harness and the nine sessions (below). | every package's evidence; the gates |
| `measure_headers.py` | Report sizes against the metadata budget, from harness logs. | WP3 |
| `test_contracts.py` | The contracts agree with each other and with the code: every server route has a policy route (a new route fails it), sizes and limits are the code's constants, schemas are valid, no version string anywhere. | CI for every contract PR |

A change to a contract file is a small PR of its own, through review, with the fixtures regenerated
(`python web/public/keys.py --fixtures`) and both tests passing. Other packages rebase on it.

## Decisions for Sam

Nine choices change what visitors see. Each has a default the agents build, so none of them blocks Wave 1. Sam can
change any of them; the package it lands in is named.

| # | Decision | Default the agents build | The alternative | Packages |
|---|---|---|---|---|
| D1 | An origin for viewers at launch | None. The Worker never forwards; films above 1024 px, Full size, Pre-process and science TIFFs stay on the Mini's private site | A small capped origin for server films | WP4, WP7b |
| D2 | Body reels | Off on the public site | A reels phase in the prebuild | WP6 |
| D3 | Full view of mosaics | A 2048 px picture of each pass's finished mosaic; while a pass builds, full view shows 1024 | 2048 at every frame, or 1024 only | WP2, WP5 |
| D4 | The Auto center switch | Always on in public | Prebuild uncentred copies | WP6 |
| D5 | One channel of a colour picture | Cut from the composite in the page, tested against the server's channel | Prebuild every channel | WP5 |
| D6 | Raw and science downloads | Archive frames from R2; science TIFF and PDS label link to OPUS | OPUS links for all three | WP3, WP5 |
| D7 | Opening a shared film | Made in the viewer's browser, with a progress note | Uploads of finished films | WP7b |
| D8 (new) | HDR highlights | Off on the public site; the usual pictures on every screen | An HDR phase in the prebuild (AVIF at 512 and 1024 for every composite, processed frame and pass picture; size not measured) | WP6, WP2 if chosen |
| D9 (new) | A mosaic pointing opened on its own | Not published; the drill-down opens the pointing's frame or colour picture | A pointings phase in the prebuild (full-size picture per pointing) | WP5, WP2 if chosen |

## Work packages

No two packages own the same file. `src/` is `web/cassini-os/src/`. The built `web/cassini-os/index.html` belongs to
nobody: each page package rebuilds it with `python web/cassini-os/src/build.py`, and on a merge conflict takes the base's
copy and rebuilds. Sizes are agent-days, my estimate.

| WP | Wave | Goal | Owns (only these) | Needs | Size |
|---|---|---|---|---|---|
| WP0 | 0 | Contracts and the zero-origin harness | `docs/public-site/`, `web/public/` (harness sessions pass to their owners below), `web/frames/resolve.py` until WP1 | nothing | 0.5 |
| WP1 | 1 | Cache-only resolver and `--public` mode | `web/frames/frame_server.py`, `web/frames/resolve.py`, read-only naming helpers added to `web/frames/obs_mosaic.py` and `web/frames/reel.py`, new `web/frames/test_resolve.py` | WP0 | 2 |
| WP2 | 1 | Tables phase and full-view pictures | `web/frames/prebuild.py`, new `web/frames/tables.py`, new `web/frames/test_prebuild_tables.py` | WP0 | 1 |
| WP3 | 1 | Publisher to R2 and to a local mirror | new `web/frames/publish.py`, new `web/frames/test_publish.py` | WP0; WP1's resolve (stub until it merges) | 1.5 |
| WP4 | 1 | The Worker | new `web/worker/` | WP0 | 1 |
| WP5 | 1 | Camera windows, lens and save menu | `src/head-quiet.html`, `src/steady-local.html`, `src/loupe.html`, `web/public/harness/sessions/s1.mjs` to `s4.mjs`, `s8.mjs` | WP0 | 2 |
| WP6 | 1 | The public switch, settings and small modules | `src/settings.html`, `src/about.html`, `src/link.html`, `src/loading.html`, `src/flag.html`, `src/reel.html`, `src/highlights.html`, `src/dock.html`, `src/bodymode.html`, `src/coverage.html`, `src/build.py` (including inlining WP7a's two files), `src/site.json`, new `web/test_public_switch.cjs`, `web/public/harness/sessions/s9.mjs` | WP0 | 1 |
| WP7a | 1 | Page ports of the film plan and the exposure levels | new `src/plan-local.js`, `src/levels-local.js`, `web/test_plan_local.py`, `web/test_levels_local.py` | WP0 | 1 |
| WP7b | 1 | Movie Editor, films, Gallery and Studio | `src/movieedit.html`, `src/export.html`, `src/segment.html`, `src/gallery.html`, `src/studio.html`, `web/public/harness/sessions/s5.mjs` to `s7.mjs` | WP0; WP7a's API (stub until it merges) | 1.5 |
| WP8 | 1 | Cloudflare setup, deploy and staging | new `web/deploy/` | WP0; Sam's Cloudflare access for the live parts only | 1 |
| WP9 | 2 | Integration on the rehearsal slice | an integration branch; fixes go to each file's owner | WP1 to WP8 | 1 |
| WP10 | 3 | Full publish and the 1,000-user check | runs only | WP9 and the full cache build | 1 + upload |

The full cache build (about 38 h, about 350 GB) and these packages do not wait for each other: no package changes a
picture or a version, and WP2's two phases run on a finished cache in a few hours.

## Cloudflare access Sam will need to give

Nothing in Wave 1 needs Cloudflare. Every package runs against the local mirror (`publish.py --to-dir`) and
`wrangler dev` or Miniflare. The first package that needs real access is **WP8, when it deploys staging**, and right
after it **WP3's first real upload** (the WP9 rehearsal on staging R2). At that point Sam does these steps on the
Cloudflare dashboard, on his own computer:

1. **The account and plan.** A Cloudflare account on **Workers Paid** ($5 a month: Workers with Analytics Engine and
   the CPU the Worker needs; R2 is billed by use on top).
2. **The domain** on Cloudflare (its nameservers moved there), so the site and the frames host get their own names.
3. **One R2 bucket**, private (no public access, no r2.dev URL), for example `cassini-os`. Staging and the public site
   share it under different manifests.
4. **One API token** for the deploy scripts (WP8), scoped to that account and zone only:
   Account: Workers Scripts Edit, Workers R2 Storage Edit, Cloudflare Pages Edit, Account Analytics Read, Access: Apps
   and Policies Edit (the staging lock); Zone (the domain): Workers Routes Edit, DNS Edit.
5. **One R2 access key pair** for the publisher (WP3), from R2 "Manage API tokens", with Object Read and Write on
   that bucket only.
6. The **account ID**.

The token, the key pair and the account ID are kept in a file on the MacBook that Sam writes himself
(`~/.cassini-cloudflare.env`, mode 600) and that a thread copies to the Mini over SSH; they are never put in the repo,
in a thread message or in memory. Nothing becomes public until Sam says go (G4): staging stays behind Cloudflare Access
and the bucket stays private.

## Rules for every agent

These come from the project's standing rules and from what went wrong on the Mini; a brief never overrides them.

- **One package, one branch, one PR.** Branch `claude/public-<wp>` off `main` (off this WP0 branch until
  WP0 merges, then merge main in). The PR targets main, starts with the attribution block and carries before and
  after evidence: screenshots, recordings or harness request logs. Nothing merges until Sam says "merge", and every PR
  goes through the review thread first.
- **Own only your files**, as the table lists them. A change you need in someone else's file goes to the lead thread
  as a request. A change to a contract file is a small PR of its own.
- **Output-neutral.** No change to any picture, cache folder name or version string. Where you touch
  `frame_server.py`, `obs_mosaic.py` or `prebuild.py`, show a sample of pictures byte-identical before and after.
- **No versions in code you write.** Keys come from `keys.py` / `keys.mjs` with tags from the manifest.
- **The built index.html.** Rebuild it with `python web/cassini-os/src/build.py`; on a conflict take the base's copy and
  rebuild. Never edit it by hand.
- **Tests.** Run the full suite at your branch point on main and record which scripts already fail; your PR
  adds no failure. `python web/public/test_contracts.py` and `node web/public/test_keys.mjs` always pass.
- **Ports.** This effort uses 8910 to 8919: WP1 8910, WP4 8911, WP5 8912, WP6 8913, WP7b 8914, WP9 8915 and 8916. Check
  a port is free with `lsof -nP -iTCP:<port> -sTCP:LISTEN` and confirm your listener's working folder before trusting
  it. Other threads use 8765, 8866, 8880 to 8901, 8930 to 8955.
- **Replay data is not in git.** A preview worktree needs `web/replay/build_data.py` at its own commit (about 5 min) and
  `build_coverage.py` before the page loads.
- **Compute.** Use every free core on the MacBook Pro (18) and the Mini (10), split across both, sharing with other
  threads; background cache builds yield. Post each piece of evidence as soon as it exists.
- **Disks.** One LaCie job at a time. Work from the T7 build drive (`/Volumes/SAM_IAC_PHOTO/cassini-work`, photos
  untouched) or the sampler and arrival caches there, read-only. Keep 50 GB free on the Mini's SSD. Never point a
  server at the live cache for writing, never touch Sam's photography, Lightroom or the lut8 and JAN05 zips.
- **Cloudflare.** Nothing public: staging behind Cloudflare Access, bucket private until Sam says go. Credentials only
  from the environment.
- **The pipeline rule.** Pictures only ever come from the repo's makers; page steps are line-for-line ports with tests
  (`docs/compute-on-viewer.md`); the separate NAC and WAC windows, mosaics and colour composites stay as they are.
- **Don't wait on Sam.** Build the defaults under Decisions, and ask only before a step that can't be undone.

## Gates

Launch is decided by the nine scripted sessions in `web/public/harness/`, not by review alone:

```
node web/public/harness/zero_origin.mjs --site <page> [--frames <frames host>] --mode before|public --out <dir>
python web/public/measure_headers.py <dir>
```

Per session the harness counts **origin** (requests that reach an origin: in `--mode before` every frame-server request,
in `--mode public` any host but Pages, the Worker and the listed CDNs; must be 0), **refused** (frames-host requests
`policy.json` refuses; must be 0), **miss** (allowed requests answered 404 or worse, Auto center's X-Center markers
counted apart; must be 0) and **cdn** (reported).

| Session | What it does | Owner | Proves |
|---|---|---|---|
| S1 | Default play from a Moment for three minutes, both cameras | WP5 | WP5, WP6 |
| S2 | Movie mode at high speed through a movie pass and a mosaic movie | WP5 | WP5 |
| S3 | Full view and the lens over a mosaic and a colour picture | WP5 | WP5, WP2 |
| S4 | The save menu: PNG, archive frame, science link | WP5 | WP5, WP3 |
| S5 | Movie Editor on a two-hour stretch: open, preview, change the look, make a 1024 px film, download | WP7b | WP7a, WP7b |
| S6 | A shared film link and a shared Studio edit, opened in a fresh browser | WP7b | WP7b |
| S7 | Studio: open a mosaic, change its looks, export | WP7b | WP7b |
| S8 | Phone viewport, default play | WP5 | WP5 |
| S9 | Every visible setting toggled in turn | WP6 | WP6 |

S5 to S7 are scripted as far as today's page allows; the steps their owner adds are logged as skipped, so a run says
plainly what it did not exercise.

- **G0**, contracts accepted (this PR merged): Wave 1 starts.
- **G1**, each PR: its own tests pass against the branch-point baseline, the sessions its brief names pass on a local
  mirror, the PR carries before and after evidence, and Sam says "merge".
- **G2**, rehearsal slice (WP9): all nine sessions pass through the Worker; `published.json` lists nothing missing for any
  URL class the policy allows; `--public` and R2 return the same bytes for 1,000 sampled URLs; a recording of each session.
- **G3**, whole mission (WP10): G2 on ten stretches spread over 1997 to 2017; cost per viewer-hour from measured
  requests and bytes per minute; 100 simulated viewers from a cloud runner with no errors and their p95 picture time.
  The tools are in `web/public/load/` (WP10a): `g3_stretches.mjs` (the ten stretches), `cost_model.mjs` and
  `load_runner.mjs`. The runner targets the rehearsal rig only; load on Cloudflare staging needs a reviewed change and
  Sam's word.
- **G4**, go public: Sam's word.

## Risks

- **Object count.** One object per published URL, plus markers, tables and alias shards: still a few million. WP3
  reports the real count on the rehearsal slice before any upload.
- **R2 metadata.** If reports exceed the 2 KB budget even trimmed, those pictures need a sidecar object and a second R2
  read on a cold edge. `docs/public-site/header-sizes.md` holds the measurement on a current cache.
- **Misses the policy cannot see.** A URL the policy allows can still be one the prebuild never makes (an uncentred
  movie frame, a `force=1` mosaic of a pass that is not a toss-up). The harness counts them as misses; the first run on
  the rehearsal mirror (WP9) lists them, and each goes to WP2 (build it) or WP5 (stop asking).
- **Pages limits.** Pages takes at most 20,000 files and 25 MiB a file. WP8 measures the replay data with coverage
  before relying on it.
- **Files shared with other threads.** `head-quiet.html`, `settings.html` and `about.html` (#414) change in other PRs, and
  `obs_mosaic.py` changes with the mosaic defect work; WP1, WP5 and WP6 merge main in daily and keep every change behind
  the public switch or output-neutral.
