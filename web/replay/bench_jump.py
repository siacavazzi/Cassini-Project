#!/usr/bin/env python3
"""
Times how long the replay (or Cassini OS) takes to show a moment after jumping to it: the page is
opened in Chrome, then the clock is set to moments in other years and the time until that year's
data is in (yearReady()) is measured. The browser cache is off, so every jump downloads its data.

  pip install playwright        # uses the installed Google Chrome, nothing else to download
  python web/replay/bench_jump.py http://localhost:8765/ [--mbps 40] [--shots out_dir]

--mbps limits the download speed like a home network (0 = no limit); --shots saves a screenshot
after each jump.
"""
import argparse
import os
import time

from playwright.sync_api import sync_playwright

MOMENTS = ["2008-10-09T19:00:00", "2000-12-30T10:00:00", "2011-11-30T12:00:00", "2004-07-01T02:00:00",
           "2016-06-01T00:00:00", "2006-03-10T06:00:00", "2013-07-19T21:00:00", "2009-11-02T07:00:00"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--mbps", type=float, default=0)
    ap.add_argument("--shots")
    ap.add_argument("--chromium", action="store_true", help="Playwright's own Chromium instead of Chrome")
    args = ap.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({} if args.chromium else {"channel": "chrome"}))
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        cdp = page.context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        if args.mbps:
            rate = args.mbps * 1e6 / 8
            cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 20,
                                                          "downloadThroughput": rate, "uploadThroughput": rate})
        received = []
        page.on("response", lambda r: received.append(r))
        start = time.time()
        page.goto(args.url + ("&" if "?" in args.url else "?") + "t=2005-01-14T09:30:00")
        page.wait_for_function("typeof yearReady === 'function' && yearReady() && document.getElementById('loading').hidden",
                               timeout=300000, polling=50)
        print(f"first load: {time.time() - start:.2f} s", flush=True)
        times = []
        for n, moment in enumerate(MOMENTS):
            page.wait_for_timeout(1500)   # let the neighbouring years finish
            received.clear()
            took = page.evaluate("""async m => {
                const t0 = performance.now();
                setTime(utcToEt(m));
                while (!yearReady()) await new Promise(r => setTimeout(r, 20));
                return (performance.now() - t0) / 1000;
            }""", moment)
            times.append(took)
            print(f"jump to {moment}: {took:.2f} s ({len(received)} files fetched by then)", flush=True)
            if args.shots:
                os.makedirs(args.shots, exist_ok=True)
                page.wait_for_timeout(500)
                page.screenshot(path=os.path.join(args.shots, f"jump_{n}.png"))
        times.sort()
        print(f"jumps: median {times[len(times) // 2]:.2f} s, max {times[-1]:.2f} s, mean {sum(times) / len(times):.2f} s")
        browser.close()


if __name__ == "__main__":
    main()
