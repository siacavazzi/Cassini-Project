#!/usr/bin/env python3
"""
Usage counts for Cassini OS: how many people use it, roughly from where, and which pictures they look at,
save and share. Only daily totals are kept, never a record per person or per request:

  - no cookies, no browser storage, nothing sent to anyone else; the page sends one word when it opens
    (POST /usage "visit", or "visit-link" when it opened on a shared moment) and one when a link is copied
  - a visitor is counted once a day by a hash of their address and browser, salted with a random value
    that lives only in memory and is replaced at midnight UTC (Plausible's method); the hashes are never
    written down, so nobody can be followed from one day to the next, or picked out at all
  - the country is Cloudflare's CF-IPCountry header (two letters) once the site is behind Cloudflare;
    home Wi-Fi and Tailscale count as "local"; no address is looked up or kept
  - pictures are counted by what the frame server is asked for: frames, composites, processed frames,
    mosaics, body reels, full-resolution views, downloads, movie exports; crawlers and headless browsers
    (our own tests) go into one "bots" total only

One JSON file per day (YYYY-MM-DD.json) in the usage folder, written every minute and on exit:

  {"day", "visitors", "countries": {"US": 3, "local": 1}, "events": {"visit": 4, "frame": 900, ...},
   "pictures": {"frame": {"N1483281115_1": 12, ...}, "download": {...}, ...}, "bots": 20}

The frame server answers GET /stats/ (the page) and /stats/usage.json?days=30 only to its own network
(home, Tailscale, this machine; not through the Cloudflare tunnel) or with ?key=$CASSINI_STATS_KEY.
"""
import atexit, datetime, hashlib, ipaddress, json, os, re, threading, time
from urllib.parse import parse_qs, urlparse

FLUSH = 60                          # seconds between writes of today's file
BEACONS = {"visit", "visit-link", "copy-link"}
BOT = re.compile(r"bot|crawl|spider|slurp|headless|curl|wget|python-|go-http|preview|facebookexternalhit|monitor", re.I)
TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
FRAME = r"[NW]\d{10}_\d+"

# what a request is, from its path: (event, the picture it counts for, or None); None for a request not counted
ROUTES = [
    (re.compile(rf"^/frames/({FRAME})\.webp$"), "frame"),
    (re.compile(rf"^/frames/({FRAME})\.png$"), "raw"),
    (re.compile(rf"^/frames/({FRAME})\.(?:tif|lbl)$"), "science"),
    (re.compile(rf"^/frames/processed/({FRAME})\.webp$"), "processed"),
    (re.compile(rf"^/frames/mosaic/({FRAME})\.webp$"), "mosaic"),
    (re.compile(r"^/frames/reel/([A-Z0-9_]+)/\d+\.webp$"), "reel"),
    (re.compile(r"^/reel/([A-Z0-9_]+)\.json$"), "body"),
    (re.compile(r"^/export/([0-9a-f]{16})\.mp4$"), "film"),
]


def classify(method, path, code, headers=None):
    """(event, picture or None) a request counts as, or None."""
    if code >= 400:
        return None
    url = urlparse(path)
    query = parse_qs(url.query)
    if method == "POST":
        return ("export", None) if url.path == "/export" else None
    if url.path == "/frames/color.webp":
        ids = query.get("ids", [""])[0]
        event, key = "composite", ids if re.fullmatch(rf"{FRAME}(,{FRAME}){{1,2}}", ids) else None
    else:
        for pattern, name in ROUTES:
            m = pattern.match(url.path)
            if m:
                event, key = name, m.group(1)
                break
        else:
            return None
    if event == "mosaic" and query.get("warm"):
        return None
    if event == "film":
        # a player asks for a film in many ranges: count its first one only
        rng = headers.get("Range", "") if headers is not None else ""
        if rng and not re.match(r"bytes=0-", rng):
            return None
    return event, key


def extras(path):
    """The other events the same request also is: a full-resolution view, a download."""
    query = parse_qs(urlparse(path).query)
    out = []
    if query.get("size", [""])[0] == "full":
        out.append("full")
    if query.get("download", ["0"])[0] not in ("", "0"):
        out.append("download")
    return out


def local(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a in TAILSCALE


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def empty(day):
    return {"day": day, "visitors": 0, "countries": {}, "events": {}, "pictures": {}, "bots": 0}


class Usage:
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.lock = threading.Lock()
        self.day = None
        self.dirty = False
        self._roll()
        threading.Thread(target=self._flusher, daemon=True).start()
        atexit.register(self.flush)

    def _path(self, day):
        return os.path.join(self.folder, f"{day}.json")

    def _roll(self):
        """A new day: write the old one, start (or pick up) today's file with a fresh salt and no hashes."""
        day = today()
        if day == self.day:
            return
        if self.day:
            self._write()
        self.day, self.salt, self.seen = day, os.urandom(16), set()
        try:
            with open(self._path(day)) as fh:
                self.counts = json.load(fh)
        except (OSError, ValueError):
            self.counts = empty(day)

    def _write(self):
        path = self._path(self.counts["day"])
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.counts, fh, separators=(",", ":"))
        os.replace(tmp, path)
        self.dirty = False

    def flush(self):
        with self.lock:
            if self.dirty:
                self._write()

    def _flusher(self):
        while True:
            time.sleep(FLUSH)
            try:
                with self.lock:
                    self._roll()
                    if self.dirty:
                        self._write()
            except OSError as e:
                print(f"usage: could not write counts ({e})", flush=True)

    def count(self, events, key=None, ip="", agent="", country=None):
        """Adds one to each event (and to key under it), and counts the visitor once today."""
        with self.lock:
            self._roll()
            c = self.counts
            self.dirty = True
            if not agent or BOT.search(agent):
                c["bots"] += 1
                return
            visitor = hashlib.sha256(self.salt + f"{ip}|{agent}".encode()).digest()[:12]
            if visitor not in self.seen:
                self.seen.add(visitor)
                c["visitors"] += 1
                where = country if country == "local" else (country or "").upper()
                where = where if re.fullmatch(r"local|[A-Z]{2}", where) and where not in ("XX", "T1") else "unknown"
                c["countries"][where] = c["countries"].get(where, 0) + 1
            for event in events:
                c["events"][event] = c["events"].get(event, 0) + 1
                if key:
                    per = c["pictures"].setdefault(event, {})
                    per[key] = per.get(key, 0) + 1

    def request(self, handler, code):
        """Counts one answered request of the frame server's (called from its log_request)."""
        headers = handler.headers
        if "/stats" in (headers.get("Referer") or ""):
            return   # the stats page's own thumbnails
        found = classify(handler.command, handler.path, code, headers)
        if not found:
            return
        event, key = found
        events = [event] + extras(handler.path)
        if event == "export":
            events = ["export"]
        ip, agent, country = who(handler)
        self.count(events, key if event != "export" else None, ip, agent, country)

    def beacon(self, handler, body):
        """POST /usage from the page: one word from BEACONS; anything else is ignored."""
        word = body.decode("ascii", "replace").strip()
        if word not in BEACONS:
            return False
        ip, agent, country = who(handler)
        self.count([word], None, ip, agent, country)
        return True

    def days(self, n):
        """The last n days' counts, oldest first (today's as it stands)."""
        self.flush()
        end = datetime.datetime.strptime(today(), "%Y-%m-%d")
        out = []
        for i in range(n - 1, -1, -1):
            day = (end - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            try:
                with open(self._path(day)) as fh:
                    out.append(json.load(fh))
            except (OSError, ValueError):
                out.append(empty(day))
        return out


def who(handler):
    """(address, browser, country) of a request: through Cloudflare, the visitor's and Cloudflare's country for it;
    straight to this machine, "local" from home Wi-Fi and Tailscale"""
    h = handler.headers
    if h.get("CF-Connecting-IP"):
        return h["CF-Connecting-IP"], h.get("User-Agent") or "", h.get("CF-IPCountry")
    ip = handler.client_address[0]
    return ip, h.get("User-Agent") or "", "local" if local(ip) else None


def may_see(handler):
    """The stats are Sam's: this machine, home Wi-Fi and Tailscale, never through the tunnel, or with the key."""
    key = os.environ.get("CASSINI_STATS_KEY")
    if key and parse_qs(urlparse(handler.path).query).get("key", [""])[0] == key:
        return True
    return local(handler.client_address[0]) and not handler.headers.get("CF-Connecting-IP")


def summary(days):
    """Totals over days for the stats page: per-day series, countries, top pictures per event."""
    events, countries, pictures = {}, {}, {}
    for d in days:
        for k, v in d["events"].items():
            events[k] = events.get(k, 0) + v
        for k, v in d["countries"].items():
            countries[k] = countries.get(k, 0) + v
        for e, per in d["pictures"].items():
            tot = pictures.setdefault(e, {})
            for k, v in per.items():
                tot[k] = tot.get(k, 0) + v
    top = {e: sorted(per.items(), key=lambda kv: -kv[1])[:25] for e, per in pictures.items()}
    return {
        "days": [{"day": d["day"], "visitors": d["visitors"], "visits": d["events"].get("visit", 0) + d["events"].get("visit-link", 0),
                  "pictures": sum(v for k, v in d["events"].items() if k in ("frame", "composite", "processed", "mosaic", "reel")),
                  "downloads": d["events"].get("download", 0), "bots": d["bots"]} for d in days],
        "visitor_days": sum(d["visitors"] for d in days),   # a person on two days counts twice: days are never joined
        "bots": sum(d["bots"] for d in days),
        "events": events,
        "countries": sorted(countries.items(), key=lambda kv: -kv[1]),
        "top": top,
    }
