#!/usr/bin/env python3
"""
Checks the usage counts (usage.py) through the real frame server, with stand-in pictures so no archive is needed:

  python web/frames/test_usage.py

Visitors are counted once a day each, by country; pictures, full views and downloads per picture; crawlers only
as bots; the stats are refused through the Cloudflare tunnel and answered at home or with the key; only daily
totals reach the disk, never an address or a browser.
"""
import io, json, os, sys, tempfile, threading, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["FRAME_SERVER_QUIET"] = "1"
import frame_server  # noqa: E402
import usage  # noqa: E402
from PIL import Image  # noqa: E402

buf = io.BytesIO()
Image.new("L", (8, 8)).save(buf, "WEBP")
PIC = buf.getvalue()
frame_server.webp = lambda *a, **k: PIC
frame_server.color_webp = lambda *a, **k: (PIC, {})
frame_server.archive_png = lambda *a, **k: PIC

tmp = tempfile.mkdtemp()
counts = frame_server.counts = usage.Usage(os.path.join(tmp, "usage"))
server = frame_server.Server(("127.0.0.1", 0), frame_server.make_handler(os.path.join(HERE, "..", "cassini-os"), tmp, None))
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_address[1]}"
FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:131.0) Gecko/20100101 Firefox/131.0"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"


def get(path, ip=None, country=None, agent=FIREFOX, method="GET", body=None, extra=None):
    h = {"User-Agent": agent, **(extra or {})}
    if ip:
        h["CF-Connecting-IP"] = ip
    if country:
        h["CF-IPCountry"] = country
    req = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# three people: one in Germany (two visits, many pictures), one in Japan, one at home; and a crawler
assert get("/usage", "203.0.113.5", "DE", method="POST", body=b"visit")[0] == 204
assert get("/usage", "203.0.113.5", "DE", method="POST", body=b"visit")[0] == 204
assert get("/usage", "198.51.100.7", "JP", SAFARI, method="POST", body=b"visit-link")[0] == 204
assert get("/usage", method="POST", body=b"visit")[0] == 204
assert get("/usage", method="POST", body=b"copy-link")[0] == 204
assert get("/usage", method="POST", body=b"anything else")[0] == 204          # answered, not counted
for _ in range(5):
    assert get("/frames/N1483281115_1.webp?size=512", "203.0.113.5", "DE")[0] == 200
assert get("/frames/N1483281115_1.webp?size=full&format=png&download=1", "203.0.113.5", "DE")[0] == 200
assert get("/frames/W1483281120_1.webp?size=512", "198.51.100.7", "JP", SAFARI)[0] == 200
assert get("/frames/color.webp?ids=N1483281115_1,N1483281125_1,N1483281135_1&size=512", "198.51.100.7", "JP", SAFARI)[0] == 200
assert get("/frames/N1483281115_1.png", "198.51.100.7", "JP", SAFARI)[0] == 200
assert get("/frames/N1483281115_1.webp?size=512", "192.0.2.9", "US", "Googlebot/2.1 (+http://www.google.com/bot.html)")[0] == 200
assert get("/frames/N1483281115_1.webp?size=512", "192.0.2.10", "US", "Mozilla/5.0 HeadlessChrome/130.0")[0] == 200
assert get("/frames/N1483281115_1.webp?size=128", extra={"Referer": BASE + "/stats/"})[0] == 200   # the stats page's own
assert get("/frames/nonsense.webp")[0] == 400                                  # refused: not counted
assert get("/about.txt")[0] == 404                                             # not a picture: not counted

# the stats: refused through the tunnel, answered at home, and with the key
assert get("/stats/usage.json", "203.0.113.5", "DE")[0] == 403
code, body = get("/stats/usage.json?days=7")
assert code == 200, code
s = json.loads(body)
today = s["days"][-1]
assert len(s["days"]) == 7
assert today["visitors"] == 3, today
assert today["visits"] == 4, today
assert dict(s["countries"]) == {"DE": 1, "JP": 1, "local": 1}, s["countries"]
assert s["events"]["frame"] == 7 and s["events"]["full"] == 1 and s["events"]["download"] == 1, s["events"]
assert s["events"]["composite"] == 1 and s["events"]["raw"] == 1 and s["events"]["copy-link"] == 1, s["events"]
assert s["events"]["visit-link"] == 1 and s["bots"] == 2, (s["events"], s["bots"])
assert s["top"]["frame"][0] == ["N1483281115_1", 6], s["top"]["frame"]
assert s["top"]["download"] == [["N1483281115_1", 1]], s["top"]
code, page = get("/stats/")
assert code == 200 and b"Cassini OS usage" in page
os.environ["CASSINI_STATS_KEY"] = "k3y"
assert get("/stats/usage.json?key=k3y", "203.0.113.5", "DE")[0] == 200
assert get("/stats/usage.json?key=wrong", "203.0.113.5", "DE")[0] == 403

# what reaches the disk: daily totals, never an address or a browser
counts.flush()
files = os.listdir(os.path.join(tmp, "usage"))
assert len(files) == 1 and files[0].endswith(".json"), files
saved = open(os.path.join(tmp, "usage", files[0])).read()
for secret in ("203.0.113", "198.51.100", "127.0.0.1", "Firefox", "Safari", "Mozilla"):
    assert secret not in saved, secret
# a restart picks today's totals up again
again = usage.Usage(os.path.join(tmp, "usage"))
assert again.counts["visitors"] == 3 and again.counts["events"]["frame"] == 7

server.shutdown()
print("usage counts: all checks pass")
print(json.dumps(json.loads(saved), indent=1))
