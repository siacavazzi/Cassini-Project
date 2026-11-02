# -*- coding: utf-8 -*-
"""
How long a WAC dust donut stays put: for one filter pair's WAC frames within --days of a date, each frame's
brightness over its neighborhood's (flat field on, WAC dust map off; no lit or busy test, each spot's lit share says
whether it could show dust) at a few spots, as a
table, and a contact sheet of each frame's ratio round each spot. The per-epoch maps (build_wac_dust.py) do not show
the donuts of W1627244567_1 at all, so either the donuts come and go within an epoch or they move; this tells which.

Run from the main folder with CASSINI_DATA and CASSINI_CISSCAL set (reads only):
  python "helper programs/dust_persistence.py" --pair CL1,CL2 --date 2009-07-25 --days 120 \
      --spots 820,620 260,290 980,840 --out DIR [--workers 3] [--most 120]
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_wac_dust as bwd  # noqa: E402
import calibration as cal  # noqa: E402
import flat_field as ff  # noqa: E402
import label_handler as lh  # noqa: E402
import stacking  # noqa: E402

HALF = 48   # px: each crop is twice this across


def ratio(path):
    """The frame's brightness over its neighborhood's (a 20 px blur), with no test of how lit or busy the scene is
    (build_wac_dust.measure's are for the maps; here each spot says itself whether it was lit), and what was
    left out: (ratio, lit share per pixel as iof / the frame's 90th percentile, why)."""
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    if ff._value(info, "INSTRUMENT_MODE_ID") != "FULL":
        return None, None, "not FULL"
    with cal.stepping("stack"):
        _, iof, _ = stacking.load_hdr(path, 120)
    if iof is None:
        return None, None, "not calibrated"
    iof = np.asarray(iof, np.float32)
    good = np.isfinite(iof)
    top = float(np.percentile(iof[good], 90)) if good.any() else 0.0
    if not top > 0:
        return None, None, "black"
    v = np.where(good, iof, 0).astype(np.float32)
    blur = cv2.GaussianBlur(v, (0, 0), 20) / np.maximum(cv2.GaussianBlur(good.astype(np.float32), (0, 0), 20), 1e-6)
    r = np.where(good & (blur > 0), cv2.GaussianBlur(v, (0, 0), 1.5) / np.maximum(blur, 1e-12), np.nan)
    return r.astype(np.float32), (blur / top).astype(np.float32), ""


def one(path):
    ff.WAC_DUST_USE = False
    try:
        r, lit, why = ratio(path)
    except Exception as e:
        return path, None, None, f"{type(e).__name__}: {e}"[:100]
    return path, r, lit, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="CL1,CL2")
    ap.add_argument("--date", default="2009-07-25")
    ap.add_argument("--days", type=float, default=120)
    ap.add_argument("--spots", nargs="+", default=["820,620", "260,290", "980,840"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--most", type=int, default=120)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    f1, f2 = a.pair.split(",")
    idx = pd.read_csv(os.path.join(bwd.REPO, "Image_index.csv"), low_memory=False)
    t0 = pd.Timestamp(a.date).timestamp()
    w = idx[(idx["INSTRUMENT_ID"].astype(str).str.contains("WIDE|ISSWA", regex=True)) & (idx["filter1"] == f1)
            & (idx["filter2"] == f2) & (idx["MISSING_LINES"].fillna(0) == 0)
            & ((idx["seconds_1970"] - t0).abs() <= a.days * 86400)].sort_values("seconds_1970")
    if len(w) > a.most:   # evenly over the window
        w = w.iloc[np.linspace(0, len(w) - 1, a.most).round().astype(int)]
    paths = [p if p.startswith("wac_data/") else "wac_data/" + os.path.basename(p) for p in w["path"]]
    when = dict(zip(paths, pd.to_datetime(w["seconds_1970"], unit="s").dt.strftime("%Y-%m-%d")))
    spots = [tuple(int(v) for v in s.split(",")) for s in a.spots]
    rows, crops = [], []
    with ProcessPoolExecutor(a.workers) as ex:
        for path, r, lit, err in ex.map(one, paths):
            row = {"frame": os.path.basename(path).split(".")[0], "date": when[path], "used": r is not None, "why": err or ""}
            if r is not None:
                r = np.pad(r, HALF, constant_values=np.nan)   # a spot near the edge keeps its crop size
                lit = np.pad(lit, HALF, constant_values=0)
                strip = []
                for k, (y, x) in enumerate(spots):
                    c = r[y:y + 2 * HALF, x:x + 2 * HALF]
                    mid = c[HALF // 2:-HALF // 2, HALF // 2:-HALF // 2]
                    row[f"spot{k}_min"] = round(float(np.nanmin(mid)), 3) if np.isfinite(mid).any() else ""
                    row[f"spot{k}_lit"] = round(float(lit[y + HALF, x + HALF]), 2)   # under ~0.2: too dark to show dust
                    strip.append(np.clip((np.nan_to_num(c, nan=1.0) - 0.6) / 0.6 * 255, 0, 255).astype(np.uint8))
                crops.append((row["frame"] + " " + row["date"], np.hstack(strip)))
            rows.append(row)
            print(row, flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(a.out, "persistence.csv"), index=False)
    if crops:
        lines = []
        for name, c in crops:
            band = np.full((14, c.shape[1]), 0, np.uint8)
            cv2.putText(band, name, (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.35, 255, 1)
            lines.append(np.vstack([band, c]))
        per = 8
        cols = [np.vstack(lines[i:i + per]) for i in range(0, len(lines), per)]
        hgt = max(c.shape[0] for c in cols)
        sheet = np.hstack([np.vstack([c, np.zeros((hgt - c.shape[0], c.shape[1]), np.uint8)]) for c in cols])
        cv2.imwrite(os.path.join(a.out, "persistence.png"), sheet)


if __name__ == "__main__":
    main()
