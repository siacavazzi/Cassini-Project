"""Synthetic check of edge registration (obs_mosaic.edge_shift, panel_places on a clouded body): mosaics of a clouded
body whose clouds move between panels (they turn with it and drift on its winds) and whose pointings SPICE put up to
30 px off, each differently. Matching the clouds' detail would follow the clouds; edge registration measures the lit
edge against the dark (the limb, a ring's edge) and lines the pointings up across it:

- Titan, a 2x2 over its limb, clouds moving 25 px a panel: the pointings land within a pixel of the first (the limb
  curves enough in each overlap to say both ways).
- Saturn's limb along a strip of 4 panels (the limb nearly straight in each overlap), clouds moving 60 px a panel: the
  panels line up across the limb within a pixel, and along it are left as SPICE has them.
- Saturn's rings, edges of concentric ringlets and gaps: lined up across the edges.
- Clouds moving with no pointing error: nothing moves. Overlaps all on the disk (no edge): SPICE's places.
- Two filters (a limb's height differs with the filter) are never measured against each other; edges nearly parallel
  to one another say nothing along them, and a move adding up past EDGE_MAX is not believed.
- A pass of a moon still takes #169's detail registration (test_panel_register.py), and its files and names.
Run: python web/test_edge_register.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import cv2
from PIL import Image
import calibration as cal
import obs_mosaic as om

rng = np.random.default_rng(7)
T = 1024
CLOUDS = cv2.GaussianBlur(rng.random((4096, 4096)).astype(np.float32), (0, 0), 14)
CLOUDS = (CLOUDS - CLOUDS.mean()) / CLOUDS.std()
FINE = cv2.GaussianBlur(rng.random((4096, 4096)).astype(np.float32), (0, 0), 2.5)
FINE = (FINE - FINE.mean()) / FINE.std()


def clouds(x, y, drift):
    """Cloud detail at sky (x, y), the clouds moved drift (dx, dy) px."""
    xi = np.clip((x - drift[0] + 2048).astype(int), 0, 4095)
    yi = np.clip((y - drift[1] + 2048).astype(int), 0, 4095)
    return 22 * CLOUDS[yi, xi] + 10 * FINE[yi, xi]


def titan(x, y, drift):
    r = np.hypot(x, y)
    disk = 1 / (1 + np.exp((r - 640) / 4.0))        # a soft hazy limb at 640 px
    return 4 + disk * (170 + clouds(x, y, drift))


def saturn(x, y, drift):
    # the limb of a disk 9000 px across (nearly straight over a panel), its centre far below the strip
    r = np.hypot(x / 1.0, (y - 4050) / 0.9)
    disk = 1 / (1 + np.exp((r - 4500) / 2.5))
    bands = 25 * np.sin(r / 37.0)                    # zonal bands, turning with the body
    return 3 + disk * (160 + bands + clouds(x, y, drift))


def rings(x, y, drift):
    # ringlets and gaps, ellipses about a centre far off, dark between them, and clumps that move along them
    r = np.hypot(x, (y + 2200) / 0.35)
    lit = np.zeros_like(r)
    for a, b in ((5300, 5420), (5480, 5530), (5600, 5900), (5950, 6100), (6180, 6215), (6300, 6700)):
        lit = np.maximum(lit, 1 / (1 + np.exp((a - r) / 1.5)) * 1 / (1 + np.exp((r - b) / 1.5)))
    return 3 + lit * (140 + 1.2 * clouds(x, y, drift))


def run(body, scene, true, err, drift, name, filters=None):
    """Tiles of scene at the true places, their clouds moved drift[k], put by SPICE at true + err; returns
    (moves, report, reports)."""
    filters = filters or ["CB3"] * len(true)
    fr = [(f"p{i}", f"N{1500000000 + i}_1", filters[i], 1000.0 + 120 * i, 600, -true[i][0], -true[i][1], 1e6)
          for i in range(len(true))]
    u = {"key": (body, name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True,
         "last": 1000 + 120 * len(fr), "kind": "mosaic"}
    scale = {"blacks": {}, "white": 1, "gamma": 3}
    p = {"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-3000, -3000, 3000, 3000],
         "fixed": True, "view": [6000, 6000], "k": 2048 / 6000, "colour": None, "grey": "CB3", "whole": False,
         "luminance": None}
    reports = [{"n": i, "id": fr[i][1], "filter": filters[i], "t": fr[i][3],
                "offset": [true[i][0] + err[i][0], true[i][1] + err[i][1]], "box": [-T / 2, -T / 2, T, T]}
               for i in range(len(true))]
    om.tile = lambda u_, j, c, s=None: reports[j]
    cache = tempfile.mkdtemp()
    td = om._tiles(u, cache, scale)
    os.makedirs(td, exist_ok=True)
    yy, xx = np.mgrid[0:T, 0:T].astype(np.float32)
    for i in range(len(true)):
        x, y = xx + true[i][0] - T / 2, yy + true[i][1] - T / 2
        v = scene(x, y, drift[i]) + rng.normal(0, 1.5, (T, T))
        im = np.zeros((T, T, 4), np.uint8)
        im[..., :3] = np.clip(v, 0, 255).astype(np.uint8)[..., None]
        im[..., 3] = 255
        Image.fromarray(im).save(f"{td}/{i}.png")
    json.dump(p, open(os.path.join(om.folder(u, cache), om.PLAN_FILE), "w"))
    report = {}
    moved = om.panel_places(u, cache, p, reports, report=report)
    return u, cache, p, moved, report, reports


def left(err, moved, i):
    """Where tile i ends up off its true place, less where tile 0 does (the mosaic as a whole may sit off)."""
    m = moved.get(i, [0, 0])
    m0 = moved.get(0, [0, 0])
    return np.array([err[i][0] + m[0] - err[0][0] - m0[0], err[i][1] + m[1] - err[0][1] - m0[1]])


def show(label, err, moved, report):
    for i in range(len(err)):
        print(label, i, "SPICE off", err[i], "moved", moved.get(i, [0, 0]), "left", np.round(left(err, moved, i), 2),
              {j: (v if isinstance(v, str) else {k: v[k] for k in ("shift", "ncc", "normal") if k in v})
               for j, v in report.get(i, {}).get("matches", {}).items()})


# 1. Titan: a 2x2 over its limb's top left, clouds 25 px a panel
true = [(-560, -560), (-120, -560), (-560, -120), (-120, -120)]
err = [(0.0, 0.0), (14.0, -9.0), (-11.0, 17.0), (21.0, 12.0)]
drift = [(25.0 * i, 0.0) for i in range(4)]
u, cache, p, moved, report, reports = run("TITAN", titan, true, err, drift, "T2X2")
show("titan", err, moved, report)
for i in range(4):
    assert np.hypot(*left(err, moved, i)) < 1.0, (i, left(err, moved, i))
# kept with the pass, in its own file, and the layout names itself for it
assert os.path.exists(os.path.join(om.folder(u, cache), om.EDGE_FILE + om.PANEL_FILE))
assert not os.path.exists(os.path.join(om.folder(u, cache), om.PANEL_FILE))
again = om.panel_places(u, cache, p, reports[:2])
assert all(again[n] == moved[n] for n in again), (again, moved)
made = om.layout(u, 3, cache)
assert made[5].endswith(om.EDGE_TAG) and om.PANEL_TAG not in made[5], made[5]
with cal.stepping("panels"):
    plain = om.layout(u, 3, cache)
    assert om.panel_places(u, cache, p, reports) == {}
assert plain[5] == made[5][:-len(om.EDGE_TAG)], (plain[5], made[5])

# #169's detail measure on the same tiles follows the clouds, or is not believed: never the pointing
td = om._tiles(u, cache, p["display_scale"])
pics = [np.asarray(Image.open(f"{td}/{i}.png").convert("RGBA")) for i in range(4)]
old = om.panel_shift(reports[0], pics[0], reports[0]["offset"], reports[1], pics[1], reports[1]["offset"])
print("detail measure, tiles 0-1:", old)
assert old[0] is None or np.hypot(old[0][0] + err[1][0], old[0][1] + err[1][1]) > 3

# 2. Saturn's limb along a strip, clouds 60 px a panel; the limb is nearly straight in each overlap
true = [(-1200, 0), (-450, 0), (300, 0), (1050, 0)]
err = [(0.0, 0.0), (8.0, -22.0), (-15.0, 13.0), (5.0, 30.0)]
drift = [(60.0 * i, 0.0) for i in range(4)]
u, cache, p, moved, report, reports = run("SATURN", saturn, true, err, drift, "LIMB")
show("saturn", err, moved, report)
for i in range(1, 4):
    (j, m), = report[i]["matches"].items()
    n = np.array(m["normal"])
    assert abs(n[1]) > 0.95, n   # the limb's normal, nearly up and down
    # across the limb within a pixel of the panel before; along it as SPICE has it (moved only across it)
    assert abs(n @ (left(err, moved, i) - left(err, moved, j))) < 1.0, (i, j, left(err, moved, i), left(err, moved, j))
    assert abs(n[0] * moved[i][1] - n[1] * moved[i][0]) < 0.05, (i, moved[i], n)

# 3. Saturn's rings: ringlet edges and gaps, clumps moving along them
true = [(-400, -200), (350, -200), (-400, 300), (350, 300)]
err = [(0.0, 0.0), (-9.0, 11.0), (6.0, -14.0), (12.0, 7.0)]
drift = [(40.0 * i, 0.0) for i in range(4)]
u, cache, p, moved, report, reports = run("SATURN", rings, true, err, drift, "RINGS")
show("rings", err, moved, report)
for i in range(1, 4):
    # the ring edges run nearly across the panels here: lined up up and down within a pixel, left and right as SPICE
    l = left(err, moved, i)
    assert abs(l[1]) < 1.0 and abs(moved[i][0]) < 1.0, (i, l, moved[i])

# 4. clouds moving 60 px a panel, SPICE right: nothing moves
true = [(-1200, 0), (-450, 0), (300, 0)]
err = [(0.0, 0.0)] * 3
u, cache, p, moved, report, reports = run("SATURN", saturn, true, err, [(60.0 * i, 0.0) for i in range(3)], "STILL")
show("still", err, moved, report)
assert all(np.hypot(*v) < 0.6 for v in moved.values()), moved

# 5. overlaps all on the disk, no edge in them: SPICE's places
true = [(-300, 1600), (450, 1600), (-300, 2300)]
err = [(0.0, 0.0), (9.0, -6.0), (-7.0, 8.0)]
u, cache, p, moved, report, reports = run("SATURN", saturn, true, err, [(60.0 * i, 0.0) for i in range(3)], "DISK")
show("disk", err, moved, report)
assert moved == {}, moved
assert all(v == "no edge" for r in report.values() for v in r["matches"].values()), report

# 6. two filters whose limbs stand at different heights (UV haze over a methane band): never matched to each other
true = [(-1200, 0), (-450, 0), (300, 0), (1050, 0)]
err = [(0.0, 0.0), (8.0, -22.0), (-15.0, 13.0), (5.0, 30.0)]
u, cache, p, moved, report, reports = run("SATURN", saturn, true, err, [(60.0 * i, 0.0) for i in range(4)], "FILTERS",
                                          filters=["UV3", "MT3", "UV3", "MT3"])
show("filters", err, moved, report)
assert all(v == "other filter" or j % 2 == i % 2 for i, r in report.items() for j, v in r["matches"].items()), report
assert all(j % 2 == i % 2 for i, r in report.items() for j in r["matches"]), report

# 7. matches across edges nearly parallel to one another that disagree a little say nothing along them (Saturn's
# equatorial map moved a panel 580 px along its limb so), and a move adding up past EDGE_MAX is not believed
a, b = np.array([-0.0901, 0.9959]), np.array([-0.0105, 0.9999])
fit = om._combine([((0.0, 5.7), a / np.linalg.norm(a)), ((0.0, -12.0), b / np.linalg.norm(b))])
print("near-parallel:", fit)
assert fit is None or abs(fit[0]) < 3, fit
fit = om._combine([((0.0, 4.0), a / np.linalg.norm(a)), ((0.0, 5.0), b / np.linalg.norm(b))])
assert fit is not None and abs(fit[0]) < 1 and abs(fit[1] - 4.5) < 0.6, fit
assert om._combine([((0.0, 70.0), None)]) is None

# 8. a moon is not a clouded body: #169's measure, file and tag
assert not om.clouded({"key": ("RHEA", "X", "N", 0)}) and om.clouded({"key": ("TITAN", "X", "N", 0)})
print("edge registration: ok")
