#!/usr/bin/env python3
"""Before/after pictures for obs_mosaic's pass layout (group H): every pass of a few observations drawn as the window
shows it, through the checkout's own makers (obs_mosaic.layout and so_far for a mosaic, movie_webp for a movie,
frame_server.processed_webp for frames that are no mosaic), nothing re-implemented.

Render one side (once with the old checkout, once with the new; each its own cache):
  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... CASSINI_CISSCAL=... \\
  python mosaic_layout_evidence.py render --code <checkout>/web/frames --cache DIR --out OUT/before OBS...
Then put the two sides together, one picture per observation, and an index page:
  python mosaic_layout_evidence.py compose OUT

OBS is TARGET:OBSERVATION_ID:CAM (TITAN:ISS_042TI_GLOBMAP001_PRIME:N). A movie or a pass of frames shows up to
FRAMES of its frames, spread over it."""
import argparse
import io
import json
import os
import sys

FRAMES = 6
SIDE = 720


def render(args):
    sys.path.insert(0, os.path.abspath(args.code))
    from PIL import Image
    import frame_server   # (first: it puts its own checkout's root, with calibration, on the path)
    import obs_mosaic as om
    import calibration
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "summary.json")
    summary = json.load(open(path)) if os.path.exists(path) else {}
    with calibration.looking("balanced"):
        for spec in args.observations:
            target, obs, cam = spec.split(":")
            rows = []
            for u in om.units(target, obs, cam):
                if not u["frames"]:
                    continue
                name = "_".join(map(str, u["key"]))
                kind = u.get("kind")
                print(name, kind, len(u["frames"]), "frames", flush=True)
                pics = []
                if kind in ("mosaic", "mosaic_movie"):
                    n = len(u["frames"]) - 1
                    made = om.layout(u, n, args.cache)
                    im = om.so_far(u, n, args.cache, made)[0] if made else None
                    pics = [im] if im is not None else []
                else:
                    count = min(FRAMES, len(u["frames"]))
                    for k in sorted({round(i * (len(u["frames"]) - 1) / max(1, count - 1)) for i in range(count)}):
                        fid = u["frames"][k][1]
                        got = (om.movie_webp(fid, 512, args.cache, ahead=0, wait=True) if kind == "movie"
                               else frame_server.processed_webp(fid, 512, args.cache))
                        if got and got[0]:
                            pics.append(Image.open(io.BytesIO(got[0])))
                files = []
                for j, im in enumerate(pics):
                    f = f"{name}_{j}.png"
                    im.save(os.path.join(args.out, f))
                    files.append(f)
                rows.append({"pass": name, "kind": kind, "frames": len(u["frames"]), "pictures": files})
            summary[spec] = rows
            with open(path, "w") as fh:
                json.dump(summary, fh, indent=1)


def _side(out, side, rows):
    """one column: each pass labelled, a mosaic as one picture, a movie or frames as a grid of three across"""
    from PIL import Image, ImageDraw
    blocks = []
    for r in rows:
        ims = [Image.open(os.path.join(out, side, f)).convert("RGBA") for f in r["pictures"]]
        if r["kind"] in ("mosaic", "mosaic_movie") and ims:
            im = ims[0]
            im.thumbnail((SIDE, SIDE))
            body = Image.new("RGB", (SIDE, im.height), (12, 12, 14))
            body.paste(im, ((SIDE - im.width) // 2, 0), im)
        else:
            cell = SIDE // 3
            body = Image.new("RGB", (SIDE, cell * max(1, (len(ims) + 2) // 3)), (12, 12, 14))
            for j, im in enumerate(ims):
                im.thumbnail((cell - 4, cell - 4))
                body.paste(im, ((j % 3) * cell + (cell - im.width) // 2, (j // 3) * cell + (cell - im.height) // 2), im)
        block = Image.new("RGB", (SIDE, body.height + 28), (30, 30, 34))
        ImageDraw.Draw(block).text((8, 8), f"{r['pass']}: {r['kind'] or 'frames'} ({r['frames']} frames)", fill=(225, 225, 225))
        block.paste(body, (0, 28))
        blocks.append(block)
    col = Image.new("RGB", (SIDE, sum(b.height + 8 for b in blocks) + 32), (20, 20, 24))
    ImageDraw.Draw(col).text((8, 10), side, fill=(255, 255, 255))
    y = 32
    for b in blocks:
        col.paste(b, (0, y))
        y += b.height + 8
    return col


def compose(args):
    from PIL import Image
    before = json.load(open(os.path.join(args.out, "before", "summary.json")))
    after = json.load(open(os.path.join(args.out, "after", "summary.json")))
    html = ["<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Mosaic layout</title>",
            "<style>body{background:#111;color:#ddd;font:15px system-ui;margin:16px}img{max-width:100%}</style>",
            "<h1>Mosaic layout (group H): before / after</h1><p>Left: main. Right: PR #194. Every pass of each observation, "
            "as the window shows it.</p>"]
    for spec in after:
        a, b = _side(args.out, "before", before.get(spec, [])), _side(args.out, "after", after[spec])
        sbs = Image.new("RGB", (2 * SIDE + 8, max(a.height, b.height)), (40, 40, 44))
        sbs.paste(a, (0, 0))
        sbs.paste(b, (SIDE + 8, 0))
        out = spec.replace(":", "_") + "_before_after.jpg"
        sbs.save(os.path.join(args.out, out), quality=88)
        html.append(f"<h3>{spec}</h3><img src='{out}' loading=lazy>")
    open(os.path.join(args.out, "index.html"), "w").write("\n".join(html))
    print("wrote", os.path.join(args.out, "index.html"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--code", required=True)
    r.add_argument("--cache", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("observations", nargs="+")
    c = sub.add_parser("compose")
    c.add_argument("out")
    args = ap.parse_args()
    render(args) if args.cmd == "render" else compose(args)


if __name__ == "__main__":
    main()
