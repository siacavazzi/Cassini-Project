"""How much of a pass phase's process time is idle at its end (processes out of stretches while the longest pass runs),
for the full build's 28 units, work taken as a pass's frames (prebuild.stretches' own measure)."""
import sys, json, heapq
sys.path.insert(0, "web/frames")
import prebuild, slices
plan = json.load(open(sys.argv[1]))
P = prebuild.all_passes()
def spans_of(u):
    if u.get("years"): return slices.parse_years(u["years"])
    return [(slices.utc(u["from"]), slices.utc(u["until"]))]
def sim(work, procs, balance):
    each = sum(work) / max(1, procs * balance)
    parts, start, w = [], 0, 0
    for k, x in enumerate(work):
        if k > start and w >= each:
            parts.append(w); start, w = k, 0
        w += x
    if start < len(work): parts.append(w)
    parts.sort(reverse=True)
    free = [0.0] * procs; heapq.heapify(free)
    for p in parts:
        t = heapq.heappop(free); heapq.heappush(free, t + p)
    end = max(free)
    return end, sum(work) / procs, max(work) if work else 0
tot = {}
for kind, pick in (("mosaics", lambda u: u["mosaic"] or u.get("kind") == "mosaic_movie"), ("movies", lambda u: u.get("kind") == "movie" or (u.get("movie") and not u["mosaic"]))):
    for procs in (6, 5):
        for balance in (8, 32, 64, 128):
            E = I = 0.0; worst = []
            for unit in plan["units"]:
                cuts = [(slices.seconds(a) if a else -1e99, slices.seconds(b) if b else 1e99) for a, b in spans_of(unit)]
                work = [len(u["frames"]) for u in P if pick(u) and any(a <= f[3] < b for f in u["frames"] for a, b in cuts)]
                if not work: continue
                end, ideal, big = sim(work, procs, balance)
                E += end; I += ideal; worst.append((end / ideal, unit["unit"], big, round(ideal)))
            worst.sort(reverse=True)
            print(f"{kind:8s} procs {procs} balance {balance:2d}: phase time {E / I:.3f} x ideal over the 28 units; worst " + ", ".join(f"{n} {r:.2f} (biggest pass {b} frames, ideal {i})" for r, n, b, i in worst[:3]))
