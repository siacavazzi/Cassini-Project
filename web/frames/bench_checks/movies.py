"""
Movie checks: a frame the film shows twice in a row (repeat_frames), and a frame unlike both its neighbours while they
agree (odd_frame: a doubled limb, a flash, a jump to another place and back).
"""
from bench_checks import Result, check, luminance

SAME = 2          # levels: two pictures within this everywhere are one picture (an encoder's rounding)


def played(p):
    """The frames the film plays, in order: a frame whose picture key (the commit's own obs_mosaic.movie_shown, kept at
    build time) is the frame before it's is held, not played again. A commit without that rule played every frame
    (and so did a result built without the hook)."""
    frames = p.frames()
    got = p.collected("repeat_frames") or {}
    keys = got.get("keys")
    if not keys or len(keys) != len(frames):
        return frames, False
    out = [f for j, f in enumerate(frames) if j == 0 or keys[j] is None or keys[j] != keys[j - 1]]
    return out, True


@check("repeat_frames", kinds=("movie",), default=True, worse_by=0.0,
       about="the film shows the same picture twice in a row (Sam 11-17: never repeat frames)")
def repeat_frames(p, limit=0):
    import numpy as np
    shown, ruled = played(p)
    reps, where = 0, []
    prev = None
    for f in shown:
        a = p.load(f)
        if prev is not None and a.shape == prev[1].shape and \
                int(np.abs(a.astype(np.int16) - prev[1].astype(np.int16)).max()) <= SAME:
            reps += 1
            where.append(f"{prev[0]}={f}")
        prev = (f, a)
    how = "by the commit's movie_shown" if ruled else "every frame (no movie_shown rule in this commit or result)"
    return Result(reps, limit, reps <= limit,
                  f"{reps} of {len(shown)} played frames repeat the picture before ({how})", where=where[:6] or None)


@repeat_frames.collect
def _shown_keys(ctx):
    """The commit's own key for what each frame plays as (obs_mosaic.movie_shown, with the arguments the benchmark
    made the frames with); None per frame for a commit without it."""
    u = ctx.unit
    if u is None or u.get("mosaic") or u.get("kind") == "mosaic_movie":
        return None
    f = getattr(ctx.om, "movie_shown", None)
    if f is None:
        return {"rule": None}
    keys = []
    for fr in u["frames"]:
        k = f(fr[1], ctx.size, ctx.cache, 0, True, True)
        keys.append(None if k is None else repr(k))
    return {"rule": "movie_shown", "keys": keys}


def _small(rgba, side=256):
    import cv2
    lum = luminance(rgba) * (rgba[..., 3] > 0)
    return cv2.resize(lum, (side, side), interpolation=cv2.INTER_AREA)


def _onto(a, b):
    """b moved onto a by phase correlation (so a steady drift or a pointing jitter is not counted here)."""
    import cv2
    import numpy as np
    (dx, dy), _ = cv2.phaseCorrelate(a, b)
    m = np.float32([[1, 0, -dx], [0, 1, -dy]])
    return cv2.warpAffine(b, m, (a.shape[1], a.shape[0]))


@check("odd_frame", kinds=("movie",), default=True,
       about="a frame unlike both neighbours while they agree: a doubled limb, a flash, a jump to another place")
def odd_frame(p, limit=3.0):
    """For each played frame between two others: its difference from the mean of its neighbours (each moved onto it),
    over half their difference from each other plus one level. A frame in a smooth movie scores about 1; a frame
    that is neither neighbour scores far more."""
    import numpy as np
    shown, _ = played(p)
    if len(shown) < 3:
        return Result(0, limit, True, f"{len(shown)} played frames: nothing to judge")
    ims = [_small(p.load(f)) for f in shown]
    scores = []
    for j in range(1, len(ims) - 1):
        a = ims[j]
        b, c = _onto(a, ims[j - 1]), _onto(a, ims[j + 1])
        lit = (a > 8) | (b > 8) | (c > 8)
        if lit.sum() < 50:
            scores.append(0.0)
            continue
        own = float(np.abs(a - (b + c) / 2)[lit].mean())
        them = float(np.abs(b - c)[lit].mean())
        scores.append(own / (them / 2 + 1.0))
    k = int(np.argmax(scores))
    worst = scores[k]
    n = sum(s > limit for s in scores)
    return Result(worst, limit, worst <= limit,
                  f"worst {worst:.1f} at {shown[k + 1]} ({n} of {len(scores)} frames over {limit})",
                  where=shown[k + 1], values={shown[j + 1]: round(s, 2) for j, s in enumerate(scores) if s > limit})
