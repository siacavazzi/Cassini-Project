#!/usr/bin/env python3
"""
How big the frame server's X-* reports really are (headers.json storage): reads the request logs the zero-origin
harness writes (--out DIR, one <session>.json per session, each request with its x-* headers) and prints, per route,
the reports' sizes as R2 object metadata, whole and trimmed to the fields the page reads, against the budget.

  node web/public/harness/zero_origin.mjs --site http://HOST:PORT --out /tmp/harness-before
  python web/public/measure_headers.py /tmp/harness-before > docs/public-site/header-sizes.md
"""
import glob
import json
import os
import sys
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import keys  # noqa: E402

with open(os.path.join(HERE, "headers.json")) as fh:
    H = json.load(fh)
BUDGET = H["storage"]["metadata_budget_bytes"]


def compact(obj):
    return json.dumps(obj, separators=(",", ":"))


def sizes(name, value):
    """(whole, trimmed) metadata bytes for one report: the header's lower-case name plus its compact JSON."""
    try:
        rep = json.loads(value)
    except ValueError:
        return len(name) + len(value), len(name) + len(value)
    whole = len(name) + len(compact(rep).encode())
    keep = set(next((v for k, v in H["page_reads"].items() if k.lower() == name), []))
    trimmed = len(name) + len(compact({k: v for k, v in rep.items() if k in keep}).encode()) if isinstance(rep, dict) else whole
    return whole, trimmed


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else 0


def main(folder):
    rows, seen = {}, set()
    for path in sorted(glob.glob(os.path.join(folder, "S*.json"))):
        with open(path) as fh:
            log = json.load(fh)
        for r in log.get("requests", []):
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            for name, value in (r.get("headers") or {}).items():
                if not name.startswith("x-") or name in ("x-hdr",):
                    continue
                u = urlsplit(r["url"])
                ans = keys.canonical(r.get("method", "GET"), u.path + ("?" + u.query if u.query else ""))
                if not ans["route"]:
                    continue   # not a frame-server route (a CDN's own x- headers)
                route = ans["route"]
                w, t = sizes(name, value)
                rows.setdefault((route, name), []).append((w, t))
    print(f"# Report sizes as R2 metadata\n\nFrom the harness logs in `{os.path.basename(os.path.abspath(folder))}`, one row per route and header, "
          f"each distinct URL counted once. Budget {BUDGET} bytes per object (headers.json storage).\n")
    print("| route | header | pictures | whole p50 | whole p95 | whole max | over budget whole | trimmed p95 | trimmed max | over budget trimmed | needs |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for (route, name), xs in sorted(rows.items()):
        ws, ts = [x[0] for x in xs], [x[1] for x in xs]
        ow, ot = sum(w > BUDGET for w in ws), sum(t > BUDGET for t in ts)
        need = "whole" if not ow else "trimmed" if not ot else "sidecar for some"
        print(f"| {route} | {name} | {len(xs)} | {pct(ws, 50)} | {pct(ws, 95)} | {max(ws)} | {ow} | {pct(ts, 95)} | {max(ts)} | {ot} | {need} |")
    if not rows:
        print("No X-* reports in these logs.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
