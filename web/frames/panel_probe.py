#!/usr/bin/env python3
"""How far apart a real mosaic's panels land where SPICE puts them, and what panel registration
(obs_mosaic.panel_places) does about it, through the checkout's own obs_mosaic (tiles, plan, layout, so_far), nothing
re-implemented.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/panel_probe.py --cache SCRATCH_CACHE --out OUTDIR PASS...

PASS is a frame id (N1477496427_2) or TARGET:OBSERVATION_ID:CAM[:pass]. Never point --cache at a cache the server
or the pre-build uses: the tiles and mosaics made here are written to it.

For each pass: every pair of overlapping pointings measured where SPICE put them (panel_shift: how far apart they
are, reference pixels and full resolution pixels, the time between them and how far the body's turning carries a
feature on its disk in that time), the moves registration makes, the pairs measured again once moved (what is left),
and the whole mosaic drawn with the panels step off and on, with 1:1 crops of the pairs moved most side by side.
OUTDIR/index.html puts them on a page and OUTDIR/probe.json keeps the numbers."""
import argparse
import html
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

CROP = 192
ZOOM = 2


def unit(spec):
    import obs_mosaic as om
    if ":" in spec:
        parts = spec.split(":")
        target, obs, cam = parts[:3]
        k = int(parts[3]) if len(parts) > 3 else None
        us = [v for v in om.units(target, obs, cam) if v["mosaic"]] or om.units(target, obs, cam)
        if not us:
            return None, None
        u = us[k] if k is not None else max(us, key=lambda v: len(v["frames"]))
        return u, len(u["frames"]) - 1
    found = om.unit_of(spec)
    return found if found else (None, None)


def pairs(u, p, tiles, places, pic):
    """Every pair of overlapping pointings (first tiles), measured with each at places[n]: [{a, b, shift, ...}]."""
    import obs_mosaic as om
    roots = {}
    for t in tiles:
        roots[t["n"]] = om._pointing_root(u, t["n"], roots)
    firsts = [t for t in tiles if roots[t["n"]] == t["n"]]
    spin = om.SPIN.get(u["key"][0])
    per_px = om.IFOV[u["key"][2]] * u["z"]   # km a reference pixel spans
    out = []
    for i, b in enumerate(firsts):
        for a in firsts[:i]:
            at_a, at_b = places[a["n"]], places[b["n"]]
            shift, how = om.panel_shift(a, pic(a["n"]), at_a, b, pic(b["n"]), at_b)
            if how in ("apart",):
                continue
            dt = abs(b["t"] - a["t"])
            row = {"a": a["n"], "b": b["n"], "filters": [a["filter"], b["filter"]], "dt": round(dt, 1),
                   "spin_px": round(2 * math.pi * spin[0] / (spin[1] * 3600) * dt / per_px, 1) if spin else None}
            if shift is None:
                row["why"] = how
            else:
                row.update(how)
                row["shift"] = [round(shift[0], 2), round(shift[1], 2)]
                row["px"] = round(math.hypot(*shift), 2)
                row["full_px"] = round(math.hypot(*shift) * u["z"] / max(u["z"], 1), 2)
            out.append(row)
    return out


def stats(rows):
    v = [r["px"] for r in rows if "px" in r]
    if not v:
        return {"measured": 0, "pairs": len(rows)}
    return {"pairs": len(rows), "measured": len(v), "median": round(float(np.median(v)), 2),
            "p90": round(float(np.percentile(v, 90)), 2), "max": round(float(max(v)), 2)}


def crop(im, x, y):
    h = CROP // 2
    x0, y0 = max(0, min(im.width - CROP, int(x) - h)), max(0, min(im.height - CROP, int(y) - h))
    return im.crop((x0, y0, x0 + CROP, y0 + CROP)).resize((CROP * ZOOM, CROP * ZOOM), Image.NEAREST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("passes", nargs="+")
    a = ap.parse_args()
    import calibration
    import obs_mosaic as om
    os.makedirs(a.out, exist_ok=True)
    every, page = [], []
    for spec in a.passes:
        u, n = unit(spec)
        if u is None:
            print(spec, "no pass")
            continue
        name = "_".join(map(str, u["key"])).replace("/", "-")
        t0 = time.time()
        p = om.plan(u, a.cache)
        tiles = [t for t in om._reports(u, a.cache, p, range(n + 1)) if "offset" in t]
        made_s = time.time() - t0
        there = om._tiles(u, a.cache, p["display_scale"])
        pics = {}

        def pic(j):
            if j not in pics:
                pics[j] = np.asarray(Image.open(os.path.join(there, f"{j}.png")).convert("RGBA"))
            return pics[j]
        spice = {t["n"]: t["offset"] for t in tiles}
        # (measured up to 6% of a frame, as in the first rounds, so the shifts registration no longer believes show)
        cap, om.PANEL_MAX = om.PANEL_MAX, 0.06
        before = pairs(u, p, tiles, spice, pic)
        om.PANEL_MAX = cap
        # the surface redrawn as at the pass's epoch (surface_pictures), measured again where SPICE put each tile
        t1 = time.time()
        surfaced = om.surface_pictures(u, a.cache, p, tiles)
        surf_s = time.time() - t1
        spics = {}

        def spic(j):
            if j not in surfaced:
                return pic(j)
            if j not in spics:
                spics[j] = np.asarray(Image.open(surfaced[j]).convert("RGBA"))
            return spics[j]
        om.PANEL_MAX = 0.06
        surface = pairs(u, p, tiles, spice, spic) if surfaced else []
        om.PANEL_MAX = cap
        t1 = time.time()
        report = {}
        drawn = [dict(t, pic=surfaced[t["n"]]) if t["n"] in surfaced else t for t in tiles]
        moved = om.panel_places(u, a.cache, p, drawn, pic=spic, report=report)
        reg_s = time.time() - t1
        placed = {n: [xy[0] + moved.get(n, [0, 0])[0], xy[1] + moved.get(n, [0, 0])[1]] for n, xy in spice.items()}
        after = pairs(u, p, tiles, placed, spic)
        rec = {"pass": spec, "key": u["key"], "tiles": len(tiles), "z_km": u["z"], "kind": u.get("kind"),
               "km_per_px": round(om.IFOV[u["key"][2]] * u["z"], 3), "tiles_s": round(made_s, 1), "register_s": round(reg_s, 2),
               "surface_s": round(surf_s, 1), "surfaced": len(surfaced),
               "before": stats(before), "surface": stats(surface), "after": stats(after),
               "moves": {str(k): v for k, v in sorted(moved.items())}, "pairs_before": before, "pairs_surface": surface,
               "pairs_after": after,
               "report": {str(k): v for k, v in report.items()}}
        print(json.dumps({k: rec[k] for k in ("pass", "key", "tiles", "km_per_px", "surfaced", "before", "surface", "after", "surface_s", "register_s")}), flush=True)
        for r in before:
            print("   before", r, flush=True)
        for k, v in sorted(moved.items()):
            print("   move", k, v, flush=True)
        # the whole mosaic, panels off and on, and crops where the pairs moved most
        pictures = {}
        for label, off in (("spice", "surface,panels"), ("surface", "panels"), ("registered", "")):
            with calibration.stepping(off):
                made = om.layout(u, n, a.cache)
                im, _ = om.so_far(u, n, a.cache, made=made, out=om.CANVAS)
            pictures[label] = (im, made)
            im.save(os.path.join(a.out, f"{name}_{label}.png"))
        _, made = pictures["spice"]
        mp, _, rect, *_ = made
        k = mp["k"] * pictures["spice"][0].width / math.ceil(rect[2] * mp["k"])
        by = {t["n"]: t for t in tiles}
        worst = sorted([r for r in before if "px" in r], key=lambda r: -r["px"])[:4]
        crops = []
        for i, r in enumerate(worst):
            ta, tb = by[r["a"]], by[r["b"]]
            # the middle of the two tiles' overlap, on the picture
            xa0, ya0 = spice[ta["n"]][0] + ta["box"][0], spice[ta["n"]][1] + ta["box"][1]
            xb0, yb0 = spice[tb["n"]][0] + tb["box"][0], spice[tb["n"]][1] + tb["box"][1]
            cx = (max(xa0, xb0) + min(xa0 + ta["box"][2], xb0 + tb["box"][2])) / 2
            cy = (max(ya0, yb0) + min(ya0 + ta["box"][3], yb0 + tb["box"][3])) / 2
            x, y = (cx - rect[0]) * k, (cy - rect[1]) * k
            row = Image.new("RGBA", (CROP * ZOOM * 3 + 16, CROP * ZOOM), (0, 0, 0, 255))
            for i3, label in enumerate(("spice", "surface", "registered")):
                row.paste(crop(pictures[label][0], x, y), ((CROP * ZOOM + 8) * i3, 0))
            fn = f"{name}_crop{i}.png"
            row.save(os.path.join(a.out, fn))
            crops.append((fn, r, round(x), round(y)))
        rec["crops"] = [{"file": c[0], "x": c[2], "y": c[3], "pair": [c[1]["a"], c[1]["b"]]} for c in crops]
        every.append(rec)
        page.append(f"<h2>{html.escape(spec)} ({len(tiles)} tiles, {rec['km_per_px']} km/px)</h2>"
                    f"<p>SPICE's places: pairs {rec['before']}<br>surface at one moment: pairs {rec['surface']}<br>"
                    f"surface and panels lined up: pairs {rec['after']}<br>"
                    f"moves {html.escape(json.dumps(rec['moves']))}</p>"
                    f"<p>whole: <a href='{name}_spice.png'>SPICE</a> | <a href='{name}_surface.png'>surface</a> | "
                    f"<a href='{name}_registered.png'>surface + panels</a></p>"
                    + "".join(f"<p>pair {c[1]['a']}–{c[1]['b']}: {c[1]['px']} px apart at SPICE's places, {c[1]['dt']} s between, "
                              f"at ({c[2]}, {c[3]}). Left SPICE, middle surface at one moment, right surface + panels lined up ({ZOOM}x)<br><img src='{c[0]}'></p>" for c in crops))
    json.dump(every, open(os.path.join(a.out, "probe.json"), "w"), indent=1, default=str)
    with open(os.path.join(a.out, "index.html"), "w") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>Panel registration probe</title><body style='background:#111;color:#ddd;font:14px sans-serif'>"
                 "<h1>Panel registration probe</h1>" + "".join(page))


if __name__ == "__main__":
    main()
