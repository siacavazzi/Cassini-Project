"""The Saturn look's ring_white worked out in the page (steady-local.html ringWhite) against obs_mosaic.ring_white, on
the same RGBA pictures: off the disk the picture back on the pass's own white, on it as drawn, eased at the limb. A
level apart where float32 rounding lands next to a half; never more.

Run: python web/test_ring_white.py"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

script = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = script[script.index("<script>") + 8:script.rindex("</script>")]
tmp = tempfile.mkdtemp()
r = np.random.default_rng(3)
CASES = [(320, 256, 1.25, 1.5, (150.0, 130.0, 90.0)), (400, 400, 1.25, 2.2, (210.5, 190.2, 140.0))]
wants = []
for q, (w, h, H, g, disk) in enumerate(CASES):
    px = np.dstack([r.integers(0, 256, (h, w, 3)), np.full((h, w), 255)]).astype(np.uint8)
    px.tofile(f"{tmp}/{q}.bin")
    wants.append(om.ring_white(px, {"headroom": H, "gamma": g, "shoulder": 0.8, "disk": disk}))
js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), C = " + json.dumps(CASES) + ";\n"
      "C.forEach(([w, h, H, g, disk], q) => { const px = new Uint8ClampedArray(fs.readFileSync('" + tmp + "/' + q + '.bin'));"
      " fs.writeFileSync('" + tmp + "/' + q + '.out', M.ringWhite(px, w, h, g, 0.8, disk)); });")
js = js.replace("M.ringWhite(px, w, h, g, 0.8, disk)", "M.ringWhite(px, w, H, g, 0.8, [disk[0], disk[1], disk[2] * " + str(om.RING_DISK) + "])")
with open(f"{tmp}/t.js", "w") as fh:
    fh.write(js)
subprocess.run(["node", f"{tmp}/t.js"], check=True)
off = total = 0
for q, ((w, h, *_), want) in enumerate(zip(CASES, wants)):
    got = np.fromfile(f"{tmp}/{q}.out", np.uint8).reshape(h, w, 4)
    d = np.abs(got.astype(int) - want.astype(int))
    assert d.max() <= 1, (q, int(d.max()))
    off += int((d > 0).sum())
    total += d.size
    assert (got != np.fromfile(f"{tmp}/{q}.bin", np.uint8).reshape(h, w, 4)).any()   # (it did change the rings)
print(f"ringWhite equals ring_white but for {off} values of {total} a level apart ({off / total:.1e})")
assert off <= total * 2e-3, off
print("ok")
