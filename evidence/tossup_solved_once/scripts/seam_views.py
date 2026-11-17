"""seam_views.py MAIN_CACHE FIX_CACHE NAME OUT_PREFIX FRAME [FRAME ...]: a toss-up pass's Mosaic view at the frames
given (1 the first), full size, as a fresh server draws it on each of two builds' caches, judged by the repo's own
seam measure (web/frames/seam_bench.py: the brightness step across the tiles' edges inside the mosaic against the
same away from them; seam95 / flat95 near 1 = seams no more visible than the picture's own texture), with 1:1 crops
of the places where the two builds differ most and where main's seams are worst, main beside the fix. Also how the
lit area changed between the two (a tile that moved uncovers a strip on one side and covers one on the other).
Both caches are read through clones the caller made."""
import importlib.util, io, json, os, sys
wt = os.environ["WT"]; sys.path.insert(0, os.path.join(wt, "web", "frames"))
import cv2
import numpy as np
from PIL import Image, ImageDraw
import prebuild, calibration, obs_mosaic as om
fs = prebuild.frame_server
spec = importlib.util.spec_from_file_location("bench_seam", os.path.join(wt, "web", "frames", "seam_bench.py"))
sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
main, fix, name, out = sys.argv[1:5]
frames = [int(x) for x in sys.argv[5:]]
u = next(u for u in prebuild.all_passes() if "_".join(map(str, u["key"])) == name)
om.tiles_ahead = lambda *a, **k: None
om.rolling_ahead = lambda *a, **k: None
C, Z = 200, 2
stats = []
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    for j in frames:
        side = {}
        for label, cache in (("main", main), ("fix", fix)):
            made = om.layout(u, j - 1, cache)
            got = om.mosaic_webp(u["frames"][j - 1][1], fs.FULL, cache, None, 0, fmt="webp", out=min(om.CANVAS, fs.FULL_MAX), force=True)
            rgba = np.asarray(Image.open(io.BytesIO(got[0])).convert("RGBA"))
            edge = sb.edges(u, made, cache, rgba.shape[:2])
            nums, worst = sb.measure(rgba, edge)
            side[label] = (rgba, nums, worst)
        (a, na, wa), (b, nb, wb) = side["main"], side["fix"]
        row = {"frame": j, "size": list(a.shape[:2]), "main": na, "fix": nb}
        for label, n_ in (("main", na), ("fix", nb)):
            row[label + "_ratio"] = round(n_["seam95"] / n_["flat95"], 3) if n_.get("seam95") and n_.get("flat95") else None
        if a.shape == b.shape:
            la, lb = a[..., :3].max(axis=2) > 8, b[..., :3].max(axis=2) > 8
            d = np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).max(axis=2)
            row.update(lit_main=int(la.sum()), lit_fix=int(lb.sum()), lit_only_main=int((la & ~lb).sum()), lit_only_fix=int((lb & ~la).sum()),
                       differ_over8=int((d > 8).sum()))
            # crops: the two places where the builds differ most, and main's worst seam
            e = cv2.blur(d.astype(np.float32), (C, C))
            spots = []
            for _ in range(2):
                y, x = np.unravel_index(int(np.argmax(e)), e.shape)
                spots.append((int(y), int(x), "differ most"))
                e[max(0, y - C):y + C, max(0, x - C):x + C] = 0
            y, x = np.unravel_index(int(np.argmax(wa)), wa.shape)
            spots.append((int(y), int(x), "main's worst seam"))
            sheet = Image.new("RGB", (len(spots) * (C * Z + 10) + 10, 2 * (C * Z + 26) + 10), (16, 16, 16))
            dr = ImageDraw.Draw(sheet)
            for i, (y, x, why) in enumerate(spots):
                y0, x0 = min(max(0, y - C // 2), a.shape[0] - C), min(max(0, x - C // 2), a.shape[1] - C)
                for r, (im, label) in enumerate(((a, "today (main)"), (b, "with the fix"))):
                    crop = Image.fromarray(im[y0:y0 + C, x0:x0 + C, :3]).resize((C * Z, C * Z), Image.NEAREST)
                    px, py = 10 + i * (C * Z + 10), 10 + r * (C * Z + 26)
                    sheet.paste(crop, (px, py + 18))
                    dr.text((px, py + 2), f"frame {j}, {label}: {why}, full size x{Z} at ({x0}, {y0})", fill=(230, 230, 230))
            sheet.save(f"{out}-frame{j:03d}.png")
        stats.append(row)
        print(json.dumps(row))
json.dump(stats, open(out + ".json", "w"), indent=1)
