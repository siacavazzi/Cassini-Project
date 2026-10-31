"""
Measures eye_colors.json, the bodies' own colors for natural color emulation (calibration.eye_mix, colors=eye): each
body's color as this pipeline's true color composites (RED + GRN + BL1/BL2/VIO, natural color) draw it, the median
over its sets of each picture's median lit color (linear, mean 1). Bodies with fewer than MIN_SETS sets are left out
(eye_mix then uses BODY_TINTS, else gray).
Usage: python web/frames/eye_colors.py SAMPLE_TSV PICTURES_DIR [OUT_JSON]
SAMPLE_TSV = rows with n, kind ("true"), target; PICTURES_DIR/<n>.webp = each set's /frames/color.webp (as the spot
checks' fetch_sample.py saves them)
"""
import collections
import csv
import json
import os
import sys

import numpy as np
from PIL import Image

MIN_SETS = 5
GAMMA = 2.2       # the composites' display gamma (calibration.tone)
LIT = 0.25        # lit: brighter than this share of the picture's 99.5th percentile
CLIPPED = 0.97    # ... and no channel near white (the shoulder bends color there)


def measure(sample, pictures):
    found = collections.defaultdict(list)
    for r in csv.DictReader(open(sample), delimiter="\t"):
        path = os.path.join(pictures, f"{r['n']}.webp")
        if r["kind"] != "true" or not os.path.exists(path):
            continue
        im = np.asarray(Image.open(path).convert("RGB"), np.float64) / 255
        lin = im ** GAMMA
        lum = lin.mean(axis=2)
        lit = (lum > LIT * np.percentile(lum, 99.5)) & (im.max(axis=2) < CLIPPED)
        if lit.sum() < 500:
            continue
        c = np.median(lin[lit], axis=0)
        found[r["target"].upper()].append(c / c.mean())
    return {t: {"rgb": [round(float(v), 4) for v in np.median(cs, axis=0)], "sets": len(cs)}
            for t, cs in sorted(found.items()) if len(cs) >= MIN_SETS and t not in ("SKY", "UNK")}


if __name__ == "__main__":
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "eye_colors.json")
    table = {"_about": "Bodies' own colors for natural color emulation (calibration.eye_mix): linear red, green, blue of "
                       "mean 1, the median of the pipeline's true color composites of the body (web/frames/eye_colors.py)."}
    table.update(measure(sys.argv[1], sys.argv[2]))
    with open(out, "w") as f:
        json.dump(table, f, indent=1)
    print(json.dumps(table, indent=1))
