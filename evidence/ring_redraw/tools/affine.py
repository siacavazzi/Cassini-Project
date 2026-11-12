#!/usr/bin/env python3
"""affine.py : for consecutive pointings, the affine map (cv2.findTransformECC, MOTION_AFFINE) taking t's overlap onto
s's, both drawn on the canvas where the layout puts them, started from t moved by the 2D ring move. Prints scale x/y,
turn, shear and the move at the overlap's middle."""
import argparse, os, sys, math
import numpy as np, cv2
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("--pairs", default=""); ap.add_argument("--spice", action="store_true"); ap.add_argument("obs")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server  # noqa
import obs_mosaic as om, calibration
from PIL import Image
with calibration.looking("balanced"):
    u = [u for u in om.units(*a.obs.split(":")) if u.get("kind") == "mosaic"][0]
    made = om.layout(u, len(u["frames"]) - 1, a.cache)
    tiles = [dict(t, offset=t.get("spice_place", t["offset"])) if a.spice else t for t in made[1] if "offset" in t]
    tl = {t["n"]: t for t in tiles}
    there = om._tiles(u, a.cache, made[0]["display_scale"])
    roots = {}
    for t in tiles:
        roots[t["n"]] = om._pointing_root(u, t["n"], roots)
    rs = sorted(set(roots.values()))
    by = {r: {t["filter"]: t for t in tiles if roots[t["n"]] == r} for r in rs}
    pairs = []
    for i in range(len(rs) - 1):
        A, B = by[rs[i]], by[rs[i + 1]]
        pairs += [(A[f]["n"], B[f]["n"]) for f in [f for f in A if f in B][:1]]
    def canvas(t):
        im = np.asarray(Image.open(t.get("pic") or os.path.join(there, f"{t['n']}.png")).convert("RGBA")).astype(np.float32)
        return im, t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1], t["box"][2] / im.shape[1]
    for sn, tn in pairs:
        s, t = tl[sn], tl[tn]
        S, T = canvas(s), canvas(t)
        x0, y0 = max(S[1], T[1]) + 10, max(S[2], T[2]) + 10
        x1, y1 = min(S[1] + S[0].shape[1] * S[3], T[1] + T[0].shape[1] * T[3]) - 10, min(S[2] + S[0].shape[0] * S[3], T[2] + T[0].shape[0] * T[3]) - 10
        W, H = int(x1 - x0), int(y1 - y0)
        g = []
        for im, ox, oy, k in (S, T):
            M = np.float32([[k, 0, ox - x0], [0, k, oy - y0]])
            v = cv2.warpAffine(im[..., :3].mean(axis=2), M, (W, H), flags=cv2.INTER_LINEAR)
            g.append(cv2.GaussianBlur(v, (0, 0), 1.0))
        best = None
        for start in ((0, 0), (-32, -8), (-16, -3), (-35, 18)):
            warp = np.float32([[1, 0, -start[0]], [0, 1, -start[1]]])
            try:
                cc, warp = cv2.findTransformECC(g[0], g[1], warp, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), None, 5)
            except cv2.error:
                continue
            if best is None or cc > best[0]:
                best = (cc, warp)
        if best is None:
            print(sn, tn, "no ECC"); continue
        cc, w = best
        # w maps s-overlap coords to t-overlap coords: t(x') = s(x) with x' = w @ [x, y, 1]
        A2 = w[:, :2]
        sx, sy = np.hypot(*A2[:, 0]), np.hypot(*A2[:, 1])
        turn = math.degrees(math.atan2(A2[1, 0], A2[0, 0]))
        mid = A2 @ np.array([W / 2, H / 2]) + w[:, 2] - np.array([W / 2, H / 2])
        print(f"{sn:>2}-{tn:<2} {s['filter']:6} ecc {cc:.3f} scale x {sx:.4f} y {sy:.4f} turn {turn:+.3f} deg, t content off by {mid[0]:+.1f},{mid[1]:+.1f} px at the middle  (box s {s['box'][2]:.0f} t {t['box'][2]:.0f})", flush=True)
