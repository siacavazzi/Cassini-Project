"""
The image benchmark's defect checks (image_bench.py, docs/image-benchmark.md): cheap, objective tests of one item's
pictures for the kinds of defect Sam kept finding by eye in cache builds (a movie that repeats or jumps to another
picture, a colour sequence drawn gray, white blown out, a glow ring past a limb, a colour cast on an icy moon...).

The comparison in image_bench says what changed between two commits. A check says what is wrong in one commit's
pictures, so a defect present on both sides is seen too. Each check runs on the base and on the candidate:
  pass        the candidate passes
  fixed       the candidate passes where the base failed
  known       both fail, the candidate no worse (a defect already on main: listed, never a FAIL by itself)
  REGRESSION  the candidate fails where the base passed, or fails clearly worse: the benchmark's verdict is FAIL
              unless --notes explains the item
  error       the check itself broke on these pictures, on both sides (reported, never a pass); broken, or nothing
              to judge, or far less judged (Result.judged) on the candidate only is a REGRESSION

Adding a check (other threads: one module of your own in this folder, so nothing collides):

    # web/frames/bench_checks/my_area.py
    from bench_checks import check, Result

    @check("my_check", kinds=("movie",), default=True, owner="my thread",
           about="what a failure looks like, in Sam's words")
    def my_check(p, limit=3.0):                 # p: Pictures; keyword arguments: the item's "checks" parameters
        value = ...                             # one number, higher = worse
        return Result(value, limit, value <= limit, "one line: what was measured", where="frame012.webp")

    @my_check.collect                           # optional: runs inside the build, with the commit's own code
    def _(ctx):                                 # ctx.prebuild / ctx.om / ctx.fs / ctx.item / ctx.unit / ctx.cache
        return {"anything": "JSON"}             # kept in the item's meta.json; the check reads p.collected("my_check")

  kinds    which items it can judge: "still", "composite", "movie" (a pass played as a movie), "mosaic" (a finished
           mosaic), "mosaic_movie" (a mosaic movie's rolling picture)
  default  True: runs on every item of those kinds (or a tuple of kinds: by default on those only); False: only on
           items that name it in image_bench_items.json
           ("checks": {"my_check": {"limit": 2.0}}). An item can switch a default check off with {"my_check": false}.
  ITEMS    a module may also add its own items: ITEMS = [{"name": ..., "kind": ..., "frame": ..., "group": "hard",
           "watch": ..., "checks": {...}}] (appended to image_bench_items.json's list; names must be new).

A check judges the pictures only (or what its collect hook kept); it never makes a picture. Changing a collect hook
changes the set key, so cached bases are built again (once); changing how a check judges does not (compare reruns it).
"""
import hashlib
import importlib
import inspect
import json
import os
import pkgutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = {}          # name: Check
LOST_SHARE = 0.5     # a candidate judged on under this share of what the base was judged on is a regression (verdict)
EXTRA_ITEMS = []     # items modules add (ITEMS)
_LOADED = False


class Result:
    """One check's answer on one item: a number (higher = worse), the limit it is held to, pass or not, a line saying
    what was measured, and where (a picture's name, a place)."""

    def __init__(self, value, limit, ok, detail="", where=None, values=None, judged=None):
        self.value = None if value is None else round(float(value), 4)
        self.limit = limit
        self.ok = bool(ok)
        self.detail = detail
        self.where = where
        self.values = values   # optional: per picture numbers, for the report
        self.judged = judged   # optional: how much the check could judge (rays, frames): far fewer than the base's fails

    def as_dict(self):
        d = {"value": self.value, "limit": self.limit, "ok": self.ok, "detail": self.detail}
        if self.where is not None:
            d["where"] = self.where
        if self.values is not None:
            d["values"] = self.values
        if self.judged is not None:
            d["judged"] = self.judged
        return d


class Check:
    def __init__(self, name, fn, kinds, default, owner, about, worse_by):
        self.name, self.fn, self.kinds, self.default = name, fn, tuple(kinds), default
        self.owner, self.about, self.worse_by = owner, about, worse_by
        self.collector = None

    def collect(self, fn):
        self.collector = fn
        return fn

    def __call__(self, *a, **k):
        return self.fn(*a, **k)


def check(name, kinds, default=False, owner="benchmark", about="", worse_by=0.25):
    """Register a check (see the module's notes). worse_by: when both sides fail, the candidate counts as a
    regression if its value is over the base's by this share of the limit (or of the base's value, the larger)."""
    def wrap(fn):
        if name in CHECKS:
            raise ValueError(f"two checks named {name}")
        c = Check(name, fn, kinds, default, owner, about or (fn.__doc__ or "").strip().split("\n")[0], worse_by)
        CHECKS[name] = c
        return c
    return wrap


def load():
    """Import every module of this folder once (each registers its checks and may add ITEMS)."""
    global _LOADED
    if _LOADED:
        return CHECKS
    _LOADED = True
    pkg = sys.modules[__name__]
    for m in sorted(pkgutil.iter_modules([HERE]), key=lambda m: m.name):
        if m.name.startswith("_") or m.name.startswith("test"):
            continue
        mod = importlib.import_module(f"{pkg.__name__}.{m.name}")
        for it in getattr(mod, "ITEMS", []) or []:
            EXTRA_ITEMS.append({**it, "_from": m.name})
    return CHECKS


def collect_key():
    """A short hash of every collect hook's source: results built with other hooks hold other collected data."""
    load()
    h = hashlib.sha256()
    for name in sorted(CHECKS):
        c = CHECKS[name].collector
        if c is not None:
            h.update(name.encode())
            h.update(inspect.getsource(c).encode())
    return h.hexdigest()[:10]


# ---------------------------------------------------------------- which checks an item gets

def item_kinds(item, meta=None):
    """The kinds an item's pictures are, as checks name them."""
    k = item.get("kind")
    if k in ("still", "composite"):
        return {k}
    meta = meta or {}
    pk = meta.get("pass_kind")
    if meta.get("mosaic") or pk == "mosaic":
        return {"mosaic"}
    if pk == "mosaic_movie":
        return {"mosaic_movie"}
    return {"movie"}


def checks_for(item, meta=None):
    """[(Check, params)] for an item: the default checks of its kind and the ones it names; {"name": false} drops one."""
    load()
    asked = item.get("checks") or {}
    kinds = item_kinds(item, meta)
    out = []
    for name, c in sorted(CHECKS.items()):
        p = asked.get(name)
        if p is False:
            continue
        if p is None and not (c.default is True or (c.default and set(c.default) & kinds)):
            continue
        if not (set(c.kinds) & kinds):
            continue
        out.append((c, p if isinstance(p, dict) else {}))
    unknown = sorted(set(asked) - set(CHECKS))
    if unknown:
        raise KeyError(f"{item.get('name')}: no such check {', '.join(unknown)}")
    return out


# ---------------------------------------------------------------- inside the build (the commit's code)

class Ctx:
    def __init__(self, prebuild, om, fs, item, unit, cache, size, out):
        self.prebuild, self.om, self.fs, self.item, self.unit, self.cache, self.size, self.out = \
            prebuild, om, fs, item, unit, cache, size, out


def collect_all(ctx, meta):
    """Each applying check's collect hook, run after the item's pictures are made: {check: data or {"error": ...}}."""
    got = {}
    for c, _ in checks_for(ctx.item, meta):
        if c.collector is None:
            continue
        try:
            got[c.name] = c.collector(ctx)
        except Exception as e:   # noqa: BLE001  (the check says it could not judge; the item stands)
            got[c.name] = {"error": f"{type(e).__name__}: {e}"[:300]}
    return got


# ---------------------------------------------------------------- judging one item's pictures

class Pictures:
    """One item's pictures in a results folder, decoded on demand (RGBA uint8)."""

    def __init__(self, folder, item, meta=None):
        self.folder, self.item = folder, item
        self.meta = meta if meta is not None else json.load(open(os.path.join(folder, "meta.json")))
        self.reports = self.meta.get("reports", {})
        self._cache = {}

    @property
    def kinds(self):
        return item_kinds(self.item, self.meta)

    def names(self, prefix=""):
        return sorted(f for f in os.listdir(self.folder) if f.endswith(".webp") and f.startswith(prefix))

    def frames(self):
        """A movie's frames in order (frameNNN.webp), not the evened copies."""
        return self.names("frame")

    def main(self):
        """The picture that stands for the item: the still, the composite, the finished mosaic, the rolling picture,
        or (a movie) its middle frame."""
        for f in ("still.webp", "composite.webp", "mosaic.webp", "rolling.webp"):
            if os.path.exists(os.path.join(self.folder, f)):
                return f
        fr = self.frames()
        return fr[len(fr) // 2] if fr else None

    def load(self, name):
        if name not in self._cache:
            import numpy as np
            from PIL import Image
            self._cache[name] = np.asarray(Image.open(os.path.join(self.folder, name)).convert("RGBA"))
            if len(self._cache) > 8:   # (a long movie: keep a few)
                self._cache.pop(next(iter(self._cache)))
        return self._cache[name]

    def report(self, name):
        return self.reports.get(name) or {}

    def collected(self, check_name):
        """What the check's collect hook kept for this item at build time (None: built without it)."""
        return (self.meta.get("collected") or {}).get(check_name)


def judge(folder, item, meta=None):
    """{check: result dict} for one item's pictures."""
    p = Pictures(folder, item, meta)
    out = {}
    for c, params in checks_for(item, p.meta):
        try:
            r = c.fn(p, **params)
            out[c.name] = r.as_dict() if r is not None else {"value": None, "ok": True, "detail": "nothing to judge"}
        except Exception as e:   # noqa: BLE001
            out[c.name] = {"value": None, "ok": False, "error": f"{type(e).__name__}: {e}"[:300], "detail": "the check broke"}
    return out


def verdict(name, base, cand):
    """pass / fixed / known / REGRESSION / error for one check, from its result on the base and on the candidate
    (either may be None: the item not built or the check new on that side). A candidate the check breaks on, finds
    nothing to judge in, or judges on far less of the picture than the base (Result.judged under LOST_SHARE of the
    base's), where the base was judged, is a REGRESSION: a blank picture or a glow that hides the limb must never
    read as a pass."""
    if cand is None:
        return "not run"
    judged_base = bool(base) and not base.get("error") and base.get("value") is not None
    if cand.get("error"):
        return "REGRESSION" if judged_base else "error"
    if cand.get("value") is None and judged_base:
        return "REGRESSION"
    jb, jc = (base or {}).get("judged"), cand.get("judged")
    if judged_base and jb and jc is not None and jc < LOST_SHARE * jb:
        return "REGRESSION"
    if cand["ok"]:
        return "fixed" if base and not base.get("ok", True) and not base.get("error") else "pass"
    if not base or base.get("error"):
        return "fail (no base)"
    if base["ok"]:
        return "REGRESSION"
    c = CHECKS.get(name)
    by = c.worse_by if c else 0.25
    b, v, lim = base.get("value"), cand.get("value"), cand.get("limit")
    if b is not None and v is not None:
        margin = by * max(abs(lim) if isinstance(lim, (int, float)) else 0, abs(b))
        if v > b + margin:
            return "REGRESSION"
    return "known"


# ---------------------------------------------------------------- small shared measures

def luminance(rgba):
    import numpy as np
    return rgba[..., :3].astype(np.float32).mean(axis=2)


def lit_mask(rgba, share=0.15, floor=10):
    """Pixels with light in them: covered, and over max(floor, share of the picture's 99.5th percentile)."""
    import numpy as np
    a = rgba[..., 3] > 0
    lum = luminance(rgba)
    if not a.any():
        return a
    top = float(np.percentile(lum[a], 99.5))
    return a & (lum > max(floor, share * top))


def chroma(rgba, mask=None):
    """Mean colour spread (max - min channel) over the mean brightness, on the lit pixels: 0 for a gray picture."""
    import numpy as np
    m = lit_mask(rgba) if mask is None else mask
    if not m.any():
        return None
    rgb = rgba[..., :3].astype(np.float32)
    return float((rgb.max(axis=2) - rgb.min(axis=2))[m].mean() / max(rgb.mean(axis=2)[m].mean(), 1.0))
