"""Synthetic check of placed tiles (pictures program phase 3: obs_mosaic's luminance base): a colour pass whose last
pointing has only its red frame shows that pointing in gray instead of leaving it out, so the mosaic never shrinks
when its colour begins; a pass whose colour filters reach every pointing draws exactly the colour picture it drew
before; a gray pass never changes filter part way through; the tile map names the gray base's frames; and a scan that
steps one filter a pointing is a mosaic, not a movie. Run: python web/test_placed_tiles.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

SCALE = {"blacks": {}, "white": 1, "gamma": 3}
OFFS = [(-380, -380), (380, -380), (-380, 380), (380, 380)]   # a 2 x 2 pass, the tiles overlapping a little
LEVEL = {"RED": 150, "GRN": 120, "BL1": 90, "CB3": 140, "MT1": 70}


def make_pass(name, seq, colour, grey, gains=None):
    """A synthetic pass: seq = [(filter, pointing)] in time order; tiles written to the cache as tile() would."""
    cache = tempfile.mkdtemp()
    fr = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 20 * i, 600, -OFFS[q][0], -OFFS[q][1], 1e6) for i, (f, q) in enumerate(seq)]
    u = {"key": ("JUPITER", name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": fr[-1][3]}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, (f, q) in enumerate(seq):
        im = np.zeros((1024, 1024, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = LEVEL[f]
        Image.fromarray(im).save(f"{td}/{i}.png")
        t = {"n": i, "id": fr[i][1], "filter": f, "t": fr[i][3], "offset": list(map(float, OFFS[q])), "box": [-512, -512, 1024, 1024]}
        t["outline"] = [[OFFS[q][0] + x, OFFS[q][1] + y] for x, y in ((-512, -512), (512, -512), (512, 512), (-512, 512))]
        json.dump(t, open(f"{td}/{i}.json", "w"))
    filters = [grey] + sorted({f for f, _ in seq} - {grey})
    plan = {"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-900, -900, 900, 900], "fixed": True,
            "view": [1800, 1800], "k": 1024 / 1800, "colour": colour, "grey": grey, "whole": False,
            "luminance": {"filters": filters, "gains": gains or {}}}
    json.dump(plan, open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
    return u, cache


def at(im, q):
    """The picture's RGBA at pointing q's middle."""
    a = np.asarray(im)
    h, w = a.shape[:2]
    return a[int((OFFS[q][1] + 900) / 1800 * h), int((OFFS[q][0] + 900) / 1800 * w)]


# 1. colour pass: pointings 0-2 in RED, GRN, BL1, pointing 3 only in RED
seq = [(f, q) for q in range(3) for f in ("RED", "GRN", "BL1")] + [("RED", 3)]
u, cache = make_pass("COLOR", seq, ["RED", "GRN", "BL1"], "RED")
cover = []
for n in range(len(seq)):
    made = om.layout(u, n, cache)
    im, rep = om.so_far(u, n, cache, made)
    cover.append(int((np.asarray(im)[..., 3] > 0).sum()))
print("covered pixels tile by tile:", cover)
assert all(b >= a for a, b in zip(cover, cover[1:])), "the mosaic shrank"
assert rep["luminance"] and rep["filter_names"] == ["RED", "GRN", "BL1"]
last = at(im, 3)
first = at(im, 0)
assert first[3] == 255 and not (first[0] == first[1] == first[2]), f"pointing 0 should show in colour: {first}"
# the gray base, matched to the colour it borders (match_grey): these tiles are flat, so the gray-only pointing
# comes out the colour's own brightness and hue, with no step at the join
assert last[3] == 255 and np.abs(last[:3].astype(int) - first[:3].astype(int)).max() <= 10, f"pointing 3 should match: {last} vs {first}"
# unmatched (too little lit picture to measure) it stays plain gray
g = np.zeros((64, 64, 4), np.uint8); g[...] = 100; g[..., 3] = 255
c = np.zeros((64, 64, 4), np.uint8); c[:, :4] = (150, 100, 90, 255)
plain = om.over_grey(c, g, 0.5, 3)
assert tuple(plain[32, 60, :3]) == (100, 100, 100)
# before: the colour picture alone left pointing 3 out
alone = om.colour_picture(u, om.plan(u, cache), ["RED", "GRN", "BL1"],
                          [om.filter_mosaic(u, om.plan(u, cache), f, made[1], made[2], cache) for f in ("RED", "GRN", "BL1")])
assert at(Image.fromarray(alone), 3)[3] == 0
print("red-only pointing drawn in gray; colour pointings in colour")

# the moment colour begins (tile 2: the first BL1) the picture covers what the gray did at tile 1
assert cover[2] >= cover[1]

# a pass taking each filter across every pointing in turn (RED x4, GRN x4, BL1 x4): drawn as the colour picture alone,
# the four gray pointings shrank to one the moment the first BL1 came; on the gray base they stay
seq2 = [(f, q) for f in ("RED", "GRN", "BL1") for q in range(4)]
u2, cache2 = make_pass("BYFILTER", seq2, ["RED", "GRN", "BL1"], "RED")
cover2 = [int((np.asarray(om.so_far(u2, n, cache2)[0])[..., 3] > 0).sum()) for n in range(len(seq2))]
print("filter by filter:", cover2)
assert all(b >= a for a, b in zip(cover2, cover2[1:])) and cover2[8] == cover2[7]

# tile map: the gray-only pointing is named by its luminance frame, the colour ones are sets
om.unit_of = lambda fid: (u, int(fid[1:11]) - 1500000000)
m = om.tile_map(u["frames"][-1][1], cache)
assert m["layers"] == {"color": ["RED", "GRN", "BL1"], "luminance": ["RED"]}, m["layers"]
assert [q["set"] for q in m["pointings"]] == [True, True, True, False], [q["set"] for q in m["pointings"]]
assert m["pointings"][3]["ids"] == {"RED": u["frames"][-1][1]} and m["pointings"][3]["luminance"] == {}
assert os.path.exists(os.path.join(om.folder(u, cache), om.MAPS_DIR, om.layout(u, len(seq) - 1, cache)[5] + ".json"))
print("tile map: sets", [q["set"] for q in m["pointings"]])

# 2. every pointing in colour: the picture is the colour picture, byte for byte, with no gray base
seq = [(f, q) for q in range(4) for f in ("RED", "GRN", "BL1")]
u, cache = make_pass("FULL", seq, ["RED", "GRN", "BL1"], "RED")
made = om.layout(u, len(seq) - 1, cache)
im, rep = om.so_far(u, len(seq) - 1, cache, made)
p = om.plan(u, cache)
alone = om.colour_picture(u, p, ["RED", "GRN", "BL1"], [om.filter_mosaic(u, p, f, made[1], made[2], cache) for f in ("RED", "GRN", "BL1")])
ref = Image.fromarray(alone, "RGBA")
s = min(om.OUT, om.CANVAS) / max(ref.size)
ref = ref.resize((max(1, round(ref.width * s)), max(1, round(ref.height * s))), Image.LANCZOS)
assert not rep["luminance"] and np.array_equal(np.asarray(im), np.asarray(ref))
assert "_L" not in made[5]
print("full colour pass unchanged")

# 3. gray pass whose grey filter (CB3) is not its first: MT1 at a place CB3 later takes is not drawn, MT1 where CB3
# never goes fills in at CB3's level (gain), and the filter drawn never changes
seq = [("MT1", 0), ("CB3", 0), ("CB3", 1), ("MT1", 1), ("CB3", 2), ("MT1", 3)]
u, cache = make_pass("GRAY", seq, None, "CB3", gains={"MT1": 2.0})
assert om.layout(u, 0, cache) is None, "the gray must not start in MT1 where CB3 comes later"
useds = [om.layout(u, n, cache)[4] for n in range(1, len(seq))]
assert all(x == ["CB3"] for x in useds), useds
im, rep = om.so_far(u, len(seq) - 1, cache)
v3, v0 = at(im, 3), at(im, 0)
assert v3[3] == 255 and v0[3] == 255, (v3, v0)
lin = lambda v: (v / 255) ** 3
print("MT1 filled in at", v3[0], "next to CB3 at", v0[0], f"(MT1 tile {LEVEL['MT1']}, gain 2 on linear)")
# the gain itself (before compose's seam matching pulls overlapping tiles together)
part = np.full((4, 4, 4), LEVEL["MT1"], np.uint8)
shaded = om._shade(part, {"gain": 2.0, "gamma": 3})
assert abs(lin(shaded[0, 0, 0]) - 2 * lin(LEVEL["MT1"])) < 0.003 and shaded[0, 0, 3] == LEVEL["MT1"]
assert om._shade(part, {}) is part
assert om.lum_frames(u, om.plan(u, cache)) == frozenset({1, 2, 4, 5})
print("gray pass keeps CB3, MT1 only where CB3 never goes")

# 3b. before the grey filter's first tile, the gray is named by the base's filter most taken so far, ties going to the
# filter taken first: the same in every process (not set order, which hash randomization changes per process)
seq = [("MT1", 1), ("CB2", 2), ("CB3", 0)]
LEVEL["CB2"] = 110
u, cache = make_pass("TIE", seq, None, "CB3")
assert om.layout(u, 1, cache)[4] == ["MT1"], om.layout(u, 1, cache)[4]
seq = [("CB2", 2), ("MT1", 1), ("CB3", 0)]
u, cache = make_pass("TIE2", seq, None, "CB3")
assert om.layout(u, 1, cache)[4] == ["CB2"]
print("ties go to the filter taken first")

# 4. a scan stepping one filter a pointing is a mosaic; a stare cycling filters in one place is a movie
scan = {"key": ("SATURN", "SCAN", "N", 0), "z": 1e6,
        "frames": [("p", f"N{i}", f, 1000.0 + i, 600, 400.0 * i, 0.0, 1e6) for i, f in enumerate(["MT1", "CB2", "MT2", "CB3", "MT3"])]}
scan["taken"] = [(fr[2], fr[5], fr[6], fr[7]) for fr in scan["frames"]]
om._judge(scan)
stare = {"key": ("SATURN", "STARE", "N", 0), "z": 1e6,
         "frames": [("p", f"N{i}", f, 1000.0 + i, 600, 3.0 * i, 0.0, 1e6) for i, f in enumerate(["MT1", "CB2", "MT2", "CB3", "MT3"])]}
stare["taken"] = [(fr[2], fr[5], fr[6], fr[7]) for fr in stare["frames"]]
om._judge(stare)
print("scan:", scan["kind"], scan["jump_frac"], "· stare:", stare["kind"], stare["jump_frac"])
assert scan["mosaic"] and scan["kind"] == "mosaic" and stare["movie"]
print("ok")
