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


def limb_rises(a, reach=48, rays=720):
    """For each ray from the lit body's centre that leaves the body inside the picture: the largest rise of brightness
    going outward over the reach px past the body's edge (each point against the darkest one nearer the limb), over
    the body's lit level, on rays whose sky further out (reach to 2 reach px) is black. (array of rises, rays judged,
    rays skipped because the sky out there is lit) or None when the picture has no lit body or no ray leaves it."""
    import cv2
    import numpy as np
    from scipy.ndimage import map_coordinates
    lum = cv2.GaussianBlur(luminance(a), (0, 0), 1.0)
    cover = cv2.erode((a[..., 3] > 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    lit = lit_mask(a, 0.25)
    if lit.sum() < 500:
        return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(lit.astype(np.uint8))
    # the body: the brightest lit area of any size (a wide glow ring round it can be larger, and must not be taken
    # for it), its edge closed over a few px
    big = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 200] or [1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))]
    k = max(big, key=lambda i: float(np.percentile(lum[lab == i], 90)))
    body = cv2.morphologyEx((lab == k).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    level = max(float(np.percentile(lum[body], 60)), 1.0)
    cy, cx = np.argwhere(body).mean(axis=0)
    H, W = lum.shape
    r = np.arange(0, 2 * max(H, W), 1.0)
    out, lit_sky = [], 0
    for t in np.linspace(0, 2 * np.pi, rays, endpoint=False):
        ys, xs = cy + r * np.sin(t), cx + r * np.cos(t)
        inside = (ys >= 0) & (ys < H - 1) & (xs >= 0) & (xs < W - 1)
        ys, xs = ys[inside], xs[inside]
        on = body[ys.astype(int), xs.astype(int)]
        if not on.any():
            continue
        e = int(np.nonzero(on)[0][-1]) + 1            # the first sample past the body's last edge on this ray
        if e + reach + 2 >= len(ys):
            continue
        yy, xx = ys[e:e + reach * 2], xs[e:e + reach * 2]
        if not cover[yy.astype(int), xx.astype(int)].all():
            continue
        prof = map_coordinates(lum, [yy, xx], order=1) / level
        if prof[reach:].mean() > 0.04:                 # not black sky out there (rings, a glow, another body)
            lit_sky += 1
            continue
        prof = prof[:reach]
        out.append(float((prof - np.minimum.accumulate(prof)).max()))
    if not out and not lit_sky:
        return None
    return np.array(out), len(out), lit_sky


@check("limb_halo", kinds=("still", "composite"), default=False,
       about="a glow ring or a black gap then a grainy halo just past a lit limb on black sky (#574)")
def limb_halo(p, limit=0.08, share=0.75):
    """Past the body's lit edge the sky should fall to black and stay there. Per ray out of the body into black sky,
    the largest rise of brightness going outward (a glow ring past a black gap), over the body's lit level; the value
    is the rise that share of the rays stay under (a halo along a stretch of the limb, not one star). A ray whose sky
    further out is lit is not judged: they are counted (judged = rays judged), so a wide glow that lights the sky past
    the limb, leaving few rays or none to judge, fails against a base judged on many (bench_checks.verdict)."""
    import numpy as np
    f = p.main()
    got = limb_rises(p.load(f))
    if got is None:
        return Result(None, limit, True, "no lit body with a limb in the picture", where=f, judged=0)
    rises, n, lit_sky = got
    if not n:
        return Result(None, limit, True, f"no ray past the limb reaches black sky ({lit_sky} rays lit out there)",
                      where=f, judged=0)
    v = float(np.quantile(rises, share))
    return Result(v, limit, v <= limit,
                  f"{share:.0%} of {n} rays past the limb rise at most {v:.3f} of the body's level outward "
                  f"({(rises > limit).mean():.0%} over {limit}; {lit_sky} rays not judged, sky lit out there)",
                  where=f, judged=n)
