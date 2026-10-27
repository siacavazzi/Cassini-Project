"""A mosaic movie's fade worked out in the page (steady-local.html: cassiniSteadyMath.fadeLight, resizeLinear,
applyLight, on the table obs_mosaic.fade_table serves) against the server's faded picture (rolling_webp fade=,
_faded's post step), on the server's own time-lapse picture (fade 0): the page's script runs in node on the
pictures' bytes, before any WebP. cv2's resize may round a sum in another order than the page (vector code, FMA),
so a value may be a level apart, on a handful of pixels in a million.

A synthetic pass in the style of test_rolling_fade.py: 4 places, 4 laps, tiles with feathered edges and texture.
Run: python web/test_fade_local.py"""
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
offs = [(-400, -400), (400, -400), (-400, 400), (400, 400)]
N = 16
fr = [(f"p{i}", f"N{1500000000 + i}_1", "CB2", 1000.0 + 30 * i, 600, 0, 0, 1e6) for i in range(N)]
u = {"key": ("JUPITER", "OBSF", "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": 1000 + 30 * N,
     "place": [i % 4 for i in range(N)], "kind": "mosaic_movie", "repeats": 4}
d = om.folder(u, cache)
TD = om._tiles(u, cache, {"blacks": {}, "white": 1, "gamma": 3})
os.makedirs(TD, exist_ok=True)
y, x = np.mgrid[0:1448, 0:1448]
for i, (_, fid, f, t, *_r) in enumerate(fr):
    r = np.random.default_rng(i)
    c = (1448 - 1024) // 2
    edge = np.minimum.reduce([x - c, y - c, c + 1024 - x, c + 1024 - y]).astype(np.float32)
    alpha = np.clip(edge / 60, 0, 1) * 255                     # feathered over 60 px
    grey = 120 + 60 * np.sin(x / (40 + 7 * i)) * np.cos(y / 55) + r.normal(0, 4, x.shape)
    im = np.dstack([np.clip(grey, 0, 255)] * 3 + [alpha]).astype(np.uint8)
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": fid, "filter": f, "t": t, "offset": list(map(float, offs[i % 4])), "box": [-724, -724, 1448, 1448]},
              open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": {"blacks": {}, "white": 1, "gamma": 3}, "angle": 0, "footprint": [-1124, -1124, 1124, 1124],
           "fixed": True, "view": [2248, 2248], "k": 2048 / 2248, "colour": None, "grey": "CB2", "whole": False},
          open(d + "/" + om.PLAN_FILE, "w"))
om.unit_of = lambda fid: (u, [q[1] for q in fr].index(fid))
om.tiles_ahead = lambda *a, **k: None
om.tile = lambda u_, j, c, s=None: json.load(open(f"{TD}/{j}.json"))
om.rolling_ahead = lambda *a, **k: None

script = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = script[script.index("<script>") + 8:script.rindex("</script>")]


def png(data):
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))


def node_fade(table, cases):
    """The page's fade of each case (frame n, fade, persist, the time-lapse picture's bytes), run in node."""
    tmp = tempfile.mkdtemp()
    for q, (_, _, _, a) in enumerate(cases):
        a.tofile(f"{tmp}/{q}.bin")
    js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), t = " + json.dumps(table) + ";\n"
          "const alphas = j => Uint8Array.from(require('zlib').inflateSync(Buffer.from(t.parts[j].alpha, 'base64')));\n"
          "const C = " + json.dumps([c[:3] for c in cases]) + ";\n"
          "C.forEach(([n, fade, persist], q) => { const px = new Uint8ClampedArray(fs.readFileSync('" + tmp + "/' + q + '.bin'));"
          " const L = M.resizeLinear(M.fadeLight(t, n, fade, persist, alphas), t.w, t.h, t.W, t.H);"
          " fs.writeFileSync('" + tmp + "/' + q + '.out', M.applyLight(px, L)); });")
    with open(f"{tmp}/fade.js", "w") as fh:
        fh.write(js)
    subprocess.run(["node", f"{tmp}/fade.js"], check=True)
    return [np.fromfile(f"{tmp}/{q}.out", np.uint8).reshape(cases[q][3].shape) for q in range(len(cases))]


FADES = ((2, 30), (8, 0), (5, 65))
off = total = pictures = 0
for laps in (1, 2):
    base = {n: png(om.rolling_webp(fr[n][1], 1024, cache, laps, fmt="png")[0]) for n in range(N)}
    H, W = base[0].shape[:2]
    table = om.fade_table(fr[0][1], cache, laps, W, H)
    assert table["local"] and len(table["frames"]) == N, table.get("frames")
    assert len(json.dumps(table)) < 60_000, len(json.dumps(table))   # the alphas are flat but for their feather: zlib
    cases, wants = [], []
    for fade in FADES:
        for n in range(N):
            cases.append((n, fade[0], fade[1], base[n]))
            wants.append(png(om.rolling_webp(fr[n][1], 1024, cache, laps, fmt="png", fade=fade)[0]))
    for (n, f, p, _), got, want in zip(cases, node_fade(table, cases), wants):
        diff = np.abs(got.astype(int) - want.astype(int))
        if diff.max() > 1:
            w = np.argwhere(diff > 1)
            print("DIFF", laps, n, f, p, len(w), [(tuple(map(int, i)), int(got[tuple(i)]), int(want[tuple(i)])) for i in w[:4]])
        assert diff.max() <= 1, int(diff.max())
        off += int((diff > 0).sum())
        total += diff.size
        pictures += 1
    print(f"laps {laps}: {W}x{H}, table {len(json.dumps(table)) / 1e3:.0f} KB for {len(table['parts'])} tiles")
assert off <= total * 1e-5, (off, total)
print(f"fade: {pictures} faded pictures (fades {FADES}, laps 1 and 2): the page's equals the server's but for {off} "
      f"values of {total} a level apart")
print("ok")
