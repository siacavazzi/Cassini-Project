"""The items each pass phase of each unit of a farm plan takes (prebuild.chosen, as farm.py runs it), and a digest of
every pass's whole record.  listing_check.py PLAN OUT [--unit NAME]   (run from the checkout under test)
Without --unit: every unit in one process. With --unit: that unit alone, as a build process lists it (main's scope)."""
import argparse, hashlib, json, sys, time
sys.path.insert(0, "web/frames")
import numpy as np
import prebuild

ap = argparse.ArgumentParser(); ap.add_argument("plan"); ap.add_argument("out"); ap.add_argument("--unit")
a = ap.parse_args()
plan = json.load(open(a.plan))


def canon(x):
    if isinstance(x, dict):
        return {str(k): canon(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (set, frozenset)):
        return sorted(repr(canon(v)) for v in x)
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    if isinstance(x, np.generic):
        return canon(x.item())
    if isinstance(x, np.ndarray):
        return ["ndarray", str(x.dtype), list(x.shape), hashlib.sha1(np.ascontiguousarray(x).tobytes()).hexdigest()]
    if isinstance(x, float):
        return repr(x)
    return x


def args_for(unit, phase):
    return argparse.Namespace(phase=phase, only=None, years=unit.get("years"), since=unit.get("from"), until=unit.get("until"))


out, t0 = {}, time.time()
for unit in plan["units"]:
    if a.unit and unit["unit"] != a.unit:
        continue
    if a.unit and hasattr(prebuild, "scoped"):   # as main sets it
        ua = args_for(unit, "mosaics")
        prebuild._scope[0] = (prebuild.spans_of(ua), ua.only)
    got = {}
    for phase in ("mosaics", "movies", "strips", "chains"):
        got[phase] = [name for name, _ in prebuild.chosen(args_for(unit, phase))]
    names = set(n for v in got.values() for n in v)
    recs = {"_".join(map(str, u["key"])): hashlib.sha1(json.dumps(canon(u), sort_keys=True).encode()).hexdigest()
            for u in prebuild.all_passes() if "_".join(map(str, u["key"])) in names}
    # watched-first's order and the stretches' sizes too, as procs --balanced works them out
    order = {}
    for phase in ("mosaics", "movies"):
        todo, n = prebuild.watched_first(prebuild.chosen(args_for(unit, phase)))
        order[phase] = [[name for name, _ in todo], n]
    out[unit["unit"]] = {"items": got, "passes": recs, "watched": order, "listed": len(prebuild.all_passes())}
json.dump(out, open(a.out, "w"))
print(f"{len(out)} unit(s), {time.time() - t0:.1f} s, {sum(len(v['passes']) for v in out.values())} pass records", flush=True)
