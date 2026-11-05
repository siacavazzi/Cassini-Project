"""Star field check of the WAC geometric correction: a WAC frame of a star field calibrated by the pipeline
(color_image.science_frame) with the "geom" step off (before) and on (after), its stars found and matched to Gaia DR3,
and the camera's pointing fitted (a rotation only, at a fixed focal length, as bootleg_autonav.project draws a
pinhole camera). What is left over is the camera's geometry the pipeline does not model."""
import sys, os, json, itertools
sys.path[:0] = [".", "web/frames"]
import numpy as np, cv2
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
import color_image as ci, calibration as cal

OUT, PATH, CAT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
cat = np.genfromtxt(CAT, delimiter=",", names=True)
cat = cat[np.argsort(cat["phot_g_mean_mag"])]
ra, de = np.radians(cat["ra"]), np.radians(cat["dec"])
U = np.stack([np.cos(de) * np.cos(ra), np.cos(de) * np.sin(ra), np.sin(de)], 1)
C = 511.5

def frame(on):
    if on:
        return ci.science_frame(PATH)[0]
    with cal.stepping(["geom"]):
        return ci.science_frame(PATH)[0]

def stars(img, n=800):
    x = np.nan_to_num(img).astype(np.float32)
    hp = x - cv2.medianBlur(x, 5) * 0 - cv2.GaussianBlur(cv2.medianBlur(x, 5), (0, 0), 8)
    s = 1.4826 * np.median(np.abs(hp - np.median(hp)))
    pk = (hp > 10 * s) & (hp == cv2.dilate(hp, np.ones((7, 7), np.uint8)))
    pk[:6, :] = pk[-6:, :] = pk[:, :6] = pk[:, -6:] = False
    pk &= np.isfinite(img)
    r, c = np.nonzero(pk)
    out = []
    for y, xx in zip(r, c):
        w = hp[y - 3:y + 4, xx - 3:xx + 4].astype(np.float64)
        w = np.clip(w - np.median(hp[y - 6:y + 7, xx - 6:xx + 7]), 0, None)
        tot = w.sum()
        if tot <= 0 or w[3, 3] / tot > 0.6:     # a hot pixel: one pixel holds the light
            continue
        yy, xg = np.mgrid[-3:4, -3:4]
        out.append((xx + (w * xg).sum() / tot, y + (w * yy).sum() / tot, tot))
    out = np.array(out)
    return out[np.argsort(-out[:, 2])][:n]

def rot(p):
    return cv2.Rodrigues(np.asarray(p, np.float64))[0]

def project(R, scale, u):
    v = u @ R          # J2000 -> camera (R is camera -> J2000)
    ok = v[:, 2] > 0
    return np.stack([C - v[:, 0] / v[:, 2] * scale, C - v[:, 1] / v[:, 2] * scale], 1), ok

def solve(det, scale):
    """pointing from the brightest stars: every pair of bright detected stars against every pair of bright catalogue
    stars at the same separation, the rotation that puts one onto the other, kept for the most matches"""
    d = det[:25, :2]
    # catalogue in a local tangent plane at its brightest star near the middle, at the given scale
    best = (0, None)
    c0 = U[0]
    for ci_ in range(min(60, len(U))):
        pass
    # tangent plane at the field's centre (mean of the bright catalogue)
    t = U[:300].mean(0); t /= np.linalg.norm(t)
    e1 = np.cross([0, 0, 1], t); e1 /= np.linalg.norm(e1); e2 = np.cross(t, e1)
    P = np.stack([(U @ e1) / (U @ t), (U @ e2) / (U @ t)], 1) * scale
    cb = P[:80]
    tree_all = cKDTree(P[:600])
    for i, j in itertools.combinations(range(len(d)), 2):
        dd = d[j] - d[i]; L = np.hypot(*dd)
        if L < 80:
            continue
        for a in range(len(cb)):
            for b in range(len(cb)):
                if a == b: continue
                cc = cb[b] - cb[a]
                if abs(np.hypot(*cc) - L) > 3:
                    continue
                # mirror (samples go to -X): fit x' = M p with M a reflection-rotation
                for flip in (1, -1):
                    ang = np.arctan2(cc[1], cc[0] * flip) - np.arctan2(dd[1], dd[0])
                    cs, sn = np.cos(ang), np.sin(ang)
                    M = np.array([[cs, -sn], [sn, cs]])
                    q = (d - d[i]) @ M.T
                    q[:, 0] *= flip
                    q += cb[a]
                    dist, _ = tree_all.query(q)
                    n = int((dist < 3).sum())
                    if n > best[0]:
                        best = (n, (M, flip, i, a, e1, e2, t))
    return best

def fit(det, scale_fixed, R0, free_scale=False):
    tree = None
    pts = det[:, :2]
    def match(R, scale):
        q, ok = project(R, scale, U)
        q = q[ok]
        tr = cKDTree(q)
        dist, k = tr.query(pts)
        return dist, q[k]
    R, scale = R0, scale_fixed
    p = cv2.Rodrigues(R)[0].ravel()
    for tol in (6, 4, 4, 4):
        dist, q = match(rot(p), scale)
        sel = dist < tol
        uu = None
        # matched catalogue unit vectors
        qall, ok = project(rot(p), scale, U)
        idx = np.nonzero(ok)[0]
        tr = cKDTree(qall[ok]); _, k = tr.query(pts[sel]); uu = U[idx[k]]
        def res(x):
            s = x[3] if free_scale else scale
            pr, _ = project(rot(x[:3]), s, uu)
            return (pr - pts[sel]).ravel()
        x0 = np.r_[p, scale] if free_scale else p
        x = least_squares(res, x0).x
        p = x[:3]
        if free_scale:
            scale = x[3]
    r = res(x).reshape(-1, 2)
    return rot(p), scale, pts[sel], r

report = {}
dets = {on: stars(frame(on)) for on in (False, True)}
print({k: len(v) for k, v in dets.items()})
import bootleg_autonav as ba, label_handler as lh, spiceypy as sp
ba.load_kernels(int(sys.argv[4]), int(sys.argv[4]))
R0 = np.array(sp.pxform("CASSINI_ISS_WAC", "J2000", ba.image_et(lh.label(PATH, as_png=True))))   # camera -> J2000, SPICE
import math
def refine_start(det, R, scale):
    """SPICE's pointing is off by some pixels: the shift that lines the most bright stars up (a vote over every
    detected-catalogue pair within 80 px), then the camera rotation that puts the stars matched at it in place"""
    q, ok = project(R, scale, U)
    q = q[ok]; uu = U[ok]
    inside = (q[:, 0] > -20) & (q[:, 0] < 1044) & (q[:, 1] > -20) & (q[:, 1] < 1044)
    q, uu = q[inside][:500], uu[inside][:500]
    d = det[:200, :2]
    diff = (d[:, None, :] - q[None, :, :]).reshape(-1, 2)
    diff = diff[(np.abs(diff) < 80).all(1)]
    H, xe, ye = np.histogram2d(diff[:, 0], diff[:, 1], bins=160, range=[[-80, 80], [-80, 80]])
    i, j = np.unravel_index(np.argmax(H), H.shape)
    off = np.array([(xe[i] + xe[i + 1]) / 2, (ye[j] + ye[j + 1]) / 2])
    tr = cKDTree(q + off); dist, k = tr.query(d)
    good = dist < 2.5
    print("start shift", off, "matched", int(good.sum()))
    cam = np.stack([-(d[good, 0] - C) / scale, -(d[good, 1] - C) / scale, np.ones(good.sum())], 1)
    cam /= np.linalg.norm(cam, axis=1)[:, None]
    sky = uu[k[good]]
    Hm = cam.T @ sky
    Uu, S, Vt = np.linalg.svd(Hm)
    Dm = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ Uu.T))])
    return Vt.T @ Dm @ Uu.T
for on, label, f in ((False, "before", 200.77), (True, "after", 200.956)):
    Rs = refine_start(dets[on], R0, f / 0.012)
    R, sc, pts, r = fit(dets[on], f / 0.012, Rs)
    _, scf, _, rf = fit(dets[on], f / 0.012, Rs, free_scale=True)
    rad = np.hypot(pts[:, 0] - 548, pts[:, 1] - 508)
    m = np.hypot(r[:, 0], r[:, 1])
    bins = [(0, 250), (250, 450), (450, 600), (600, 800)]
    report[label] = {"stars_matched": int(len(m)), "focal_mm_fixed": f, "rms_px": round(float(np.sqrt((m ** 2).mean())), 3),
                     "rms_by_radius_px": {f"{lo}-{hi}": round(float(np.sqrt((m[(rad >= lo) & (rad < hi)] ** 2).mean())), 3) if ((rad >= lo) & (rad < hi)).sum() > 2 else None for lo, hi in bins},
                     "median_by_radius_px": {f"{lo}-{hi}": round(float(np.median(m[(rad >= lo) & (rad < hi)])), 3) if ((rad >= lo) & (rad < hi)).sum() > 2 else None for lo, hi in bins},
                     "stars_by_radius": {f"{lo}-{hi}": int(((rad >= lo) & (rad < hi)).sum()) for lo, hi in bins},
                     "best_focal_mm_if_free": round(float(scf * 0.012), 3),
                     "rms_px_free_focal": round(float(np.sqrt((rf ** 2).sum(1).mean())), 3)}
    np.save(f"{OUT}/resid_{label}.npy", np.c_[pts, r])
    # figure: residual arrows x60 on the frame
    img = frame(on)
    lo, hi = np.nanpercentile(img, 50), np.nanpercentile(img, 99.8)
    g = (np.clip((np.nan_to_num(img, nan=lo) - lo) / (hi - lo), 0, 1) ** 0.5 * 255).astype(np.uint8)
    g = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    for (x, y), (dx, dy) in zip(pts, r):
        if dx * dx + dy * dy > 16:
            continue
        cv2.arrowedLine(g, (int(x), int(y)), (int(x - dx * 60), int(y - dy * 60)), (0, 200, 255), 2, tipLength=0.2)
        cv2.circle(g, (int(x), int(y)), 4, (80, 255, 80), 1)
    rep = report[label]
    cv2.putText(g, f"{label.upper()}: geom {'on' if on else 'off'}, pinhole at {f} mm, {rep['stars_matched']} Gaia stars", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
    cv2.putText(g, f"star off its Gaia place, arrows x60. median px by radius 0-250/250-450/450-600/600+: " + "/".join(str(v) for v in rep['median_by_radius_px'].values()), (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
    cv2.imwrite(f"{OUT}/stars_{label}.png", g)
    # the four corners, 6x, with where Gaia puts each star (red circles) on the frame as calibrated
    q, ok = project(R, sc, U)
    plain = cv2.cvtColor((np.clip((np.nan_to_num(img, nan=lo) - lo) / (hi - lo), 0, 1) ** 0.5 * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    tiles = []
    Z, W = 6, 100
    for r0, c0 in ((4, 4), (4, 1024 - W - 4), (1024 - W - 4, 4), (1024 - W - 4, 1024 - W - 4)):
        t = cv2.resize(plain[r0:r0 + W, c0:c0 + W], (W * Z, W * Z), interpolation=cv2.INTER_NEAREST)
        sel = ok & (q[:, 0] > c0 - 2) & (q[:, 0] < c0 + W + 2) & (q[:, 1] > r0 - 2) & (q[:, 1] < r0 + W + 2)
        for x, y in q[sel]:
            cv2.circle(t, (int((x - c0 + 0.5) * Z), int((y - r0 + 0.5) * Z)), 14, (40, 40, 255), 2)
        tiles.append(np.pad(t, ((4, 4), (4, 4), (0, 0))))
    band = np.zeros((44, len(tiles) * (W * Z + 8), 3), np.uint8)
    cv2.putText(band, f"{label.upper()} (geom {'on' if on else 'off'}, pinhole {f} mm): the 4 corners at 6x, red = Gaia star places", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.imwrite(f"{OUT}/corners_{label}.png", np.vstack([band, np.hstack(tiles)]))
json.dump(report, open(f"{OUT}/report.json", "w"), indent=1)
print(json.dumps(report, indent=1))
