"""
Pointing checks (Sam 2026-11-18: "we never use two different sources of pointing in a sequence"; the 2017 build played
most movies at SPICE's raw pointing, which scatters 3 to 26 px from frame to frame, and Enceladus setting behind
Saturn, 293EN ENCSET001, mixed the pictures' places with SPICE's):

  pointing_jitter   how far the movie's picture jumps from frame to frame beyond its own smooth motion
  pointing_sources  how many of the movie's frames play at SPICE's own raw pointing (none should: every frame is
                    placed by the pictures, or on SPICE's smoothed path between frames the pictures place)
"""
from bench_checks import Result, check, luminance

SMOOTH = 3.0      # frames: the movie's own motion, a Gaussian of this many frames over its frame-to-frame moves
SURE = 0.05       # phase correlation peak under which a pair says nothing (a blank frame, a hidden target)


def _grey(rgba):
    import numpy as np
    return (luminance(rgba) * (rgba[..., 3] > 0)).astype(np.float32)


def _even(n):
    import cv2
    m = cv2.getOptimalDFTSize(n)
    return m if m % 2 == 0 else cv2.getOptimalDFTSize(m + 1)


def moves(p):
    """[(dx, dy) or None]: the picture's move from each frame to the next (px of the frames as made), by phase
    correlation padded to an even DFT size (cv2's own odd padding is half a pixel off), Hann window."""
    import cv2
    import numpy as np
    out, prev = [], None
    for f in p.frames():
        g = _grey(p.load(f))
        if prev is not None and prev.shape == g.shape and prev.max() > 8 and g.max() > 8:
            h, w = g.shape
            pad = lambda x: cv2.copyMakeBorder(x, 0, _even(h) - h, 0, _even(w) - w, cv2.BORDER_CONSTANT, value=0)
            (dx, dy), resp = cv2.phaseCorrelate(pad(prev), pad(g), pad(cv2.createHanningWindow((w, h), cv2.CV_32F)))
            out.append((float(dx), float(dy)) if resp >= SURE else None)
        else:
            out.append(None)
        prev = g
    return out


@check("pointing_jitter", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.25,
       about="the movie jumps around from frame to frame (SPICE's pointing scatter, or two pointing sources mixed)")
def pointing_jitter(p, limit=3.0):
    """The 90th percentile of the frame-to-frame moves' departure from the movie's own smooth motion (a Gaussian of
    SMOOTH frames over the moves): about 0 to 1 px in a steady movie, however it pans; SPICE's scatter shows as 5 to
    25 px."""
    import numpy as np
    m = moves(p)
    idx = [i for i, v in enumerate(m) if v is not None]
    if len(idx) < 4:
        return Result(0, limit, True, f"{len(idx)} frame pairs to measure: nothing to judge")
    v = np.array([m[i] for i in idx])
    t = np.array(idx, float)
    w = np.exp(-0.5 * ((t[:, None] - t[None, :]) / SMOOTH) ** 2)
    smooth = (w @ v) / w.sum(axis=1)[:, None]
    dev = np.hypot(*(v - smooth).T)
    p90 = float(np.percentile(dev, 90))
    k = int(np.argmax(dev))
    frames = p.frames()
    where = frames[idx[k] + 1] if idx[k] + 1 < len(frames) else None
    return Result(p90, limit, p90 <= limit,
                  f"frame-to-frame jump past the movie's own motion: p90 {p90:.1f} px, largest {dev.max():.1f} px "
                  f"({len(idx)} pairs)", where=where,
                  values={frames[i + 1]: round(float(d), 1) for i, d in zip(idx, dev) if d > limit})


@check("pointing_sources", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.0,
       about="frames of one movie placed by different sources of pointing (some at SPICE's raw place)")
def pointing_sources(p, limit=0):
    got = p.collected("pointing_sources")
    if not got or got.get("frames") is None:
        return Result(None, limit, True, "the build kept no pointing facts (collect hook missing)")
    n = got["on_spice"]
    return Result(n, limit, n <= limit,
                  f"{n} of {got['frames']} frames at SPICE's raw pointing; {got.get('linked')} placed by the pictures, "
                  f"{got.get('smoothed')} on the smoothed path ({'stabilized' if got.get('auto') else 'not stabilized'} "
                  f"by default)")


@pointing_sources.collect
def _sources(ctx):
    """How the commit plays the movie by default: stabilized or at SPICE's places (obs_mosaic.auto_steady), and how
    its stabilization chain placed each frame (the kept chain's hows)."""
    import json
    import os
    u, om = ctx.unit, ctx.om
    if u is None or u.get("mosaic") or u.get("kind") == "mosaic_movie" or u.get("track"):
        return None
    path = os.path.join(om.folder(u, ctx.cache), om.STEADY_FILE)
    how = json.load(open(path)).get("how", {}) if os.path.exists(path) else {}
    auto = bool(om.auto_steady(u, ctx.cache))
    hows = [str(h) for h in how.values()]
    linked = sum(h.startswith(("linked", "first")) for h in hows)
    smoothed = sum("no match" in h for h in hows)
    # (at SPICE's raw pointing: every frame of a movie not stabilized by default; in one that is, a frame its chain
    # left at SPICE's own place ("SPICE (no link)") or moved by SPICE's raw step (held past the reach, before 11-18))
    raw = len(u["frames"]) if not auto else sum(h.startswith("SPICE") for h in hows)
    if auto and not hasattr(om, "STEADY_HIDDEN"):
        raw += sum(h.startswith("held") for h in hows)
    return {"frames": len(u["frames"]), "auto": auto, "linked": linked, "smoothed": smoothed, "on_spice": raw}


ITEMS = [
    {"name": "encset293-movie", "kind": "pass", "frame": "N1884013382_1", "group": "hard",
     "watch": "Enceladus setting behind Saturn: steady to the end, no frame at SPICE's raw pointing (2026-11-18)"},
    {"name": "aurstare289-movie", "kind": "pass", "frame": "N1881947254_1", "group": "hard",
     "watch": "Saturn aurora stare, nothing to match: on SPICE's smoothed path, no jitter"},
    {"name": "titancloud264-movie", "kind": "pass", "frame": "N1867408664_1", "group": "hard",
     "watch": "Titan cloud watch: steady, no frame at SPICE's raw pointing"},
    {"name": "fring277-movie", "kind": "pass", "frame": "N1875199754_1", "group": "hard",
     "watch": "F ring strand stare: steady across the ring"},
]
