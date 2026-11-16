"""tossup_sheet.py MAIN_CACHE FIX_CACHE NAME OUT_PREFIX: a toss-up movie pass's mosaic view at a few frames, as a
server shows it today on a cache main built (drawn on request where the build's picture is not the one asked for) and
as the fixed build pre-made it; a sheet (today | with the fix | difference x8) and the numbers. Both caches are read
through clones the caller made (a request writes into its cache)."""
import io, json, os, sys
wt = os.environ["WT"]; sys.path.insert(0, os.path.join(wt, "web", "frames"))
import numpy as np
from PIL import Image, ImageDraw
import prebuild, calibration, obs_mosaic
main, fix, name, out = sys.argv[1:5]
u = next(u for u in prebuild.all_passes() if "_".join(map(str, u["key"])) == name)
n = len(u["frames"])
rows, stats = [], []
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    # frames with a mosaic to show in both (not one with nothing above black yet), four spread over the pass
    shown = []
    for j in range(n):
        made = obs_mosaic.layout(u, j, fix)
        if made and not obs_mosaic.is_blank(obs_mosaic._mosaic_path(u, made, 1024, fix)):
            shown.append(j)
    picks = sorted({shown[min(len(shown) - 1, round((len(shown) - 1) * q))] for q in (0.2, 0.5, 0.75, 1.0)}) if shown else []
    for j in picks:
        pair = []
        for cache in (main, fix):
            made = obs_mosaic.layout(u, j, cache)
            path = obs_mosaic._mosaic_path(u, made, 1024, cache) if made else None
            there = bool(path and os.path.exists(path))
            got = obs_mosaic._mosaic_at(u, j, 1024, cache) if made else None
            im = Image.open(io.BytesIO(got[0])).convert("RGB") if got else Image.new("RGB", (64, 64))
            pair.append((im, there, os.path.basename(path) if path else "-"))
        a, b = np.asarray(pair[0][0]).astype(int), np.asarray(pair[1][0]).astype(int)
        same = a.shape == b.shape
        d = np.abs(a - b) if same else None
        stats.append({"frame": j, "id": u["frames"][j][1], "today_prebuilt": pair[0][1], "fix_prebuilt": pair[1][1],
                      "today": pair[0][2], "fix": pair[1][2], "size": list(a.shape[:2]),
                      "pixels_differing": int((d.max(axis=2) > 0).sum()) if same else None,
                      "over_8_levels": int((d.max(axis=2) > 8).sum()) if same else None,
                      "max_levels": int(d.max()) if same else None, "mean_abs": round(float(d.mean()), 3) if same else None})
        rows.append((j, pair, d))
S, Hh = 640, 400
sheet = Image.new("RGB", (3 * S + 40, len(rows) * (Hh + 34) + 10), (16, 16, 16))
draw = ImageDraw.Draw(sheet)
for r, (j, pair, d) in enumerate(rows):
    y = 10 + r * (Hh + 34)
    # the part of the picture that holds anything in either, a little round it, so the strip is not a sliver
    lit = np.asarray(pair[0][0]).max(axis=2) > 0
    if pair[1][0].size == pair[0][0].size:
        lit |= np.asarray(pair[1][0]).max(axis=2) > 0
    ys, xs = np.nonzero(lit)
    box = (max(0, xs.min() - 12), max(0, ys.min() - 12), min(lit.shape[1], xs.max() + 13), min(lit.shape[0], ys.max() + 13)) if len(ys) else None
    fit = lambda im: (lambda t: (t.thumbnail((S, Hh)), t)[1])(im.crop(box) if box else im.copy())
    for c, (im, there, nm) in enumerate(pair):
        sheet.paste(fit(im), (10 + c * (S + 10), y + 22))
        label = (f"frame {j + 1} of {n}: today, " + ("pre-built" if there else "drawn on request")) if c == 0 else \
            ("with the fix, " + ("pre-built" if there else "NOT pre-built"))
        draw.text((10 + c * (S + 10), y + 4), label, fill=(230, 230, 230))
    if d is not None:
        sheet.paste(fit(Image.fromarray(np.clip(d * 8, 0, 255).astype(np.uint8))), (10 + 2 * (S + 10), y + 22))
        draw.text((10 + 2 * (S + 10), y + 4), "difference x8", fill=(230, 230, 230))
sheet.save(out + ".png")
# and close up: for each frame the 240 x 150 px window where the two differ most, three times enlarged (nearest pixel),
# today above, with the fix below, so where the tiles meet can be judged by eye
Z, zw, zh = 3, 240, 150
zoom = Image.new("RGB", (len(rows) * (zw * Z + 10) + 10, 2 * (zh * Z + 26) + 10), (16, 16, 16))
zdraw = ImageDraw.Draw(zoom)
for r, (j, pair, d) in enumerate(rows):
    if d is None:
        continue
    e = d.max(axis=2).astype(np.float64)
    c = np.cumsum(np.cumsum(np.pad(e, ((1, 0), (1, 0))), axis=0), axis=1)
    hh, ww = min(zh, e.shape[0]), min(zw, e.shape[1])
    tot = c[hh:, ww:] - c[:-hh, ww:] - c[hh:, :-ww] + c[:-hh, :-ww]
    y0, x0 = np.unravel_index(int(np.argmax(tot)), tot.shape)
    for c_, (im, there, nm) in enumerate(pair):
        crop = im.crop((x0, y0, x0 + ww, y0 + hh)).resize((ww * Z, hh * Z), Image.NEAREST)
        x, y = 10 + r * (zw * Z + 10), 10 + c_ * (zh * Z + 26)
        zoom.paste(crop, (x, y + 18))
        zdraw.text((x, y + 2), f"frame {j + 1}: " + ("today" if c_ == 0 else "with the fix") + f", x{Z} at ({x0}, {y0})",
                   fill=(230, 230, 230))
zoom.save(out + "-zoom.png")
json.dump(stats, open(out + ".json", "w"), indent=1)
for s in stats:
    print(s)
