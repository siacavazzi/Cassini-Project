#!/usr/bin/env python3
"""Bright subjects blown white in movies and mosaics (spot check round 2): evidence for the pass scale's even body
and FILL_SHARE (obs_mosaic.pass_scale). Draws with the checkout given by WT (main's for before, this one's for
after), in the repo venv, with the frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE,
CASSINI_CISSCAL). Read-only on the archive.

  python web/frames/bright_evidence.py census --out census.tsv
      every pass (geometry only, no pictures): whether it is "all body" (filled) under main's rule and the branch's
      (FILL_SHARE), the body's radius in pixels and the share of the frames on its disk
  python web/frames/bright_evidence.py draw --cache DIR --out DIR FRAME_ID ...
      for each pass named by one of its frames: its plan's display scale (plan(), into the scratch cache DIR) and
      up to FRAMES of its frames drawn as their tiles are (color_image.processed_frame with tile_scale), a JPEG
      strip of the body and a JSON line each: md5 of every frame's pixels, share of the body's pixels drawn 250 or
      over, the body's median
  python web/frames/bright_evidence.py compare BEFORE AFTER --out DIR
      before | after strips and a table: scale before/after, identical pixels or not

Run draw once on a checkout of main (before) and once on the branch (after), each with its own scratch cache.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import sys

WT = os.path.expanduser(os.environ.get("WT", "~/dev/wt-groupc"))
sys.path[:0] = [os.path.join(WT, "web", "frames"), WT]
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import reel  # noqa: E402
import obs_mosaic as om  # noqa: E402
import color_image  # noqa: E402

FRAMES = 4
SIDE = 320


def census(out):
    idx, _ = reel.load_index()
    n = flipped = 0
    with open(out, "w") as fh:
        fh.write("pass\tfirst\tt\tframes\tkind\tradius_px\tshare_mean\tfilled_main\tfilled_branch\n")
        for (target, obs, inst) in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices:
            if not isinstance(obs, str) or inst not in ("ISSNA", "ISSWA"):
                continue
            cam = "N" if inst == "ISSNA" else "W"
            try:
                us = om.units(target, obs, cam)
            except Exception as e:
                print(target, obs, cam, "error", e)
                continue
            for u in us:
                frames = [fr for fr in u["frames"] if fr[7]]
                if not frames:
                    continue
                radius = om.FILL_RADIUS.get(target, 0) / om.IFOV[cam]
                centre = [math.hypot(x, y) < radius / z for *_, x, y, z in frames]
                share = [om._disk_share(x, y, radius / z) if hasattr(om, "_disk_share") else 0.0 for *_, x, y, z in frames]
                fill_share = getattr(om, "FILL_SHARE", 0.0)
                old = float(np.mean(centre)) > om.FILLED
                new = float(np.mean([c and s >= fill_share for c, s in zip(centre, share)])) > om.FILLED
                n += 1
                flipped += old != new
                rpx = om.RADIUS.get(target, 0) / (u["z"] * om.IFOV[cam]) if u.get("z") else 0
                fh.write(f"{'_'.join(map(str, u['key']))}\t{u['frames'][0][1]}\t{u['frames'][0][3]:.0f}\t{len(u['frames'])}\t"
                         f"{u.get('kind')}\t{rpx:.0f}\t{np.mean(share):.3f}\t{int(old)}\t{int(new)}\n")
            with om._lock:
                om._units.clear()
    print(f"{n} passes, {flipped} no longer all body")


def body_box(img):
    """the body's box on a drawn tile: its pixels 40 or over, padded"""
    grey = img[..., :3].max(axis=2)
    lit = (grey >= 40) & (img[..., 3] > 0)
    if not lit.any():
        lit = img[..., 3] > 0
    if not lit.any():
        return None
    rows, cols = np.where(lit)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    pad = max(8, (max(r1 - r0, c1 - c0)) // 8)
    return max(0, r0 - pad), min(img.shape[0], r1 + pad), max(0, c0 - pad), min(img.shape[1], c1 + pad)


def draw(ids, cache, out):
    os.makedirs(out, exist_ok=True)
    for fid in ids:
        found = om.unit_of(fid)
        if not found:
            print(fid, "in no pass")
            continue
        u, _ = found
        name = f"{fid}_{'_'.join(map(str, u['key']))}"
        try:
            p = om.plan(u, cache)
        except Exception as e:
            print(fid, "plan error", repr(e)[:300])
            continue
        scale = p["display_scale"]
        head = {"pass": fid, "key": list(u["key"]), "frames": len(u["frames"]), "kind": u.get("kind"),
                "movie": bool(u.get("movie")), "mosaic": bool(u.get("mosaic")), "colour": p.get("colour"),
                "scale": {k: v for k, v in scale.items() if k in ("blacks", "white", "gamma", "shoulder", "filled", "floor", "toe")}}
        rows, cells = [], []
        frames = u["frames"]
        picks = sorted(set(round(i * (len(frames) - 1) / max(FRAMES - 1, 1)) for i in range(min(FRAMES, len(frames)))))
        at = [fr[1] for fr in frames].index(fid) if fid in [fr[1] for fr in frames] else None
        if at is not None and at not in picks:
            picks = sorted(picks[:FRAMES - 1] + [at])
        for n in picks:
            path, fid2, f, t, nm, x, y, z = frames[n]
            row = {"n": n, "id": fid2, "filter": f}
            try:
                img, _, rep = color_image.processed_frame(
                    [path], hdr=True, scale=om.tile_scale(scale, f, bool(u.get("movie")), {}),
                    repeat_window=u.get("repeat_gap", om.mosaic_benchmark.REPEAT_GAP),
                    around=om._around(u, n) if u.get("movie") else None)
            except Exception as e:
                row["error"] = repr(e)[:200]
                rows.append(row)
                continue
            row["md5"] = hashlib.md5(np.ascontiguousarray(img).tobytes()).hexdigest()
            grey = img[..., :3].max(axis=2)
            body = (grey >= 40) & (img[..., 3] > 0)
            row["body_px"] = int(body.sum())
            if body.any():
                row["white_share"] = round(float((grey[body] >= 250).mean()), 4)
                row["body_p5_50_95"] = [int(v) for v in np.percentile(grey[body], (5, 50, 95))]
            box = body_box(img)
            if box is not None:
                r0, r1, c0, c1 = box
                crop = img[r0:r1, c0:c1, :3]
                k = SIDE / max(crop.shape[:2])
                crop = cv2.resize(crop, (max(1, round(crop.shape[1] * k)), max(1, round(crop.shape[0] * k))),
                                  interpolation=cv2.INTER_AREA)
                cell = np.zeros((SIDE, SIDE, 3), np.uint8)
                cell[:crop.shape[0], :crop.shape[1]] = crop
                cv2.putText(cell, f"{fid2} {f}", (4, SIDE - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 255), 1)
                cells.append(cell)
            rows.append(row)
        head["tiles"] = rows
        print(json.dumps(head, default=str))
        with open(os.path.join(out, name + ".json"), "w") as fh:
            json.dump(head, fh, default=str)
        if cells:
            cv2.imwrite(os.path.join(out, name + ".jpg"), np.hstack(cells), [cv2.IMWRITE_JPEG_QUALITY, 90])


def compare(before, after, out):
    os.makedirs(out, exist_ok=True)
    print("pass\tkey\tgamma\twhite\tblack(first band)\tshoulder\tframes identical\twhite share\tbody median")
    for fa in sorted(glob.glob(os.path.join(after, "*.json"))):
        fb = os.path.join(before, os.path.basename(fa))
        if not os.path.exists(fb):
            continue
        a, b = json.load(open(fa)), json.load(open(fb))
        sa, sb = a["scale"], b["scale"]
        band = next(iter(sb.get("blacks") or {}), None)
        same = sum(1 for x, y in zip(a["tiles"], b["tiles"]) if x.get("md5") and x.get("md5") == y.get("md5"))
        ws = lambda t: "/".join(f"{x.get('white_share', 0):.2f}" for x in t)
        md = lambda t: "/".join(str((x.get("body_p5_50_95") or [0, 0, 0])[1]) for x in t)
        print(f"{a['pass']}\t{'_'.join(map(str, a['key']))}\t{sb.get('gamma')}->{sa.get('gamma'):.2f}\t"
              f"{sb.get('white', 0):.4g}->{sa.get('white', 0):.4g}\t"
              f"{(sb.get('blacks') or {}).get(band, 0):.4g}->{(sa.get('blacks') or {}).get(band, 0):.4g}\t"
              f"{sb.get('shoulder')}->{sa.get('shoulder')}\t{same}/{len(a['tiles'])}\t{ws(b['tiles'])} -> {ws(a['tiles'])}\t"
              f"{md(b['tiles'])} -> {md(a['tiles'])}")
        ja, jb = fa[:-5] + ".jpg", fb[:-5] + ".jpg"
        if os.path.exists(ja) and os.path.exists(jb):
            ia, ib = cv2.imread(ja), cv2.imread(jb)
            w = max(ia.shape[1], ib.shape[1])
            pad = lambda im: np.hstack([im, np.zeros((im.shape[0], w - im.shape[1], 3), np.uint8)])
            band_b = np.zeros((22, w, 3), np.uint8); cv2.putText(band_b, "main", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            band_a = np.zeros((22, w, 3), np.uint8); cv2.putText(band_a, "fixed", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.imwrite(os.path.join(out, os.path.basename(ja)), np.vstack([band_b, pad(ib), band_a, pad(ia)]),
                        [cv2.IMWRITE_JPEG_QUALITY, 90])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("census", "draw", "compare"))
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--cache")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.what == "census":
        census(a.out)
    elif a.what == "draw":
        draw(a.ids, a.cache, a.out)
    else:
        compare(a.ids[0], a.ids[1], a.out)
