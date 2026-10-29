# Before/after evidence for repeat exposures only at the same pointing (stacking.same_place): the finished mosaic of
# each pass below, made by the pipeline (obs_mosaic: every tile through color_image.processed_frame, then the pass's
# mosaic), with the frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE, CASSINI_CISSCAL).
# Run it once in a checkout of the code before and once in one of the code after, each with its own cache, then
# --compose puts the two side by side:
#   python evidence/repeat_place/render.py --cache CACHE_BEFORE --out OUT --tag before
#   python evidence/repeat_place/render.py --cache CACHE_AFTER --out OUT --tag after
#   python evidence/repeat_place/render.py --out OUT --compose
import argparse
import io
import json
import os
import sys
import time

REPO = os.getcwd()
sys.path.insert(0, os.path.join(REPO, "web", "frames"))
sys.path.insert(0, REPO)

# (name, first tile of the pass: the same frame before and after, so unit_of finds the same pass)
PASSES = [("phoebe_000PH_HIRESA001", "N1465672572_2"), ("rhea_045RH_REGGEOD001", "N1558967673_1"),
          ("dione_050DI_REGMAPF001", "N1569826640_1"), ("rhea_020RH_REGGEODE001", "N1516221581_1"),
          ("saturn_077RF_HIRESFRNG002", "N1595325201_1"), ("enceladus_158EN_ENCEL001", "N1702359393_1")]

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--cache")
ap.add_argument("--tag")
ap.add_argument("--compose", action="store_true")
ap.add_argument("--only", default="", help="comma separated names")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
todo = [p for p in PASSES if not a.only or p[0] in a.only.split(",")]

if not a.compose:
    import obs_mosaic as om
    for name, first in todo:
        t0 = time.time()
        u, _ = om.unit_of(first)
        for n in range(len(u["frames"])):
            om.tile(u, n, a.cache)
        last = u["frames"][-1][1]
        made = om.mosaic_webp(last, "full", a.cache, fmt="png", ahead=0, force=True)
        if made is None:
            print(name, "no mosaic")
            continue
        with open(os.path.join(a.out, f"{name}_{a.tag}.png"), "wb") as fh:
            fh.write(made[0])
        info = {"pass": list(u["key"]), "kind": u["kind"], "tiles": len(u["frames"]), "last": last,
                "behind": made[1].get("behind"), "seconds": round(time.time() - t0)}
        with open(os.path.join(a.out, f"{name}_{a.tag}.json"), "w") as fh:
            json.dump(info, fh)
        print(name, a.tag, info, flush=True)
else:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default()
    for name, _ in todo:
        pics = [os.path.join(a.out, f"{name}_{t}.png") for t in ("before", "after")]
        if not all(os.path.exists(p) for p in pics):
            continue
        ims = [Image.open(p).convert("RGB") for p in pics]
        infos = [json.load(open(p[:-4] + ".json")) for p in pics]
        h = max(i.height for i in ims)
        sheet = Image.new("RGB", (sum(i.width for i in ims) + 16, h + 28), "black")
        x = 0
        for im, info, t in zip(ims, infos, ("before", "after")):
            sheet.paste(im, (x, 28))
            ImageDraw.Draw(sheet).text((x + 8, 8), f"{t}: {info['tiles']} tiles ({name})", fill="white", font=font)
            x += im.width + 16
        sheet.save(os.path.join(a.out, f"{name}_before_after.png"))
        print("wrote", f"{name}_before_after.png")
