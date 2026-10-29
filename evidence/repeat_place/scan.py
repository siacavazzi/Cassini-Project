"""Whole-mission scan of the repeat-exposure rule, before and after (obs_mosaic.units, stacking.find_repeats).

For every pass of every observation and camera: its tiles (frames that are pictures of their own), and for each
tile the repeats stacking.load_hdr would merge into it (find_repeats within the pass's repeat_gap, 8 frames at
most), with how far SPICE puts each repeat from the tile. "before" is the same code with stacking.same_place
answering None (SPICE not asked), which is the old rule exactly: the first frame of a filter in each repeat_gap,
every same-filter frame within it merged. Needs CASSINI_GEOMETRY_CACHE and Image_index.csv.

  CASSINI_GEOMETRY_CACHE=.../geometry.sqlite python scan.py OUT.tsv [--targets PHOEBE,RHEA]
"""
import argparse
import math
import os
import sys
import time

REPO = os.environ.get("CASSINI_REPO", os.getcwd())
sys.path.insert(0, os.path.join(REPO, "web", "frames"))
sys.path.insert(0, REPO)
os.chdir(REPO)
import obs_mosaic as om  # noqa: E402
import stacking  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--targets", default="")
ap.add_argument("--far", type=float, default=40, help="px: a merged repeat further than this is misaligned")
a = ap.parse_args()

idx, observations = om._observations()
keys = sorted(k for k in observations if all(isinstance(x, str) for x in k))
if a.targets:
    keep = set(a.targets.split(","))
    keys = [k for k in keys if k[0] in keep]
rule = stacking.same_place
where = {}


def scan(mode):
    stacking.same_place = rule if mode == "after" else (lambda p, q: None)
    om._units.clear()
    out = {}
    for target, obs, inst in keys:
        cam = "N" if inst == "ISSNA" else "W"
        try:
            us = om.units(target, obs, cam)
        except Exception as e:
            print("units failed", target, obs, cam, e)
            continue
        for u in us:
            worst, bad, unknown, merged = 0.0, 0, 0, 0
            for path, fid, *_ in u["frames"]:
                reps = stacking.find_repeats(path, u["repeat_gap"], 8)[1:]
                ids = [stacking.frame_id(p) for p in reps]
                g0 = where.get(fid)
                far = 0.0
                for r in ids:
                    g = where.get(r)
                    if g0 is None or g is None:
                        unknown += 1
                        continue
                    far = max(far, math.hypot(g[0] - g0[0], g[1] - g0[1]))
                merged += len(ids)
                worst = max(worst, far)
                bad += far > a.far
            out[(target, obs, cam, u["key"][3])] = (u["kind"], len(u["frames"]), merged, unknown, bad, round(worst))
    return out


t0 = time.time()
where.update(stacking.places(idx["id"].tolist()))
print(f"{len(where)} placed frames, {len(keys)} observation/cameras", flush=True)
before = scan("before")
print(f"before: {time.time() - t0:.0f} s", flush=True)
after = scan("after")
print(f"after: {time.time() - t0:.0f} s", flush=True)
with open(a.out, "w") as fh:
    fh.write("target\tobs\tcam\tpass\tkind_before\tkind_after\ttiles_before\ttiles_after\tmerged_before\tmerged_after"
             "\tunplaced_before\tunplaced_after\tbad_tiles_before\tbad_tiles_after\tworst_px_before\tworst_px_after\n")
    for k in sorted(set(before) | set(after), key=str):
        b, c = before.get(k, (None,) * 6), after.get(k, (None,) * 6)
        fh.write("\t".join(map(str, (*k, b[0], c[0], b[1], c[1], b[2], c[2], b[3], c[3], b[4], c[4], b[5], c[5]))) + "\n")
print("wrote", a.out)
