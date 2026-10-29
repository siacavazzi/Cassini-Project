# Before/after evidence for a dense scan judged a mosaic again (obs_mosaic._judge: a creep that adds up to a jump
# over one repeat window is a jump). Each pass below as the site draws it, through the pipeline: when _judge calls it
# a mosaic, its finished mosaic (obs_mosaic.mosaic_webp, not forced); when it calls it a movie, a contact sheet of
# twelve of its frames spread over the pass (obs_mosaic.tile, the movie's frames). With the frame server's
# environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE, CASSINI_CISSCAL). Run it once in a checkout
# of the code before and once in one of the code after, each with its own cache, then --compose puts them side by side:
#   python evidence/creep_scan/render.py --cache CACHE_BEFORE --out OUT --tag before
#   python evidence/creep_scan/render.py --cache CACHE_AFTER --out OUT --tag after
#   python evidence/creep_scan/render.py --out OUT --compose
# --old-repeats draws with the repeat rule before #189 (stacking.same_place not asked: every frame of a filter within
# the repeat window merged, wherever it pointed), tag "pre189"; --compose puts it first when it is there.
import argparse
import json
import os
import sys
import time

REPO = os.getcwd()
sys.path.insert(0, os.path.join(REPO, "web", "frames"))
sys.path.insert(0, REPO)

# (name, first frame of the pass: the same before and after, so unit_of finds the same pass)
PASSES = [("saturn_013RI_AZSCNHIPH001", "N1503241997_1"), ("tethys_166TE_TETHYS001_CIRS", "N1716174363_1"),
          ("saturn_282RI_HIRESAFRG001", "N1878007577_1"), ("saturn_033RI_AZSCNLOPH001", "N1542721535_1")]
SHEET = 12

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--cache")
ap.add_argument("--tag")
ap.add_argument("--compose", action="store_true")
ap.add_argument("--only", default="", help="comma separated names")
ap.add_argument("--old-repeats", action="store_true")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
todo = [p for p in PASSES if not a.only or p[0] in a.only.split(",")]

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
font = ImageFont.load_default()

if not a.compose:
    import io
    import obs_mosaic as om
    if a.old_repeats:
        import stacking
        stacking.same_place = lambda p, q: None
    for name, first in todo:
        t0 = time.time()
        u, _ = om.unit_of(first)
        info = {"pass": list(u["key"]), "kind": u["kind"], "tiles": len(u["frames"]),
                "jump_frac": u["jump_frac"], "dwell": u["dwell"]}
        if u["mosaic"]:
            for n in range(len(u["frames"])):
                om.tile(u, n, a.cache)
            made = om.mosaic_webp(u["frames"][-1][1], "full", a.cache, fmt="png", ahead=0)
            im = Image.open(io.BytesIO(made[0])).convert("RGB")
        else:
            # the movie's frames: twelve tiles spread over the pass, in a 4 x 3 sheet
            scale = om.plan(u, a.cache)["display_scale"]
            picks = sorted({round(i * (len(u["frames"]) - 1) / (SHEET - 1)) for i in range(SHEET)})
            cells = []
            for n in picks:
                om.tile(u, n, a.cache)
                rec = om._kept_tiles(u, a.cache, scale)
                there = rec["tiles_dir"] if rec is not None else om._tiles(u, a.cache, scale)
                p = os.path.join(there, f"{n}.png")
                cells.append(Image.open(p).convert("RGB") if os.path.exists(p) else Image.new("RGB", (64, 64)))
            side = 400
            im = Image.new("RGB", (4 * side, 3 * side), "black")
            for i, c in enumerate(cells):
                c.thumbnail((side - 8, side - 8))
                im.paste(c, ((i % 4) * side + 4, (i // 4) * side + 4))
                ImageDraw.Draw(im).text(((i % 4) * side + 8, (i // 4) * side + 8), f"frame {picks[i] + 1}",
                                        fill="white", font=font)
        im.save(os.path.join(a.out, f"{name}_{a.tag}.png"))
        info["seconds"] = round(time.time() - t0)
        with open(os.path.join(a.out, f"{name}_{a.tag}.json"), "w") as fh:
            json.dump(info, fh)
        print(name, a.tag, info, flush=True)
else:
    for name, _ in todo:
        tags = [t for t in ("pre189", "before", "after") if os.path.exists(os.path.join(a.out, f"{name}_{t}.png"))]
        if "before" not in tags or "after" not in tags:
            continue
        pics = [os.path.join(a.out, f"{name}_{t}.png") for t in tags]
        ims = [Image.open(p).convert("RGB") for p in pics]
        for im in ims:
            im.thumbnail((1600, 1600))
        infos = [json.load(open(p[:-4] + ".json")) for p in pics]
        h = max(i.height for i in ims)
        sheet = Image.new("RGB", (sum(i.width for i in ims) + 16, h + 28), "black")
        x = 0
        for im, info, t in zip(ims, infos, tags):
            sheet.paste(im, (x, 28))
            what = f"{t}: {info['kind']}, {info['tiles']} pictures, jump share {info['jump_frac']:.2f} ({name})"
            ImageDraw.Draw(sheet).text((x + 8, 8), what, fill="white", font=font)
            x += im.width + 16
        sheet.save(os.path.join(a.out, f"{name}_before_after.jpg"), quality=90)
        print("wrote", f"{name}_before_after.jpg")
