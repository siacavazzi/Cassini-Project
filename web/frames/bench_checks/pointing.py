"""
Pointing checks (Sam 2026-11-18: "we never use two different sources of pointing in a sequence"; the 2017 build played
most movies at SPICE's raw pointing, which scatters 3 to 26 px from frame to frame, and Enceladus setting behind
Saturn, 293EN ENCSET001, mixed the pictures' places with SPICE's):

  pointing_jitter   how far the movie's picture jumps from frame to frame beyond its own smooth motion
  pointing_sources  how many of the movie's frames play at SPICE's own raw pointing (none should: every frame is
                    placed by the pictures, or on SPICE's smoothed path between frames the pictures place). It reads
                    the commit's own placement (its collect hook), so it is paired with pointing_jitter, which measures
                    the pictures themselves
"""
import math

from bench_checks import Result, check, luminance

SMOOTH = 3.0      # frames: the movie's own motion, a Gaussian of this many frames over its frame-to-frame moves
SURE = 0.15       # phase correlation peak under which a pair says nothing (a blank frame, a hidden target, a ring
#                   scan whose ringlets repeat: such pairs read as moves of hundreds of px between frames 1 to 3 px apart)
FARTHEST = 0.25   # of the picture's side: a move further than this between two frames is not measured as one (a scan's
#                   frames sharing too little to match), left out like an unsure pair


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
            out.append((float(dx), float(dy)) if resp >= SURE and math.hypot(dx, dy) <= FARTHEST * min(h, w) else None)
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
    where = frames[idx[k]]   # (moves()[i] is the move from frame i - 1 to frame i)
    return Result(p90, limit, p90 <= limit,
                  f"frame-to-frame jump past the movie's own motion: p90 {p90:.1f} px, largest {dev.max():.1f} px "
                  f"({len(idx)} pairs)", where=where,
                  values={frames[i]: round(float(d), 1) for i, d in zip(idx, dev) if d > limit})


@check("pointing_sources", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.0,
       about="frames of one movie placed by different sources of pointing (some at SPICE's raw place)")
def pointing_sources(p, limit=0):
    got = p.collected("pointing_sources")
    if not got or got.get("frames") is None:
        return Result(None, limit, True, "the build kept no pointing facts (collect hook missing)")
    n = got["on_spice"]
    if got.get("follows"):
        return Result(0, limit, True, f"the view follows the frames: each of {got['frames']} drawn as the camera took it, "
                                      "no pointing places it")
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
    # (a pass whose view follows its frames draws each frame as the camera took it, filling the picture: no pointing
    # places it, so none is SPICE's; obs_mosaic._steady_table's own test)
    try:
        p = om.plan(u, ctx.cache)
        fp = om.movie_footprint(u, ctx.cache, p)
        radius = om.RADIUS.get(u["key"][0], 0) / (u["z"] * om.IFOV[u["key"][2]])
        follows = bool(om.follows(fp, om.movie_rect(fp, {"offset": (0.0, 0.0)}, radius, True, om.pass_seen(u))))
    except Exception:   # noqa: BLE001  (a commit without these: counted as before)
        follows = False
    if follows:
        return {"frames": len(u["frames"]), "auto": False, "linked": 0, "smoothed": 0, "on_spice": 0, "follows": True}
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
    {"name": "daphnis257n1-movie", "kind": "pass", "frame": "N1863264697_1", "group": "hard",
     "watch": "Daphnis colour movie: channels line up along the Keeler gap edge, no blue-violet fringe (#602 regression)"},
    {"name": "fring039-movie", "kind": "pass", "frame": "N1551253524_1", "group": "hard",
     "watch": "2007 F ring movie (039RF FMOVIE001): no jitter (#602 regression, p90 16.5 to 31 px)"},
    {"name": "fring183-movie", "kind": "pass", "frame": "N1741151683_1", "group": "hard",
     "watch": "2013 F ring movie (183RF FMOVIE001): no jitter (#602 regression, p90 19.5 to 28.8 px)"},
    {"name": "titancloud264-movie", "kind": "pass", "frame": "N1867408664_1", "group": "hard",
     "watch": "Titan cloud watch: steady, no frame at SPICE's raw pointing"},
]


def _fringe(rgba):
    """How much more colourful a colour picture is along its sharpest edges than over its picture: the mean chroma
    (max channel less min, levels) within 2 px of its top 3 % of brightness edges, less its median chroma, inside its
    lit picture (none for a grey picture or too little lit). Channels that do not line up put colour along every edge
    (257DA DAPHNIS001 after #602: -0.1 before, 6.0 with its blue channel 10 px off along the Keeler gap)."""
    import cv2
    import numpy as np
    a = rgba.astype(np.float32)
    rgb = a[..., :3]
    if float(np.abs(rgb[..., 0] - rgb[..., 1]).max()) < 1 and float(np.abs(rgb[..., 2] - rgb[..., 1]).max()) < 1:
        return None
    lit = a[..., 3] > 0
    lum = rgb.mean(axis=2)
    g = cv2.GaussianBlur(lum, (0, 0), 1.0)
    G = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    m = (cv2.erode(lit.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) & (lum > 20)
    if m.sum() < 1000:
        return None
    edge = m & (G >= np.percentile(G[m], 97))
    near = (cv2.dilate(edge.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & m
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    return float(chroma[near].mean() - np.median(chroma[m]))


@check("channel_registration", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.25,
       about="a colour movie's channels do not line up: a coloured fringe along edges (257DA DAPHNIS001, #602)")
def channel_registration(p, limit=4.0):
    """The 90th percentile, over a colour movie's frames, of how much more colourful each is along its sharpest edges
    than over its picture (_fringe, levels). A body's own colour along a limb scores high on both sides (a known
    failure); a set whose channels come apart scores higher than before (a regression)."""
    import numpy as np
    vals = {}
    for f in p.frames():
        m = _fringe(p.load(f))
        if m is not None:
            vals[f] = round(m, 2)
    if len(vals) < 2:
        return Result(0, limit, True, "no colour frames to judge")
    v = np.array(list(vals.values()))
    p90 = float(np.percentile(v, 90))
    worst = max(vals, key=vals.get)
    return Result(p90, limit, p90 <= limit, f"colour along edges past the picture's own: p90 {p90:.2f} levels, largest "
                                            f"{vals[worst]:.2f} ({len(vals)} colour frames)", where=worst,
                  values={k: x for k, x in vals.items() if x > limit})
