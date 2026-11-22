"""
Mosaic checks: a mosaic movie that lacks a panel most of the time (missing_panel: two tiles of its raster drawn in
one slot, so each lap's second one takes the first one's place), and a pass that is not built as the kind of pass it
should be (not_mosaic: a mosaic drawn as a movie or a stare).
"""
from bench_checks import Result, check

TWICE = 2   # a pair of pointings the camera steps straight between this often is two tiles of the raster, not a drift


@check("missing_panel", kinds=("mosaic", "mosaic_movie"), default=True, owner="mosaic thread", worse_by=0.0,
       about="a mosaic movie with a panel missing most of the time: two tiles of the raster share one slot "
             "(Sam 11-18, 2017-09-08 north pole map)")
def missing_panel(p, limit=0):
    """The pairs of pointings, a tile's step or more apart, that the camera steps straight between lap after lap
    (two tiles) but that the commit's slots draw as one (the newer wipes the older out). Kept at build time from the
    pass's pointings by the collect hook."""
    got = p.collected("missing_panel")
    if got and got.get("kind") is not None and got["kind"] != "mosaic_movie":
        return Result(0, limit, True, f"a {got['kind']}, not a mosaic movie: one slot a tile")
    if not got or got.get("pairs") is None:
        return Result(None, limit, False, "no slots kept for this pass (the collect hook found no mosaic movie)")
    pairs = got["pairs"]
    n = len(pairs)
    return Result(n, limit, n <= limit,
                  f"{n} pairs of tiles the camera steps between {TWICE}+ times drawn in one slot "
                  f"({got['slots']} slots for {got['pointings']} pointings)",
                  where=", ".join(f"{f} {a}/{b}" for f, a, b in pairs[:4]) or None, judged=got.get("steps"))


@missing_panel.collect
def _slots(ctx):
    """With the commit's own code: the pass's pointings (frames a tile's step apart, mosaic.min_step, from the geometry
    the pass holds), the steps between them in time order, and which of those pairs the commit's slots merge."""
    u = ctx.unit
    if u is None:
        return None
    if u.get("kind") != "mosaic_movie" or not u.get("z"):
        return {"kind": u.get("kind"), "pairs": None}
    import collections
    import mosaic
    step = mosaic.min_step * ctx.om.FRAME
    slots = ctx.om.slots(u)
    # each filter's pointings on their own, and the steps between one frame of a filter and its next: a scan that
    # creeps while it takes its filters (the camera riding a UVIS slew, 000SA AURORAA011: six filters a third of a
    # frame apart at each of two places) puts each filter somewhere else at one place, and stepping from one
    # filter's frame to the next filter's is that creep, not a step between tiles of the raster
    seen, pointing = collections.defaultdict(list), []
    for fr in u["frames"]:
        x, y, z = fr[5:8]
        if not z:
            pointing.append(None)
            continue
        f = fr[2]
        pt = (-x * z / u["z"], -y * z / u["z"])
        # the nearest pointing of the filter seen so far within a tile's step, else a new one (the newest copy: a
        # drift is followed)
        best = None
        for i, q in enumerate(seen[f]):
            d = max(abs(pt[0] - q[0]), abs(pt[1] - q[1]))
            if d < step and (best is None or d < best[0]):
                best = (d, i)
        if best is None:
            seen[f].append(pt)
            pointing.append((f, len(seen[f]) - 1))
        else:
            seen[f][best[1]] = pt
            pointing.append((f, best[1]))
    stepped, wiped, prev = collections.Counter(), collections.Counter(), {}
    for j, at in enumerate(pointing):
        if at is None:
            continue
        f, i = at
        before = prev.get(f)
        if before is not None and i != before[0]:
            pair = (f, min(i, before[0]), max(i, before[0]))
            stepped[pair] += 1
            # the step lands in the slot the filter's frame before it is in: the newer tile takes the older one's place
            if slots[j] is not None and slots[j] == before[1]:
                wiped[pair] += 1
        prev[f] = (i, slots[j])
    pairs = sorted(q for q, k in stepped.items() if k >= TWICE and wiped[q] >= TWICE)
    return {"kind": "mosaic_movie", "pairs": [list(q) for q in pairs], "pointings": max((len(v) for v in seen.values()), default=0),
            "slots": len({s for s in slots if s is not None}), "steps": sum(stepped.values())}


@check("not_mosaic", kinds=("movie", "mosaic", "mosaic_movie"), default=False, owner="mosaic thread", worse_by=0.0,
       about="a pass that should build as a mosaic (or mosaic movie) built as a movie or a stare")
def not_mosaic(p, expect=("mosaic", "mosaic_movie"), limit=0):
    """1 when the commit built the item's pass as another kind than the item expects (meta pass_kind), else 0."""
    kind = (p.meta or {}).get("pass_kind")
    bad = int(kind not in tuple(expect))
    return Result(bad, limit, bad <= limit, f"built as {kind!r}, expected one of {list(expect)}")


ITEMS = [
    {"name": "npole0908-mosaicmovie", "kind": "pass", "frame": "W1883571253_1", "group": "hard",
     "watch": "a panel missing most of the time: the 2x2's columns are half a frame apart and were drawn as one slot",
     "checks": {"missing_panel": {}, "not_mosaic": {"expect": ["mosaic_movie"]}}},
]
