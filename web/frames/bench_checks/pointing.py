"""
Pointing checks (Sam 2026-11-18: "we never use two different sources of pointing in a sequence"; the 2017 build played
most movies at SPICE's raw pointing, which scatters 3 to 26 px from frame to frame, and Enceladus setting behind
Saturn, 293EN ENCSET001, mixed the pictures' places with SPICE's):

  pointing_jitter   how far the movie's picture jumps from frame to frame beyond its own smooth motion
  pointing_sources  how many of the movie's frames play at SPICE's own raw pointing, or on SPICE's step in a sequence
                    the pictures otherwise place (none should: a sequence is placed by the pictures end to end, or
                    whole on SPICE's smoothed path). It reads
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


CREEP_MIN = 3.0   # px: (pointing_creep) a frame-to-frame move smaller than this is no part of a slide or a snap


@check("pointing_creep", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.25,
       about="the picture slides one way over a few frames and snaps back (a held frame redrawn as the body turns)")
def pointing_creep(p, limit=5.0):
    """The largest snap back: a move against the slide of the two or more moves before it, all the same way (each at
    least CREEP_MIN), as the smaller of the slide and the snap. A held frame's picture turned to each frame's time slid
    with the body's turn and the next picture of its own snapped it back (#625: Saturn 2017's held frames 35 px each
    way, every 4th frame); a pan or a steady movie has none, and scatter (pointing_jitter) has no slide before it."""
    import numpy as np
    m = moves(p)
    worst, where, count = 0.0, None, 0
    frames = p.frames()
    for i, v in enumerate(m):
        if v is None or math.hypot(*v) < CREEP_MIN:
            continue
        run = []
        j = i - 1
        while j >= 0 and m[j] is not None and math.hypot(*m[j]) >= CREEP_MIN and len(run) < 8:
            if run and np.dot(m[j], run[0]) <= 0:
                break
            run.append(m[j])
            j -= 1
        if len(run) < 2:
            continue
        slide = np.sum(run, axis=0)
        back = -float(np.dot(v, slide)) / max(float(np.hypot(*slide)), 1e-6)
        if back <= 0:
            continue
        snap = min(float(np.hypot(*slide)), back)
        if snap > limit:
            count += 1
        if snap > worst:
            worst, where = snap, frames[i]
    return Result(round(worst, 2), limit, worst <= limit,
                  f"largest snap back after a slide: {worst:.1f} px ({count} over {limit:.0f} px)", where=where)


@check("pointing_sources", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.0,
       about="frames of one movie placed by different sources of pointing (some at SPICE's raw place)")
def pointing_sources(p, limit=0):
    got = p.collected("pointing_sources")
    if not got or got.get("frames") is None:
        return Result(None, limit, True, "the build kept no pointing facts (collect hook missing)")
    n = got["on_spice"] + (got.get("mixed") or 0)
    made = len(p.frames())
    if made * 2 < got["frames"]:
        # (a movie whose pictures could not be read, LeanFrameMissing without the 12-bit originals: its chain had
        # nothing to place, so how it would be placed is not known; the build's own errors report the pictures)
        return Result(None, limit, True, f"only {made} of {got['frames']} frames made: pointing not judged")
    if got.get("follows"):
        return Result(0, limit, True, f"the view follows the frames: each of {got['frames']} drawn as the camera took it, "
                                      "no pointing places it")
    return Result(n, limit, n <= limit,
                  f"{got['on_spice']} of {got['frames']} frames at SPICE's raw pointing, {got.get('mixed') or 0} on SPICE's "
                  f"step among frames the pictures place; {got.get('linked')} placed by the pictures, "
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
    # (two sources in one sequence: a chain whose frames the pictures place in part, the rest held on SPICE's step or
    # path. from_pictures puts those between the pictures' own places; before it they counted as smoothed only)
    by_spice = sum(h.startswith("held") for h in hows)
    mixed = by_spice if auto and by_spice and by_spice < len(hows) else 0
    return {"frames": len(u["frames"]), "auto": auto, "linked": linked, "smoothed": smoothed, "on_spice": raw,
            "mixed": mixed}


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


def channel_offset(rgba, side=128, patches=4):
    """How far (px) a colour picture's red or blue channel sits from its green, whichever is further: each channel's
    edges (Sobel of a 1.2 px blur) phase-correlated with green's in the picture's `patches` busiest squares of `side`
    px, the median move per channel. None for a grey picture or one without edges. It measures the offset itself, so
    a body's own colour, a clipped channel's flat core or an overexposed glow (which read as colour along every edge,
    11-20 spot: Jupiter 2000, Enceladus 2004, Rhea, Saturn; all within 0.4 px) do not count, and an offset reads at
    its own size (a 1 px shift reads 0.8 to 1.1 px, 10 px reads 9.8)."""
    import cv2
    import numpy as np
    a = rgba.astype(np.float32)
    rgb = a[..., :3]
    if float(np.abs(rgb[..., 0] - rgb[..., 1]).max()) < 1 and float(np.abs(rgb[..., 2] - rgb[..., 1]).max()) < 1:
        return None
    lit = (a[..., 3] > 0).astype(np.float32)
    edges = []
    for c in range(3):
        g = cv2.GaussianBlur(rgb[..., c] * lit, (0, 0), 1.2)
        edges.append(np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)))
    h, w = lit.shape
    if h < side or w < side:
        return None
    busy = cv2.boxFilter(edges[1], -1, (side, side))
    win = cv2.createHanningWindow((side, side), cv2.CV_32F)
    got = {0: [], 2: []}
    for _ in range(patches):
        y, x = np.unravel_index(int(np.argmax(busy)), busy.shape)
        y0, x0 = int(min(max(y - side // 2, 0), h - side)), int(min(max(x - side // 2, 0), w - side))
        busy[max(0, y0 - side // 2):y0 + 3 * side // 2, max(0, x0 - side // 2):x0 + 3 * side // 2] = 0
        ref = edges[1][y0:y0 + side, x0:x0 + side]
        if ref.mean() < 0.5:
            continue
        for c in got:
            (dx, dy), resp = cv2.phaseCorrelate(ref, edges[c][y0:y0 + side, x0:x0 + side], win)
            if resp >= 0.08:
                got[c].append((dx, dy))
    off = [float(np.hypot(*np.median(np.array(v), axis=0))) for v in got.values() if v]
    drift = channel_drift(rgba)
    return max(off + ([drift] if drift is not None else [])) if off or drift is not None else None


def channel_drift(rgba):
    """How far (px) red or blue sits from green by the colour along the picture's edges, whichever is further: each
    channel (scaled to green's level over the lit picture) less green, fitted over the sharpest edges as a step along
    green's gradient (a channel d px off reads as -d . grad(green)). A body's own colour and an even glow round it
    cancel round its outline; a channel offset adds up all along it, signed, whichever way it lies, also where only
    part of a channel is off (a colour mixed from several filters, one of them 12 px off: 241TI's blue, rz-titan16
    on #606, which edge matching read as 0.5 px). Clipped pixels are left out. Titan's haze on a crescent's outer
    limb reads 1.5 to 3 px: a limb colour on one side only."""
    import cv2
    import numpy as np
    a = rgba.astype(np.float32)
    rgb = a[..., :3]
    lit = cv2.erode((a[..., 3] > 0).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    sm = [cv2.GaussianBlur(rgb[..., c], (0, 0), 1.0) for c in range(3)]
    g = sm[1]
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0) / 8, cv2.Sobel(g, cv2.CV_32F, 0, 1) / 8
    mag = np.hypot(gx, gy)
    ok = lit & (rgb.max(axis=2) < 250) & (g > 3)
    if ok.sum() < 500:
        return None
    edge = ok & (mag >= np.percentile(mag[ok], 97)) & (mag > 2)
    if edge.sum() < 50:
        return None
    out = []
    for c in (0, 2):
        k = float(np.median(sm[c][ok])) / max(float(np.median(g[ok])), 1e-3)
        d = sm[c] / max(k, 1e-3) - g
        sol = np.linalg.lstsq(np.stack([gx[edge], gy[edge]], 1), d[edge], rcond=None)[0]
        out.append(float(np.hypot(*sol)))
    return max(out)


@check("channel_registration", kinds=("movie",), default=True, owner="pointing thread", worse_by=0.25,
       about="a colour movie's channels do not line up: a coloured fringe along edges (257DA DAPHNIS001, #602)")
def channel_registration(p, limit=0.7):
    """The 90th percentile, over a colour movie's frames, of how far its red or blue channel sits from its green
    (channel_offset: the larger of the edges' own match and the colour along them, channel_drift; px): 0.1 to 0.55 px in a set that lines up (no fringe to the eye, 11-20 Fable 5.2); 0.76 px on fine storm clouds is one (rz-saturn11-movie3)."""
    import numpy as np
    vals = {}
    for f in p.frames():
        m = channel_offset(p.load(f))
        if m is not None:
            vals[f] = round(m, 2)
    if len(vals) < 2:
        return Result(0, limit, True, "no colour frames to judge")
    v = np.array(list(vals.values()))
    p90 = float(np.percentile(v, 90))
    worst = max(vals, key=vals.get)
    return Result(p90, limit, p90 <= limit, f"red or blue channel off green: p90 {p90:.2f} px, largest "
                                            f"{vals[worst]:.2f} px ({len(vals)} colour frames)", where=worst,
                  values={k: x for k, x in vals.items() if x > limit})
