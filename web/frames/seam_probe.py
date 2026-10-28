#!/usr/bin/env python3
"""What makes a seam at one place of a real pass's mosaic, for the blend step's work (mosaic.composite): the tiles
under that place, each tile's colour and alpha against its distance from its edge (made and at the canvas's size),
the bench's pictures along a line through the place, and the newest tile at the place drawn again over the picture
so far, as the pass grows it, with what the blend works with along that line (its weight, the seam, its colours).
Then which tiles made the line what it is: the filter's mosaic drawn again (whole, as the pass draws its first
GROW_FROM tiles; then, with --history, grown a tile at a time to the newest), and every tile that changed the line
by more than --change levels shown with what it drew over, its weight and seam, and the line after it.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/seam_probe.py --cache SCRATCH_CACHE --bench BENCH_OUT PASS X,Y [X,Y ...] [--half 24] [--dir h]
      [--history] [--change 2]

PASS as seam_bench.py takes it; X,Y on the bench's 2048 px picture; --dir h: the line runs left to right (across a
tile edge that runs up and down), v: top to bottom. Reads the scratch cache seam_bench.py drew into and writes
nothing but the mosaics it draws again there. Prints text only."""
import argparse
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import seam_bench


def row(label, values, fmt="{:5.0f}"):
    print(f"  {label:<14}" + " ".join(fmt.format(v) if np.isfinite(v) else "    ." for v in values))


def profile(rgba, d, at=None, box=None, upto=16):
    """mean alpha and colour (mean of the bands) of rgba by whole distance d from its edge, 0..upto, and at
    feather-ish depth (the inside), over box (y0, y1, x0, x1) or all of it."""
    if box is not None:
        y0, y1, x0, x1 = box
        rgba, d = rgba[y0:y1, x0:x1], d[y0:y1, x0:x1]
    a = rgba[..., 3].astype(np.float32)
    lum = rgba[..., :3].astype(np.float32).mean(axis=2)
    rd = np.rint(d).astype(int)
    out = []
    for k in list(range(0, upto + 1)) + ([at] if at else []):
        m = (rd == k) & (a > 0)
        out.append((k, int(m.sum()), float(a[m].mean()) if m.any() else np.nan, float(lum[m].mean()) if m.any() else np.nan,
                    float(np.percentile(lum[m], 10)) if m.any() else np.nan))
    return out


def show_profile(title, prof):
    print(f"  {title}")
    print("    d(px)  count  alpha  mean   p10")
    for k, c, a, l, p in prof:
        print(f"    {k:5d} {c:6d} {a:6.1f} {l:6.1f} {p:6.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--bench", required=True, help="seam_bench.py's --out for this pass")
    ap.add_argument("--half", type=int, default=24)
    ap.add_argument("--dir", default="h", choices="hv")
    ap.add_argument("--history", action="store_true", help="grow the filter's mosaic tile by tile past GROW_FROM too")
    ap.add_argument("--change", type=float, default=2.0, help="levels a tile must change the line by to be shown")
    ap.add_argument("spec")
    ap.add_argument("at", nargs="+")
    args = ap.parse_args()
    import calibration
    import mosaic
    import obs_mosaic as om

    with calibration.looking("balanced"):
        u, n = seam_bench.unit(args.spec)
        if u is None:
            print("no pass", args.spec)
            return
        name = "_".join(map(str, u["key"]))
        made = om.layout(u, n, args.cache)
        p, tiles, rect, count, used, lname = made
        k = p["k"]
        W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)
        feather = max(8, round(64 * k / 0.5))
        base = om.lum_base(u, p, tiles, used)
        filters = list(used) + ([om.LUM] if base else [])
        print(f"pass {name}: {n + 1} tiles, kind {u.get('kind')}, filters {used}, luminance base {bool(base)}, "
              f"canvas {W}x{H}, k {k:.4f}, feather_px {feather}, filled {p['display_scale'].get('filled')}, "
              f"levels {round(math.log2(max(feather * mosaic.BAND_TOP, 1)))}")
        benches = {}
        for label, off in seam_bench.SETTINGS:
            path = os.path.join(args.bench, f"{name}-{off.replace(',', '_') or 'all'}.jpg")
            if os.path.exists(path):
                benches[label] = np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)
        shape = next(iter(benches.values())).shape if benches else (H, W)
        sy, sx = H / shape[0], W / shape[1]
        print(f"bench pictures {shape[1]}x{shape[0]} ({list(benches)}), canvas px per bench px {sx:.3f} x {sy:.3f}")
        there = om._tiles(u, args.cache, p["display_scale"])
        mines = {f: om._mine(u, p, tiles, f) for f in filters}

        for spot in args.at:
            X, Y = (float(v) for v in spot.split(","))
            cx, cy = X * sx, Y * sy
            half = args.half * max(sx, sy)
            print(f"\n=== at {X:.0f},{Y:.0f} on the bench picture = canvas {cx:.1f},{cy:.1f}; line {args.dir} +-{args.half} bench px")
            step = np.arange(-args.half, args.half + 1)
            for label, pic in benches.items():
                xs = np.clip(np.rint(X + (step if args.dir == "h" else 0)).astype(int), 0, pic.shape[1] - 1)
                ys = np.clip(np.rint(Y + (step if args.dir == "v" else 0)).astype(int), 0, pic.shape[0] - 1)
                row(label, pic[ys, xs])
            row("offset", step, "{:5d}")

            for f in filters:
                mine = mines[f]
                near = []
                for j, t in enumerate(mine):
                    bx, by, bw, bh = t["box"]
                    left = round((t["offset"][0] + bx - rect[0]) * k)
                    top = round((t["offset"][1] + by - rect[1]) * k)
                    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
                    if left - half <= cx < left + sw + half and top - half <= cy < top + sh + half:
                        near.append((j, t, left, top, sw, sh))
                if not near:
                    continue
                print(f"\n filter {f}: {len(mine)} tiles; {len(near)} within the line's reach, newest last:")
                for j, t, left, top, sw, sh in near[-6:]:
                    part = om._shade(om._part(os.path.join(there, f"{t['n']}.png"), sw, sh), t)
                    a = part[..., 3]
                    dist = cv2.distanceTransform(np.pad((a > 0).astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
                    py, px = int(round(cy - top)), int(round(cx - left))
                    inside = 0 <= py < sh and 0 <= px < sw
                    with Image.open(os.path.join(there, f"{t['n']}.png")) as im:
                        nw, nh = im.size
                    print(f"  #{j} tile {t['n']} {t.get('id')} t={t.get('t')} stacked={t.get('stacked')} "
                          f"calibrated={t.get('calibrated')} gain={t.get('gain')} made {nw}x{nh} drawn {sw}x{sh} "
                          f"(x{sw / nw:.2f}) at {left},{top}; here alpha {int(a[py, px]) if inside else '-'}, "
                          f"{dist[py, px] if inside else 0:.1f} px from its edge")
                j, t, left, top, sw, sh = near[-1]
                part = om._shade(om._part(os.path.join(there, f"{t['n']}.png"), sw, sh), t)
                a = part[..., 3]
                dist = cv2.distanceTransform(np.pad((a > 0).astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
                py, px = int(round(cy - top)), int(round(cx - left))
                r = int(round(4 * feather))
                box = (max(py - r, 0), min(py + r, sh), max(px - r, 0), min(px + r, sw))
                show_profile(f"newest, tile {t['n']} drawn ({sw}x{sh}), by distance from its edge, within {r} px of the place:",
                             profile(part, dist, feather, box))
                native = np.asarray(Image.open(os.path.join(there, f"{t['n']}.png")).convert("RGBA"))
                nd = cv2.distanceTransform(np.pad((native[..., 3] > 0).astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
                show_profile(f"the same tile as made ({native.shape[1]}x{native.shape[0]}), all its edges:",
                             profile(native, nd, max(1, round(feather * native.shape[1] / sw))))
                # along the line: the tile drawn, and what the blend works with when it is drawn over the picture so far
                st = np.arange(-int(round(half)), int(round(half)) + 1)
                lx = np.clip(np.rint(px + (st if args.dir == "h" else 0)).astype(int), 0, sw - 1)
                ly = np.clip(np.rint(py + (st if args.dir == "v" else 0)).astype(int), 0, sh - 1)
                print("  along the line, canvas px:")
                row("offset", st, "{:5d}")
                row("tile alpha", a[ly, lx])
                row("tile colour", part[ly, lx, :3].astype(np.float32).mean(axis=1))
                row("edge dist", dist[ly, lx], "{:5.1f}")
                grown = not (f == om.LUM or j <= om.GROW_FROM or j >= len(mine))
                if not grown:
                    print("  (not grown at this tile: no redraw)")
                for label, off in (seam_bench.SETTINGS if grown else []):
                    with calibration.stepping(off):
                        before = om._filter_path(u, f, j, rect, args.cache)
                        after = om._filter_path(u, f, j + 1, rect, args.cache)
                        if not os.path.exists(before):
                            print(f"  [{label}] no picture so far before tile #{j} in the cache ({before})")
                            continue
                        rgba = np.asarray(Image.open(before).convert("RGBA")).copy()
                        under = rgba.copy()
                        caught = {}
                        cut, bands, blended = mosaic._seam_cut, mosaic._bands_blended, mosaic._blended

                        def seam_cut(a_, has_, below_, color_, under_):
                            s, found = cut(a_, has_, below_, color_, under_)
                            caught.update(a=a_.copy(), has=has_.copy(), below=below_.copy(), color=color_.copy(),
                                          under=under_.copy(), seam=s.copy())
                            return s, found

                        def bl(out, infos, *rest, **kw):
                            caught["boxes"] = [None if i is None else i[0] for i in infos]
                            caught["area"] = rest[3] if len(rest) > 3 else kw.get("area")
                            caught["ramps"] = [None if i is None or len(i) < 6 else i[4] for i in infos]
                            return blended(out, infos, *rest, **kw)
                        composite = mosaic.composite

                        def co(frames_, gains_, *rest, **kw):
                            caught["gain"] = np.asarray(gains_)[-1]
                            return composite(frames_, gains_, *rest, **kw)
                        mosaic._seam_cut, mosaic._blended, mosaic.composite = seam_cut, bl, co
                        kept = []
                        try:
                            om._over(u, p, rgba, t, rect, args.cache, kept=kept)
                        finally:
                            mosaic._seam_cut, mosaic._blended, mosaic.composite = cut, blended, composite
                        x0r = max(left - (feather + 1), 0)
                        y0r = max(top - (feather + 1), 0)
                        print(f"  [{label}] tile #{j} drawn again over the picture so far:")
                        lxc = np.clip(np.rint(cx + (st if args.dir == "h" else 0)).astype(int), 0, W - 1)
                        lyc = np.clip(np.rint(cy + (st if args.dir == "v" else 0)).astype(int), 0, H - 1)
                        row("so far", under[lyc, lxc, :3].astype(np.float32).mean(axis=1))
                        row("so far alpha", under[lyc, lxc, 3])
                        row("drawn", rgba[lyc, lxc, :3].astype(np.float32).mean(axis=1))
                        row("drawn alpha", rgba[lyc, lxc, 3])
                        if "gain" in caught:
                            print(f"   (the tile's gain, matched to the picture so far: {np.round(caught['gain'], 3)})")
                        lv = kept[0]["field"] if kept and kept[0] else None
                        if lv is not None:
                            grid, c, gy, gx = lv
                            whole = mosaic._field(lv, (gy, gy + grid.shape[0] * c, gx, gx + grid.shape[1] * c))[..., 0]
                            fy = np.clip(lyc - gy, 0, whole.shape[0] - 1)
                            fx = np.clip(lxc - gx, 0, whole.shape[1] - 1)
                            row("level field", whole[fy, fx], "{:5.2f}")
                            g = np.exp(grid[..., 0])
                            print(f"   (its leveling over the tile: mean x{g.mean():.3f}, from x{g.min():.3f} to x{g.max():.3f})")
                        elif label == "blend + level":
                            print("   (no leveling for this tile)")
                        if os.path.exists(after):
                            nxt = np.asarray(Image.open(after).convert("RGBA"))
                            row("cached next", nxt[lyc, lxc, :3].astype(np.float32).mean(axis=1))
                        if "a" in caught and caught.get("boxes") and caught["boxes"][1] is not None:
                            b = caught["boxes"][1]
                            area = caught["area"]
                            oy, ox = y0r + b[0], x0r + b[2]
                            by_ = np.clip(lyc - oy, 0, caught["a"].shape[0] - 1)
                            bx_ = np.clip(lxc - ox, 0, caught["a"].shape[1] - 1)
                            row("has", caught["has"][by_, bx_], "{:5.1f}")
                            row("below", caught["below"][by_, bx_], "{:5.1f}")
                            if caught["ramps"][1] is not None:
                                row("ramp", caught["ramps"][1][by_, bx_], "{:5.2f}")
                            row("weight a", caught["a"][by_, bx_], "{:5.2f}")
                            row("seam", caught["seam"][by_, bx_], "{:5.1f}")
                            lum = lambda v: v if v.ndim == 1 else v.mean(axis=1)
                            row("tile toned", lum(caught["color"][by_, bx_]))
                            row("under", lum(caught["under"][by_, bx_]))
                            print(f"   (box {b}, area {area}, region at {x0r},{y0r})")
                        elif label != "before":
                            print("   (the tile met nothing below it: drawn with its weight alone)")

                for label, off in (seam_bench.SETTINGS[1:] if f != om.LUM else []):
                    with calibration.stepping(off):
                        history(u, p, f, mine, rect, args.cache, k, W, H, cx, cy, half, args, label)


def history(u, p, f, mine, rect, cache, k, W, H, cx, cy, half, args, label):
    """The filter f's mosaic drawn again as the pass draws it (its first GROW_FROM tiles whole, then a tile at a time
    with --history), and the tiles that changed the line through (cx, cy) by more than args.change levels."""
    import mosaic
    import obs_mosaic as om
    st = np.arange(-int(round(half)), int(round(half)) + 1)
    lx = np.clip(np.rint(cx + (st if args.dir == "h" else 0)).astype(int), 0, W - 1)
    ly = np.clip(np.rint(cy + (st if args.dir == "v" else 0)).astype(int), 0, H - 1)
    seen = []

    def watch(region, names):
        def w(i, origin, sl, parts):
            if i not in names:
                return
            ay, ax = ly - region[0] - origin[0] - sl[0].start, lx - region[1] - origin[1] - sl[1].start
            hh, ww = parts["has"].shape
            on = (ay >= 0) & (ay < hh) & (ax >= 0) & (ax < ww)
            if not on.any():
                return
            ay, ax = np.clip(ay, 0, hh - 1), np.clip(ax, 0, ww - 1)
            pick = lambda v: np.where(on, (v if v.ndim == 2 else v.mean(axis=2))[ay, ax], np.nan) if v is not None else None
            seen.append((names[i], {n: pick(v) for n, v in parts.items()}))
        return w

    def show(name, got):
        before, after = got["before"], got["after"]
        change = np.nanmax(np.abs(after - before)) if np.isfinite(after - before).any() else 0
        if change <= args.change:
            return
        print(f"  [{label}] {name} changed the line by up to {change:.0f}:")
        for n in ("before", "after", "color", "has", "below", "ramp", "a", "seam"):
            if got.get(n) is not None:
                row(n if n != "color" else "tile toned", got[n], "{:5.0f}" if n in ("before", "after", "color") else "{:5.2f}")

    first = mine[:om.GROW_FROM] if len(mine) > om.GROW_FROM else mine
    window, shown = om._window(u, p, first, rect, cache)
    print(f"\n filter {f}, {label}: its first {len(shown)} tiles drawn whole, the tiles that changed the line:")
    row("offset", st, "{:5d}")
    mosaic._watch = watch((0, 0), {i: f"tile #{mine.index(t)} {t['n']} {t.get('id')}" for i, t in enumerate(shown)})
    try:
        rgba = om._compose(window, k, pin=None) if window else np.zeros((H, W, 4), np.uint8)
    finally:
        mosaic._watch = None
    for name, got in seen:
        show(name, got)
    row("whole", rgba[ly, lx, :3].astype(np.float32).mean(axis=1))
    if not args.history or len(mine) <= om.GROW_FROM:
        return
    print(f" filter {f}, {label}: grown a tile at a time, the tiles that changed the line:")
    rgba = rgba.copy()
    for j in range(om.GROW_FROM, len(mine)):
        t = mine[j]
        bx, by, bw, bh = t["box"]
        left = round((t["offset"][0] + bx - rect[0]) * k)
        top = round((t["offset"][1] + by - rect[1]) * k)
        sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
        if not (left - half <= cx < left + sw + half and top - half <= cy < top + sh + half):
            om._over(u, p, rgba, t, rect, cache)
            continue
        pad = max(8, round(64 * k / 0.5)) + 1
        seen.clear()
        mosaic._watch = watch((max(top - pad, 0), max(left - pad, 0)), {1: f"tile #{j} {t['n']} {t.get('id')}"})
        try:
            om._over(u, p, rgba, t, rect, cache)
        finally:
            mosaic._watch = None
        for name, got in seen:
            show(name, got)
    row("grown", rgba[ly, lx, :3].astype(np.float32).mean(axis=1))


if __name__ == "__main__":
    main()
