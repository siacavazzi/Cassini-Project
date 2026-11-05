#!/usr/bin/env python3
"""Ring reprojection before/after, through the checkout's own obs_mosaic (tiles, plan, layout, so_far): each pass's
whole mosaic drawn with the rings step off (main's way: Saturn's tiles as taken, registered on edges) and on (rings
redrawn as at the epoch, pointings registered on the rings' radial profile), the moves both make, and the numbers.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python evidence/ring_reproj/render.py --cache SCRATCH_CACHE --out OUTDIR FRAME...
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "web", "frames"))
sys.path.insert(0, os.path.join(HERE, "..", ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=("before", "after"))
    ap.add_argument("--crop", action="append", default=[],
                    help="x0,y0,x1,y1 fractions of the mosaic: that part drawn at native resolution (mosaic_native) too")
    ap.add_argument("frames", nargs="+")
    a = ap.parse_args()
    import cv2
    cv2.setNumThreads(1)
    import calibration
    import obs_mosaic as om
    os.makedirs(a.out, exist_ok=True)
    for spec in a.frames:
        u, _ = om.unit_of(spec)
        n = len(u["frames"]) - 1
        name = "_".join(map(str, u["key"])).replace("/", "-")
        t0 = time.time()
        p = om.plan(u, a.cache)
        tiles = [t for t in om._reports(u, a.cache, p, range(n + 1)) if "offset" in t]
        print(spec, u["key"], len(tiles), "tiles", f"{time.time() - t0:.0f} s", flush=True)
        rec = {"frame": spec, "key": u["key"], "tiles": len(tiles), "km_px": om.IFOV[u["key"][2]] * u["z"]}
        for label, off in (("before", "rings"), ("after", "")):
            if a.only and a.only != label:
                continue
            t0 = time.time()
            with calibration.stepping(off):
                made = om.layout(u, n, a.cache)
                report = {}
                drawn = made[1]
                moved = om.panel_places(u, a.cache, made[0], [t for t in drawn if "offset" in t], report=report) \
                    if made else {}
                im, _ = om.so_far(u, n, a.cache, made=made, out=om.CANVAS)
            rec[label] = {"name": made[5] if made else None, "s": round(time.time() - t0, 1),
                          "redrawn": sum(1 for t in drawn if "pic" in t) if made else 0,
                          "moves": {str(k): v for k, v in sorted(moved.items())},
                          "rect": made[2] if made else None, "k": made[0]["k"] if made else None}
            if im is not None:
                im.save(os.path.join(a.out, f"{name}_{label}.png"))
                rec[label]["size"] = im.size
            for i, c in enumerate(a.crop):
                import mosaic_native
                import shutil
                box = tuple(float(v) for v in c.split(","))
                with calibration.stepping(off):
                    found = mosaic_native.picture(u["frames"][n][1], a.cache, crop=box, fmt="png")
                if found:
                    shutil.copy(found[0], os.path.join(a.out, f"{name}_{label}_crop{i}.png"))
                    rec[label].setdefault("crops", []).append({"crop": box, **{k: v for k, v in found[1].items() if k in ("width", "height", "scale")}})
                    print("   crop", i, found[1], flush=True)
            print(" ", label, json.dumps({k: v for k, v in rec[label].items() if k != "moves"}), flush=True)
            print("   moves", json.dumps(rec[label]["moves"])[:3000], flush=True)
        with open(os.path.join(a.out, f"{name}.json"), "w") as fh:
            json.dump(rec, fh, indent=1, default=str)


if __name__ == "__main__":
    main()
