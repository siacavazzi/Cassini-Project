"""Partial frames (fix plan group D, 2026-10-29): a frame that came down with most of its lines lost in downlink
(obs_mosaic.partial, the tile's "lost") is held rather than shown in movies and mosaics, and a small body's pass is
not drawn with the body clipped white (pass_scale's disk white).
- a mosaic movie (rolling_layout) keeps a place's whole copy up over a newer partial one, and shows a partial copy
  only where its place has nothing else, drawn under the rest
- a mosaic (filter_mosaic, composed whole and grown a tile at a time) draws a partial tile under its other tiles: it
  shows only where nothing else covers
- pass_scale: a body a few per cent of the frame (Jupiter in a WAC frame) is no longer far above white; a body that
  fills the frames keeps the scale it had
The movies' hold (movie_frame, held_of) and its page port are checked in web/test_steady_local.py.
Run: python web/test_partial_frames.py"""
import os, sys, json, tempfile, io  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import stacking  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
SCALE = {"blacks": {}, "white": 1, "gamma": 3}

# ---- a mosaic movie: 4 places, 3 laps; lap 3's copy of place 1 (frame 9) came down partial, and so did the only copy
# so far of place 2 at frame 2 (lap 1)
offs = [(-400, -400), (400, -400), (-400, 400), (400, 400)]
fr = [(f"p{i}", f"N{1500000000 + i}_1", "CB2", 1000.0 + 30 * i, 600, 0, 0, 1e6) for i in range(12)]
u = {"key": ("JUPITER", "OBSP", "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": 1400,
     "place": [i % 4 for i in range(12)], "kind": "mosaic_movie"}
TD = om._tiles(u, cache, SCALE)
os.makedirs(TD, exist_ok=True)
PARTIAL = {2, 9}
for i, (_, fid, f, t, *_r) in enumerate(fr):
    im = np.zeros((1448, 1448, 4), np.uint8)
    c = (1448 - 1024) // 2
    im[c:c + 1024, c:c + 1024, 3] = 255
    im[c:c + 1024, c:c + 1024, :3] = 60 + 60 * (i // 4)
    if i in PARTIAL:
        im[c:c + 800, c:c + 1024, 3] = 0   # its last 800 lines never came down (north up: the top)
    Image.fromarray(im).save(f"{TD}/{i}.png")
    j = {"n": i, "id": fid, "filter": f, "t": t, "offset": list(map(float, offs[i % 4])), "box": [-724, -724, 1448, 1448]}
    if i in PARTIAL:
        j["lost"] = 0.78
    json.dump(j, open(f"{TD}/{i}.json", "w"))
d = om.folder(u, cache)
json.dump({"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-1124, -1124, 1124, 1124], "fixed": True,
           "view": [2248, 2248], "k": 2048 / 2248, "colour": None, "grey": "CB2", "whole": False}, open(d + "/" + om.PLAN_FILE, "w"))
om.unit_of = lambda fid: (u, [x[1] for x in fr].index(fid))
om.tiles_ahead = lambda *a, **k: None
om.tile = lambda u_, j, c, s: json.load(open(f"{om._tiles(u_, c, s)}/{j}.json"))

assert om.partial(json.load(open(f"{TD}/9.json"))) and not om.partial(json.load(open(f"{TD}/5.json")))
p, tiles, *_ = om.rolling_layout(u, 9, cache)
ns = [t["n"] for t in tiles]
assert 5 in ns and 9 not in ns, ns              # place 1: lap 2's whole copy held over lap 3's partial one
p, tiles, *_ = om.rolling_layout(u, 3, cache)
ns = [t["n"] for t in tiles]
assert ns[0] == 2 and sorted(ns) == [0, 1, 2, 3], ns   # place 2's only copy is partial: drawn, first (under)
p, tiles, *_ = om.rolling_layout(u, 7, cache)
assert 2 not in [t["n"] for t in tiles], tiles   # ... until a whole copy of it arrives (frame 6)


def level(n):
    data, rep = om.rolling_webp(fr[n][1], 512, cache, 1)
    im = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")).astype(int)
    return [float(im[a:b, c:e, 0].mean()) for a, b, c, e in ((60, 120, 60, 120), (60, 120, -120, -60), (-120, -60, 60, 120))]


at8, at9, at10 = level(8), level(9), level(10)
# place 1 (top right) at frame 9 is lap 2's copy, as at frame 8; place 2 at frame 10 is lap 3's whole copy
assert abs(at9[1] - at8[1]) < 1 and at9 == at8, (at8, at9)
assert at10[2] > at9[2] + 20, (at9, at10)
top_right = at9[1]
print(f"mosaic movie: a newer partial copy leaves the whole one up (place 1 at {top_right:.0f}, as at frame 8); "
      "a place with only a partial copy shows it, under the rest")

# ---- a mosaic of one filter: a partial tile over a whole one's place is drawn under it, both composed whole (few
# tiles) and grown a tile at a time (more than GROW_FROM)
for count in (4, om.GROW_FROM + 3):
    side = int(np.ceil(np.sqrt(count)))
    fr2 = [(f"m{i}", f"N{1510000000 + 100 * count + i}_1", "CL1", 1000.0 + 10 * i, 600, 0, 0, 1e6) for i in range(count + 1)]
    v = {"key": ("MIMAS", f"OBSM{count}", "N", 0), "frames": fr2, "z": 1e6, "movie": False, "mosaic": True, "last": 2000}
    TV = om._tiles(v, cache, SCALE)
    os.makedirs(TV, exist_ok=True)
    places = [((i % side) * 900.0, (i // side) * 900.0) for i in range(count)] + [(-450.0, 0.0)]   # the last: half over tile 0
    for i, (_, fid, f, t, *_r) in enumerate(fr2):
        im = np.zeros((1024, 1024, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = 250 if i == count else 90
        lost = i == count
        if lost:
            im[:600, :, 3] = 0
        Image.fromarray(im).save(f"{TV}/{i}.png")
        j = {"n": i, "id": fid, "filter": f, "t": t, "offset": list(places[i]), "box": [-512, -512, 1024, 1024]}
        if lost:
            j["lost"] = 0.6
        json.dump(j, open(f"{TV}/{i}.json", "w"))
    tl = [json.load(open(f"{TV}/{i}.json")) for i in range(count + 1)]
    x0 = -450 - 512
    x1 = (side - 1) * 900 + 512
    y1 = ((count - 1) // side) * 900 + 512
    rect = (x0, -512, x1 - x0, y1 + 512)
    pv = {"display_scale": SCALE, "k": 0.25, "colour": None, "grey": "CL1"}
    with calibration.looking("balanced"):
        rgba = om.filter_mosaic(v, pv, "CL1", tl, rect, cache)
    rgba = np.asarray(rgba) if not isinstance(rgba, bytes) else np.asarray(Image.open(io.BytesIO(rgba)).convert("RGBA"))
    k = 0.25
    at = lambda x, y: rgba[int((y - rect[1]) * k), int((x - rect[0]) * k)].astype(int)
    over_whole, alone = at(100, 300), at(-800, 300)   # (the partial tile's lit part: y 88..512)
    # tile 0 (90) stays on top, a level or so off for the seams' gains; where nothing else is, the partial (250) shows
    assert over_whole[0] < 130 and over_whole[3] == 255, over_whole
    assert alone[0] > 200 and alone[3] == 255, alone
    print(f"mosaic of {count + 1} tiles ({'grown' if count > om.GROW_FROM else 'composed whole'}): the partial tile is under "
          f"the whole one ({over_whole[0]}) and shows where nothing else is ({alone[0]})")

# ---- pass_scale: Jupiter about 20 px across WAC frames of mostly sky

def frames_of(radius_px, where):
    """Frames of a pass with the body's disk radius_px (full resolution) at where (x, y shift that centres it), and the
    stand-in load_hdr that gives their I/F: faint noisy sky, the disk lit with a limb-darkened face."""
    z = om.RADIUS["JUPITER"] / (radius_px * om.IFOV["W"])
    fr3 = [(f"j{i}", f"W{1520000000 + i}_1", "CB2", 1000.0 + 60 * i, 750, where[0], where[1], z) for i in range(12)]
    yy, xx = np.mgrid[:1024, :1024].astype(np.float32)
    cy, cx = 511.5 - where[1], 511.5 - where[0]
    rr = np.hypot(yy - cy, xx - cx) / radius_px
    face = np.where(rr < 1, 0.3 * np.sqrt(np.clip(1 - rr ** 2, 0, 1)) + 0.05, 0).astype(np.float32)

    def load_hdr(path, window=120, max_frames=8, valid=False):
        noise = np.random.default_rng(int(path[1:]))   # (the same frame, the same noise)
        sky = (0.002 + 0.0007 * noise.standard_normal((1024, 1024))).astype(np.float32)
        return None, sky + face, 1
    return fr3, load_hdr


real = stacking.load_hdr
with calibration.looking("balanced"):
    for radius, where, kind in ((10, (80.0, -60.0), "small"), (150, (380.0, 0.0), "medium"), (400, (0.0, 0.0), "filled")):
        fr3, stacking.load_hdr = frames_of(radius, where)
        w = {"key": ("JUPITER", f"OBSJ{radius}", "W", 0), "frames": fr3, "z": fr3[0][7], "movie": True}
        least = om.DISK_LEAST
        om.DISK_LEAST = 1 << 30   # no disk measured: the scale as it was
        old = om.pass_scale(fr3, w)
        om.DISK_LEAST = least
        # (the disk's white alone: an even face's floor black, _even_body, is web/test_even_body.py's)
        even_body, om._even_body = om._even_body, lambda by, on, inner, levels, base, blacks, white, *a: (blacks, white, 0.0)
        new = om.pass_scale(fr3, w)
        om._even_body = even_body
        top = 0.35 - old["blacks"]["CB2"]   # the disk's brightest (centre of the face)
        if kind == "small":
            assert top / old["white"] > 2 and top / new["white"] < 1.3, (old["white"], new["white"], top)
            print(f"small body ({2 * radius} px): white {old['white']:.4f} -> {new['white']:.4f}; the disk's brightest at "
                  f"{top / old['white']:.1f}x white before (clipped), {top / new['white']:.2f}x now")
        elif kind == "medium":
            # (7% of the frame: its 99.9th percentile is already on the body; the disk's 99.5th sits a little higher)
            assert old["white"] <= new["white"] < 1.1 * old["white"], (old["white"], new["white"])
            print(f"medium body ({2 * radius} px, 7% of the frame): white {old['white']:.4f} -> {new['white']:.4f} "
                  f"({new['white'] / old['white'] - 1:+.1%})")
        else:
            assert new == old, (new, old)
            print(f"body filling the frames ({2 * radius} px): scale unchanged (white {new['white']:.4f})")
stacking.load_hdr = real
print("ok")
