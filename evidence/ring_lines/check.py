"""Before/after check of garbled_lines on thin ringlets lying along the lines (spot check round 3: N1498392374_1 and
N1498395214_1 drew black lines across the rings where the live site showed a ringlet), through the pipeline itself
(color_image.processed_frame, unrotated: no SPICE here). Run it once in a checkout of main and once in the fix
branch, then compare:

    python evidence/ring_lines/check.py render OUT/before      (in main's checkout)
    python evidence/ring_lines/check.py render OUT/after       (in the branch's checkout)
    python evidence/ring_lines/check.py compare OUT            (side by side pictures and zooms)
    python evidence/ring_lines/check.py sweep MAIN_LABEL_HANDLER OUT [N] [YEAR]
        (N frames of YEAR, default 400 of 2005, spread through those that lost lines: how many pixels garbled_lines finds in
        each, in this checkout and in MAIN_LABEL_HANDLER, e.g. a copy of main's label_handler.py; garbled.tsv)

with CASSINI_DATA (and CASSINI_CISSCAL) set as for the frame server. Writes PNGs, never touches the cache."""
import importlib.util
import json
import os
import sys
import time

import numpy as np

# (name, frame, zoom box x0, y0, x1, y1 on the 1024 picture)
FRAMES = [("ringlet", "N1498392374_1", 250, 180, 1024, 340),
          ("gap", "N1498395214_1", 60, 260, 1024, 380),
          ("garbage", "W1545335176_2", 0, 0, 1024, 760)]


def index():
    import pandas as pd
    idx = pd.read_csv("Image_index.csv", usecols=["path", "MISSING_LINES", "IMAGE_MID_TIME"], low_memory=False)
    idx["id"] = idx.path.str.split("/").str[-1].str.split(".").str[0]
    return idx


def render(out):
    import cv2
    import color_image
    import label_handler as lh

    def no_spice(*a, **k):
        raise RuntimeError("no SPICE in this check")
    lh.label.auto_center = no_spice
    os.makedirs(out, exist_ok=True)
    idx = index()
    report = {}
    for name, fid, *_ in FRAMES:
        t = time.time()
        rgba, _, rep = color_image.processed_frame([idx.path[idx.id == fid].iloc[0]])
        rgba = np.asarray(rgba)
        cv2.imwrite(os.path.join(out, f"{name}__{fid}.png"), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        report[name] = {"lost": int((rgba[..., 3] == 0).sum()), "s": round(time.time() - t, 1)}
        print(name, fid, report[name], flush=True)
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump(report, fh, indent=1)


def compare(out):
    import cv2

    def flat(p):
        im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        # transparent shows black, as on the site
        return (im[..., :3].astype(np.float32) * (im[..., 3:] / 255.0)).astype(np.uint8) if im.shape[2] == 4 else im

    def label(im, text):
        bar = np.full((28, im.shape[1], 3), 24, np.uint8)
        cv2.putText(bar, text, (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (90, 220, 250), 1, cv2.LINE_AA)
        return np.vstack([bar, im])

    for name, fid, x0, y0, x1, y1 in FRAMES:
        b, a = (flat(os.path.join(out, s, f"{name}__{fid}.png")) for s in ("before", "after"))
        gap = np.full((b.shape[0] + 28, 8, 3), 0, np.uint8)
        cv2.imwrite(os.path.join(out, f"{name}_{fid}_before_after.png"),
                    np.hstack([label(b, f"BEFORE (main)  {fid}"), gap, label(a, "AFTER (this branch)")]))
        zb, za = (cv2.resize(im[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST) for im in (b, a))
        bar = np.full((8, zb.shape[1], 3), 0, np.uint8)
        cv2.imwrite(os.path.join(out, f"{name}_{fid}_zoom_before_after.png"),
                    np.vstack([label(zb, f"BEFORE (main)  {fid}  zoom 2x"), bar, label(za, "AFTER (this branch)")]))
        print(name, fid, "written", flush=True)


def sweep(main_lh, out, n=400, year="2005"):
    import cv2
    import data_source as ds
    import label_handler as lh
    spec = importlib.util.spec_from_file_location("lh_main", main_lh)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    os.makedirs(out, exist_ok=True)
    idx = index()
    import pandas as pd
    ml = pd.to_numeric(idx.MISSING_LINES, errors="coerce").fillna(0)
    # (evenly through the year's frames that lost lines, ring scans and moons alike)
    pick = idx[idx.IMAGE_MID_TIME.astype(str).str.startswith(year) & (ml > 0)]
    pick = pick.iloc[np.linspace(0, len(pick) - 1, min(int(n), len(pick))).astype(int)]
    rows = ["id\tlines\tmain_px\tbranch_px\tmain_lines\tbranch_lines"]
    for p, fid in zip(pick.path, pick.id):
        base = p.split(".")[0]
        img = ds.imread(base + ".png", cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        mask = np.ones(img.shape, bool)
        if ds.exists(base + ".prefix.gz"):
            import gzip
            prefix = np.frombuffer(gzip.decompress(ds.read_bytes(base + ".prefix.gz")), np.uint8).reshape(img.shape[0], -1)
            mask &= np.arange(img.shape[1]) < (prefix[:, 2].astype(int) * 256 + prefix[:, 3])[:, None]
        o, b = old.garbled_lines(img, mask), lh.garbled_lines(img, mask)
        rows.append(f"{fid}\t{img.shape[0]}\t{o.sum()}\t{b.sum()}\t{o.any(1).sum()}\t{b.any(1).sum()}")
        if o.sum() != b.sum():
            print(rows[-1], flush=True)
    with open(os.path.join(out, "garbled.tsv"), "w") as fh:
        fh.write("\n".join(rows) + "\n")
    print(len(rows) - 1, "frames,", sum(1 for r in rows[1:] if r.split("\t")[2] != r.split("\t")[3]), "changed")


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    sys.path.insert(0, os.path.join(os.getcwd(), "web", "frames"))
    {"render": render, "compare": compare, "sweep": sweep}[sys.argv[1]](*sys.argv[2:])
