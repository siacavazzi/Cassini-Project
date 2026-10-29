"""A movie whose frames come closer than REPEAT_GAP keeps them apart (repeat_window), so obs_mosaic.units splits its
frames again after _judge placed them; every frame must still have a place (u["place"]), a slot and a lap, or so_far
and the mosaic movie rules index past the end. TITAN ISS_209TI_CLOUD002_PRIME (N1792936427_1, 2026-10-29) raised
IndexError in so_far's lap_of(u)[n]: 30 tiles, 11 places. Run: python web/test_movie_repeat_places.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pass_grouping import Obs, units, om, kinds  # (runs that file's checks first: the grouping stays as it was)

# a stare at Titan, one filter every 30 s, creeping a hundredth of a frame each time: repeats at 120 s, its own
# window 15 s
m = Obs("ISS_209TI_CLOUD002_PRIME")
for k in range(30):
    m.frame(("CL1", "CB3"), (0.01 * k, 0.0), dt=30)
us = units(m)
bad = []
for name, passes in us.items():
    for u in passes:
        n = len(u["frames"])
        lens = {"place": len(u["place"]), "slots": len(om.slots(u)), "lap_of": len(om.lap_of(u))}
        print(name, u["kind"], u["repeat_gap"], n, lens)
        if any(v != n for v in lens.values()):
            bad.append((name, n, lens))
        # what so_far reads for its label at the pass's last tile
        om.lap_of(u)[min(n - 1, len(u["frames"]) - 1)]
stare = us[m.name]
assert kinds(stare) == [("movie", 30)], kinds(stare)
assert stare[0]["repeat_gap"] < om.mosaic_benchmark.REPEAT_GAP
assert not bad, bad
print("ok")
