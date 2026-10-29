"""Evidence for mosaic movies keeping their picture (obs_mosaic.rolling_layout: the gray base under the colour, and each
lap's copy of a place on the level of the copy it replaces), from a pre-built cache's plans and tiles, read only.

    # every mosaic movie of the cache: how much of the picture each frame covers, by the rule before (only the colour
    # filters' tiles once a set exists) and now (the colour over the gray base); a collapse is a frame that loses
    # more than COLLAPSE of the covered area. Plans and tile reports only: nothing is drawn or made
    python web/frames/mosaic_movie_evidence.py --src ~/server/cache/cassini-prebuild --obs-dir obs-v46 --scan out/scan.json

    # one pass drawn frame by frame, as the windows play it (rolling_webp, 512 px), into a scratch cache whose plan and
    # tiles are hard links to the source's (new files only land in the scratch folder): run once from a worktree of
    # the code before and once from one of the code after, into two --scratch folders
    python web/frames/mosaic_movie_evidence.py --src ... --obs-dir obs-v46 --scratch /tmp/e-after \\
        --draw SATURN ISS_117RI_EQXSHADOW001_PRIME N --out out/after

    # the two side by side, frame by frame (PNGs numbered from 0 for ffmpeg), and a sheet of the frames whose
    # coverage changed most between the two
    python web/frames/mosaic_movie_evidence.py --compare out/before/<pass> out/after/<pass> out/compare/<pass>

--code <worktree> imports that worktree's obs_mosaic instead of this file's (the code before, with this script from
the code after). Run with the frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE): the passes are
worked out from the index and the geometry cache. Never point --scratch at the served cache.
"""
import argparse
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if "--code" in sys.argv:
    sys.path.insert(0, os.path.join(os.path.abspath(os.path.expanduser(sys.argv[sys.argv.index("--code") + 1])), "web", "frames"))
else:
    sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

COLLAPSE = 0.4   # a frame losing more than this share of the picture's covered area (the checker's test)
SWING = 0.12     # a place's level stepping by more than this, then back (the checker's A-B-A test)
SIDE = 256       # px: the covered area is measured on the view at this size


def split(name):
    """(target, observation, camera) of a pass folder's name (TARGET_OBS..._CAM_PASS[_r..][_g2])."""
    parts = name.split("_")
    while parts and (parts[-1].startswith("r") and parts[-1][1:].replace(".", "").isdigit() or parts[-1] == "g2"):
        parts.pop()
    if len(parts) < 4 or parts[-2] not in ("N", "W"):
        return None
    return parts[0], "_".join(parts[1:-2]), parts[-2]


def read_only(src, plans=True):
    """obs_mosaic reading the cache's tile reports (and plans) and making nothing: a tile not made is not placed."""
    real = om.plan

    def plan(u, cache):
        with open(os.path.join(om.folder(u, src), om.PLAN_FILE)) as f:
            return json.load(f)

    def tile(u, j, cache, scale=None):
        path = os.path.join(om._tiles(u, src, scale or plan(u, src)["display_scale"]), f"{j}.json")
        if not os.path.exists(path):
            return {"n": j, "filter": u["frames"][j][2]}
        with open(path) as f:
            return json.load(f)
    om.tile = tile
    if plans:
        om.plan = plan
        om.lap_gain = lambda *a, **k: 1.0   # (no pictures read: the gains do not change what is covered)
    return real


def covered(tiles, rect, mask=None):
    import cv2
    k = SIDE / max(rect[2], rect[3])
    W, H = max(1, math.ceil(rect[2] * k)), max(1, math.ceil(rect[3] * k))
    canvas = np.zeros((H, W), np.uint8)
    for t in tiles:
        if "offset" not in t:
            continue
        if t.get("outline"):
            pts = np.array([[(x - rect[0]) * k, (y - rect[1]) * k] for x, y in t["outline"]], np.int32)
        else:
            bx, by, bw, bh = t["box"]
            x0, y0 = t["offset"][0] + bx - rect[0], t["offset"][1] + by - rect[1]
            pts = np.array([[x0, y0], [x0 + bw, y0], [x0 + bw, y0 + bh], [x0, y0 + bh]], np.float64) * k
        cv2.fillPoly(canvas, [pts.astype(np.int32)], 1)
    return float(canvas.mean())


def scan(src, out):
    read_only(src)
    root = os.path.join(src, f"{om.VERSIONS['balanced']}-q{om.QUALITY}")
    seen, rows = set(), []
    for name in sorted(os.listdir(root)):
        got = split(name)
        if not got or got in seen:
            continue
        seen.add(got)
        try:
            us = om.units(*got)
        except Exception as e:
            print("skip", got, type(e).__name__, e, flush=True)
            continue
        for u in us:
            if u.get("kind") != "mosaic_movie" or not os.path.exists(os.path.join(om.folder(u, src), om.PLAN_FILE)):
                continue
            before, after, what = [], [], []
            for n in range(len(u["frames"])):
                made = om.rolling_layout(u, n, src)
                if not made:
                    before.append(0.0)
                    after.append(0.0)
                    what.append(None)
                    continue
                p, tiles, rect, count, used, _ = made
                before.append(covered([t for t in tiles if t["filter"] in used], rect))
                after.append(covered([t for t in tiles if t.get("drawn")], rect))
                what.append({"filter": u["frames"][n][2], "used": used, "tiles": len(tiles),
                             "drawn": sorted(t["n"] for t in tiles if t.get("drawn")), "slot": om.slots(u)[n]})
            drops = lambda a: [n for n in range(1, len(a)) if a[n - 1] > 0 and a[n] < (1 - COLLAPSE) * a[n - 1]]
            row = {"pass": os.path.basename(om.folder(u, src)), "frames": len(u["frames"]),
                   "collapses_before": drops(before), "collapses_after": drops(after),
                   "covered_before": [round(x, 3) for x in before], "covered_after": [round(x, 3) for x in after]}
            # what each frame of a collapse after draws, the frame before it and itself
            row["after_detail"] = [{"n": n, "covered": after[n - 1:n + 1], "was": what[n - 1], "now": what[n]}
                                   for n in row["collapses_after"]]
            rows.append(row)
            for d in row["after_detail"]:
                print("  collapse after", json.dumps(d), flush=True)
            print(row["pass"], len(u["frames"]), "frames, collapses before", len(row["collapses_before"]),
                  "after", len(row["collapses_after"]), flush=True)
    summary = {"mosaic_movies": len(rows), "collapsing_before": sum(1 for r in rows if r["collapses_before"]),
               "collapsing_after": sum(1 for r in rows if r["collapses_after"])}
    print(json.dumps(summary), flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"summary": summary, "passes": rows}, f)


def link_pass(u, src, scratch):
    """The pass's plan and tiles in the scratch cache: its JSON files copied, its tile pictures hard links to the
    source's, or symlinks to where they really are when the source is on another volume (a pre-built cache's tiles
    linked onto another disk image). Nothing writes into them: the cache writes a file anew and renames it over
    (reel._cached), which replaces the link in the scratch folder, never what it points at."""
    a, b = om.folder(u, src), om.folder(u, scratch)
    os.makedirs(b, exist_ok=True)
    for name in os.listdir(a):
        s, d = os.path.join(a, name), os.path.join(b, name)
        if os.path.exists(d):
            continue
        if os.path.isdir(s) and name.startswith("tiles-"):
            os.makedirs(d)
            for x in os.listdir(s):
                f, g = os.path.realpath(os.path.join(s, x)), os.path.join(d, x)
                if x.endswith(".json"):
                    shutil.copy2(f, g)
                    continue
                try:
                    os.link(f, g)
                except OSError:   # (another volume: EXDEV)
                    os.symlink(f, g)
        elif os.path.isfile(s) and name.endswith(".json"):
            shutil.copy2(s, d)


def levels(im, u, made, size):
    """Each slot's level in the picture (the median of its lit middle), by slot."""
    p, tiles, rect, *_ = made
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    k = a.shape[1] / rect[2]
    out = {}
    where = om.slots(u)
    for t in tiles:
        if not t.get("drawn", t["filter"] in made[4]):
            continue
        cx, cy = (t["offset"][0] - rect[0]) * k, (t["offset"][1] - rect[1]) * k
        r = max(2, int(0.2 * om.FRAME * k))
        box = a[max(0, int(cy) - r):int(cy) + r, max(0, int(cx) - r):int(cx) + r]
        lit = box[..., :3].mean(axis=2)[box[..., 3] > 250]
        if lit.size > 20:
            out[where[t["n"]]] = float(np.median(lit))
    return out


def swings(series):
    """A-B-A swings in one place's levels, at the frames its copy changes: a step past SWING, then one back."""
    steps = [math.log(b / a) for a, b in zip(series, series[1:]) if a > 2 and b > 2]
    big = [s for s in steps if abs(s) > math.log(1 + SWING)]
    return sum(1 for a, b in zip(big, big[1:]) if a * b < 0)


def draw(src, scratch, target, obs, cam, out, size):
    import io
    from PIL import Image
    read_only(scratch, plans=False)
    om.tiles_ahead = lambda *a, **k: None
    om.rolling_ahead = lambda *a, **k: None
    os.makedirs(out, exist_ok=True)
    rows = []
    us = om.units(target, obs, cam)
    for u in us:
        there = os.path.exists(os.path.join(om.folder(u, src), om.PLAN_FILE))
        print(json.dumps({"pass": os.path.basename(om.folder(u, src)), "kind": u.get("kind"), "frames": len(u["frames"]),
                          "in_source": there}), flush=True)
    if not us:
        print("no passes for", target, obs, cam, "(the observation id as the index has it, e.g. ISS_117RI_EQXSHADOW001_PRIME)")
    for u in us:
        if u.get("kind") != "mosaic_movie" or not os.path.exists(os.path.join(om.folder(u, src), om.PLAN_FILE)):
            continue
        link_pass(u, src, scratch)
        name = os.path.basename(om.folder(u, src))
        os.makedirs(os.path.join(out, name), exist_ok=True)
        by_slot, last, frames = {}, {}, []
        for n, fr in enumerate(u["frames"]):
            res = om.rolling_webp(fr[1], size, scratch, 1, wait=True)
            if not res or not res[0]:
                frames.append({"n": n, "id": fr[1], "picture": None})
                continue
            data, rep = res
            with open(os.path.join(out, name, f"{n:04d}.webp"), "wb") as f:
                f.write(data)
            im = Image.open(io.BytesIO(data))
            a = np.asarray(im.convert("RGBA"))
            made = om.rolling_layout(u, n, scratch)
            lv = levels(im, u, made, size)
            at = {}
            for t in made[1]:
                if t.get("drawn", t["filter"] in made[4]):
                    at.setdefault(om.slots(u)[t["n"]], set()).add(t["n"])
            # a place's level each time what is drawn there changes
            for s, ns in at.items():
                if s in lv and last.get(s) != ns:
                    last[s] = ns
                    by_slot.setdefault(s, []).append(lv[s])
            frames.append({"n": n, "id": fr[1], "filter": fr[2], "covered": round(float((a[..., 3] > 128).mean()), 4),
                           "mean": round(float(a[..., :3][a[..., 3] > 128].mean()) if (a[..., 3] > 128).any() else 0.0, 2),
                           "filters": rep.get("filter_names"), "base": rep.get("luminance")})
            print(name, n, fr[1], fr[2], frames[-1]["covered"], frames[-1]["mean"], flush=True)
        row = {"pass": name, "frames": frames, "swings": sum(swings(v) for v in by_slot.values())}
        cov = [f.get("covered", 0) for f in frames]
        if cov:
            top = 0
            drops = 0
            for c in cov:
                if top and c < (1 - COLLAPSE) * top:
                    drops += 1
                top = max(top, c) if c else top
            row["collapsed_frames"] = drops
        rows.append(row)
        print(json.dumps({"pass": name, "swings": row["swings"], "collapsed_frames": row.get("collapsed_frames")}), flush=True)
    with open(os.path.join(out, f"{target}_{obs}_{cam}.json"), "w") as f:
        json.dump(rows, f)


def compare(before, after, out, sheet=6):
    """before | after for every frame both drew (the frames' pictures from --draw), numbered from 0, and sheet.png:
    the sheet frames where the two differ most in what they cover."""
    from PIL import Image, ImageDraw
    os.makedirs(out, exist_ok=True)
    names = sorted(set(os.listdir(before)) & set(os.listdir(after)))
    names = [x for x in names if x.endswith(".webp")]
    rows = []
    for q, x in enumerate(names):
        pair = []
        for d in (before, after):
            im = Image.open(os.path.join(d, x)).convert("RGBA")
            bg = Image.new("RGBA", im.size, (20, 20, 20, 255))
            pair.append(Image.alpha_composite(bg, im).convert("RGB"))
        w, h = max(p.width for p in pair), max(p.height for p in pair)
        canvas = Image.new("RGB", (2 * w + 8, h + 22), (0, 0, 0))
        for i, (p, label) in enumerate(zip(pair, ("before", "after"))):
            canvas.paste(p, (i * (w + 8), 22))
            ImageDraw.Draw(canvas).text((i * (w + 8) + 6, 4), f"{label}  frame {int(x[:4])}", fill=(220, 220, 220))
        canvas.save(os.path.join(out, f"{q:04d}.png"))
        a, b = (np.asarray(Image.open(os.path.join(d, x)).convert("RGBA"))[..., 3] > 128 for d in (before, after))
        rows.append((float(b.mean() - a.mean()), q))
    picks = sorted(q for _, q in sorted(rows, reverse=True)[:sheet])
    if picks:
        ims = [Image.open(os.path.join(out, f"{q:04d}.png")) for q in picks]
        sheet_im = Image.new("RGB", (ims[0].width, sum(i.height for i in ims)), (0, 0, 0))
        y = 0
        for i in ims:
            sheet_im.paste(i, (0, y))
            y += i.height
        sheet_im.save(os.path.join(out, "sheet.png"))
    print(json.dumps({"frames": len(names), "sheet": picks}), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", help="the pre-built cache to read (never written)")
    ap.add_argument("--obs-dir", default=None, help="its mosaics' version folder, e.g. obs-v46 (default this code's)")
    ap.add_argument("--scan", help="write the coverage scan of every mosaic movie here (JSON)")
    ap.add_argument("--draw", nargs=3, metavar=("TARGET", "OBSERVATION", "CAM"))
    ap.add_argument("--scratch", help="the scratch cache --draw draws into")
    ap.add_argument("--out", help="--draw: the folder for the pictures and their numbers")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--compare", nargs=3, metavar=("BEFORE", "AFTER", "OUT"))
    ap.add_argument("--code", help="a worktree whose obs_mosaic is used (read before the arguments)")
    a = ap.parse_args()
    if a.compare:
        compare(*a.compare)
        return
    if a.obs_dir:
        om.VERSIONS["balanced"] = a.obs_dir
    src = os.path.expanduser(a.src)
    if a.scan:
        scan(src, a.scan)
    if a.draw:
        assert a.scratch and a.out and os.path.abspath(a.scratch) != os.path.abspath(src)
        draw(src, os.path.expanduser(a.scratch), *a.draw, a.out, a.size)


if __name__ == "__main__":
    main()
