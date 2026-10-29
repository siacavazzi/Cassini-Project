"""The frame ids whose pictures change with the small-artifact fixes (group I), for prebuild --only after the swap.
Run from the repo root with CASSINI_DATA set (the SSD zip copy): python evidence/small_artifacts/list_remakes.py OUTDIR

  lost.txt      frames that lost pixels (a short line in the prefix, or MISSING_LINES without one), with every frame
                stacked or merged with one (find_repeats, 120 s): fill_lines' slant and trial, and the stack's rule
                for the block the reference lost (as evidence/lost_lines/lost_frames.py, the same set)
  garbled.txt   of those, the frames garbled_lines finds garbled lines in (their pictures change most), and their
                repeats; already in lost.txt, listed apart so they can go first
  stacked.txt   frames with a repeat of the same camera, target, observation and filter within 120 s (the stack's change
                test now leaves clipped pixels and their column out): an upper bound, as only stacks with a clipped
                star or limb next to a change come out different
Movies (one-frame spikes) change in every pass with sky: that is the movies phase, not a list.
Reads the archive's prefixes in member order (about 80 s on the SSD), then the PNGs of the frames that lost pixels."""
import gzip
import os
import sys
import time
import zipfile

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, os.getcwd())
import data_source as ds  # noqa: E402
import label_handler as lh  # noqa: E402
import stacking  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
idx = pd.read_csv("Image_index.csv", low_memory=False)
idx["ml"] = pd.to_numeric(idx["MISSING_LINES"], errors="coerce").fillna(0).astype(int)
idx["id"] = idx["path"].str.split("/").str[-1].str.split(".").str[0]
source = os.environ["CASSINI_DATA"]
short, t0 = {}, time.time()


def prefix_short(data):
    prefix = np.frombuffer(gzip.decompress(data), np.uint8)
    if len(prefix) % 24:
        return None
    valid = prefix.reshape(-1, 24)[:, 2].astype(np.uint16) * 256 + prefix.reshape(-1, 24)[:, 3]
    return bool(valid.min() < valid.max() or valid.max() < len(valid))


if zipfile.is_zipfile(source):
    with zipfile.ZipFile(source) as z:
        members = sorted((i for i in z.infolist() if i.filename.endswith(".prefix.gz")), key=lambda i: i.header_offset)
        for k, info in enumerate(members):
            short[os.path.basename(info.filename).split(".")[0]] = prefix_short(z.read(info))
            if k % 50000 == 0:
                print(f"{k}/{len(members)} prefixes, {time.time() - t0:.0f} s", flush=True)
else:
    for p in idx.path:
        base = p.rsplit(".", 1)[0] + ".prefix.gz"
        if ds.exists(base):
            short[os.path.basename(base).split(".")[0]] = prefix_short(ds.read_bytes(base))
lost = np.array([short[i] if short.get(i) is not None else ml > 0 for i, ml in zip(idx.id, idx.ml)])
print(f"frames that lost pixels: {lost.sum()}", flush=True)

stacking.load_index()


def with_repeats(paths):
    got = set()
    for p in paths:
        got |= {r.split("/")[-1].split(".")[0] for r in stacking.find_repeats(p, 120, 50)}
    return got


garbled = []
for k, p in enumerate(idx.path[lost]):
    try:
        lbl = lh.label(p, as_png=True)
        if lbl.info.get("MISSING_PACKET_FLAG") != "YES":
            continue
        img = ds.imread(p.rsplit(".", 1)[0] + ".png", cv2.IMREAD_GRAYSCALE)
        lines, samples = int(lbl.info["LINES"]), int(lbl.info["LINE_SAMPLES"])
        if img is None or img.shape != (lines, samples):
            continue
        if lh.garbled_lines(img, img > 0).any():
            garbled.append(p)
    except Exception as e:
        print(f"{p}: {e}")
    if k % 5000 == 0:
        print(f"{k}/{lost.sum()} checked for garbled lines, {len(garbled)} found, {time.time() - t0:.0f} s", flush=True)
sets = {"lost": with_repeats(idx.path[lost]), "garbled": with_repeats(garbled)}
order = idx.sort_values("seconds_1970")
g = order.groupby(["INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME"])["seconds_1970"]
near = (g.diff() <= 120) | (-g.diff(-1) <= 120)
sets["stacked"] = set(order.id[near])
for name, ids in sets.items():
    with open(os.path.join(out, f"{name}.txt"), "w") as fh:
        fh.write("\n".join(sorted(ids)) + "\n")
    print(f"{name}.txt: {len(ids)} frames")
