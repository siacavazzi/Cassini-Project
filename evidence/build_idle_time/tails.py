"""From a finished build's per-process status files (the last unit each slot built): how much of each phase's
process time was spent after a process ran out of work (idle tail) and how much was not making items (start-up, waits)."""
import glob, json, os, sys, collections
for root in sys.argv[1:]:
    for slot in sorted(glob.glob(os.path.join(os.path.expanduser(root), "slot*"))) or [os.path.expanduser(root)]:
        by = collections.defaultdict(list)
        for f in glob.glob(os.path.join(slot, "status-*-*of*.json")):
            s = json.load(open(f))
            if s.get("state") == "done":
                by[s["phase"]].append(s)
        line = []
        for ph in ("frames", "composites", "processed", "mosaics", "movies", "strips", "chains"):
            ps = by.get(ph)
            if not ps: continue
            t0, t1 = min(p["started"] for p in ps), max(p["updated"] for p in ps)
            n, wall = len(ps), max(p["updated"] for p in ps) - min(p["started"] for p in ps)
            tail = sum(t1 - p["updated"] for p in ps)
            made = sum(p["made_s"] for p in ps)
            line.append(f"{ph[:5]} {wall:6.0f}s x{n}: tail idle {100 * tail / (n * wall):4.1f}%, making {100 * made / (n * wall):4.1f}%, items {sum(p['done'] for p in ps)}")
        print(os.path.basename(os.path.dirname(slot + '/')) if False else slot.replace(os.path.expanduser('~'), '~'))
        for l in line: print("   ", l)
