"""Before/after check of the small-artifact fixes (group I of the picture fix plan) on real frames, through the
pipeline itself (color_image.processed_frame: stacked, lost lines filled, calibrated, toned; left unrotated, as no
SPICE is loaded here). Run it once in a checkout of main and once in the fix branch, then compare:

    python evidence/small_artifacts/check_samples.py render OUT/before      (in main's checkout)
    python evidence/small_artifacts/check_samples.py render OUT/after       (in the branch's checkout)
    python evidence/small_artifacts/check_samples.py compare OUT            (side by side pictures, GIFs, index.html)
    python evidence/small_artifacts/check_samples.py diag                   (numbers on the frames, printed)

with CASSINI_DATA (and CASSINI_CISSCAL) set as for the frame server. Writes PNGs, never touches the cache."""
import inspect
import json
import os
import sys
import time

import numpy as np

FRAMES = {"star-boxes": "W1601346192_1", "fill-dashes": "N1800422096_8", "corrupt-rows": "W1545335176_2",
          "dash-rows": "N1463204038_1", "dash-rows-2001": "W1360287337_1"}
# (name, observation, a frame in it or None for the middle, frames each side)
MOVIES = [("speckle-aurstare", "ISS_216SA_AURSTARE001_VIMS", "N1810754140_1", 7),
          ("speckle-kiviuq", "ISS_202OT_KIVRES125_PRIME", None, 8),
          ("striping-eg60", "ISS_150RI_EG60PHASE001_VIMS", "N1688438098_1", 3)]


def index():
    import pandas as pd
    idx = pd.read_csv("Image_index.csv", usecols=["path", "OBSERVATION_ID", "FILTER_NAME", "INSTRUMENT_ID",
                                                  "seconds_1970", "MISSING_LINES"], low_memory=False)
    idx["id"] = idx.path.str.split("/").str[-1].str.split(".").str[0]
    return idx


def path_of(idx, fid):
    return idx.path[idx.id == fid].iloc[0]


def around(u, n):
    """the same filter's frames just before and after frame n of pass u (obs_mosaic._around, which main lacks)"""
    frames, f = u["frames"], u["frames"][n][2]
    before = next((frames[j][0] for j in range(n - 1, -1, -1) if frames[j][2] == f), None)
    after = next((frames[j][0] for j in range(n + 1, len(frames)) if frames[j][2] == f), None)
    return [before, after]


def movie_runs(idx):
    """name -> (the pass (obs_mosaic.units), the indices of the run of its frames to draw)."""
    sys.path.insert(0, os.path.join(os.getcwd(), "web", "frames"))
    import obs_mosaic
    import data_source as ds
    out = {}
    for name, obs, mid, side in MOVIES:
        r = idx[idx.OBSERVATION_ID == obs].iloc[0]
        inst = "N" if r.path.startswith("nac") else "W"
        for u in (u for t in ("SATURN", "KIVIUQ") for u in obs_mosaic.units(t, obs, inst)):
            ids = [fr[1] for fr in u["frames"]]
            at = ids.index(mid) if mid in ids else (len(ids) // 2 if mid is None else None)
            if at is None:
                continue
            first = max(0, min(at - side, len(ids) - 2 * side - 1))
            # (only frames whose neighbours the data has: a sample of the archive holds a stretch of the pass)
            run = [n for n in range(first, min(len(ids), first + 2 * side + 1))
                   if all(p is None or ds.exists(p.rsplit(".", 1)[0] + ".lbl") for p in [u["frames"][n][0]] + around(u, n))]
            out[name] = (u, run)
            break
    return out


def render(out):
    import cv2
    import color_image
    import label_handler as lh

    def no_spice(*a, **k):
        raise RuntimeError("no SPICE in this check")
    lh.label.auto_center = no_spice
    around_ok = "around" in inspect.signature(color_image.processed_frame).parameters
    os.makedirs(out, exist_ok=True)
    idx = index()
    report = {}
    for name, fid in FRAMES.items():
        t = time.time()
        rgba, _, rep = color_image.processed_frame([path_of(idx, fid)])
        cv2.imwrite(os.path.join(out, f"{name}__{fid}.png"), cv2.cvtColor(np.asarray(rgba), cv2.COLOR_RGBA2BGRA))
        report[name] = {k: v for k, v in rep.items() if k != "why"} | {"s": round(time.time() - t, 1)}
        print(name, fid, report[name], flush=True)
    runs = movie_runs(idx)
    import obs_mosaic
    for name, (u, run) in runs.items():
        # as obs_mosaic._tile_made draws a movie's tile: on the pass's one display scale (here worked out over the run)
        scale = obs_mosaic.pass_scale([u["frames"][n] for n in run], u)
        for k, n in enumerate(run):
            path, fid, f = u["frames"][n][:3]
            kw = {"around": obs_mosaic._around(u, n)} if around_ok else {}
            seen = {}
            rgba, _, rep = color_image.processed_frame([path], hdr=True, scale=obs_mosaic.tile_scale(scale, f, True, seen),
                                                       repeat_window=u.get("repeat_gap", 120), **kw)
            rep.update(seen)
            cv2.imwrite(os.path.join(out, f"{name}__{k:02d}__{fid}.png"), cv2.cvtColor(np.asarray(rgba), cv2.COLOR_RGBA2BGRA))
            report[f"{name}/{k:02d}"] = {kk: v for kk, v in rep.items() if kk != "why"}
        print(name, len(run), "frames", flush=True)
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)


def compare(out):
    """Side by side (before | after) of every picture, on black (transparent shows black, as in the windows); the
    movies also as a GIF each, both halves on one viewing stretch (the dark stares are faint at the pipeline's own
    tone; the stretch is the same on both sides). Writes out/index.html."""
    from PIL import Image, ImageDraw
    before, after = os.path.join(out, "before"), os.path.join(out, "after")
    names = sorted(n for n in os.listdir(after) if n.endswith(".png"))

    def flat(p):
        a = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
        return a[..., :3] * a[..., 3:] / 255

    def pair(n, lo=None, hi=None):
        b, a = flat(os.path.join(before, n)), flat(os.path.join(after, n))
        if lo is not None:
            b, a = [(np.clip((x - lo) / max(hi - lo, 1e-3), 0, 1) ** 0.6) * 255 for x in (b, a)]
        im = Image.fromarray(np.hstack([b, np.full((b.shape[0], 8, 3), 90), a]).astype(np.uint8))
        ImageDraw.Draw(im).text((8, 8), "before", fill=(255, 220, 0))
        ImageDraw.Draw(im).text((b.shape[1] + 16, 8), "after", fill=(255, 220, 0))
        return im, np.abs(b - a).max(axis=2)

    rows = []
    for n in names:
        if "__" in n and n.split("__")[1].isdigit():
            continue
        im, d = pair(n)
        im.save(os.path.join(out, "pair__" + n))
        rows.append((n, int((d > 2).sum())))
    movies = sorted({n.split("__")[0] for n in names if n.split("__")[1].isdigit()})
    for m in movies:
        ns = [n for n in names if n.startswith(m + "__")]
        g = flat(os.path.join(before, ns[0])).mean(axis=2)
        lo, hi = np.percentile(g, 50), np.percentile(g, 99.7)
        frames = [pair(n, lo, hi)[0] for n in ns]
        frames[0].save(os.path.join(out, f"movie__{m}.gif"), save_all=True, append_images=frames[1:], duration=400, loop=0)
        frames[len(frames) // 2].save(os.path.join(out, f"movie__{m}__still.png"))
        rows.append((f"{m} ({len(ns)} frames)", None))
    html = ["<!doctype html><meta charset=utf-8><title>Group I before/after</title><body style='background:#111;color:#ddd;font:14px sans-serif'>",
            "<h1>Small frame artifacts: before | after</h1><p>Pipeline output (processed_frame), unrotated; transparent shows black.</p>"]
    for n, changed in rows:
        if changed is None:
            m = n.split(" ")[0]
            html.append(f"<h2>{n}</h2><img src='movie__{m}.gif' style='max-width:100%'>")
        else:
            html.append(f"<h2>{n} ({changed} px changed by more than 2 levels)</h2><img src='pair__{n}' style='max-width:100%'>")
    with open(os.path.join(out, "index.html"), "w") as fh:
        fh.write("\n".join(html))
    print("\n".join(f"{n}: {c}" for n, c in rows))


def diag():
    """Numbers on the raw frames: their labels' data-quality fields, the line prefix's short lines, and the rows
    whose values jump from both neighbours (the corrupt rows' signature)."""
    import gzip
    import cv2
    import data_source as ds
    import label_handler as lh
    idx = index()
    for name, fid in FRAMES.items():
        path = path_of(idx, fid)
        lbl = lh.label(path, as_png=True)
        info = lbl.info
        keys = ["LINES", "LINE_SAMPLES", "MISSING_LINES", "DATA_CONVERSION_TYPE", "INST_CMPRS_TYPE", "INSTRUMENT_MODE_ID",
                "EXPOSURE_DURATION", "GAIN_MODE_ID", "BIAS_STRIP_MEAN", "INST_CMPRS_RATIO", "MISSING_PACKET_FLAG",
                "IMAGE_OBSERVATION_TYPE", "DATA_SET_ID", "SEQUENCE_ID", "SHUTTER_STATE_ID", "TELEMETRY_FORMAT_ID",
                "VALID_MAXIMUM", "ORDER_OF_SAMPLES" ]
        print(f"== {name} {fid}", {k: info.get(k) for k in keys})
        base = path.split(".")[0]
        codes = ds.imread(base + ".png", cv2.IMREAD_GRAYSCALE).astype(np.float32)
        lines, samples = codes.shape
        if ds.exists(base + ".prefix.gz"):
            prefix = np.frombuffer(gzip.decompress(ds.read_bytes(base + ".prefix.gz")), np.uint8).reshape(lines, -1)
            valid = prefix[:, 2].astype(int) * 256 + prefix[:, 3]
            print("prefix bytes/line", prefix.shape[1], "short lines", int((valid < samples).sum()),
                  "valid counts (first 12 short):", [(int(y), int(v)) for y, v in zip(np.nonzero(valid < samples)[0], valid[valid < samples])][:12])
            print("prefix columns mean per byte:", np.round(prefix.mean(0), 1).tolist())
        mask = lbl.valid_mask()
        print("valid_mask lost px (1024 grid):", int((~mask).sum()))
        up, dn = np.abs(codes[1:-1] - codes[:-2]), np.abs(codes[1:-1] - codes[2:])
        skip = np.abs(codes[:-2] - codes[2:])
        jump = np.minimum(up, dn) - skip
        rough = np.abs(np.diff(codes, axis=1))
        noise = 1.4826 * float(np.median(np.abs(codes[1:] - codes[:-1]))) / np.sqrt(2)
        row_jump = np.median(jump, axis=1)
        frac = (jump > 6 * max(noise, 1)).mean(axis=1)
        print(f"noise {noise:.2f}; rows with >25% of pixels jumping 6 sigma from both neighbours: "
              f"{int((frac > 0.25).sum())}; >10%: {int((frac > 0.10).sum())}")
        worst = np.argsort(-frac)[:25]
        print("worst rows (row, frac jumping, median jump, row mean, nbr means, row roughness, nbr roughness):")
        for r in sorted(worst):
            y = r + 1
            print(f"  {y:4d} {frac[r]:.2f} {row_jump[r]:6.1f} {codes[y].mean():6.1f} {codes[y-1].mean():6.1f}/{codes[y+1].mean():6.1f}"
                  f" {np.median(rough[y]):5.1f} {np.median(rough[y-1]):5.1f}/{np.median(rough[y+1]):5.1f}"
                  f" first_x>{6*max(noise,1):.0f}: {int(np.argmax(jump[r] > 6 * max(noise, 1)))}")
        # the run of jumping pixels along the worst row: where it starts and stops
        r = int(worst[0])
        on = (jump[r] > 6 * max(noise, 1)).astype(int)
        print("  worst row's jumping runs (start, end):", [(int(a), int(b)) for a, b in zip(np.nonzero(np.diff(np.r_[0, on]) == 1)[0], np.nonzero(np.diff(np.r_[on, 0]) == -1)[0])][:12])


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    if sys.argv[1] == "render":
        render(sys.argv[2])
    elif sys.argv[1] == "compare":
        compare(sys.argv[2])
    else:
        diag()
