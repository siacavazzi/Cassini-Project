"""
Processing-level checks: the camera window's Full level against its Processed level (PRs 575/576, the level bar).

On a still, Full and Processed are the same picture (/frames/processed/<ID>.webp). On a pass played as a movie they
are not: Processed is the frame on its own display scale (frame_server.processed_webp), Full is the pass's movie frame
(obs_mosaic.movie_frame), the same tile drawn on the pass's one display scale (pass_scale, tile_scale), sometimes a
held frame of another filter. Sam 11-19, 2017 build: going Raw to Processed looks good, then Full looks completely
different, with another black level and vertical banding seen nowhere else. Where the pass's black sits under a frame's
own sky, the sky comes up gray and its fixed column pattern shows as stripes (tile_scale's "veil").

  full_black   how far the Full frame's sky floor sits over the Processed frame's (levels of 255)
  full_banding how much more column banding the Full frame's sky has than the Processed frame's (levels of 255)

Both compare each played movie frame (frameNNN.webp) with the commit's own Processed picture of the frame it shows
(its report's "held", else itself), measured at build time by the collect hook (the Processed picture itself is not
kept). Up to SAMPLE frames of a pass are measured, spread over it.
"""
from bench_checks import Result, check

SAMPLE = 16          # frames of a movie measured (evenly spread)
SKY_SHARE = 30       # percentile of the covered pixels under which a pixel counts as sky (the darker part of the frame)
BAND_SMOOTH = 31     # px: column means minus their running mean over this many columns is the banding
MIN_COVER = 2000     # covered pixels a picture needs to be judged


def measure(rgba):
    """{floor, band, n} of one picture (RGBA uint8): floor the 10th percentile of the covered pixels' brightness;
    band the spread (std) of the sky's column means about their running mean; None when too little is covered."""
    import numpy as np
    from scipy.ndimage import uniform_filter1d
    a = np.asarray(rgba)
    if a.ndim == 2:
        a = np.dstack([a, a, a, np.full(a.shape, 255, np.uint8)])
    elif a.shape[2] == 3:
        a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
    lum = a[..., :3].astype(np.float32).mean(axis=2)
    cover = a[..., 3] > 200
    if cover.sum() < MIN_COVER:
        return None
    v = lum[cover]
    floor = float(np.percentile(v, 10))
    sky = cover & (lum <= np.percentile(v, SKY_SHARE))
    cnt = sky.sum(axis=0)
    keep = cnt > max(30, 0.1 * a.shape[0])
    band = None
    if keep.sum() > 2 * BAND_SMOOTH:
        col = (lum * sky).sum(axis=0)[keep] / cnt[keep]
        band = float(np.std(col - uniform_filter1d(col, BAND_SMOOTH)))
    return {"floor": round(floor, 2), "band": None if band is None else round(band, 3), "n": int(cover.sum())}


def _decode(data):
    import io
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))


def _pairs(p):
    """[(frame name, Full measure, Processed measure)] for the movie frames the collect hook measured."""
    got = p.collected("full_black") or {}
    out = []
    for name, proc in (got.get("processed") or {}).items():
        if name not in p.names() or proc is None:
            continue
        full = measure(p.load(name))
        if full is None:
            continue
        out.append((name, full, proc))
    return out, got


def _no_data(got, limit):
    why = (got or {}).get("error") or ("built without the levels collect hook" if not got else "no frame measured")
    return Result(None, limit, True, f"nothing to judge: {why}")


@check("full_black", kinds=("movie",), default=True, owner="processing-level thread",
       about="the Full level's movie frame has a gray black where Processed has black sky (Sam 11-19, 2017 build)")
def full_black(p, limit=20.0):
    """The worst played frame's Full sky floor over its Processed sky floor, in levels of 255."""
    pairs, got = _pairs(p)
    if not pairs:
        return _no_data(got, limit)
    jumps = [(full["floor"] - proc["floor"], name) for name, full, proc in pairs]
    worst, where = max(jumps)
    bad = sum(1 for j, _ in jumps if j > limit)
    return Result(worst, limit, worst <= limit,
                  f"Full sky floor over Processed by up to {worst:.0f} levels ({bad} of {len(jumps)} frames over {limit:.0f})",
                  where=where, values={n: round(j, 1) for j, n in jumps}, judged=len(jumps))


@check("full_banding", kinds=("movie",), default=True, owner="processing-level thread",
       about="vertical banding in the Full level's movie frame that the Processed frame does not show")
def full_banding(p, limit=1.0):
    """The worst played frame's sky column banding at Full over its banding at Processed, in levels of 255."""
    pairs, got = _pairs(p)
    pairs = [(n, f, q) for n, f, q in pairs if f["band"] is not None and q.get("band") is not None]
    if not pairs:
        return _no_data(got, limit)
    more = [(full["band"] - proc["band"], name) for name, full, proc in pairs]
    worst, where = max(more)
    bad = sum(1 for m, _ in more if m > limit)
    return Result(worst, limit, worst <= limit,
                  f"Full sky banding over Processed by up to {worst:.2f} levels ({bad} of {len(more)} frames over {limit})",
                  where=where, values={n: round(m, 3) for m, n in more}, judged=len(more))


@full_black.collect
def _processed_levels(ctx):
    """The commit's own Processed picture (frame_server.processed_webp, as the level bar asks for it: centred where
    the pre-build centres) of the frame each sampled movie frame shows, measured; the picture is not kept."""
    u = ctx.unit
    if u is None or u.get("mosaic") or u.get("kind") == "mosaic_movie":
        return None
    import os
    frames = u["frames"]
    n = len(frames)
    picks = sorted({round(i * (n - 1) / max(1, SAMPLE - 1)) for i in range(min(n, SAMPLE))})
    out, centred = {}, getattr(ctx.prebuild, "centred", lambda _id: None)
    for j in picks:
        name = f"frame{j:03d}.webp"
        if not os.path.exists(os.path.join(ctx.out, name)):
            continue
        # (the frame this movie frame shows: its report's "held", from the movie frame as the benchmark made it,
        # kept in the cache, so asking again makes nothing)
        try:
            again = ctx.om.movie_webp(frames[j][1], ctx.size, ctx.cache, 0, True, wait=True, ahead=0, centre=True)
            rep = (again[1] if isinstance(again, tuple) else None) or {}
        except Exception:   # noqa: BLE001
            rep = {}
        shown = rep.get("held") or frames[j][1]
        try:
            made = ctx.fs.processed_webp(shown, ctx.size, ctx.cache, centre=centred(shown))
            data = made[0] if isinstance(made, tuple) else made
            out[name] = dict(measure(_decode(data)) or {}, shown=shown) if data else None
        except Exception as e:   # noqa: BLE001  (that frame unmeasured; the others stand)
            out[name] = None
            out.setdefault("_errors", []).append(f"{shown}: {type(e).__name__}: {e}"[:200])
    errors = out.pop("_errors", None)
    return {"processed": out, **({"errors": errors} if errors else {})}


# the 2017 ring movie Sam saw it on: the rings' dark side, IR3's pass black under zero, its frames gray and striped at
# Full (sky level 5 at Processed, 151 at Full); five frames, so it costs little
ITEMS = [{"name": "platdark270-movie", "kind": "pass", "frame": "N1871348495_1", "group": "hard",
          "watch": "rings' dark side, 2017: the Full level's movie frames on black sky like the Processed frames, no gray "
                   "veil, no vertical stripes (full_black, full_banding)"}]
