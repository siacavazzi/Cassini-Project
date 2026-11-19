"""
Light checks: white blown out where it should not be (clipped_white), and a glow ring or a dark gap past a lit limb
against black sky (limb_halo, #574: sky smoothing lifted the faint sky off Saturn's soft limb edge).
"""
from bench_checks import Result, check, lit_mask, luminance


@check("clipped_white", kinds=("still", "composite", "movie", "mosaic", "mosaic_movie"), default=False,
       about="the lit picture blown to white (a disk, a ring, a block gone flat white)")
def clipped_white(p, max=0.01):
    """The share of the lit picture at white (254 or more in any channel), on the item's main picture and, for a
    mosaic, its full-size picture too; held to max (the item's own: some subjects clip in the camera)."""
    names = [p.main()] + (["mosaic_full.webp"] if "mosaic_full.webp" in p.names() else [])
    worst, where = 0.0, None
    for f in names:
        if not f:
            continue
        a = p.load(f)
        m = lit_mask(a)
        if not m.any():
            continue
        share = float((a[..., :3].max(axis=2)[m] >= 254).mean())
        if share >= worst:
            worst, where = share, f
    return Result(worst, max, worst <= max, f"{worst:.2%} of the lit picture at white (limit {max:.2%})", where=where)


def limb_profile(a, sky_frac=0.04, reach=24, step=1.0):
    """The mean brightness (over the body's lit level) at each distance 1..reach px outside the lit body's edge, on
    the sides that face black sky; and the far sky's level the same way. None when there is no such edge."""
    import cv2
    import numpy as np
    lum = luminance(a)
    cover = a[..., 3] > 0
    lit = lit_mask(a, 0.25)
    if lit.sum() < 500:
        return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(lit.astype(np.uint8))
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    body = lab == k
    body = cv2.morphologyEx(body.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    level = float(np.percentile(lum[body], 60))
    # distance outside the body, on covered pixels only, away from the picture's edges and from other lit things
    dist = cv2.distanceTransform((~body).astype(np.uint8), cv2.DIST_L2, 5)
    other = cv2.dilate((lit & ~body).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    edge = cv2.erode(cover.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    usable = edge & ~other & ~body
    far = usable & (dist > reach * 2) & (dist < reach * 6)
    if far.sum() < 500:
        return None
    sky = float(np.median(lum[far]))
    if sky > sky_frac * level:      # not black sky (a glow, a ring plane behind): nothing to judge
        return None
    prof = []
    for d in np.arange(1, reach + 1, step):
        ring = usable & (dist > d - 0.5) & (dist <= d + 0.5)
        if ring.sum() < 50:
            return None
        prof.append(float(lum[ring].mean()))
    return np.array(prof) / max(level, 1.0), sky / max(level, 1.0)


@check("limb_halo", kinds=("still", "composite"), default=False,
       about="a glow ring or a black gap then a grainy halo just past a lit limb on black sky (#574)")
def limb_halo(p, limit=0.02):
    """Past the body's lit edge the sky should fall to black and stay there. The value is the largest rise of the
    sky's brightness going outward (each distance against the darkest one nearer the limb), over the body's lit level:
    a halo outside a dark gap scores its height; a clean limb scores about 0."""
    import numpy as np
    f = p.main()
    got = limb_profile(p.load(f))
    if got is None:
        return Result(None, limit, True, "no lit limb on black sky to judge", where=f)
    prof, sky = got
    lows = np.minimum.accumulate(prof)
    rise = float((prof - lows).max())
    at = int(np.argmax(prof - lows)) + 1
    return Result(rise, limit, rise <= limit,
                  f"sky rises {rise:.3f} of the body's level {at} px past the limb (far sky {sky:.3f})", where=f)
