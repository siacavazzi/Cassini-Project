#!/usr/bin/env python3
"""
The cost sheet (WP8): requests and bytes per viewer-minute, measured, and what 1,000 viewers cost a month.

  python web/deploy/cost.py --harness DIR [DIR ...]   zero_origin.mjs --out folders (--mode public through the Worker,
                                                     or --mode before: every frames request is one the Worker will get)
  python web/deploy/cost.py --ae --since 2026-11-20T00:00:00Z [--env staging]
                                                     the live Worker's Analytics Engine points (needs the token: Account
                                                     Analytics Read) over a window, per request class
  python web/deploy/cost.py --counts FILE             hand-entered per-session counts (same fields as a harness summary)
  ... [--storage-gb 200] [--cache-hit 0.5] [--cpu-ms 2] [--md OUT.md]

Only the frames host costs money: Pages serves the page and the replay data free, and Cloudflare charges nothing for
bytes out, so bytes are reported but priced at zero. Each frames request is one Worker request and one Analytics
Engine point; an edge-cache miss adds one R2 read (Class B), --cache-hit the share that are hits.
"""
import argparse
import glob
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PRICE = json.load(open(os.path.join(HERE, "pricing.json")))
PLAYING = {"S1", "S2", "S8"}   # the sessions that play for --minutes; the others are short, scripted visits


def from_harness(dirs):
    rows = []
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "S*.json"))):
            s = json.load(open(f))
            fr = [r for r in s.get("requests", []) if (r.get("k") or {}).get("cls") == "frames"]
            st = [r for r in s.get("requests", []) if (r.get("k") or {}).get("cls") == "static"]
            rows.append({"session": s["session"], "mode": s.get("mode"), "seconds": s["seconds"],
                         "frames_requests": len(fr), "frames_bytes": sum(r.get("bytes") or 0 for r in fr),
                         "static_requests": len(st), "static_bytes": sum(r.get("bytes") or 0 for r in st)})
    return rows


AE_SQL = """SELECT blob1 AS store, blob5 AS outcome, blob3 AS cache, SUM(_sample_interval) AS requests,
SUM(_sample_interval * double1) AS bytes, SUM(_sample_interval * double2) AS r2_reads
FROM {dataset} WHERE timestamp > toDateTime('{since}') GROUP BY store, outcome, cache FORMAT JSON"""


def from_ae(since, env):
    """The live Worker's points (WP4's layout: blob1 store, blob3 cache, blob5 outcome, double1 bytes, double2 R2
    reads; POST /usage words as blob1 'usage', blob2 the word)."""
    sys.path.insert(0, HERE)
    import cf
    conf = cf.site_env()
    ds = conf["USAGE_DATASET_STAGING" if env == "staging" else "USAGE_DATASET_PRODUCTION"]
    tok, acct = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
    sql = AE_SQL.format(dataset=ds, since=since.replace("T", " ").rstrip("Z"))
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{acct}/analytics_engine/sql",
                                 data=sql.encode(), headers={"Authorization": "Bearer " + tok})
    return json.load(urllib.request.urlopen(req, timeout=60))["data"]


def per_minute(rows, only_playing=True):
    use = [r for r in rows if r["session"] in PLAYING] if only_playing else rows
    use = use or rows
    mins = sum(r["seconds"] for r in use) / 60
    tot = lambda k: sum(r[k] for r in use)
    return {"sessions": [r["session"] for r in use], "minutes": round(mins, 2),
            "frames_requests_per_min": tot("frames_requests") / mins, "frames_mb_per_min": tot("frames_bytes") / mins / 1e6,
            "static_mb_per_visit": tot("static_bytes") / len(use) / 1e6}


def month_cost(req, storage_gb, cache_hit, cpu_ms):
    P = PRICE
    over = lambda n, inc: max(0.0, n - inc) / 1e6
    worker = P["workers_paid_monthly"] + over(req, P["workers_requests_included"]) * P["workers_per_million_requests"]
    cpu = over(req * cpu_ms, P["workers_cpu_ms_included"]) * P["workers_per_million_cpu_ms"]
    ae = over(req, P["analytics_engine_points_included"]) * P["analytics_engine_per_million_points"]
    r2_reads = req * (1 - cache_hit)
    r2 = over(r2_reads, P["r2_class_b_included"]) * P["r2_per_million_class_b"]
    store = max(0.0, storage_gb - P["r2_storage_gb_free"]) * P["r2_storage_per_gb_month"]
    return {"requests": req, "workers": worker, "cpu": cpu, "analytics": ae, "r2_reads": r2, "storage": store,
            "total": worker + cpu + ae + r2 + store}


SCENARIOS = [
    ("1,000 viewers at once for one hour (a launch spike), in a month that is otherwise quiet", 1000 * 60),
    ("1,000 visits a day, 10 minutes each, for 30 days", 1000 * 10 * 30),
    ("1,000 viewers at once, all day, every day for 30 days (the ceiling)", 1000 * 60 * 24 * 30),
]


def sheet(pm, storage_gb, cache_hit, cpu_ms, source):
    rpm = pm["frames_requests_per_min"]
    lines = [f"# Cost sheet", "", f"Source: {source}. Sessions {', '.join(pm['sessions'])}, {pm['minutes']} viewer-minutes.", "",
             f"- **{rpm:.1f} frames requests per viewer-minute** ({rpm * 60:,.0f} an hour), "
             f"{pm['frames_mb_per_min']:.2f} MB of pictures a minute (bytes out cost nothing on Cloudflare)",
             f"- page and replay data per visit from Pages: {pm['static_mb_per_visit']:.1f} MB (free)",
             f"- assumed: edge-cache hit share {cache_hit:.0%} (each miss is one R2 read), {cpu_ms} ms of Worker CPU a request, "
             f"{storage_gb} GB in R2; prices from pricing.json ({PRICE['checked']})", "",
             "| scenario | viewer-minutes | Worker requests | Workers | CPU | Analytics | R2 reads | R2 storage | **month** |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, vmin in SCENARIOS:
        c = month_cost(vmin * rpm, storage_gb, cache_hit, cpu_ms)
        lines.append(f"| {name} | {vmin:,} | {c['requests']:,.0f} | ${c['workers']:.2f} | ${c['cpu']:.2f} | ${c['analytics']:.2f} | "
                     f"${c['r2_reads']:.2f} | ${c['storage']:.2f} | **${c['total']:.2f}** |")
    hour = month_cost(60 * rpm, 0, cache_hit, cpu_ms)
    marginal = (hour["requests"] / 1e6) * (PRICE["workers_per_million_requests"] + PRICE["analytics_engine_per_million_points"]
                                           + (1 - cache_hit) * PRICE["r2_per_million_class_b"] + cpu_ms * PRICE["workers_per_million_cpu_ms"])
    lines += ["", f"Past the included amounts, one viewer-hour costs about **${marginal:.4f}** "
                  f"(so 1,000 viewer-hours about ${marginal * 1000:.2f})."]
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", nargs="+"); ap.add_argument("--counts"); ap.add_argument("--ae", action="store_true")
    ap.add_argument("--since"); ap.add_argument("--env", default="staging")
    ap.add_argument("--storage-gb", type=float, default=200); ap.add_argument("--cache-hit", type=float, default=0.5)
    ap.add_argument("--cpu-ms", type=float, default=2); ap.add_argument("--md")
    a = ap.parse_args(argv)
    if a.ae:
        print(json.dumps(from_ae(a.since, a.env), indent=1))
        return 0
    if a.harness:
        rows, src = from_harness(a.harness), "harness logs " + ", ".join(a.harness)
    elif a.counts:
        rows, src = json.load(open(a.counts))["sessions"], a.counts
    else:
        ap.error("--harness, --counts or --ae")
    text = sheet(per_minute(rows), a.storage_gb, a.cache_hit, a.cpu_ms, src)
    if a.md:
        open(a.md, "w").write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
