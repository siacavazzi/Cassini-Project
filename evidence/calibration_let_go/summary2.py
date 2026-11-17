#!/usr/bin/env python3
"""summary2.py BASE_DIR VARIANT_DIR: as summary.py, with each pass's instructions retired (/usr/bin/time -l), a count
of the work done that does not move with the machine's load as CPU seconds do on a shared Mac."""
import hashlib, json, os, re, sys
base, var = sys.argv[1], sys.argv[2]
P = {p["name"]: p for p in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", "passes.json")))}


def times(d):
    out = {}
    for l in open(os.path.join(d, "times.txt")):
        w = l.split()
        t = open(os.path.join(d, "log", f"{w[0]}-{w[1]}.time")).read()
        out[(w[0], w[1])] = {"cpu": float(w[5]), "peak": int(w[8]), "exit": int(w[3]), "errors": int(w[11]),
                             "instr": int(re.search(r"(\d+)\s+instructions retired", t).group(1)) / 1e9}
    return out


def files(root, name):
    out = {}
    for d, _, fs in os.walk(root):
        rel = os.path.relpath(d, root)
        if any(part.startswith(name) for part in rel.split(os.sep)):
            for f in fs:
                out[os.path.join(rel, f)] = os.path.join(d, f)
    return out


def digest(p):
    h = hashlib.sha1()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


tb, tv = times(base), times(var)
sb = sv = cb = cv = 0.0; nf = nd = 0; n = 0
print("| pass | kind | frames | instructions, main (billions) | this branch | change | CPU s, main | this branch | peak memory MB, main | this branch | files compared | identical |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for key in tb:
    if key not in tv:
        continue
    name, phase = key
    fa, fb = files(os.path.join(base, "cache"), name), files(os.path.join(var, "cache"), name)
    both = sorted(set(fa) & set(fb))
    differ = [p for p in both if os.path.getsize(fa[p]) != os.path.getsize(fb[p]) or digest(fa[p]) != digest(fb[p])]
    only = sorted(set(fa) ^ set(fb))
    b, v = tb[key], tv[key]
    sb += b["instr"]; sv += v["instr"]; cb += b["cpu"]; cv += v["cpu"]; nf += len(both); nd += len(differ) + len(only); n += 1
    p = P.get(name, {})
    kind = ("toss-up " if p.get("tossup") else "") + ("mosaic movie" if p.get("kind") == "mosaic_movie" else "mosaic" if p.get("in_mosaics") else "movie")
    ident = "all" if not differ and not only else f"{len(both) - len(differ)} ({len(differ)} differ, {len(only)} in one only)"
    print(f"| {name} | {kind} | {p.get('n', '')} | {b['instr']:.0f} | {v['instr']:.0f} | {100 * (v['instr'] - b['instr']) / b['instr']:+.1f}% | {b['cpu']:.0f} | {v['cpu']:.0f} | {b['peak']} | {v['peak']} | {len(both)} | {ident} |")
    for q in (differ + only)[:8]:
        print(f"|  |  |  |  |  |  |  |  |  |  | {'differs' if q in differ else 'in one only'}: {q[-100:]} |  |")
print(f"| **{n} passes** |  |  | **{sb:.0f}** | **{sv:.0f}** | **{100 * (sv - sb) / sb:+.1f}%** | {cb:.0f} | {cv:.0f} |  |  | {nf} | {'**all**' if not nd else str(nf - nd)} |")
