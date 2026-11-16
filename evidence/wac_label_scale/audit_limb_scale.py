"""Audit S1: the cameras' pixel scale measured on real limbs. For whole-disk frames of Rhea and Dione (the roundest
moons), as the pipeline draws them (calibration.calibrate, with the wide-angle geometric correction), the lit limb is
found along rays from the disk's middle (steepest fall, to a fraction of a pixel) and a circle fitted to it, center
free, so pointing does not matter. SPICE gives the limb's angular size (the limb ellipse of the body's own radii seen
from Cassini). tan(angular radius) / fitted radius in pixels = radians per pixel.
usage: audit_limb_scale.py cands.json out.jsonl"""
import sys, os, json, math
sys.path.insert(0, "."); sys.path.insert(0, "web/frames")
import numpy as np, cv2, spiceypy as sp
import bootleg_autonav as ba, calibration as cal, data_source as ds, label_handler as lh
cands = json.load(open(sys.argv[1]))
loaded = None
def limb_tan(target, et):
    """The limb's angular radius seen from Cassini, as tan(angle): mean and the two extremes (its ellipse)."""
    pos, lt = sp.spkpos(target, et, "J2000", "LT+S", "CASSINI")
    rot = sp.pxform("J2000", "IAU_" + target, et - lt)
    view = rot @ (-np.asarray(pos))                      # Cassini from the body's center, body-fixed
    a, b, c = sp.bodvrd(target, "RADII", 3)[1]
    center, smaj, smin = sp.el2cgv(sp.edlimb(a, b, c, view))
    axis = -view / np.linalg.norm(view)
    t = []
    for phi in np.linspace(0, 2 * math.pi, 360, endpoint=False):
        d = center + math.cos(phi) * smaj + math.sin(phi) * smin - view
        t.append(np.linalg.norm(np.cross(d, axis)) / float(d @ axis))
    return float(np.mean(t)), float(np.min(t)), float(np.max(t)), float(np.linalg.norm(pos))
def fit_circle(x, y):
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]; sol = np.linalg.lstsq(A, x * x + y * y, rcond=None)[0]
    cx, cy = sol[0], sol[1]; r = math.sqrt(sol[2] + cx * cx + cy * cy)
    for _ in range(20):                                  # geometric refinement (Gauss-Newton)
        dx, dy = x - cx, y - cy; d = np.hypot(dx, dy)
        J = np.c_[-dx / d, -dy / d, -np.ones(len(x))]; step = np.linalg.lstsq(J, -(d - r), rcond=None)[0]
        cx, cy, r = cx + step[0], cy + step[1], r + step[2]
    return cx, cy, r, float(np.std(np.hypot(x - cx, y - cy) - r))
with open(sys.argv[2], "a") as out:
    for cam, rows in cands.items():
        for frame, target, r0 in rows:
            rec = dict(frame=frame, cam=cam, target=target)
            try:
                path = ("nac_data/" if cam == "N" else "wac_data/") + frame + ".png"
                lbl = lh.label(path, as_png=True)
                year = int(str(lbl.info["IMAGE_TIME"])[:4])
                if year != loaded:
                    sp.kclear(); ba.load_kernels(year, year); loaded = year
                loc = ba.find_target_cached(lbl)
                et = float(lbl.geometry["et"])
                tan_mean, tan_min, tan_max, rng = limb_tan(target, et)
                img = lbl.resize_image(); img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
                iof = cal.calibrate(ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE), lbl.get_info(), img, smooth=False)
                if iof is None: raise ValueError("not calibrated")
                im = cv2.GaussianBlur(np.asarray(iof, np.float32), (0, 0), 0.7)
                cx, cy = ba.CCD_CENTER - float(loc[0]), ba.CCD_CENTER - float(loc[1])
                bright = float(np.percentile(im, 99.0))
                for rnd in range(2):                     # second round from the fitted middle
                    xs, ys = [], []
                    rr = np.arange(r0 - 30, r0 + 30, 0.25, dtype=np.float32)
                    for th in np.deg2rad(np.arange(0, 360, 1.0)):
                        px = (cx + rr * math.cos(th)).astype(np.float32); py = (cy + rr * math.sin(th)).astype(np.float32)
                        if px.min() < 2 or py.min() < 2 or px.max() > 1021 or py.max() > 1021: continue
                        prof = cv2.remap(im, px.reshape(1, -1), py.reshape(1, -1), cv2.INTER_LINEAR).ravel()
                        g = np.gradient(prof)
                        k = int(np.argmin(g))
                        if k < 8 or k > len(g) - 9: continue
                        inside, outside = float(prof[max(k - 24, 0):k - 6].mean()), float(prof[k + 6:k + 24].mean())
                        if inside < 0.3 * bright or outside > 0.15 * inside: continue        # a lit limb: bright to black
                        den = g[k - 1] - 2 * g[k] + g[k + 1]
                        sub = 0.5 * (g[k - 1] - g[k + 1]) / den if den != 0 else 0.0
                        r_edge = float(rr[k] + 0.25 * sub)
                        xs.append(cx + r_edge * math.cos(th)); ys.append(cy + r_edge * math.sin(th))
                    if len(xs) < 100: raise ValueError(f"only {len(xs)} limb rays")
                    x, y = np.array(xs), np.array(ys)
                    fx, fy, fr, resid = fit_circle(x, y)
                    keep = np.abs(np.hypot(x - fx, y - fy) - fr) < max(3 * resid, 0.5)          # craters and hills on the limb out
                    fx, fy, fr, resid = fit_circle(x[keep], y[keep])
                    cx, cy, r0 = fx, fy, fr
                rec.update(rays=int(keep.sum()), radius_px=fr, resid=resid, tan=tan_mean, tan_spread=(tan_max - tan_min) / tan_mean, range_km=rng,
                           rad_per_px=tan_mean / fr, centre_off=float(np.hypot(fx - (ba.CCD_CENTER - float(loc[0])), fy - (ba.CCD_CENTER - float(loc[1])))),
                           filt=str(lbl.info.get("FILTER_NAME")))
            except Exception as e:
                rec["err"] = f"{type(e).__name__} {e}"[:140]
            out.write(json.dumps(rec) + "\n"); out.flush()
            print(rec, flush=True)
