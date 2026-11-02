# -*- coding: utf-8 -*-
"""
How long a WAC dust donut stays put: for one filter pair's WAC frames within --days of a date, each frame's dust ratio
(build_wac_dust.measure: its brightness over its neighborhood's, flat field on, WAC dust map off) at a few spots, as a
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
import flat_field as ff  # noqa: E402

HALF = 48   # px: each crop is twice this across


def one(path):
    ff.WAC_DUST_USE = False
    try:
        r = bwd.measure(path)
    except Exception as e:
        return path, None, str(e)[:100]
    return path, r, None


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
        for path, codes, err in ex.map(one, paths):
            row = {"frame": os.path.basename(path).split(".")[0], "date": when[path], "used": codes is not None, "why": err or ""}
            if codes is not None:
                r = np.pad(bwd.decode(codes), HALF, constant_values=np.nan)   # a spot near the edge keeps its crop size
                strip = []
                for k, (y, x) in enumerate(spots):
                    c = r[y:y + 2 * HALF, x:x + 2 * HALF]
                    row[f"spot{k}_min"] = round(float(np.nanmin(c[HALF // 2:-HALF // 2, HALF // 2:-HALF // 2])), 3) if np.isfinite(c).any() else ""
                    strip.append(np.clip((np.nan_to_num(c, nan=1.0) - 0.85) / 0.3 * 255, 0, 255).astype(np.uint8))
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
