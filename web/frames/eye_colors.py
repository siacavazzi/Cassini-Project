"""
Measures eye_colors.json, the bodies' own colors for natural color emulation (calibration.eye_mix, colors=eye): each
body's color as this pipeline's true color sets (RED + GRN + BL1/BL2/VIO, natural color) measure it, the median over
its sets of each set's median lit color (linear, mean 1). Bodies with fewer than MIN_SETS sets are left out (eye_mix
then uses BODY_TINTS, else gray).

Each set is made by the pipeline's own color path (color_image.load_aligned: repeat exposures stacked, calibrated to
I/F, aligned, the camera's natural matrix), and its color is read in linear light, as the matrix gives it, just before
the display tone (calibration.tone): every lit pixel the camera did not saturate counts. The table was measured from
the drawn pictures before (11-16): there an icy moon's lit disk sits at white, so its pixels were the ones left out as
"near white" and the color came from the limb, terminator and Saturn-lit edge, all warm. Enceladus measured
[1.12, 1.01, 0.77], an orange cast on every emulated frame of it (taste call 17), where its true color sets are
near gray.

Usage (from the repo, with CASSINI_DATA and the geometry cache set, as the frame server runs):
  python web/frames/eye_colors.py [--per N] [--workers N] [--targets A,B] [--out OUT_JSON] [--sets SETS_JSON]
--per: at most this many sets a body, spread over the mission (default PER); --sets: also writes each set's color
"""
import argparse
import contextlib
import json
import multiprocessing
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

MIN_SETS = 5
PER = 24            # sets measured a body, at most, evenly spread over its true color sets in time
LIT = 0.25          # lit: brighter than this share of the set's 99.5th percentile brightness (linear) ...
LEAST = 500         # ... and at least this many such pixels, or the set is left out (a dot of a body)
INNER = 0.8         # only the body's own disk, as SPICE places it on the set's reference frame: this share of its radius,
INNER_PX = 16       # ... less this many full resolution pixels for SPICE's error. The whole picture's lit pixels were
#                     whatever else was brightest in it too: Saturn behind a moon, its rings, a crescent's limb
# the bodies measured (the table's since it began, 10-30): a body in the table is one natural color emulation knows,
# which decides whose color a storm watch filed under a rider moon takes (calibration.mix_target: Janus, Helene,
# Prometheus... drawn in Saturn's color, not their own); a body is added here only with that checked
BODIES = ("ATLAS", "DIONE", "ENCELADUS", "IAPETUS", "MIMAS", "RHEA", "SATURN", "TETHYS", "TITAN")
# bodies whose color stays as it is (Sam's taste call): natural color itself draws with theirs, not only the emulation
# (Titan's two-filter approximate color, pair_mix; Saturn's and Titan's methane sets, emulated), so a new measure of
# them changes stored pictures. Measured in linear light Titan is a deeper orange [1.44, 1.03, 0.53] (11-17)
KEEP = ("SATURN", "TITAN")
SKIP = {"SKY", "UNK", "NONE", "DARK", "STAR", "PLAQUE", "CAL_LAMPS", "DARKSKY"}
FOLDERS = {"N": "nac_data", "W": "wac_data"}


@contextlib.contextmanager
def _linear_capture(seen):
    """calibration.tone, while in this block, also hands its mixed linear picture (3 x H x W, white 1, before the toe,
    shoulder and gamma) and the pixels any channel saturated to seen; the picture it draws is unchanged."""
    import calibration as cal
    tone = cal.tone

    def capture(channels, margin, mix=None, *args, **kwargs):
        if mix is not None and len(channels) == 3:
            x = cal.apply_mix(mix, np.stack(channels).astype(np.float32))
            sat = kwargs.get("saturated")
            clipped = None
            if sat is not None and any(m is not None and m.any() for m in sat):
                clipped = np.logical_or.reduce([m for m in sat if m is not None])
            seen.append((np.asarray(x), clipped))
        return tone(channels, margin, mix, *args, **kwargs)

    cal.tone = capture
    try:
        yield
    finally:
        cal.tone = tone


def set_color(ids):
    """The set's median lit color (linear, mean 1) and its lit pixel count, or None (drawn gray, nothing lit)."""
    import color_image
    seen = []
    with _linear_capture(seen):
        try:
            _, _, ref, report = color_image.load_aligned([f"{FOLDERS[i[0]]}/{i}.png" for i in ids])
        except Exception as e:
            print(f"{ids}: {e}", flush=True)
            return None
    if not seen or report.get("grey") or not report.get("calibrated"):
        return None
    x, clipped = seen[-1]
    lum = x.mean(axis=0)
    disk = _disk(ref, lum.shape)
    if disk is None or disk.sum() < LEAST:
        return None
    top = float(np.percentile(lum[disk], 99.5))
    if top < SUNLIT:
        return None
    lit = disk & (lum > LIT * top)
    if clipped is not None and clipped.shape == lum.shape:
        lit &= ~clipped
    if lit.sum() < LEAST:
        return None
    c = np.median(x[:, lit], axis=1)
    if c.min() <= 0:
        return None
    return [float(v) for v in c / c.mean()], int(lit.sum())


SUNLIT = 0.5        # the body's disk at least this bright against the set's white (1): the body is what the picture
#                     is exposed for, lit by the Sun. A moon far dimmer than its picture's white is a night side lit by
#                     Saturn, or a speck before a lit Saturn: Saturnshine's orange read as the moon's own (Enceladus at
#                     a twelfth of white, [1.27, 1.04, 0.70])


def _disk(lbl, shape):
    """The inner part of the frame's target's disk (INNER, INNER_PX) as SPICE places it, a mask of shape, or None
    (SPICE can't place it, a body of no known size)."""
    import color_image
    import obs_mosaic
    target = lbl.info.get("TARGET_NAME")
    locs = color_image._spice_locs([lbl])
    if target not in obs_mosaic.RADIUS or not locs or not locs[0] or len(locs[0]) < 3 or not locs[0][2]:
        return None
    loc = locs[0]
    cam = "W" if lbl.info.get("INSTRUMENT_ID") == "ISSWA" else "N"
    radius = obs_mosaic.RADIUS[target] / (float(loc[2]) * obs_mosaic.IFOV[cam])
    reach = radius * INNER - INNER_PX
    if reach <= 0:
        return None
    k = 1024 / shape[0]   # (a summed frame's pixels are full resolution ones scaled to 1024, as color_image.off_disk)
    rows = np.arange(shape[0], dtype=np.float32)[:, None] * k
    cols = np.arange(shape[1], dtype=np.float32)[None, :] * k
    cy, cx = color_image.ba.CCD_CENTER - float(loc[1]), color_image.ba.CCD_CENTER - float(loc[0])
    return (rows - cy) ** 2 + (cols - cx) ** 2 < reach * reach


def _work(job):
    target, ids, t = job
    return target, ids, t, set_color(ids)


def true_sets(targets=None, per=PER):
    """(target, ids, time) of up to per of each body's true color sets (reel.shots' kind "true"), spread over time."""
    import reel
    names = targets or BODIES
    jobs = []
    for target in names:
        sets = [s for s in reel.shots(target) if s.get("kind") == "true" and len(s.get("ids", [])) == 3]
        if len(sets) < MIN_SETS:
            continue
        pick = sorted(set(np.linspace(0, len(sets) - 1, min(per, len(sets))).round().astype(int).tolist()))
        jobs += [(target, sets[k]["ids"], sets[k]["t"]) for k in pick]
    return jobs


def measure(jobs, workers=1):
    found, each = {}, []
    # in time order, a few at a time: a worker keeps to one year's SPICE kernels
    jobs = sorted(jobs, key=lambda j: j[2])
    if workers > 1:
        pool = multiprocessing.get_context("spawn").Pool(workers)
        results = pool.imap_unordered(_work, jobs, chunksize=4)
    else:
        pool, results = None, map(_work, jobs)
    for k, (target, ids, t, got) in enumerate(results):
        print(f"[{k + 1}/{len(jobs)}] {target} {'_'.join(ids)} {None if got is None else [round(v, 3) for v in got[0]]}",
              flush=True)
        each.append({"target": target, "ids": ids, "t": t, "rgb": got[0] if got else None, "lit": got[1] if got else 0})
        if got:
            found.setdefault(target.upper(), []).append(got[0])
    if pool is not None:
        pool.close()
        pool.join()
    table = {t: {"rgb": [round(float(v), 4) for v in np.median(cs, axis=0)], "sets": len(cs)}
             for t, cs in sorted(found.items()) if len(cs) >= MIN_SETS and t not in SKIP}
    return table, each


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=PER)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--targets", default="")
    ap.add_argument("--out", default=os.path.join(REPO, "eye_colors.json"))
    ap.add_argument("--sets", default="")
    a = ap.parse_args()
    jobs = true_sets([t for t in a.targets.split(",") if t] or None, a.per)
    print(len(jobs), "sets", flush=True)
    table, each = measure(jobs, a.workers)
    if a.sets:
        with open(a.sets, "w") as f:
            json.dump(each, f, indent=1)
    out = {"_about": "Bodies' own colors for natural color emulation (calibration.eye_mix): linear red, green, blue of "
                     "mean 1, the median over the body's true color sets of each one's median lit color, read in linear "
                     "light from the pipeline's own color path (web/frames/eye_colors.py)."}
    # a body none of whose sets passes (Atlas: a speck, or Saturn-lit) keeps the color it had, so it stays a known
    # body (mix_target) and its pictures don't change
    if os.path.exists(a.out):
        with open(a.out) as f:
            before = json.load(f)
        for t in KEEP:
            if t in table and t in before:
                print(f"{t} keeps {before[t]['rgb']} (measured {table[t]['rgb']})")
        table.update({t: v for t, v in before.items() if t in BODIES and (t not in table or t in KEEP)})
    out.update(dict(sorted(table.items())))
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))
