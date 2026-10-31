"""obs_mosaic.surface_pictures with the tiles it keeps as taken remembered (SURFACE_TAKEN), against the form it
replaced (copied here as it was at d0777e6): the same redrawn pictures and the same answer on the first call and on
every later one, as a pass's mosaic grows a tile at a time, read back from its file (a fresh process) or kept in the
pass's record (the frame server); after the first call, no kernels, sky fields or tile pictures for the tiles kept as
taken, and no other year's kernels loaded for the tiles across New Year. SPICE is made up: each frame sees a moon
turned by an angle that grows with its time from the pass's middle (test_sky_field's view), so the tiles near the
middle are redrawn and those far from it would be stretched too much. Run: python web/test_surface_taken.py"""
import calendar
import json
import math
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reproject as rp  # noqa: E402

R, D = 500.0, 100000.0   # the moon's radius and distance, km
SIDE = 192               # a tile's side, px


def view(turn):
    c = np.array([D, 0.0, 0.0])
    a = math.radians(turn)
    rot = np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1.0]])
    s = np.array([-1.0, 0.2, 0.1])
    return {"c": c, "ch": c / D, "north": np.array([0.0, 0.0, 1.0]), "east": np.cross([0.0, 0.0, 1.0], c / D),
            "rot": rot, "radii": np.array([R, R, R]), "sun": rot @ (s / np.linalg.norm(s))}


# ---------- the form replaced (d0777e6), with the module's own helpers ----------
def surface_before(u, cache, p, tiles):
    if not om.calibration.step("surface") or not tiles or om.clouded(u):
        return {}
    there = om._tiles(u, cache, p["display_scale"])
    out_dir = os.path.join(there, om.SURFACE_DIR)
    out, todo = {}, []
    for t in tiles:
        if "offset" not in t:
            continue
        path = os.path.join(out_dir, f"{t['n']}.png")
        if os.path.exists(path):
            out[t["n"]] = path
        elif os.path.exists(os.path.join(there, f"{t['n']}.png")):
            todo.append(t)
    if not todo:
        return out
    fr = u["frames"]
    mid = fr[len(fr) // 2]
    ets = om._ets([mid[1]] + [t["id"] for t in todo])
    if mid[1] not in ets:
        return out
    km_px = om.IFOV[u["key"][2]] * u["z"]
    with om._spice_lock:
        if not om._with_kernels(mid[3]):
            return out
        try:
            epoch = rp.sky_view(u["key"][0], ets[mid[1]])
        except Exception as e:
            print(f"no surface for {u['key'][0]}: {type(e).__name__}: {e}"[:200], flush=True)
            return out
        os.makedirs(out_dir, exist_ok=True)
        for t in todo:
            if t["id"] not in ets or not om._with_kernels(t["t"]):
                continue
            try:
                if time.gmtime(t["t"]).tm_year != time.gmtime(mid[3]).tm_year:
                    continue
                view_ = rp.sky_view(u["key"][0], ets[t["id"]])
            except Exception as e:
                print(f"no surface for {t['id']}: {type(e).__name__}: {e}"[:200], flush=True)
                continue
            src = os.path.join(there, f"{t['n']}.png")
            with om._lock:
                image = om._made_pictures.get(src)
            if image is None:
                image = np.asarray(Image.open(src).convert("RGBA"))
            h, w = image.shape[:2]
            gy, gx = np.mgrid[0:h + om.SURFACE_STEP:om.SURFACE_STEP, 0:w + om.SURFACE_STEP:om.SURFACE_STEP].astype(np.float64)
            x0, y0 = t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1]
            dx, dy, weight = rp.sky_field(epoch, view_, gx + x0, gy + y0, km_px)
            path = os.path.join(out_dir, f"{t['n']}.png")
            stretch = rp.field_stretch(dx, dy, weight, om.SURFACE_STEP)
            if stretch > om.SURFACE_STRETCH:
                pass   # (it printed "surface: tile n kept as taken")
                continue
            Image.fromarray(rp.warp_sky(image, dx, dy, weight, om.SURFACE_STEP)).save(path + ".part.png", compress_level=1)
            os.replace(path + ".part.png", path)
            out[t["n"]] = path
    return out


# ---------- made-up SPICE, counted ----------
calls = {"loads": 0, "year": None, "fields": 0, "ets": 0}
when = {}      # frame id -> et (here its time)
middle = [0.0]


def with_kernels(t):
    year = time.gmtime(t).tm_year
    if calls["year"] != year:
        calls["loads"] += 1
        calls["year"] = year
    return True


def ets(ids):
    calls["ets"] += 1
    return {i: when[i] for i in ids if i in when}


def sky_view(target, et):
    return view((et - middle[0]) / 30.0)   # a degree every 30 s from the pass's middle


_field = rp.sky_field


def sky_field(*a, **k):
    calls["fields"] += 1
    return _field(*a, **k)


om._with_kernels, om._ets, rp.sky_view, rp.sky_field = with_kernels, ets, sky_view, sky_field
om.print = lambda *a, **k: None


def make_pass(cache, start):
    """A 3x3 mosaic of the moon with 2 filters, a frame a minute from start (UTC, s since 1970), its tile pictures."""
    km_px = 0.5
    u = {"key": ("ENCELADUS", "ISS_TEST_SURFACE", "N", 0), "z": km_px / om.IFOV["N"], "frames": []}
    tiles = []
    rng = np.random.default_rng(7)
    n = 0
    for gy in (-1, 0, 1):
        for gx in (-1, 0, 1):
            for f in ("CL1", "GRN"):
                t = start + 60.0 * n
                fid = f"N{int(t)}_1"
                u["frames"].append((f"x/{fid}.png", fid, f, t, 0, 0, 0, u["z"]))
                when[fid] = t
                tiles.append({"n": n, "id": fid, "filter": f, "t": t, "offset": [gx * 800.0 + 20 * n, gy * 800.0 - 10 * n],
                              "box": [-SIDE / 2, -SIDE / 2, SIDE, SIDE]})
                n += 1
    tiles[5].pop("offset")   # one frame SPICE could not place
    there = om._tiles(u, cache, P["display_scale"])
    os.makedirs(there, exist_ok=True)
    for t in tiles:
        im = rng.integers(0, 256, (SIDE, SIDE, 4), dtype=np.uint8)
        im[..., 3] = 255
        Image.fromarray(im).save(os.path.join(there, f"{t['n']}.png"))
    mid = u["frames"][len(u["frames"]) // 2]
    middle[0] = mid[3]
    return u, tiles


def pictures(cache, u):
    d = os.path.join(om._tiles(u, cache, P["display_scale"]), om.SURFACE_DIR)
    if not os.path.isdir(d):
        return {}
    out = {}
    for name in sorted(os.listdir(d)):
        with open(os.path.join(d, name), "rb") as fh:
            out[name] = fh.read()
    return out


def rel(out, cache):
    return {n: os.path.relpath(p, cache) for n, p in out.items()}


P = {"display_scale": {"test": "surface taken"}}
root = tempfile.mkdtemp()
ok = True
try:
    for label, start in (("one year", calendar.timegm((2005, 3, 9, 12, 0, 0))),
                         ("across New Year", calendar.timegm((2004, 12, 31, 23, 50, 0)))):
        a, b = os.path.join(root, label, "before"), os.path.join(root, label, "after")
        u, tiles = make_pass(a, start)
        make_pass(b, start)
        assert u["frames"][0][3] < u["frames"][-1][3]
        for k in range(len(tiles)):
            # the mosaic grown a tile at a time (layout: tiles 0..k), as a window plays the pass and the pre-build makes it
            grown = tiles[:k + 1]
            om._passes.clear()
            calls.update(loads=0, fields=0, ets=0, year=None)
            want = surface_before(u, a, P, grown)
            before = dict(calls)
            calls.update(loads=0, fields=0, ets=0, year=None)
            got = om.surface_pictures(u, b, P, grown)
            after = dict(calls)
            assert rel(want, a) == rel(got, b), (label, k, rel(want, a), rel(got, b))
            pa, pb = pictures(a, u), pictures(b, u)
            pb.pop(om.SURFACE_TAKEN, None)
            assert pa == pb, (label, k, sorted(pa), sorted(pb))
            # each tile is worked out once: the new tile only (the old form worked out every tile kept as taken again)
            assert after["fields"] <= 1 and after["fields"] <= before["fields"], (label, k, before, after)
            assert after["loads"] <= 1, (label, k, after)
        # every later call, from the file (a fresh process) and from the pass's record (the server): nothing worked out
        kept = sorted(set(t["n"] for t in tiles if "offset" in t) - set(om.surface_pictures(u, b, P, tiles)))
        with open(os.path.join(om._tiles(u, b, P["display_scale"]), om.SURFACE_DIR, om.SURFACE_TAKEN)) as fh:
            taken = json.load(fh)
        assert taken == kept and kept, (label, taken, kept)
        want = rel(surface_before(u, a, P, tiles), a)
        calls.update(loads=0, fields=0, ets=0, year=None)
        om._passes.clear()
        again = om.surface_pictures(u, b, P, tiles)
        om._keep_plan(u, b, P, None)
        again2 = om.surface_pictures(u, b, P, tiles)
        again3 = om.surface_pictures(u, b, P, tiles)
        print(f"{label}: {len(rel(again, b))} tiles redrawn, {len(taken)} kept as taken {taken}; later calls: "
              f"{calls['fields']} sky fields, {calls['loads']} kernel loads, {calls['ets']} geometry reads")
        assert calls["fields"] == 0 and calls["loads"] == 0 and calls["ets"] == 0, calls
        assert rel(again, b) == rel(again2, b) == rel(again3, b) == want
        assert om._kept_tiles(u, b, P["display_scale"])["surface_taken"] == set(taken)
        # the form replaced: every later call works out each tile kept as taken again (and, across New Year, loads the
        # other year's kernels for its tiles and the middle's again after them)
        calls.update(loads=0, fields=0, ets=0, year=None)
        surface_before(u, a, P, tiles)
        print(f"  the form replaced, each later call: {calls['fields']} sky fields, {calls['loads']} kernel loads")
        assert calls["fields"] == len([n for n in taken if time.gmtime(tiles[n]["t"]).tm_year == time.gmtime(middle[0]).tm_year])
        if label == "across New Year":
            assert calls["loads"] > 1
            assert any(time.gmtime(tiles[n]["t"]).tm_year != time.gmtime(middle[0]).tm_year for n in taken)
finally:
    shutil.rmtree(root, ignore_errors=True)
print("surface taken: ok")
