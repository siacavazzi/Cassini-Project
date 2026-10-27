#!/usr/bin/env python3
"""
Times a stretch of the timeline made ahead (the frame server's POST /prebuild, what the page's Pre-process button
asks): starts it with the page's default choices, follows /prebuild/<id>.json every --every seconds until it is done,
failed or stopped, and reports how long it took, how fast it went, and every stall (no new picture for --stall
seconds) with the job's state and, when the server samples its threads (FRAME_SERVER_SAMPLE=1), what its threads
were doing meanwhile (GET /debug/samples). A stretch made already is answered from the cache, so a second run times
the cached path alone.

  python web/frames/bench_segment.py http://localhost:8790 2006-09-15T14:30:00 2006-09-15T17:13:00 [--out seg.json]
    --cams NW --sizes 512,1024   as the page asks on a desktop (a phone asks 512)
    --again                      when the first run is done, ask again for the same stretch a second later (a new job:
                                 the same stretch asked again is the same job, answered as done), so the second run
                                 times the cached path
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode


def call(base, path, method="GET", timeout=60):
    req = urllib.request.Request(base.rstrip("/") + path, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def samples(base):
    try:
        status, body = call(base, "/debug/samples", timeout=10)
        return body.decode() if status == 200 else None
    except (OSError, urllib.error.HTTPError):
        return None


def one(base, q, every, stall, max_s):
    """One stretch, from POST to its end: [(seconds, state, done, total, through)], the stalls, the last status."""
    t0 = time.monotonic()
    status, body = call(base, "/prebuild?" + urlencode(q), "POST")
    job = json.loads(body)
    if "id" not in job:
        raise SystemExit(f"the server said {job}")
    log, stalls, last_done, last_move, sampled = [], [], -1, t0, samples(base)
    while True:
        now = time.monotonic()
        log.append([round(now - t0, 2), job["state"], job.get("done", 0), job.get("total", 0), job.get("through"), job.get("eta")])
        if job.get("done", 0) != last_done:
            if last_done >= 0 and now - last_move >= stall:
                stalls[-1]["ended_at"] = round(now - t0, 1)
            last_done, last_move = job.get("done", 0), now
        elif now - last_move >= stall and (not stalls or stalls[-1].get("ended_at") is not None or stalls[-1]["from"] != round(last_move - t0, 1)):
            stalls.append({"from": round(last_move - t0, 1), "state": job["state"], "done": job.get("done"), "total": job.get("total"),
                           "through": job.get("through"), "ended_at": None, "samples": samples(base)})
        if job["state"] in ("done", "failed", "stopped") or now - t0 > max_s:
            break
        time.sleep(every)
        try:
            _, body = call(base, f"/prebuild/{job['id']}.json")
            job = json.loads(body)
        except (OSError, urllib.error.HTTPError, ValueError):
            pass
    took = time.monotonic() - t0
    if stalls and stalls[-1].get("ended_at") is None:
        stalls[-1]["ended_at"] = round(took, 1)
    return {"id": job["id"], "seconds": round(took, 2), "final": job, "log": log, "stalls": stalls,
            "pictures_per_second": round(job.get("done", 0) / took, 1) if took else None, "samples_after": samples(base)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("start")
    ap.add_argument("until")
    ap.add_argument("--cams", default="NW")
    ap.add_argument("--sizes", default="512,1024")
    ap.add_argument("--every", type=float, default=0.5)
    ap.add_argument("--stall", type=float, default=10.0, help="seconds without a new picture that count as a stall")
    ap.add_argument("--max", type=float, default=1800, help="seconds to follow a stretch at most")
    ap.add_argument("--again", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    # the page's defaults (segment.html params(): Settings at their defaults, the default look)
    q = {"from": args.start, "until": args.until, "cams": args.cams, "sizes": args.sizes, "mosaics": "1", "steady": "1",
         "color": "1", "processed": "1", "center": "1", "trail": "0", "laps": "1", "fade": "0", "persist": "35"}
    runs = []
    for k in range(2 if args.again else 1):
        if k:
            # a new job for the same pictures (the same choices are the same job, answered as done)
            import datetime
            q["from"] = (datetime.datetime.fromisoformat(args.start) + datetime.timedelta(seconds=1)).isoformat()
        r = one(args.base, q, args.every, args.stall, args.max)
        runs.append(r)
        f = r["final"]
        print(f"run {k + 1}: {f['state']} {f.get('done')}/{f.get('total')} pictures in {r['seconds']} s = {r['pictures_per_second']}/s, "
              f"{f.get('errors')} errors, {len(r['stalls'])} stalls" + "".join(
                  f"\n   stall {s['from']}-{s['ended_at']} s in {s['state']} at {s['done']}/{s['total']} (through {s['through']})" for s in r["stalls"]), flush=True)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"base": args.base, "query": q, "runs": runs}, fh, indent=1)


if __name__ == "__main__":
    main()
