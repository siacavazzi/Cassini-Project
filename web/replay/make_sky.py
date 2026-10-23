#!/usr/bin/env python3
"""
Builds the viewer's star sky (data/textures/sky/sky_2k|4k|8k.webp) from NASA SVS "Deep Star Maps 2020"
(https://svs.gsfc.nasa.gov/4851, public domain; stars from Hipparcos, Tycho-2 and Gaia DR2, plus the Milky Way).

The SVS maps are equirectangular in J2000 celestial coordinates (RA 0h in the middle, RA growing to the left,
Dec +90 at the top) and above 1024x512 only come as linear HDR EXR. This script decodes the EXR with ffmpeg,
averages it down to each tier in linear light (so a star keeps its brightness as the map shrinks) and maps it to
8-bit with an exposure curve fitted to NASA's own display thumbnail (starmap_2020_4k_print.jpg).

  python web/replay/make_sky.py --exr starmap_2020_8k.exr --print starmap_2020_4k_print.jpg --out web/replay/data/textures/sky

It also checks the orientation: it looks for a set of bright stars where the RA convention above puts them and
prints how bright the map is there against the mirrored conventions.
"""
import argparse, json, math, os, subprocess
import numpy as np
from PIL import Image

STARS = {  # name: RA, Dec (J2000, degrees)
    "Sirius": (101.287, -16.716), "Canopus": (95.988, -52.696), "Arcturus": (213.915, 19.182),
    "Vega": (279.234, 38.784), "Capella": (79.172, 45.998), "Rigel": (78.634, -8.202),
    "Betelgeuse": (88.793, 7.407), "Procyon": (114.825, 5.225), "Achernar": (24.429, -57.237),
    "Altair": (297.696, 8.868), "Aldebaran": (68.980, 16.509), "Antares": (247.352, -26.432),
    "Spica": (201.298, -11.161), "Pollux": (116.329, 28.026), "Deneb": (310.358, 45.280),
}


def read_exr(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "json", path], check=True, capture_output=True).stdout
    s = json.loads(out)["streams"][0]; w, h = s["width"], s["height"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "gbrpf32le", "-"],
                         check=True, capture_output=True).stdout
    g, b, r = np.frombuffer(raw, np.float32).reshape(3, h, w)
    return np.clip(np.stack([r, g, b], -1), 0, None)


def shrink(img, f):
    h, w, c = img.shape
    return img.reshape(h // f, f, w // f, f, c).mean((1, 3))


def curve(L, k, gamma):
    return (1 - np.exp(-k * L)) ** (1 / gamma)


def fit(lin, ref):
    """exposure k and gamma so curve(lin) matches NASA's thumbnail (both 1024x512), on luminance"""
    yl = lin @ [0.2126, 0.7152, 0.0722]
    yr = (ref.astype(np.float32) / 255) @ [0.2126, 0.7152, 0.0722]
    best = None
    for gamma in np.arange(1.0, 3.01, 0.1):
        # match the median and the 99th percentile in turn by scanning k on a log grid
        for k in np.exp(np.linspace(math.log(1e-3), math.log(1e6), 400)) / max(np.median(yl), 1e-12):
            e = np.mean((curve(yl, k, gamma) - yr) ** 2)
            if best is None or e < best[0]: best = (e, k, gamma)
    return best[1], best[2], best[0]


def orientation(img):
    h, w, _ = img.shape
    y = img @ [0.2126, 0.7152, 0.0722]
    conv = {"RA 0h mid, grows left (expected)": lambda ra: 0.5 - ra / 360,
            "RA 0h mid, grows right": lambda ra: 0.5 + ra / 360,
            "RA 0h left edge, grows right": lambda ra: ra / 360}
    bg = float(np.median(y))
    res = {}
    for name, f in conv.items():
        vals = []
        for ra, dec in STARS.values():
            x = int((f(ra) % 1) * w); r = int((0.5 - dec / 180) * h)
            vals.append(float(y[max(0, r - 3):r + 4, [(x + d) % w for d in range(-3, 4)]].max()) / max(bg, 1e-12))
        res[name] = float(np.median(vals))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exr", required=True)
    ap.add_argument("--print", dest="ref", help="NASA's 1024x512 display thumbnail to fit the exposure to")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tiers", default="8k,4k,2k")
    ap.add_argument("--quality", type=int, default=90)
    ap.add_argument("--k", type=float); ap.add_argument("--gamma", type=float)
    a = ap.parse_args()
    lin = read_exr(a.exr)
    h, w, _ = lin.shape
    print(f"{a.exr}: {w}x{h}")
    print("orientation, median brightness at 15 bright stars over the sky median:")
    for k, v in orientation(shrink(lin, w // 2048)).items(): print(f"  {v:10.1f}  {k}")
    if a.k and a.gamma: k, gamma = a.k, a.gamma
    elif a.ref:
        k, gamma, e = fit(shrink(lin, w // 1024), np.asarray(Image.open(a.ref).convert("RGB")))
        print(f"fitted to {a.ref}: k={k:.4g} gamma={gamma:.2f} rms={math.sqrt(e) * 255:.1f}/255")
    else: raise SystemExit("give --print or --k and --gamma")
    os.makedirs(a.out, exist_ok=True)
    for t in a.tiers.split(","):
        tw = int(t[:-1]) * 1024
        img = lin if tw == w else shrink(lin, w // tw)
        px = np.round(np.clip(curve(img, k, gamma), 0, 1) * 255).astype(np.uint8)
        p = os.path.join(a.out, f"sky_{t}.webp")
        Image.fromarray(px).save(p, quality=a.quality, method=6)
        print(f"{p}: {tw}x{tw // 2}, {os.path.getsize(p) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
