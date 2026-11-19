"""
Colour checks: a colour picture or sequence drawn gray (gray_colour: Titan cloud watches in black and white, June
2004 Saturn with no colour, colour sets dropped to gray because a channel did not line up), and a colour cast on a
body that should be near neutral (body_tint: orange icy moons).
"""
from bench_checks import Result, chroma, check, lit_mask
from bench_checks.movies import played

GRAY = 0.01       # chroma under this: the picture is gray (a colour picture of Saturn or a moon sits at 0.02-0.6)


def _pictures(p, every=1):
    """The pictures that show the item: a movie's played frames, else its main picture(s)."""
    if "movie" in p.kinds:
        shown, _ = played(p)
        return shown[::every]
    names = [f for f in ("composite.webp", "mosaic.webp", "rolling.webp", "still.webp") if f in p.names()]
    return names[:1]


@check("gray_colour", kinds=("composite", "movie", "mosaic", "mosaic_movie"), default=("composite",),
       about="a picture or sequence that should be in colour is drawn gray (black and white)")
def gray_colour(p, max_gray=0.0, expect="colour"):
    """The share of the item's shown pictures that are gray (chroma under GRAY), held to max_gray. Composites run it
    by default (a colour composite drawn gray is the defect); a pass names it when it should play in colour."""
    pics = _pictures(p)
    if not pics:
        return Result(None, max_gray, True, "no picture")
    vals = {}
    for f in pics:
        c = chroma(p.load(f))
        vals[f] = None if c is None else round(c, 4)
    judged = [v for v in vals.values() if v is not None]
    if not judged:
        return Result(None, max_gray, True, "nothing lit")
    gray = sum(v < GRAY for v in judged) / len(judged)
    why = {p.report(f).get("grey") for f in pics if p.report(f).get("grey")}
    return Result(gray, max_gray, gray <= max_gray,
                  f"{gray:.0%} of {len(judged)} pictures gray (median chroma {sorted(judged)[len(judged) // 2]:.3f})"
                  + (f"; the pipeline says: {', '.join(sorted(map(str, why)))}" if why else ""),
                  where=next((f for f, v in vals.items() if v is not None and v < GRAY), None))


@check("body_tint", kinds=("still", "composite", "movie", "mosaic"), default=False,
       about="a colour cast on a body that should be near neutral (orange icy moons)")
def body_tint(p, limit=0.06, rgb=(1.0, 1.0, 1.0)):
    """On the body's lit disk (the lit pixels from its 30th to its 95th brightness percentile, away from the dark limb
    and terminator and from white): the largest |ln| of red over green and blue over green, against the expected
    ratios rgb. Enceladus drawn [1.12, 1.01, 0.77] (the orange cast, #570) scores 0.27; near gray scores under 0.05."""
    import numpy as np
    f = p.main()
    a = p.load(f)
    m = lit_mask(a, 0.2)
    if m.sum() < 200:
        return Result(None, limit, True, "body too small to judge")
    lum = a[..., :3].astype(np.float32).mean(axis=2)
    lo, hi = np.percentile(lum[m], [30, 95])
    use = m & (lum >= lo) & (lum <= hi) & (a[..., :3].max(axis=2) < 250)
    if use.sum() < 100:
        return Result(None, limit, True, "no unclipped disk to judge")
    r, g, b = (float(a[..., k][use].astype(np.float64).mean()) for k in range(3))
    er, eg, eb = rgb
    val = max(abs(np.log((r / g) / (er / eg))), abs(np.log((b / g) / (eb / eg))))
    return Result(val, limit, val <= limit, f"disk colour R:G:B {r / g:.2f}:1:{b / g:.2f} (expected {er / eg:.2f}:1:{eb / eg:.2f})",
                  where=f)
