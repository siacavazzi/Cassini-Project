#!/usr/bin/env python3
"""Before/after evidence for placed tiles (pictures program phase 3) on real passes, through the checkout's own
obs_mosaic (so_far: SPICE-placed tiles, mosaic.compose, colour_picture), nothing re-implemented.

Render one side (run once with the old checkout, once with the new; each its own cache):
  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python placed_tiles_evidence.py render --code <checkout>/web/frames --cache DIR --out OUT/before PASS...
Then put them side by side with an index page:
  python placed_tiles_evidence.py compose OUT

PASS is a frame id (W1537023863_1) or TARGET:OBSERVATION_ID:CAM[:pass] (TITAN:ISS_181TI_TEA001_CIRS:N). For each
pass it draws the mosaic at a few tiles: the tile before colour begins, the tile colour begins, the tile where the
covered area changes most, and the last tile, plus the covered share of the picture at up to STEPS tiles spread
over the pass (shrinks: how often and how far the covered area falls from one step to the next)."""
import argparse
import json
import os
import sys

STEPS = 24


def render(args):
    sys.path.insert(0, os.path.abspath(args.code))
    import numpy as np
    import calibration
    import obs_mosaic as om
    import reel
    os.makedirs(args.out, exist_ok=True)
    idx, _ = reel.load_index()
    summary = {}
    with calibration.looking("balanced"):
        for spec in args.passes:
            if ":" in spec:
                parts = spec.split(":")
                target, obs, cam = parts[:3]
                k = int(parts[3]) if len(parts) > 3 else None
                us = [v for v in om.units(target, obs, cam) if v["mosaic"]] or om.units(target, obs, cam)
                if not us:
                    print(spec, "no pass", flush=True)
                    continue
                u = us[k] if k is not None else max(us, key=lambda v: len(v["frames"]))
            else:
                found = om.unit_of(spec)
                if not found:
                    print(spec, "in no pass", flush=True)
                    continue
                u = found[0]
            name = "_".join(map(str, u["key"]))
            n_all = len(u["frames"])
            print(name, n_all, "tiles", u.get("kind"), flush=True)
            p = om.plan(u, args.cache)
            steps = sorted(set([round(i * (n_all - 1) / max(1, STEPS - 1)) for i in range(STEPS)]))
            # colour begins: the first tile at which every colour filter has a tile
            first = None
            if p["colour"]:
                seen = set()
                for j, fr in enumerate(u["frames"]):
                    seen.add(fr[2])
                    if all(f in seen for f in p["colour"]):
                        first = j
                        break
            if first is not None:
                steps = sorted(set(steps + [max(0, first - 1), first]))
            cover, pics = [], {}
            for n in steps:
                made = om.layout(u, n, args.cache)
                im, rep = om.so_far(u, n, args.cache, made) if made else (None, None)
                if im is None:
                    cover.append([n, 0.0, None])
                    continue
                a = np.asarray(im)
                cover.append([n, round(float((a[..., 3] > 0).mean()), 4), rep.get("filter_names")])
                pics[n] = im
            drops = [(b[0], a[1] - b[1]) for a, b in zip(cover, cover[1:]) if b[1] < a[1] - 0.005]
            keep = {n_all - 1}
            if first is not None:
                keep |= {max(0, first - 1), first}
            if drops:
                keep.add(max(drops, key=lambda d: d[1])[0])
            for n in sorted(keep):
                if n in pics:
                    pics[n].save(os.path.join(args.out, f"{name}_{n}.png"))
            summary[name] = {"tiles": n_all, "kind": u.get("kind"), "colour": p["colour"], "grey": p["grey"],
                             "colour_begins": first, "cover": cover, "shrinks": len(drops),
                             "worst_shrink": round(max([d[1] for d in drops] or [0.0]), 4), "shown": sorted(keep)}
            print(name, "shrinks", len(drops), "worst", summary[name]["worst_shrink"], flush=True)
            with open(os.path.join(args.out, "summary.json"), "w") as fh:
                json.dump(summary, fh, indent=1)


def compose(args):
    from PIL import Image, ImageDraw
    before = json.load(open(os.path.join(args.out, "before", "summary.json")))
    after = json.load(open(os.path.join(args.out, "after", "summary.json")))
    rows = []
    for name in after:
        b, a = before.get(name, {}), after[name]
        shown = sorted(set(a["shown"]) | set(b.get("shown", [])))
        for n in shown:
            pair = []
            for side in ("before", "after"):
                path = os.path.join(args.out, side, f"{name}_{n}.png")
                im = Image.open(path).convert("RGBA") if os.path.exists(path) else Image.new("RGBA", (512, 512))
                im.thumbnail((720, 720))
                bg = Image.new("RGB", (720, 760), (12, 12, 14))
                bg.paste(im, ((720 - im.width) // 2, 40 + (720 - im.height) // 2), im)
                ImageDraw.Draw(bg).text((12, 12), f"{side}  {name}  tile {n + 1} of {a['tiles']}", fill=(220, 220, 220))
                pair.append(bg)
            sbs = Image.new("RGB", (1448, 760), (40, 40, 44))
            sbs.paste(pair[0], (0, 0))
            sbs.paste(pair[1], (728, 0))
            out = f"{name}_{n}_before_after.jpg"
            sbs.save(os.path.join(args.out, out), quality=88)
            why = "colour begins" if n == a.get("colour_begins") else "tile before colour" if a.get("colour_begins") is not None and n == a["colour_begins"] - 1 else "last tile" if n == a["tiles"] - 1 else "largest shrink before"
            rows.append((name, n, why, out))
    html = ["<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Placed tiles</title>",
            "<style>body{background:#111;color:#ddd;font:15px system-ui;margin:16px}img{max-width:100%}td,th{padding:2px 8px;text-align:right}</style>",
            "<h1>Placed tiles: before / after</h1><p>Left: pictures before phase 3. Right: the gray base with color where all three filters cover.</p>",
            "<table><tr><th>pass</th><th>tiles</th><th>shrinks before</th><th>worst before</th><th>shrinks after</th><th>worst after</th></tr>"]
    for name in after:
        b, a = before.get(name, {}), after[name]
        html.append(f"<tr><td>{name}</td><td>{a['tiles']}</td><td>{b.get('shrinks')}</td><td>{b.get('worst_shrink')}</td><td>{a['shrinks']}</td><td>{a['worst_shrink']}</td></tr>")
    html.append("</table>")
    for name, n, why, out in rows:
        html.append(f"<h3>{name} · tile {n + 1} ({why})</h3><img src='{out}' loading=lazy>")
    open(os.path.join(args.out, "index.html"), "w").write("\n".join(html))
    print("wrote", os.path.join(args.out, "index.html"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--code", required=True)
    r.add_argument("--cache", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("passes", nargs="+")
    c = sub.add_parser("compose")
    c.add_argument("out")
    args = ap.parse_args()
    render(args) if args.cmd == "render" else compose(args)


if __name__ == "__main__":
    main()
