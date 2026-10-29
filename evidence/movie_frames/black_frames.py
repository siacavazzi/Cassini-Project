#!/usr/bin/env python3
"""Why do some movie frames of lit passes draw black? (fix plan group D, 2026-10-29)

Reads only what the live cache already holds (the movie pictures, their reports, the tiles' reports and each
pass's plan) plus, for each black frame found, the frame itself from the archive (stacking.load_hdr, as the tile was
made) and its label. Makes no pictures and writes nothing but its own TSV.

  cd ~/dev/Cassini-Project && CASSINI_REPO=$PWD CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... \\
    nice -n 19 .venv/bin/python ~/Documents/group-d/black_frames.py --cache ~/server/cache/cassini-prebuild \\
    --version obs-v46-q95 --sample 420 --out ~/Documents/group-d/black_frames.tsv

A frame is black as the movie checker counted it: mean under 1 and 99.5th percentile under 8 (of 255) in its
512 px default movie picture (movie-2/512/<n>_0_1_c2.webp), in a pass whose median frame is lit (mean 3+).
Each black frame gets the measures that tell the three candidate causes apart:
  raise   the tile's own black (tile_scale's black_of, "black" in its report) above the frame's content
  calib   the frame not calibrated ("calibrated" false in its report)
  lost    most of the frame lost in downlink (label valid_mask)
  dim     the frame's content under the pass's black for its filter (too faint for the pass's one scale)
  colour  a colour set whose member is one of the above
"""
import argparse
import glob
import hashlib
import json
import os
import random
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("CASSINI_REPO") or os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "web", "frames"))


def stats(path):
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    lit = a[..., 3] > 0
    v = a[..., :3].mean(axis=2)[lit]
    if v.size == 0:
        return 0.0, 0.0, 0.0
    return float(v.mean()), float(np.percentile(v, 99.5)), float(lit.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--version", default="obs-v46-q95")
    ap.add_argument("--sample", type=int, default=420)
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--passes", nargs="*", default=[], help="pass folders (names) to look at besides the sample")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = os.path.join(os.path.expanduser(args.cache), args.version)
    folders = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d, "movie-2", "512")))
    random.Random(args.seed).shuffle(folders)
    picks = list(dict.fromkeys(args.passes + folders[:args.sample]))
    print(f"{len(folders)} movie passes cached; looking at {len(picks)}", flush=True)

    import reel  # noqa: E402
    import stacking  # noqa: E402
    import label_handler as lh  # noqa: E402
    idx, _ = reel.load_index()
    path_of = dict(zip(idx["id"], idx["path"]))
    full = __import__("pandas").read_csv(os.path.join(REPO, "Image_index.csv"), usecols=["path", "MISSING_LINES"], low_memory=False)
    ml = dict(zip(full["path"], full["MISSING_LINES"]))

    rows, black_n, frames_n, lit_passes = [], 0, 0, 0
    for k, name in enumerate(picks):
        base = os.path.join(root, name)
        pics = sorted(glob.glob(os.path.join(base, "movie-2", "512", "*_0_1_c2.webp")),
                      key=lambda p: int(os.path.basename(p).split("_")[0]))
        if not pics:
            continue
        got = [(p, stats(p)) for p in pics]
        frames_n += len(got)
        if np.median([s[0] for _, s in got]) < 3:
            continue
        lit_passes += 1
        try:
            with open(os.path.join(base, "plan4.json")) as fh:
                plan = json.load(fh)
        except OSError:
            plan = None
        scale = (plan or {}).get("display_scale", {})
        gap = float(name.rsplit("_r", 1)[1]) if "_r" in name.rsplit("_", 1)[-1] else 120.0
        # the tiles' reports on the plan's scale (obs_mosaic._tiles), by frame id, read once a pass
        tiles, tdir = {}, os.path.join(base, "tiles-" + hashlib.md5(json.dumps(scale, sort_keys=True).encode()).hexdigest()[:8])
        for q in glob.glob(os.path.join(tdir, "*.json")):
            try:
                with open(q) as fh:
                    t = json.load(fh)
                tiles[t.get("id")] = t
            except (OSError, ValueError):
                pass
        for p, (mean, top, cover) in got:
            if not (mean < 1 and top < 8):
                continue
            black_n += 1
            n = int(os.path.basename(p).split("_")[0])
            try:
                with open(p[:-4] + "json") as fh:
                    rep = json.load(fh)
            except OSError:
                rep = {}
            ids = rep.get("ids") or [rep.get("id")]
            for fid in ids:
                if not fid:
                    continue
                row = {"pass": name, "n": n, "frame": rep.get("id"), "member": fid, "colour": ",".join(rep.get("color") or []),
                       "mean": round(mean, 2), "p995": round(top, 1), "cover": round(cover, 3), "why": rep.get("why", "")}
                tj = tiles.get(fid) or {}
                if os.path.exists(os.path.join(tdir, f"{tj.get('n')}.png")):
                    row["tile_mean"], row["tile_p995"], _ = (round(v, 2) for v in stats(os.path.join(tdir, f"{tj.get('n')}.png")))
                f = tj.get("filter", "")
                row.update({"filter": f, "calibrated": tj.get("calibrated"), "raised": tj.get("black"),
                            "pass_black": scale.get("blacks", {}).get(f), "white": scale.get("white"),
                            "missing_lines": ml.get(path_of.get(fid, ""), ""), "suffix": fid.rsplit("_", 1)[-1]})
                path = path_of.get(fid)
                if path:
                    try:
                        lbl, iof, nst, valid = stacking.load_hdr(path, gap, valid=True)
                        row["exposure"] = lbl.info.get("EXPOSURE_DURATION")
                        row["stacked"] = nst
                        row["valid"] = round(float(np.mean(valid)), 3) if valid is not None else ""
                        if iof is not None:
                            q = iof[::4, ::4].astype(np.float32)
                            for pc in (50, 99, 99.9):
                                row[f"iof_p{pc:g}"] = float(np.percentile(q, pc))
                    except Exception as e:  # noqa: BLE001
                        row["error"] = f"{type(e).__name__}: {e}"[:120]
                b, w = row.get("pass_black"), row.get("white")
                causes = []
                if row.get("calibrated") is False:
                    causes.append("calib")
                if isinstance(row.get("valid"), float) and row["valid"] < 0.5:
                    causes.append("lost")
                top_iof = row.get("iof_p99.9")
                if top_iof is not None and b is not None:
                    if row.get("raised") is not None and b < top_iof <= row["raised"] + 0.02 * (w or 0):
                        causes.append("raise")
                    elif top_iof <= b + 0.02 * (w or 0):
                        causes.append("dim")
                if "offset" not in tj and tj:
                    causes.append("unplaced")
                row["cause"] = "+".join(causes) or "other"
                rows.append(row)
        if k % 20 == 0:
            print(f"{k + 1}/{len(picks)} passes, {black_n} black frames so far", flush=True)

    keys = list(dict.fromkeys(k for r in rows for k in r))
    os.makedirs(os.path.dirname(os.path.expanduser(args.out)), exist_ok=True)
    with open(os.path.expanduser(args.out), "w") as fh:
        fh.write("\t".join(keys) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(k, "")) for k in keys) + "\n")
    from collections import Counter
    c = Counter(r["cause"] for r in rows)
    print(f"passes {len(picks)}, lit {lit_passes}, frames {frames_n}, black frames {black_n}, members {len(rows)}")
    print("causes:", dict(c.most_common()))
    print("suffix _2+ among black members:", sum(1 for r in rows if r.get("suffix") not in ("1", "")))


if __name__ == "__main__":
    main()
