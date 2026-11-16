"""Audit S3: calibration.sun_distance against SPICE's Sun to target (or to Cassini) distance for the frames before 2004.
usage: audit_sun_distance.py"""
import sys, os, sqlite3, collections, math, datetime
sys.path.insert(0, "."); sys.path.insert(0, "web/frames")
import numpy as np, spiceypy as sp
import bootleg_autonav as ba, calibration as cal
db = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/labels.sqlite"))
rows = db.execute("select frame, TARGET_NAME, IMAGE_MID_TIME, IMAGE_TIME from l where substr(IMAGE_MID_TIME,1,4) < '2004' and frame not like '% %' order by IMAGE_MID_TIME").fetchall()
AU = 149597870.7
out = collections.defaultdict(list)
loaded = None
for f, t, mid, when in rows:
    year = int(mid[:4])
    if year != loaded:
        sp.kclear(); ba.load_kernels(year, year); loaded = year
    try:
        et = sp.utc2et(mid.replace("Z", ""))
    except Exception as e:
        continue
    used = cal.sun_distance({"TARGET_NAME": t, "IMAGE_TIME": when})
    craft = np.linalg.norm(sp.spkpos("CASSINI", et, "J2000", "NONE", "SUN")[0]) / AU
    body = None
    name = {"MASURSKY": "2685"}.get(t, t)
    try:
        body = np.linalg.norm(sp.spkpos(name, et, "J2000", "NONE", "SUN")[0]) / AU
    except Exception:
        pass
    out[(year, t)].append((used, craft, body))
for (year, t), v in sorted(out.items()):
    used = np.array([x[0] if x[0] is not None else np.nan for x in v]); craft = np.array([x[1] for x in v])
    body = np.array([x[2] if x[2] is not None else np.nan for x in v])
    print(f"{year} {t:10s} n={len(v):5d}  used {np.nanmedian(used):6.3f} AU  Cassini {np.median(craft):6.3f}  target {np.nanmedian(body) if np.isfinite(body).any() else float('nan'):6.3f}"
          f"  I/F factor used/true {(np.nanmedian(used) / (np.nanmedian(body) if np.isfinite(body).any() else np.median(craft))) ** 2:7.2f}")
