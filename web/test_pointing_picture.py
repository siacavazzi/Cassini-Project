"""Synthetic check of opening a mosaic's pointing (pictures program phase 4, obs_mosaic.pointing_picture, the route
/frames/mosaic/<ID>/p/<n>.webp): an opened pointing matches its spot in the mosaic. A 2 x 2 color pass whose tiles are
textured and each exposed differently (so the mosaic's seam corrections matter), whose color is mixed (natural color),
and whose last place has only its red frame (drawn in the gray base): each pointing, opened and brought to the mosaic's
scale, is the mosaic's picture where that pointing is on top; one filter's channel is that filter's mosaic there; the
links before pointings were numbered (frame.webp?ids=) find the same pointing. Run: python web/test_pointing_picture.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

SCALE = {"blacks": {}, "white": 1, "gamma": 2.2}
OFFS = [(-380, -380), (380, -380), (-380, 380), (380, 380)]   # a 2 x 2 pass, the tiles overlapping
LEVEL = {"RED": 150, "GRN": 120, "BL1": 90}
EXPOSE = [0.82, 1.0, 1.17, 0.93]   # each place's frames a little brighter or darker: the seams the mosaic corrects
yy, xx = np.mgrid[0:1024, 0:1024].astype(np.float32)


def texture(q):
    """The same ground under every tile: a pattern fixed to the body (reference pixels), so overlaps agree."""
    gx, gy = xx - 512 + OFFS[q][0], yy - 512 + OFFS[q][1]
    return 0.75 + 0.2 * np.sin(gx / 37.0) * np.cos(gy / 53.0) + 0.05 * np.sin((gx + gy) / 11.0)


def make_pass(name, seq):
    cache = tempfile.mkdtemp()
    fr = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 20 * i, 600, -OFFS[q][0], -OFFS[q][1], 1e6) for i, (f, q) in enumerate(seq)]
    u = {"key": ("JUPITER", name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": fr[-1][3]}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, (f, q) in enumerate(seq):
        im = np.zeros((1024, 1024, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = np.clip(LEVEL[f] * EXPOSE[q] * texture(q), 0, 255).round().astype(np.uint8)[..., None]
        Image.fromarray(im).save(f"{td}/{i}.png")
        t = {"n": i, "id": fr[i][1], "filter": f, "t": fr[i][3], "offset": list(map(float, OFFS[q])), "box": [-512, -512, 1024, 1024]}
        t["outline"] = [[OFFS[q][0] + x, OFFS[q][1] + y] for x, y in ((-512, -512), (512, -512), (512, 512), (-512, 512))]
        json.dump(t, open(f"{td}/{i}.json", "w"))
    plan = {"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-900, -900, 900, 900], "fixed": True,
            "view": [1800, 1800], "k": 1024 / 1800, "colour": ["RED", "GRN", "BL1"], "grey": "RED", "whole": False,
            "luminance": {"filters": ["RED", "GRN", "BL1"], "gains": {}}}
    json.dump(plan, open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
    om.unit_of = lambda fid: (u, int(fid[1:11]) - 1500000000)
    return u, cache


def on_mosaic(rgba, at, p, rect):
    """An opened pointing (RGBA, at = (x, y, k) as _pointing gives) brought to the mosaic canvas's scale and place."""
    x, y, k = at
    s = p["k"] / k
    im = Image.fromarray(rgba).resize((round(rgba.shape[1] * s), round(rgba.shape[0] * s)), Image.LANCZOS)
    W, H = round(rect[2] * p["k"]), round(rect[3] * p["k"])
    out = np.zeros((H, W, 4), np.uint8)
    left, top = round((x - rect[0]) * p["k"]), round((y - rect[1]) * p["k"])
    a = np.asarray(im)
    x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + a.shape[1], W), min(top + a.shape[0], H)
    out[y0:y1, x0:x1] = a[y0 - top:y1 - top, x0 - left:x1 - left]
    return out


def top_of(q, rect, p, shape, later):
    """The mosaic canvas pixels where place q is the frame on top: inside it, away from its soft edge, and outside every
    later place (drawn over it)."""
    H, W = shape
    gy, gx = np.mgrid[0:H, 0:W]
    rx, ry = gx / p["k"] + rect[0], gy / p["k"] + rect[1]
    edge = 512 - 160   # reference pixels in from the tile's edge, past the compose's soft edge
    inside = lambda o, m: (np.abs(rx - o[0]) < m) & (np.abs(ry - o[1]) < m)
    mask = inside(OFFS[q], edge)
    for r in later:
        mask &= ~inside(OFFS[r], 512 + 40)
    return mask


# a color pass: places 0-2 in RED, GRN, BL1, place 3 only in RED (drawn in the gray base)
seq = [(f, q) for q in range(3) for f in ("RED", "GRN", "BL1")] + [("RED", 3)]
u, cache = make_pass("POINT", seq)
last = len(seq) - 1
made = om.layout(u, last, cache)
p, tiles, rect, count, used, name = made
mos, rep = om.so_far(u, last, cache, made, out=round(rect[2] * p["k"]))
mos = np.asarray(mos)
assert mos.shape[:2] == (round(rect[3] * p["k"]), round(rect[2] * p["k"])), mos.shape
mapped = om.tile_map(u["frames"][last][1], cache)
assert [q["set"] for q in mapped["pointings"]] == [True, True, True, False]
place = {q["n"]: next(OFFS.index(tuple(t["offset"])) for t in tiles if t["n"] == q["tiles"][0]) for q in mapped["pointings"]}
by_id = {t["id"]: t for t in tiles}
worst = 0.0
for q in mapped["pointings"]:
    data, info = om.pointing_picture(u["frames"][last][1], q["n"], cache, "full", "png")
    pic = np.asarray(Image.open(__import__("io").BytesIO(data)).convert("RGBA"))
    colour = info["color"]
    layers = [(by_id[q["ids"][f]], f) for f in used] if colour else [(by_id[list(q["ids"].values())[-1]], om.LUM)]
    tint = None if colour else om.grey_tint(om.colour_picture(u, p, used, [om.filter_mosaic(u, p, g, tiles, rect, cache, "RED") for g in used]),
                                            om.filter_mosaic(u, p, om.LUM, tiles, rect, cache), p["k"], SCALE["gamma"])
    rgba, at = om._pointing(u, p, tiles, rect, count, used, layers, cache, None, tint)
    assert np.array_equal(rgba, pic), "the route's picture is _pointing's"
    assert at[2] == 1.0 and max(pic.shape[:2]) == 1024, (at, pic.shape)   # the tiles' full size, not the mosaic's
    placed = on_mosaic(rgba, at, p, rect)
    mask = top_of(place[q["n"]], rect, p, mos.shape[:2], [place[r["n"]] for r in mapped["pointings"] if r["n"] > q["n"]])
    assert mask.sum() > 5000, mask.sum()
    diff = np.abs(placed[..., :3].astype(int) - mos[..., :3].astype(int))[mask]
    print(f"pointing {q['n']} ({'color' if colour else 'gray'}): mean difference {diff.mean():.2f} levels, 99th percentile "
          f"{np.percentile(diff, 99):.0f}, over {int(mask.sum())} px where it is on top")
    worst = max(worst, diff.mean())
    assert diff.mean() < 2.5 and np.percentile(diff, 99) <= 8, "the opened pointing must match its spot in the mosaic"
    if colour:
        # the color mix is applied: without it (the planes stacked as they are, as frame.webp drew it before) the
        # pointing does not match
        planes = [om._pointing(u, p, tiles, rect, count, used, layers, cache, c)[0] for c in range(3)]
        unmixed = np.dstack([pl[..., 0] for pl in planes] + [planes[0][..., 3]])
        before = np.abs(on_mosaic(unmixed, at, p, rect)[..., :3].astype(int) - mos[..., :3].astype(int))[mask]
        print(f"    the same frames unmixed (before): mean difference {before.mean():.2f} levels")
        assert before.mean() > diff.mean() + 3
        # one filter's channel: that filter's mosaic there
        fm = om.filter_mosaic(u, p, used[1], tiles, rect, cache, max(used, key=lambda f: count[f]))
        ch = on_mosaic(planes[1], at, p, rect)
        cd = np.abs(ch[..., 0].astype(int) - fm[..., 0].astype(int))[mask]
        assert cd.mean() < 2.5, cd.mean()
    else:
        # without the tint toward the colour it borders (plain gray, as frame.webp drew it before) it does not match
        plain = on_mosaic(om._pointing(u, p, tiles, rect, count, used, layers, cache)[0], at, p, rect)
        before = np.abs(plain[..., :3].astype(int) - mos[..., :3].astype(int))[mask]
        print(f"    the same frame untinted (before): mean difference {before.mean():.2f} levels")
        assert before.mean() > diff.mean() + 3
print(f"every pointing matches its spot (worst mean difference {worst:.2f} levels)")

# the links before pointings were numbered: frame.webp?ids= names the same pointing
q2 = mapped["pointings"][1]
assert om.pointing_of(mapped, list(q2["ids"].values()))["n"] == 2
assert om.pointing_of(mapped, [q2["ids"]["GRN"]])["n"] == 2
assert om.pointing_of(mapped, ["N1499999999_1"]) is None
assert om.pointing_picture(u["frames"][last][1], 9, cache) is None
print("ok")
