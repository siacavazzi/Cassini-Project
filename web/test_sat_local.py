"""The page's colour mix with saturation excess (steady-local.html mix / fillClipped, each plane's kept .sat.webp) gives
colour_picture's picture with sat: a band the camera saturated, drawn white, floored at the light it saturated on.
Synthetic planes, as web/test_clipped_colour.py's Rhea-like case (154RH MUTUALEVE002's lime-green Rhea).
Run: python web/test_sat_local.py"""
import os
import sys
import json
import subprocess
import tempfile
import atexit
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

root = tempfile.mkdtemp(prefix="test_sat_local_")
atexit.register(shutil.rmtree, root, True)

u = {"key": ("SATURN", "TEST", "W", 0)}
p = {"display_scale": {"gamma": 1.5}}
FILTERS = ["RED", "GRN", "BL1"]
gam = 1.5
H = W = 200
ramp = np.tile(np.linspace(0.25, 1.0, W, dtype=np.float32), (H, 1))
enc = lambda v: np.clip(np.power(np.clip(v, 0, 1), 1 / gam) * 255 + 0.5, 0, 255)
dec = lambda v: np.power(v.astype(np.float32) / 255, gam)
r, g, b = enc(ramp), enc(0.95 * ramp), enc(0.85 * ramp)
sat = ramp > 0.8
level = np.where(sat, enc(0.95 * ramp), 0).astype(np.uint8)
g = np.where(sat, 255.0, g)
g = np.round(cv2.GaussianBlur(g.astype(np.float32), (0, 0), 0.7))
planes = [np.dstack([v.astype(np.uint8)] * 3 + [np.full((H, W), 255, np.uint8)]) for v in (r, g, b)]
# the excess as kept beside a movie frame: in 1/255 steps (_place_sat)
ex = np.where(level > 0, np.maximum(dec(g) - dec(level), 0), 0).astype(np.float32)
ex = (np.clip(ex * 255 + 0.5, 0, 255).astype(np.uint8).astype(np.float32) / 255).astype(np.float32)

mix = calibration.color_mix("W", FILTERS, "SATURN", None, obs="TEST")
c = {"filters": FILTERS, "mix": None if mix is None else np.asarray(mix, float).tolist(), "gamma": gam,
     "shoulder": calibration.SHOULDER, "clip": om._clip_fill()}
server = om.colour_picture(u, p, FILTERS, planes, sat=[None, ex, None])
plain = om.colour_picture(u, p, FILTERS, planes)

page = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = page[page.index("<script>") + 8:page.index("</script>")]
for q, pl in enumerate(planes):
    pl.tofile(f"{root}/{q}.bin")
ex.tofile(f"{root}/ex.bin")
js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), c = " + json.dumps(c) + ";\n"
      f"const P = [0, 1, 2].map(q => new Uint8ClampedArray(fs.readFileSync('{root}/' + q + '.bin')));\n"
      f"const e = new Float32Array(fs.readFileSync('{root}/ex.bin').buffer.slice(0));\n"
      f"fs.writeFileSync('{root}/with.out', M.mix(P, c, {W}, [null, e, null]));\n"
      f"fs.writeFileSync('{root}/without.out', M.mix(P, c, {W}));\n")
open(f"{root}/t.js", "w").write(js)
subprocess.run(["node", f"{root}/t.js"], check=True)
withs = np.fromfile(f"{root}/with.out", np.uint8).reshape(H, W, 4)
without = np.fromfile(f"{root}/without.out", np.uint8).reshape(H, W, 4)
for name, a, b_ in (("with excess", withs, server), ("without", without, plain)):
    d = np.abs(a.astype(int) - b_.astype(int))
    assert d.max() <= 1, (name, int(d.max()), np.argwhere(d > 1)[:4].tolist())
    print(f"{name}: the page's mix equals colour_picture's but for {int((d > 0).sum())} values a level apart")
inside = withs[100, 170:195, :3].astype(int)
assert (inside[:, 1] <= inside[:, 0] + 1).all(), inside[::5]
assert (without[100, 170:195, 1].astype(int) > without[100, 170:195, 0].astype(int) + 1).any()
print("the page floors a saturated band at the light it saturated on (%s; without its map %s); ok" % (inside[10], without[100, 180, :3]))

# a gain over 1 on the set (exposure normalization brightening the frame): the planes gained (_shade's table, the
# page's M.lut), their white staying white, the light the band saturated on scaled by the gain (_sat_excess); the
# page works its excess out from the kept one at gain 1 (M.gainedExcess) and its mix equals colour_picture's
G = 1.4
gained = [om._shade(pl, {"gain": G, "gamma": gam}) for pl in planes]
ex_g = np.where(level > 0, np.maximum(dec(gained[1][..., 0]) - dec(level) * np.float32(G), 0), 0).astype(np.float32)
ex_g = (np.clip(ex_g * 255 + 0.5, 0, 255).astype(np.uint8).astype(np.float32) / 255).astype(np.float32)
server_g = om.colour_picture(u, p, FILTERS, gained, sat=[None, ex_g, None])
q1 = np.clip(ex * 255 + 0.5, 0, 255).astype(np.uint8)
np.dstack([q1, q1, q1, np.full_like(q1, 255)]).tofile(f"{root}/sd.bin")
for q, pl in enumerate(gained):
    pl.tofile(f"{root}/g{q}.bin")
js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), c = " + json.dumps(c) + ";\n"
      f"const P = [0, 1, 2].map(q => new Uint8ClampedArray(fs.readFileSync('{root}/g' + q + '.bin')));\n"
      f"const D = new Uint8ClampedArray(fs.readFileSync('{root}/1.bin')), sd = new Uint8ClampedArray(fs.readFileSync('{root}/sd.bin'));\n"
      f"const e = M.gainedExcess(sd, D, M.lut({G}, {gam}), {G}, {gam});\n"
      f"fs.writeFileSync('{root}/ge.bin', Buffer.from(e.buffer));\n"
      f"fs.writeFileSync('{root}/gained.out', M.mix(P, c, {W}, [null, e, null]));\n")
open(f"{root}/g.js", "w").write(js)
subprocess.run(["node", f"{root}/g.js"], check=True)
ge = np.fromfile(f"{root}/ge.bin", np.float32).reshape(H, W)
de = np.abs(ge - ex_g)
assert de.max() <= 2.5 / 255, (float(de.max()) * 255, np.argwhere(de > 2.5 / 255)[:4].tolist())
out_g = np.fromfile(f"{root}/gained.out", np.uint8).reshape(H, W, 4)
d = np.abs(out_g.astype(int) - server_g.astype(int))
assert d.max() <= 1, (int(d.max()), np.argwhere(d > 1)[:4].tolist())
print(f"gain {G}: the page's excess is the server's within {de.max() * 255:.1f}/255, and its mix colour_picture's but for "
      f"{int((d > 0).sum())} values a level apart; ok")
