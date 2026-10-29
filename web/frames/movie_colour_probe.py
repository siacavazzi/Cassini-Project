#!/usr/bin/env python3
"""
What a movie's colour frame is drawn from, for a look elsewhere: for each frame id named, the pass's colour set at
that frame (as movie_frame picks it), each filter's plane as movie_frame places it at OUT (SPICE's places), the colour
picture made of them (colour_picture), the set's colour still (the frame server's composite), and the movie frame
in colour and grey (exposure normalization 8, as the page asks), as PNGs, plus each set tile's report and how the
pipeline's alignment (_shift_onto) finds each filter against the newest: probe.json. Fresh cache of its own.
  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... CASSINI_CISSCAL=... python web/frames/movie_colour_probe.py \\
      N1677190309_1 [more ids] --out DIR
"""
import argparse
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import frame_server  # noqa: E402  (loads the index as the server does; its composite is the colour still)
import obs_mosaic as om  # noqa: E402


def probe(fid, cache, out):
    u, n = om.unit_of(fid)
    p = om.plan(u, cache)
    sc = p["display_scale"]
    rec = {"pass": list(u["key"]), "n": n, "colour": p["colour"]}
    want = p["colour"]
    got = None
    for run in reversed(om.colour_sets(u["frames"][:n + 1])):
        g = {f: j for f, j in run if f in want}
        if len(g) == len(want):
            got = g
            break
    if not got:
        rec["why"] = "no complete set"
        return rec
    js = [got[f] for f in want]
    tiles = [om.tile(u, j, cache, sc) for j in js]
    rec["tiles"] = [{k: t.get(k) for k in ("n", "id", "filter", "t", "offset", "spice_offset", "registered", "box")} for t in tiles]
    t = tiles[js.index(max(js))]
    rect = om.movie_rect(om.movie_footprint(u, cache, p), t)
    k = om.OUT / max(rect[2], rect[3])
    W, H = max(1, math.ceil(rect[2] * k)), max(1, math.ceil(rect[3] * k))
    planes = [om._place(u, q, rect, k, W, H, cache, sc) for q in tiles]
    for f, a in zip(want, planes):
        Image.fromarray(a, "RGBA").save(os.path.join(out, f"{fid}-plane-{f}.png"))
    Image.fromarray(om.colour_picture(u, p, want, planes), "RGBA").save(os.path.join(out, f"{fid}-colour.png"))
    ref = max(js)
    there = om._tiles(u, cache, sc)
    pic = lambda j: np.asarray(Image.open(os.path.join(there, f"{j}.png")).convert("RGBA"))
    q = om.tile(u, ref, cache, sc)
    rec["pairs"] = {}
    for j in js:
        if j != ref:
            tj = om.tile(u, j, cache, sc)
            shift, how = om._shift_onto(q, pic(ref), q["offset"], tj, pic(j), tj["offset"])
            rec["pairs"][f"{ref},{j}"] = {"shift": shift, "how": how}
    rec["view"], rec["k"] = list(rect), k
    # the same set as a colour still (the frame server's composite, color_image.load_aligned on linear data), and the
    # movie frame in colour and grey as the page asks for it by default (exposure normalization 8)
    try:
        im, rep = frame_server.composite([q["id"] for q in tiles])
        im.convert("RGBA").save(os.path.join(out, f"{fid}-still.png"))
        rec["still"] = {"aligned": rep.get("aligned"), "calibrated": rep.get("calibrated")}
    except Exception as e:
        rec["still"] = {"error": f"{type(e).__name__}: {e}"[:300]}
    for name, colour in (("movie", True), ("grey", False)):
        im, rep = om.movie_frame(u, n, cache, colour=colour, exposure=8)
        if im is not None:
            im.save(os.path.join(out, f"{fid}-{name}.png"))
        rec[name] = {k: rep.get(k) for k in ("color", "ids", "exposure", "set_places")}
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    cache = tempfile.mkdtemp(dir=args.out)
    res = {}
    with calibration.looking("balanced"):
        for fid in args.ids:
            try:
                res[fid] = probe(fid, cache, args.out)
            except Exception as e:
                res[fid] = {"error": f"{type(e).__name__}: {e}"[:300]}
    with open(os.path.join(args.out, "probe.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
