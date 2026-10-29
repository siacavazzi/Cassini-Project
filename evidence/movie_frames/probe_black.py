#!/usr/bin/env python3
"""Why does tile_scale's black_of raise a movie frame's black above everything in it? (group D, 2026-10-29)
For each frame id: the I/F its tile is drawn from (what load_channels gets, captured), and black_of's steps on it
(the sky mask, the sky level, the frame's own grain, the pass's sky top), with the pass's scale from its cached plan.
Writes nothing. CASSINI_REPO = the checkout whose code is probed.

  CASSINI_REPO=<checkout> CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python probe_black.py --cache <cache> \\
      --version obs-v46-q95 W1823078862_1 ..."""
import argparse
import json
import os
import sys

repo = os.environ["CASSINI_REPO"]
sys.path[:0] = [os.path.join(repo, "web", "frames"), repo]
import numpy as np  # noqa: E402
import calibration  # noqa: E402
import color_image  # noqa: E402
import obs_mosaic as om  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cache", required=True)
ap.add_argument("--version", default="obs-v46-q95")
ap.add_argument("ids", nargs="+")
args = ap.parse_args()
cache = os.path.expanduser(args.cache)
got = {}
real = calibration.load_channels


def spy(labels, images=None, *a, **k):
    iofs = calibration._calibrated(labels, images if images is not None else [l.resize_image() for l in labels], k.get("iofs"))
    got["iofs"] = iofs
    got["info"] = labels[0].get_info()
    return real(labels, images, *a, **k)


calibration.load_channels = spy
for fid in args.ids:
    found = om.unit_of(fid)
    if not found:
        print(fid, "in no pass"); continue
    u, n = found
    name = "_".join(map(str, u["key"])) + ("" if u.get("repeat_gap", 120) >= 120 else f"_r{u['repeat_gap']:g}")
    try:
        scale = json.load(open(os.path.join(cache, args.version, name, om.PLAN_FILE)))["display_scale"]
    except OSError:
        print(fid, "no cached plan for", name); continue
    fr = u["frames"][n]
    f = fr[2]
    seen = {}
    with calibration.looking("balanced"):
        im, _, rep = color_image.processed_frame([fr[0]], hdr=True, scale=om.tile_scale(scale, f, True, seen),
                                                 repeat_window=u.get("repeat_gap", 120))
    iof, info = got.get("iofs", [None])[0], got.get("info", {})
    out = {"id": fid, "pass": name, "n": n, "filter": f, "exposure": info.get("EXPOSURE_DURATION"),
           "conversion": info.get("DATA_CONVERSION_TYPE"), "compression": info.get("INST_CMPRS_TYPE"),
           "gain": info.get("GAIN_MODE_ID"), "pass_black": scale["blacks"].get(f), "white": scale["white"],
           "sky_top": scale.get("sky_tops", {}).get(f), "raised": seen.get("black"), "calibrated": rep.get("calibrated")}
    if iof is not None:
        q = iof[::4, ::4].astype(np.float32)
        p999 = float(np.percentile(q, 99.9))
        m = q < 0.05 * p999
        out.update({"iof_p1": float(np.percentile(q, 1)), "iof_p50": float(np.median(q)), "iof_p99": float(np.percentile(q, 99)),
                    "iof_p999": p999, "iof_max": float(q.max()), "sky_share": float(m.mean())})
        if m.mean() > om.SKY_MIN:
            (level,), margin = calibration.sky_levels([[q]], [[m]])
            fine = om._sky_fine([q], [m])
            own = float(np.percentile(fine, om.SKY_TOP_PCT) - np.median(fine)) if fine.size > 100 else 0.0
            out.update({"sky_level": level, "sky_median": float(np.median(q[m])), "own_grain": own, "fine_n": int(fine.size),
                        "values": int(np.unique(q).size)})
        drawn = np.asarray(im)[..., :3][np.asarray(im)[..., 3] > 0] if im is not None else np.zeros(1)
        out["drawn_mean"] = float(drawn.mean())
    print(json.dumps({k: (round(v, 6) if isinstance(v, float) else v) for k, v in out.items()}), flush=True)
