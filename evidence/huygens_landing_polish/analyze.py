"""Reads a step.cjs log and prints where the camera moves fast or jumps while the picture is visible.
    python3 analyze.py OUT.json [FPS]
"""
import json
import math
import sys

d = json.load(open(sys.argv[1]))
FPS = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
log = [r for r in d["log"] if r["T"] is not None]


def sub(a, b): return [a[i] - b[i] for i in range(3)]
def norm(a): return math.sqrt(sum(x * x for x in a))
def unit(a): n = norm(a) or 1; return [x / n for x in a]
def ang(a, b): return math.degrees(math.acos(max(-1, min(1, sum(x * y for x, y in zip(unit(a), unit(b)))))))


rows = []
for i in range(1, len(log)):
    a, b = log[i - 1], log[i]
    ra, rb = sub(a["cam"], a["sub"]), sub(b["cam"], b["sub"])
    rows.append(dict(T=b["T"], focus=b["focus"], black=b["black"], turn=ang(a["dir"], b["dir"]) * FPS, orbit=ang(ra, rb) * FPS,
                     dist=norm(rb) * 1.4959787e8 * 1e3 if False else norm(rb), dz=(norm(rb) / (norm(ra) or 1e-30)) ** FPS, sx=b["sx"], sy=b["sy"],
                     dsx=(b["sx"] - a["sx"]) * FPS, dsy=(b["sy"] - a["sy"]) * FPS, read=b["read"]))

print("caps:")
for t, c in d["caps"]:
    print(f"  {t:6.2f}  {c[:150]}")
print("sound calls:")
for t, k, a in d["snd"]:
    if k == "chord" or True:
        pass
last = None
for t, k, a in d["snd"]:
    key = (k, a if k == "chord" else ("on" if a != "[0]" else "off"))
    if key != last:
        print(f"  {t if t is None else round(t, 2)}  {k} {a}")
        last = key

print("\nper second (visible = black < 0.5): turn deg/s (view direction), orbit deg/s (camera around subject), zoom x/s, subject on screen")
sec = {}
for r in rows:
    sec.setdefault(int(r["T"]), []).append(r)
for s in sorted(sec):
    rs = sec[s]
    vis = [r for r in rs if r["black"] < 0.5] or rs
    print(f"  {s:4d} {rs[-1]['focus'][:4]} black {max(r['black'] for r in rs):.2f}  turn {max(r['turn'] for r in vis):7.1f}  orbit {max(r['orbit'] for r in vis):7.1f}  "
          f"zoom {min(r['dz'] for r in vis):6.2f}..{max(r['dz'] for r in vis):6.2f}  dist {rs[-1]['dist'] * 1e6:9.1f}  sub ({rs[-1]['sx']:+.2f},{rs[-1]['sy']:+.2f})  "
          f"dsub {max(abs(r['dsx']) + abs(r['dsy']) for r in vis):5.2f}  {rs[-1]['read'][:60]}")

print("\njumps while visible (one frame): turn > 3 deg or subject moved > 0.05 of the screen or distance changed > 4%")
for i in range(1, len(log)):
    a, b = log[i - 1], log[i]
    if min(a["black"], b["black"]) > 0.9:
        continue
    t = ang(a["dir"], b["dir"]); ds = abs(b["sx"] - a["sx"]) + abs(b["sy"] - a["sy"])
    ra, rb = norm(sub(a["cam"], a["sub"])), norm(sub(b["cam"], b["sub"]))
    if t > 3 or ds > 0.05 or abs(rb / (ra or 1e-30) - 1) > 0.04:
        print(f"  T {b['T']:7.2f} black {b['black']:.2f} focus {a['focus']}->{b['focus']} turn {t:6.2f} deg  dsub {ds:.3f}  dist x{rb / (ra or 1e-30):.3f}")
print("\nafter:", json.dumps(d["after"]))
