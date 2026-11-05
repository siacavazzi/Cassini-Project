# Image check of the pointing: for consecutive frames of one observation (same camera, <= 300 s apart) whose
# pictures overlap, the offset of their content (template match) against the offset SPICE gives their target.
# argv: repo before.sqlite after.sqlite years(comma)
import sys, os
sys.path.insert(0, sys.argv[1])
import data_source as ds, cv2, numpy as np, sqlite3, pandas as pd
b = sqlite3.connect(sys.argv[2]); a = sqlite3.connect(sys.argv[3])
years = sys.argv[4].split(",")
ix = pd.read_csv(sys.argv[1] + "/Image_index.csv", usecols=["path", "OBSERVATION_ID", "TARGET_NAME", "seconds_1970", "IMAGE_MID_TIME"], low_memory=False)
ix = ix[(ix.TARGET_NAME == "TITAN") & ix.path.str.startswith("nac_data") & ix.IMAGE_MID_TIME.str[:4].isin(years)]
ix["frame"] = ix.path.str.split("/").str[-1].str.split(".").str[0]
tagged = {f for f, in a.execute("select frame from pointing")}
ix = ix[ix.frame.isin(tagged)].sort_values("seconds_1970")
def pos(db, f):
    r = db.execute("select x,y from target where frame=? and error is null", (f,)).fetchone()
    return None if r is None else np.array(r)
cache = {}
def img(p):
    if p not in cache:
        im = ds.imread(p, cv2.IMREAD_GRAYSCALE)
        if im.shape[0] != 1024: im = cv2.resize(im, (1024, 1024))
        im = cv2.medianBlur(im, 5).astype(np.float32)
        cache.clear(); cache[p] = cv2.GaussianBlur(im, (0, 0), 5) - cv2.GaussianBlur(im, (0, 0), 30)
    return cache[p]
out = []
for obs, g in ix.groupby("OBSERVATION_ID"):
    rows = list(g.itertuples())
    for p, q in zip(rows, rows[1:]):
        if q.seconds_1970 - p.seconds_1970 > 300: continue
        pb, qb, pa, qa = pos(b, p.frame), pos(b, q.frame), pos(a, p.frame), pos(a, q.frame)
        if any(v is None for v in (pb, qb, pa, qa)): continue
        eb, ea = qb - pb, qa - pa
        guess = (ea + eb) / 2
        if np.abs(guess).max() > 300: continue
        A = img(p.path); B = ds.imread(q.path, cv2.IMREAD_GRAYSCALE)
        if B.shape[0] != 1024: B = cv2.resize(B, (1024, 1024))
        B = cv2.medianBlur(B, 5).astype(np.float32); B = cv2.GaussianBlur(B, (0, 0), 5) - cv2.GaussianBlur(B, (0, 0), 30)
        c = B[312:712, 312:712]
        m = cv2.matchTemplate(A, c, cv2.TM_CCOEFF_NORMED); _, mx, _, loc = cv2.minMaxLoc(m)
        if mx < 0.6: continue
        s = np.array([loc[0] - 312, loc[1] - 312])
        out.append((p.frame, q.frame, *s, *eb, *ea, mx))
        print(p.frame, q.frame, "content", s, "before", eb.round(1), "after", ea.round(1), round(mx, 2), flush=True)
o = np.array([r[2:] for r in out], dtype=float)
db_ = np.hypot(o[:, 0] - o[:, 2], o[:, 1] - o[:, 3]); da = np.hypot(o[:, 0] - o[:, 4], o[:, 1] - o[:, 5])
print(f"{len(o)} pairs; |content - SPICE| px: before median {np.median(db_):.1f} p90 {np.percentile(db_, 90):.1f} | after median {np.median(da):.1f} p90 {np.percentile(da, 90):.1f}; after closer in {np.sum(da < db_)}, before closer in {np.sum(db_ < da)}")
big = np.hypot(o[:, 0], o[:, 1]) > 10
print(f"pairs whose content jumped > 10 px: {big.sum()}; before median miss {np.median(db_[big]) if big.any() else 0:.1f}, after {np.median(da[big]) if big.any() else 0:.1f}")
