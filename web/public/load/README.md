# Gate G3 tools (public site, WP10a)

Gate G3 (the plan's WP10): G2 again on ten stretches spread over the mission, cost per viewer-hour from measured
requests and bytes per minute, and 100 simulated viewers with no errors and their p95 picture time reported. These
tools take the zero-origin harness's logs (`web/public/harness/zero_origin.mjs --out DIR`) and do the last two; the
first is the harness itself, run on the ten stretches.

| File | What it is |
|---|---|
| `load_runner.mjs` | Replays harness logs as N viewers (default 100) against the rehearsal Worker; errors and picture times |
| `cost_model.mjs` | Requests, R2 reads and bytes per viewer-minute by what Cloudflare bills; cost at 1,000 viewers, with WP8's `web/deploy/pricing.json` |
| `stretches.json` | The ten G3 stretches (2000 to 2017), each a moment the page itself offers, plus two spares |
| `g3_stretches.mjs` | Runs harness session S1 on each stretch (`--moment`, `--speed`), G2's counts per stretch, then the cost model |
| `fixture_log.mjs` | A log of every key fixture, so the runner can be run on the Worker's fixture mirror without the rig |
| `replay.mjs` | Shared: reading logs, request classes, the target guard, percentiles |
| `test_load.mjs` | `node --test web/public/load/test_load.mjs` |

## Load only goes to the rig

`load_runner.mjs` and `g3_stretches.mjs` refuse any target that is not this computer, the home network (10/8,
172.16/12, 192.168/16) or the tailnet (100.64/10): the host is resolved and every address must be private, and
`*.workers.dev`, `*.pages.dev`, `*.r2.dev`, `*.ts.net` and any `cassinios` name are refused by name. The frames host
must then answer `/health` with 200 and `X-Site-Env: local`, with no `CF-Ray` and no `Server: cloudflare`, so a local
address that forwards to Cloudflare (`wrangler dev --remote`, a tunnel, a proxy) is refused too. The `--site` host
(Pages or a static copy) has no `/health` and gets the address check only; by default its requests are not replayed.
There is no flag around either check. Load on Cloudflare staging would be a change to `replay.mjs`, through review, with Sam's word.

## The G3 run on the rig (WP9a: Worker on 8915, page on 8916)

```
# 1. G2 on the ten stretches (three minutes each, S1 default play), then the cost model on their logs
node web/public/load/g3_stretches.mjs --site http://HOST:8916 --frames http://HOST:8915 --out ~/cassini-build/public/g3/stretches

# 2. the cost model on any logs, with the session mix of a visit (S1 default play most of the time)
node web/public/load/cost_model.mjs --mix S1=6,S2=2,S3=1,S8=1 --json cost.json ~/cassini-build/public/g3/stretches/*/ G2-LOGS/

# 3. 100 viewers, arriving over a minute, each replaying one stretch's log as recorded
node web/public/load/load_runner.mjs --frames http://HOST:8915 --viewers 100 --ramp 60 --out ~/cassini-build/public/g3/load ~/cassini-build/public/g3/stretches/*/
```

Run the load from a different computer than the Worker (the Mini against the MacBook's rig over the LAN), so the load's
own CPU does not slow the Worker it measures. The runner warns when its own event loop lags (then run two runners with
50 viewers each). Wrangler dev on a Mac is not Cloudflare's edge: G3's picture times on the rig show the Worker's and
the mirror's own cost, not a visitor's; the edge's times come with staging.

## What the runner judges

Each answer is compared with the status the harness logged for the same request: the same status is **ok** (a probe's
or a marker's 404 and a refusal's 404 or 405 included); a network error, a timeout or a 5xx is an **error**; a logged
answer that is now 404 is a **miss**; any other difference is **changed**. G3 passes when all three are 0. Picture
time is from sending the request to its last byte; a viewer keeps at most `--per-host` (6) requests open to a host, as
a browser does on HTTP/1.1, and the time a request waits for a slot is reported apart (`wait95`). Only GET and HEAD are
replayed (the page's `POST /usage` has no body in the logs), and static requests only with `--site`.

## What the cost model counts

From the Worker's code (`web/worker/src/index.mjs`), per frames request: one Worker request, its CPU (`--cpu-ms`,
default 1) and one Analytics Engine data point; a picture is one R2 Class B read unless the Cache API answers it
(`--edge-hit`, default 0.5, the capacity report's pessimistic share), a 404 reads every fallback key, a marker one; a
table answer is two reads (alias shard and pass part, which the Cache API does not hold), one for a 404; the manifest is
read once per isolate a minute. Static requests go to Pages and R2 egress is free: both are counted and shown at $0.

It prints rates per viewer-minute for each session and for the mix, the cost of 1,000 viewers for one hour (no
allowances), the same at 0, 0.5 and 0.9 edge-cache shares, four months with Workers Paid's allowances and 250 GB of
storage, and the Class A cost of one full publish (5 million objects).
