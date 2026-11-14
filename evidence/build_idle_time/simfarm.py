"""Simulates farm.py run's unit hand-out for the full build's plan: when each slot runs dry, and what the idle tail costs."""
import heapq, sys
W = [25965,24182,22957,20897,20867,19301,19128,18591,18502,18140,17965,16946,16800,16750,16678,16203,15626,15229,14894,14720,13971,13888,13503,13326,11759,3161,1725,343]
def sim(units, slots, regroup=False, overhead=0.0):
    """slots: [(machine, speed of the machine)], units heaviest first; regroup: a machine's free slots' share goes to its busy ones.
    overhead: fixed work per unit (same units as weight), per slot. Returns (end, per-slot ends)."""
    per = {}
    for m, s in slots: per[m] = per.get(m, 0) + 1
    left = sorted(units, reverse=True)
    # event simulation with rates that change when a machine's slot runs dry
    state = [{"m": m, "sp": s, "rem": 0.0, "busy": False, "end": 0.0} for m, s in slots]
    t = 0.0
    for st in state:
        if left: st["rem"] = left.pop(0) + overhead; st["busy"] = True
    while any(st["busy"] for st in state):
        def rate(st):
            n = sum(1 for x in state if x["m"] == st["m"] and x["busy"]) if regroup else per[st["m"]]
            return st["sp"] / n
        dt = min(st["rem"] / rate(st) for st in state if st["busy"])
        rates = {id(st): rate(st) for st in state if st["busy"]}
        t += dt
        for st in state:
            if st["busy"]:
                st["rem"] -= rates[id(st)] * dt
                if st["rem"] < 1e-9:
                    if left: st["rem"] = left.pop(0) + overhead
                    else: st["busy"] = False; st["end"] = t
    return t, [(st["m"], round(st["end"], 2)) for st in state]
total = sum(W); slots = [("mbp", 2.2)] * 3 + [("mini", 1.0)] * 2
ideal = total / 3.2
for name, units in (("plan (28 units)", W), ("units halved (56)", [w / 2 for w in W for _ in (0, 1)]), ("units in four (112)", [w / 4 for w in W for _ in range(4)])):
    for regroup in (False, True):
        end, ends = sim(units, slots, regroup)
        print(f"{name:20s} regroup={regroup!s:5}  end {end / ideal:.3f} x ideal   slots end at " + " ".join(f"{m}:{e / ideal:.2f}" for m, e in ends))
