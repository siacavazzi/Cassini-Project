"""Synthetic checks of an even body's floor black in a pass's scale (obs_mosaic.pass_scale, _even_body): a moon's full
disk against the sky (Dione at zero phase, Rhea) has its black raised to its floor as a single picture's is
(calibration.evenness), the single picture's gamma and shoulder, and keeps its surface instead of a white disk; a
crescent, a body too small to have an inside and a pass the body fills keep the scale they had.
Run: python web/test_even_body.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic as om  # noqa: E402  (puts the repo on the path)
import calibration  # noqa: E402
import stacking  # noqa: E402

rng = np.random.default_rng(5)
yy, xx = np.mgrid[:1024, :1024].astype(np.float32)
# a surface of its own: brighter and darker patches a few per cent apart, as Dione's wispy terrain at zero phase
terrain = 1 + 0.06 * np.sin(xx / 23.0) * np.cos(yy / 31.0) + 0.03 * np.sin((xx + yy) / 9.0)


def frames_of(radius_px, face, filters=("CL1/CL2",), level=None):
    """Frames of a Dione pass, the disk radius_px (full resolution) at the frame's centre; face(rr, cos) is its I/F
    at rr (of its radius) from the centre and cos the cosine to the sun's direction across the disk (1 at the
    sub-solar side), and the stand-in load_hdr that gives their I/F, over a faint noisy sky."""
    z = om.RADIUS["DIONE"] / (radius_px * om.IFOV["N"])
    fr = [(f"d{n}", f"N{1549190000 + n}_1", f, 1000.0 + 60 * n, 600, 0.0, 0.0, z)
          for n, f in enumerate(f for _ in range(6) for f in filters)]
    rr = np.hypot(yy - 511.5, xx - 511.5) / radius_px
    across = (xx - 511.5) / radius_px
    lit = {f: np.where(rr < 1, face(rr, across) * terrain * (level or {}).get(f, 1.0), 0).astype(np.float32)
           for f in filters}
    by = {p: f for p, _, f, *_ in fr}

    def load_hdr(path, window=120, max_frames=8, valid=False):
        noise = np.random.default_rng(int(path[1:]) + 7)
        sky = (0.002 + 0.0008 * noise.standard_normal((1024, 1024))).astype(np.float32)
        return None, sky + lit[by[path]], 1
    return fr, load_hdr, lit, rr


def scales(fr, load, *a):
    """(the scale without the even body's floor, the scale with it)"""
    stacking.load_hdr = load
    u = {"key": ("DIONE", "ISS_038DI_TEST", "N", 0), "frames": fr, "z": fr[0][7], "movie": True}
    even_body, om._even_body = om._even_body, lambda by, on, inner, levels, base, blacks, white, *b: (blacks, white, 0.0)
    old = om.pass_scale(fr, u, *a)
    om._even_body = even_body
    return old, om.pass_scale(fr, u, *a)


def shown(scale, iof, f):
    t = om.tile_scale(scale, f)
    return calibration.display(iof, t["blacks"][0], t["white"], t["gamma"], t.get("shoulder"), t.get("toe"))[..., 0]


real = stacking.load_hdr
with calibration.looking("balanced"):
    # ---- Dione at zero phase: one even bright disk (Lommel-Seeliger: no limb darkening), 240 px across
    fr, load, lit, rr = frames_of(120, lambda rr, c: np.full_like(rr, 0.9))
    old, new = scales(fr, load)
    _, iof, _ = load(fr[0][0])
    disk = rr < 0.9
    before, after = shown(old, iof, "CL1/CL2")[disk], shown(new, iof, "CL1/CL2")[disk]
    spread = lambda v: float(np.percentile(v, 95) - np.percentile(v, 5))
    print(f"zero phase disk: black {old['blacks']['CL1/CL2']:.4f} -> {new['blacks']['CL1/CL2']:.4f}, white "
          f"{old['white']:.3f} -> {new['white']:.3f}, gamma {old['gamma']} -> {new['gamma']:.2f}; disk drawn >= 250 "
          f"{np.mean(before >= 250):.0%} -> {np.mean(after >= 250):.0%}, its 5-95% spread {spread(before):.0f} -> "
          f"{spread(after):.0f} levels")
    assert new["blacks"]["CL1/CL2"] > 0.5 and new["gamma"] < 2.4 and new["shoulder"] == calibration.SHOULDER
    assert np.mean(before >= 250) > 0.25 and np.mean(after >= 250) < 0.05
    assert spread(after) > 2.5 * spread(before)
    # the brightest of the disk is still white, as before (the white is as far above the black as it was)
    assert np.percentile(after, 99.9) >= 240
    # the sky stays black
    sky = rr > 1.3
    assert np.mean(shown(new, iof, "CL1/CL2")[sky] > 8) < 0.01

    # ---- a lit face with limb darkening (Rhea at low phase): less even, less floor, part of the gamma
    fr, load, lit, rr = frames_of(120, lambda rr, c: 0.7 * np.sqrt(np.clip(1 - rr ** 2, 0, 1)) ** 1.5)
    old_r, new_r = scales(fr, load)
    print(f"limb-darkened face: black {old_r['blacks']['CL1/CL2']:.4f} -> {new_r['blacks']['CL1/CL2']:.4f}, gamma "
          f"{old_r['gamma']} -> {new_r['gamma']:.2f}")
    assert old_r["gamma"] > new_r["gamma"] > new["gamma"]

    # ---- a crescent (Dione at high phase): its night side is in the disk's inside, so not even: as it was
    fr, load, lit, rr = frames_of(120, lambda rr, c: 0.9 * np.clip(c - 0.6, 0, None))
    old_c, new_c = scales(fr, load)
    print(f"crescent: scale unchanged ({new_c == old_c})")
    assert new_c == old_c

    # ---- a body too small to have an inside (a SPICE error and FLOOR_EDGE across): as it was
    fr, load, lit, rr = frames_of(20, lambda rr, c: np.full_like(rr, 0.9))
    old_s, new_s = scales(fr, load)
    print(f"small disk (40 px): scale unchanged ({new_s == old_s})")
    assert new_s == old_s

    # ---- a colour set: each band's black the same share of its own floor, so the colour stays what the camera saw
    # (one black in I/F would take more of the dimmer blue band and turn a gray moon orange)
    level = {"RED": 1.0, "GRN": 0.9, "BL1": 0.75}
    fr, load, lit, rr = frames_of(120, lambda rr, c: np.full_like(rr, 0.9), tuple(level), level)
    for true_colour in (True, False):
        old_t, new_t = scales(fr, load, ["RED", "GRN", "BL1"], true_colour)
        rise = {f: new_t["blacks"][f] - old_t["blacks"][f] for f in level}
        print(f"{'true' if true_colour else 'false'} colour: blacks rose", {f: round(v, 4) for f, v in rise.items()})
        assert min(rise.values()) > 0.3 and np.ptp([rise[f] / level[f] for f in level]) < 0.02
        _, iofs, _ = zip(*(load(p) for p, _, f, *_ in fr[:3]))
        lit_of = {f: float(np.median(calibration.decode(shown(new_t, iof, f)[rr < 0.9] / 255.0, new_t["gamma"])))
                  for (_, _, f, *_), iof in zip(fr[:3], iofs)}
        print("  the disk's linear brightness per band", {f: round(v, 3) for f, v in lit_of.items()})
        assert abs(lit_of["BL1"] / lit_of["RED"] - level["BL1"]) < 0.1
stacking.load_hdr = real
print("ok")
