"""
Makes the pictures of the "How the pictures are made" page (web/cassini-os/how/) from a running frame server, so
every picture on it is one the pipeline drew: the archive's raw frame (/frames/<ID>.png), a frame with a pipeline
step turned off (?off=<step>, calibration.STEPS) and with every step on, a color set (/frames/color.webp) with its
channels not aligned or drawn straight, the frame placed by SPICE (/frames/processed/<ID>.webp?center=1) and a
mosaic as it grows (/frames/mosaic/<ID>.webp). This script only fetches them, scales them down by area averaging (no
sharpening) and saves them as JPEG; the numbers it writes (pictures.json) come from the server's own report headers
and the geometry cache.

    python web/cassini-os/how/make_images.py http://127.0.0.1:8971 [--geometry path/to/geometry.sqlite]
"""
import argparse
import io
import json
import os
import sqlite3
import sys
import time
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "img")

# color sets for the color section, each RED / GRN / BL1: Titan, 25 Jan 2009 (orange haze, blue at its rim); Saturn,
# 15 Oct 2004 (WAC, rings); Jupiter, 10 Feb 2001 (a crescent leaving it, its channels far apart before lining up)
COLOR_SETS = {
    "titan": ["N1611563684_1", "N1611563651_1", "N1611563618_1"],
    "saturn": ["W1476557029_1", "W1476557102_1", "W1476557207_1"],
    "jupiter": ["N1360507132_1", "N1360507098_2", "N1360507028_1"],
}
# Jupiter, 29 December 2000 (ISS_C23JU_PORTRAIT_PRIME): the first lap of the 3 x 3 color portrait, each pointing a
# CB2 / GRN / BL1 set (the server's mosaic manifest, /frames/mosaic/N1356763433_1.json)
JUPITER = [
    {"BL1": "N1356755399_1", "GRN": "N1356755453_1", "CB2": "N1356755518_1"},
    {"BL1": "N1356755859_1", "GRN": "N1356755913_1", "CB2": "N1356755978_1"},
    {"BL1": "N1356756279_1", "GRN": "N1356756333_1", "CB2": "N1356756398_1"},
    {"BL1": "N1356756729_1", "GRN": "N1356756783_1", "CB2": "N1356756848_1"},
    {"BL1": "N1356757179_1", "GRN": "N1356757233_1", "CB2": "N1356757298_1"},
    {"BL1": "N1356757629_1", "GRN": "N1356757683_1", "CB2": "N1356757748_2"},
    {"BL1": "N1356758079_1", "GRN": "N1356758133_1", "CB2": "N1356758198_1"},
    {"BL1": "N1356758529_1", "GRN": "N1356758583_1", "CB2": "N1356758648_1"},
    {"BL1": "N1356758979_1", "GRN": "N1356759033_1", "CB2": "N1356759098_1"},
]
# the portrait's second lap, an hour later (the pass is a mosaic movie: the same 3 x 3 grid taken again), the last
# pointing without its CB2 frame; the mosaic as each pointing's last frame arrives
JUPITER_LAP2 = ["N1356759918_1", "N1356760378_1", "N1356760798_1", "N1356761248_1", "N1356761698_2", "N1356762148_1",
                "N1356762598_1", "N1356763048_1", "N1356763433_1"]
# Enceladus, 4 December 2016 (ISS_251EN_SPXREDTE001_CIRS): nine clear frames with the moon all over the frame, for
# the centering animation (each as taken, and where SPICE puts its center and which way is north)
CENTER = ["N1859559558_1", "N1859559604_1", "N1859559804_1", "N1859559854_1", "N1859560054_1", "N1859560104_2",
          "N1859560304_1", "N1859560354_1", "N1859560554_1"]
# one step turned off, each on a frame where it shows (name, frame or color set, the step, what to say)
STEPS = [
    ("fill", "N1525449680_5", "fill"),          # Dione, 4 May 2006: 66 lines lost in downlink, in bands
    ("fill2", "N1500061303_1", "fill"),         # Enceladus, 14 Jul 2005: half its lines lost, every other one
    ("ering", "W1537014482_1", "fill"),         # Enceladus in the E ring, 15 Sep 2006: the bottom of the frame lost
    ("twohz", "N1475861757_1", "twohz"),        # Iapetus, 7 Oct 2004: faint sky with the 2 Hz hum's bands
]
# raw frames to choose from in the raw frame section, as the archive's PNG copy has them
RAW = ["N1525449680_5", "N1500061303_1", "W1537014482_1", "W1476557029_1", "N1611563684_1"]


def fetch(base, path, tries=40):
    """The answer's bytes and headers; a mosaic still making its tiles (X-Reel "behind" > 0) is asked again."""
    for _ in range(tries):
        with urllib.request.urlopen(base + path, timeout=900) as r:
            data, headers = r.read(), dict(r.headers)
        reel = json.loads(headers.get("X-Reel", "{}") or "{}")
        if reel.get("behind", 0) == 0:
            return data, headers
        time.sleep(5)
    raise RuntimeError(f"{path} still has tiles to make")


def save(data, name, size, gray=False):
    im = Image.open(io.BytesIO(data))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        black = Image.new("RGBA", im.size, (0, 0, 0, 255))
        im = Image.alpha_composite(black, im)
    im = im.convert("L" if gray else "RGB")
    if size and max(im.size) > size:
        k = size / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.BOX)   # area average: no sharpening
    im.save(os.path.join(OUT, name + ".jpg"), quality=86, optimize=True, progressive=True)
    return im.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("server")
    ap.add_argument("--geometry", default=os.environ.get("CASSINI_GEOMETRY_CACHE"))
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    base = a.server.rstrip("/")
    os.makedirs(OUT, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    facts = {}
    want = lambda k: not only or k in only

    def report(headers, key="X-Composite"):
        return json.loads(headers.get(key, "{}") or "{}")

    if want("jupiter"):
        for n, s in enumerate(JUPITER, 1):
            for f, i in s.items():
                save(fetch(base, f"/frames/{i}.png")[0], f"jup-{n}-raw-{f}", 240, gray=True)
            ids = ",".join([s["CB2"], s["GRN"], s["BL1"]])
            d, h = fetch(base, f"/frames/color.webp?ids={ids}&size=1024")
            save(d, f"jup-{n}-color", 480)
            facts[f"jup-{n}-color"] = report(h)
            d, h = fetch(base, f"/frames/mosaic/{s['CB2']}.webp?size=1024")
            facts[f"jup-{n}-mosaic"] = report(h, "X-Reel")
            save(d, f"jup-{n}-mosaic", 900)

    if want("pointing"):
        # the pointing diagram's frames as taken (pointing.json, make_pointing.py)
        with open(os.path.join(HERE, "pointing.json")) as f:
            for frame in json.load(f):
                save(fetch(base, f"/frames/{frame['id']}.png")[0], f"point-{frame['id']}", 512, gray=True)

    if want("raw"):
        for i in RAW:
            save(fetch(base, f"/frames/{i}.png")[0], f"raw-{i}", 640, gray=True)

    if want("color"):
        for name, ids in COLOR_SETS.items():
            for k, i in zip(("red", "green", "blue"), ids):
                save(fetch(base, f"/frames/{i}.webp?size=1024")[0], f"color-{name}-{k}", 420, gray=True)
            path = f"/frames/color.webp?ids={','.join(ids)}&size=1024"
            d, h = fetch(base, path)
            save(d, f"color-{name}", 640)
            facts[f"color-{name}"] = report(h)
            save(fetch(base, path + "&off=align")[0], f"color-{name}-noalign", 640)
            save(fetch(base, path + "&colors=raw")[0], f"color-{name}-rawfilters", 640)
            save(fetch(base, path + "&off=calibrate")[0], f"color-{name}-nocal", 640)

    if want("center"):
        for n, i in enumerate(CENTER, 1):
            save(fetch(base, f"/frames/{i}.png")[0], f"center-{n}", 512, gray=True)
        if a.geometry:
            db = sqlite3.connect(f"file:{a.geometry}?mode=ro", uri=True)
            for n, i in enumerate(CENTER, 1):
                x, y, z, angle = db.execute("select x, y, z, angle from target where frame = ?", (i,)).fetchone()
                facts[f"center-{n}"] = {"id": i, "sample": round(511.5 - x, 1), "line": round(511.5 - y, 1), "km": round(z),
                                        "north": round(angle, 2)}

    if want("lap2"):
        for n, i in enumerate(JUPITER_LAP2, 10):
            d, h = fetch(base, f"/frames/mosaic/{i}.webp?size=1024")
            facts[f"jup-{n}-mosaic"] = report(h, "X-Reel")
            save(d, f"jup-{n}-mosaic", 900)

    if want("steps"):
        # the frame through the whole pipeline (/frames/processed: stacked, filled, calibrated, north up) with one
        # step turned off, and the archive's raw frame beside it
        for name, frame, step in STEPS:
            path = f"/frames/processed/{frame}.webp?size=1024"
            save(fetch(base, path)[0], f"step-{name}-on", 640, gray=True)
            save(fetch(base, path + f"&off={step}")[0], f"step-{name}-off", 640, gray=True)
            # every clean-up and calibration step off, placed the same way, so the two line up
            save(fetch(base, path + "&off=stack,hdr,fill,calibrate")[0], f"step-{name}-alloff", 640, gray=True)

    if a.geometry and want("jupiter"):
        db = sqlite3.connect(f"file:{a.geometry}?mode=ro", uri=True)
        for n, s in enumerate(JUPITER, 1):
            x, y, z, angle = db.execute("select x, y, z, angle from target where frame = ?", (s["GRN"],)).fetchone()
            facts[f"jup-{n}-spice"] = {"sample": round(511.5 - x, 1), "line": round(511.5 - y, 1), "km": round(z), "north": round(angle, 2)}
    old = {}
    path = os.path.join(HERE, "pictures.json")
    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
    old.update(facts)
    with open(path, "w") as f:
        json.dump(old, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    sys.exit(main())
