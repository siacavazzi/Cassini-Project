#!/usr/bin/env python3
"""
Times jumps the way they happen in use: Cassini OS plays for a while, its camera windows asking the frame
server for pictures, then the clock jumps to another month and the time until that month's data is in
(yearReady(), the loading screen's wait) is measured. Unlike bench_jump.py the browser cache stays on and
the windows are busy, so a jump also shows how long its data waited for a free connection to the server.

  pip install playwright        # uses the installed Google Chrome, nothing else to download
  python web/replay/bench_jump_busy.py http://localhost:8765/ [--busy 25] [--video out_dir] [--json out.json]

For each jump it prints the wait, how many frame-server requests were in flight at the jump, how long the
month's data waited for a connection, and how many picture requests the page dropped (canceled).
"""
import argparse
import json
import os
import time

from playwright.sync_api import sync_playwright

# back and forth between 2005 and 2006 and a few further jumps, at busy imaging times
MOMENTS = ["2005-02-17T02:30:00", "2006-09-15T14:28:00", "2005-11-26T21:00:00", "2006-03-09T07:00:00",
           "2005-03-09T08:30:00", "2006-07-22T00:00:00", "2008-10-09T19:00:00", "2005-07-14T19:00:00",
           "2006-01-02T06:00:00", "2005-10-11T17:00:00"]
START = "2006-09-15T14:00:00"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--busy", type=float, default=25, help="seconds of playback before each jump")
    ap.add_argument("--video", help="folder for a recording of the run")
    ap.add_argument("--json", help="write the numbers here")
    ap.add_argument("--chromium", action="store_true", help="Playwright's own Chromium instead of Chrome")
    args = ap.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({} if args.chromium else {"channel": "chrome"}))
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  **({"record_video_dir": args.video, "record_video_size": {"width": 1440, "height": 900}} if args.video else {}))
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        reqs = {}   # requestId -> {url, sent, queued, done, canceled}
        cdp.on("Network.requestWillBeSent", lambda e: reqs.setdefault(e["requestId"], {"url": e["request"]["url"], "sent": e["timestamp"]}))
        cdp.on("Network.requestServedFromCache", lambda e: reqs.get(e["requestId"], {}).update(cached=True))

        def got(e):
            r, t = reqs.get(e["requestId"]), e["response"].get("timing")
            if r is not None and t:
                r["queued"] = t["requestTime"] + t["sendStart"] / 1000 - r["sent"]
        cdp.on("Network.responseReceived", got)
        cdp.on("Network.loadingFinished", lambda e: reqs.get(e["requestId"], {}).update(done=e["timestamp"]))
        cdp.on("Network.loadingFailed", lambda e: reqs.get(e["requestId"], {}).update(done=e["timestamp"], canceled=e.get("canceled", False)))
        start = time.time()
        page.goto(args.url + ("&" if "?" in args.url else "?") + "t=" + START)
        page.wait_for_function("typeof yearReady === 'function' && yearReady() && document.getElementById('loading').hidden",
                               timeout=300000, polling=50)
        print(f"first load: {time.time() - start:.2f} s", flush=True)
        out = []
        for moment in MOMENTS:
            page.evaluate("setPlaying(true)")
            page.wait_for_timeout(args.busy * 1000)
            frames = lambda: [k for k, r in reqs.items() if "/frames/" in r["url"]]
            in_flight = sum(1 for k in frames() if "done" not in reqs[k])
            before = set(reqs)
            took = page.evaluate("""async m => {
                const t0 = performance.now();
                setTime(utcToEt(m));
                while (!yearReady()) await new Promise(r => setTimeout(r, 20));
                return (performance.now() - t0) / 1000;
            }""", moment)
            page.wait_for_timeout(300)   # the last network events
            new = [reqs[k] for k in reqs if k not in before]
            data = [r for r in new if "/data/months/" in r["url"] or "/data/years/" in r["url"]]
            queued = max((r.get("queued", 0) for r in data), default=0)
            canceled = sum(1 for k in frames() if k in before and reqs[k].get("canceled"))
            row = {"to": moment, "wait_s": round(took, 2), "frame_requests_in_flight": in_flight,
                   "data_queued_s": round(queued, 2), "data_files": len(data), "pictures_dropped": canceled}
            out.append(row)
            print(f"jump to {moment}: {took:.2f} s; {in_flight} picture requests in flight, data waited "
                  f"{queued:.2f} s for a connection ({len(data)} files), {canceled} picture requests dropped", flush=True)
        w = sorted(r["wait_s"] for r in out)
        summary = {"median_s": w[len(w) // 2], "max_s": w[-1], "mean_s": round(sum(w) / len(w), 2)}
        print(f"jumps: median {summary['median_s']:.2f} s, max {summary['max_s']:.2f} s, mean {summary['mean_s']:.2f} s")
        if args.json:
            with open(args.json, "w") as fh:
                json.dump({"url": args.url, "busy_s": args.busy, "jumps": out, **summary}, fh, indent=1)
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
