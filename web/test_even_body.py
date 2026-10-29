"""Synthetic checks of bright bodies in a pass's scale (obs_mosaic.pass_scale): a moon's full disk against the sky
(Dione at zero phase, Rhea) has its black raised to the floor of what is lit, as a single picture's is
(calibration.evenness, _even_body), and its shoulder, and keeps its surface instead of a white disk; a small body in the
middle of the frames (filled) has the white of its disk (DISK_WHITE). A crescent, rings beside the body, a body too
small to have an inside and a disk over all of every frame keep the scale they had. Run: python web/test_even_body.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic as om  # noqa: E402  (puts the repo on the path)
import calibration  # noqa: E402
import stacking  # noqa: E402

yy, xx = np.mgrid[:1024, :1024].astype(np.float32)
# a surface of its own: brighter and darker patches a few per cent apart, as Dione's wispy terrain at zero phase
terrain = 1 + 0.06 * np.sin(xx / 23.0) * np.cos(yy / 31.0) + 0.03 * np.sin((xx + yy) / 9.0)


def frames_of(radius_px, face, filters=("CL1/CL2",), level=None, where=(0.0, 0.0), extra=None, target="DIONE"):
    """Frames of a pass, the disk radius_px (full resolution) where SPICE puts it (where: the shift that centres it);
    face(rr, across) is its I/F at rr (of its radius) from its centre and across (of its radius) toward the sun; extra:
    I/F added over the frame (rings); and the stand-in load_hdr that gives their I/F, over a faint noisy sky."""
    z = om.RADIUS[target] / (radius_px * om.IFOV["N"])
    fr = [(f"d{n}", f"N{1549190000 + n}_1", f, 1000.0 + 60 * n, 600, where[0], where[1], z)
          for n, f in enumerate(f for _ in range(6) for f in filters)]
    cy, cx = 511.5 - where[1], 511.5 - where[0]
    rr = np.hypot(yy - cy, xx - cx) / radius_px
    across = (xx - cx) / radius_px
    lit = {f: np.where(rr < 1, face(rr, across) * terrain * (level or {}).get(f, 1.0), 0).astype(np.float32)
           + (0 if extra is None else extra) for f in filters}
    by = {p: f for p, _, f, *_ in fr}

    def load_hdr(path, window=120, max_frames=8, valid=False):
        noise = np.random.default_rng(int(path[1:]) + 7)
        sky = (0.002 + 0.0008 * noise.standard_normal((1024, 1024))).astype(np.float32)
        return None, sky + lit[by[path]], 1
    return fr, load_hdr, rr


def scales(fr, load, *a, target="DIONE"):
    """(the scale without the even body's floor, the scale with it)"""
    stacking.load_hdr = load
    u = {"key": (target, "ISS_038DI_TEST", "N", 0), "frames": fr, "z": fr[0][7], "movie": True}
    even_body, om._even_body = om._even_body, lambda by, on, inner, levels, blacks, white, drawn: (blacks, white, 0.0)
    old = om.pass_scale(fr, u, *a)
    om._even_body = even_body
    return old, om.pass_scale(fr, u, *a)


def shown(scale, iof, f):
    t = om.tile_scale(scale, f)
    return calibration.display(iof, t["blacks"][0], t["white"], t["gamma"], t.get("shoulder"), t.get("toe"))[..., 0]


spread = lambda v: float(np.percentile(v, 95) - np.percentile(v, 5))
flat = lambda rr, c: np.full_like(rr, 0.9)
real = stacking.load_hdr
with calibration.looking("balanced"):
    # ---- Dione at zero phase: one even bright disk (Lommel-Seeliger: no limb darkening), 240 px across, in the middle
    # of the frames (a filled pass, as 038DI's) and off to one side (a body against the sky)
    for where, kind in (((0.0, 0.0), "filled"), ((300.0, 0.0), "against the sky")):
        fr, load, rr = frames_of(120, flat, where=where)
        old, new = scales(fr, load)
        assert new["filled"] == (kind == "filled")
        _, iof, _ = load(fr[0][0])
        disk = rr < 0.9
        before, after = shown(old, iof, "CL1/CL2")[disk], shown(new, iof, "CL1/CL2")[disk]
        print(f"zero phase disk, {kind}: black {old['blacks']['CL1/CL2']:.4f} -> {new['blacks']['CL1/CL2']:.4f}, white "
              f"{old['white']:.3f} -> {new['white']:.3f}, gamma {old['gamma']} -> {new['gamma']:.2f}; disk drawn >= 250 "
              f"{np.mean(before >= 250):.0%} -> {np.mean(after >= 250):.0%}, its 5-95% spread {spread(before):.0f} -> "
              f"{spread(after):.0f} levels")
        assert new["blacks"]["CL1/CL2"] > 0.5 and new["shoulder"] == calibration.SHOULDER
        assert new["gamma"] == (1.5 if kind == "filled" else om.DISK_GAMMA)
        assert np.mean(after >= 250) < 0.05 and spread(after) > 2.5 * spread(before)
        # the brightest of the disk is as bright as before, and the sky stays black
        assert abs(np.percentile(after, 99.9) - np.percentile(before, 99.9)) <= 12
        assert np.mean(shown(new, iof, "CL1/CL2")[rr > 1.3] > 8) < 0.01

    # ---- a lit face with limb darkening (Rhea at low phase), against the sky: less even, less floor, part of the gamma
    fr, load, rr = frames_of(120, lambda rr, c: 0.7 * np.sqrt(np.clip(1 - rr ** 2, 0, 1)) ** 1.5, where=(300.0, 0.0))
    old_r, new_r = scales(fr, load)
    print(f"limb-darkened face: black {old_r['blacks']['CL1/CL2']:.4f} -> {new_r['blacks']['CL1/CL2']:.4f}, gamma "
          f"{old_r['gamma']} -> {new_r['gamma']:.2f}")
    assert old_r["gamma"] > new_r["gamma"] > om.DISK_GAMMA and new_r["blacks"]["CL1/CL2"] > old_r["blacks"]["CL1/CL2"]

    # ---- a crescent: its lit part is far from even, and keeps nearly all of its light (a little of its floor black,
    # as a single picture's)
    fr, load, rr = frames_of(120, lambda rr, c: 0.9 * np.clip(c - 0.6, 0, None))
    old_c, new_c = scales(fr, load)
    _, iof, _ = load(fr[0][0])
    crescent = (rr < 1) & (iof > 0.05 * iof.max())
    dark = lambda sc: float(np.mean(shown(sc, iof, "CL1/CL2")[crescent] <= 3))
    print(f"crescent: black {old_c['blacks']['CL1/CL2']:.4f} -> {new_c['blacks']['CL1/CL2']:.4f}, its lit part drawn "
          f"black {dark(old_c):.1%} -> {dark(new_c):.1%}")
    assert dark(new_c) < dark(old_c) + 0.05

    # ---- as they were: the even disk with faint rings across the frames (lit too: 117RI EQXSHADOW's rings went black
    # under a floor taken on Saturn's disk alone); a disk too small to have an inside
    unchanged = {}
    rings = np.where(np.abs(yy - 0.3 * xx - 650) < 60, 0.03, 0).astype(np.float32)
    fr, load, rr = frames_of(120, flat, where=(300.0, 0.0), extra=rings)
    unchanged["rings beside the disk"] = scales(fr, load)
    fr, load, rr = frames_of(20, flat, where=(300.0, 0.0))
    unchanged["small disk (40 px)"] = scales(fr, load)
    for kind, (old, new) in unchanged.items():
        print(f"{kind}: scale unchanged ({new == old})")
        assert new == old, (kind, new, old)

    # ---- a small bright body in the middle of the frames (filled, as Titan in 000TI's movie): the frames' 99.5th
    # percentile was on the sky; white is at least its disk's now
    least = om.DISK_LEAST
    fr, load, rr = frames_of(20, flat, target="TITAN")
    stacking.load_hdr = load
    u = {"key": ("TITAN", "ISS_000TI_TEST", "N", 0), "frames": fr, "z": fr[0][7], "movie": True}
    om.DISK_LEAST = 1 << 30   # no disk measured: the scale as it was
    old = om.pass_scale(fr, u)
    om.DISK_LEAST = least
    new = om.pass_scale(fr, u)
    _, iof, _ = load(fr[0][0])
    print(f"small disk in the middle of the frames: filled {new['filled']}, white {old['white']:.4f} -> {new['white']:.4f}, "
          f"disk drawn >= 250 {np.mean(shown(old, iof, 'CL1/CL2')[rr < 0.9] >= 250):.0%} -> "
          f"{np.mean(shown(new, iof, 'CL1/CL2')[rr < 0.9] >= 250):.0%}")
    assert old["filled"] and new["filled"] and new["white"] > 0.8 > 10 * old["white"]
    # a disk over all of every frame (a map): the same white
    fr, load, rr = frames_of(900, flat, target="TITAN")
    stacking.load_hdr = load
    u = {"key": ("TITAN", "ISS_000TI_TEST", "N", 0), "frames": fr, "z": fr[0][7]}
    om.DISK_LEAST = 1 << 30
    old = om.pass_scale(fr, u)
    om.DISK_LEAST = least
    print(f"disk over every frame: filled {old['filled']}, scale unchanged ({om.pass_scale(fr, u) == old})")
    assert om.pass_scale(fr, u) == old

    # ---- a colour set: each band's black the same share of its own floor, so the colour stays what the camera saw
    # (one black in I/F would take more of the dimmer blue band and turn a gray moon orange)
    level = {"RED": 1.0, "GRN": 0.9, "BL1": 0.75}
    fr, load, rr = frames_of(120, flat, tuple(level), level, where=(300.0, 0.0))
    for true_colour in (True, False):
        old_t, new_t = scales(fr, load, ["RED", "GRN", "BL1"], true_colour)
        rise = {f: new_t["blacks"][f] - old_t["blacks"][f] for f in level}
        print(f"{'true' if true_colour else 'false'} colour: blacks rose", {f: round(v, 4) for f, v in rise.items()})
        assert min(rise.values()) > 0.3 and np.ptp([rise[f] / level[f] for f in level]) < 0.03
        _, iofs, _ = zip(*(load(p) for p, _, f, *_ in fr[:3]))
        lit_of = {f: float(np.median(calibration.decode(shown(new_t, iof, f)[rr < 0.9] / 255.0, new_t["gamma"])))
                  for (_, _, f, *_), iof in zip(fr[:3], iofs)}
        print("  the disk's linear brightness per band", {f: round(v, 3) for f, v in lit_of.items()})
        assert abs(lit_of["BL1"] / lit_of["RED"] - level["BL1"]) < 0.1
stacking.load_hdr = real
print("ok")
