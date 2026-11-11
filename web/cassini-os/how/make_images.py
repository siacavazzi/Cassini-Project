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

# Rhea, 16 January 2005 (ISS_00CRH_REGGEODA001_PRIME): a true color set, RED / GRN / BL1, and a clear frame
RHEA = {"red": "N1484528640_1", "green": "N1484528657_1", "blue": "N1484528674_1", "clear": "N1484528732_1"}
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
# one step turned off, each on a frame where it shows (name, frame or color set, the step, what to say)
STEPS = [
    ("fill", "N1500061303_1", "fill"),          # Enceladus, 14 Jul 2005: a third of its lines lost in downlink
    ("calibrate", "color:" + ",".join([RHEA["red"], RHEA["green"], RHEA["blue"]]), "calibrate"),
]


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

    if want("rhea"):
        rgb = ",".join([RHEA["red"], RHEA["green"], RHEA["blue"]])
        for k, i in RHEA.items():
            save(fetch(base, f"/frames/{i}.png")[0], f"rhea-raw-{k}", 512, gray=True)
            save(fetch(base, f"/frames/{i}.webp?size=1024")[0], f"rhea-frame-{k}", 512, gray=True)
        d, h = fetch(base, f"/frames/color.webp?ids={rgb}&size=1024")
        save(d, "rhea-color", 640)
        facts["rhea-color"] = report(h)
        save(fetch(base, f"/frames/color.webp?ids={rgb}&size=1024&off=align")[0], "rhea-color-noalign", 640)
        save(fetch(base, f"/frames/color.webp?ids={rgb}&size=1024&colors=raw")[0], "rhea-color-rawfilters", 640)
        save(fetch(base, f"/frames/color.webp?ids={rgb}&size=1024&off=calibrate")[0], "rhea-color-nocal", 640)
        d, h = fetch(base, f"/frames/color.webp?ids={rgb}&size=1024&center=1")
        save(d, "rhea-color-centered", 640)
        facts["rhea-color-centered"] = report(h)
        d, h = fetch(base, f"/frames/processed/{RHEA['clear']}.webp?size=1024&center=1")
        save(d, "rhea-centered", 512, gray=True)
        save(fetch(base, f"/frames/{RHEA['clear']}.png")[0], "point-rhea", 512, gray=True)

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
        save(fetch(base, f"/frames/{JUPITER[0]['GRN']}.png")[0], "point-jupiter", 512, gray=True)

    if want("steps"):
        for name, what, step in STEPS:
            if what.startswith("color:"):
                path = f"/frames/color.webp?ids={what[6:]}&size=1024"
            else:
                path = f"/frames/{what}.webp?size=1024"
                save(fetch(base, f"/frames/{what}.png")[0], f"step-{name}-raw", 640, gray=True)
            save(fetch(base, path)[0], f"step-{name}-on", 640)
            save(fetch(base, path + f"&off={step}")[0], f"step-{name}-off", 640)

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
