"""ring_fit_time.py CACHE_CLONE NAME: the time a pass's whole-pass ring fit takes in this checkout (WT), on a built
pass's tiles: the clone's kept ring and solve files are removed, the pass's last layout is asked (as solve_places
does), and obs_mosaic.ring_places is timed where it is called (CPU seconds of this process, calls, tiles searched).
Prints the answers' digest too, so two checkouts can be seen to give the same fits."""
import glob, hashlib, json, os, sys, time, tracemalloc
wt = os.environ["WT"]; sys.path.insert(0, os.path.join(wt, "web", "frames"))
import prebuild, calibration, obs_mosaic as om
cache, name = sys.argv[1:3]
u = next(u for u in prebuild.all_passes() if "_".join(map(str, u["key"])) == name)
folder = glob.glob(os.path.join(cache, "obs-*", name + "*"))[0]
for f in sorted(set(glob.glob(os.path.join(folder, "*global*.json")) + glob.glob(os.path.join(folder, "rings-*.json")))):
    os.remove(f)
real = om.ring_places
spent = {"cpu": 0.0, "calls": 0, "tiles": 0, "digest": hashlib.sha1(), "held": 0.0}
MEM = "--mem" in sys.argv   # the most ring_places holds at once (Python's and numpy's allocations), over what was held before it


def timed(u_, tiles, picture, fixed=None, ref=None):
    t0 = time.process_time()
    if MEM:
        before = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
    out, made = real(u_, tiles, picture, fixed=fixed, ref=ref)
    if MEM:
        spent["held"] = max(spent["held"], (tracemalloc.get_traced_memory()[1] - before) / 1e6)
    spent["cpu"] += time.process_time() - t0
    spent["calls"] += 1
    spent["tiles"] += len(out)
    spent["digest"].update(json.dumps({str(k): v for k, v in sorted(out.items())}, sort_keys=True).encode())
    if made is not None:
        spent["digest"].update(made.tobytes())
    return out, made


om.ring_places = timed
if MEM:
    tracemalloc.start()
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    t0 = time.process_time()
    made = om.layout(u, len(u["frames"]) - 1, cache)
    whole = time.process_time() - t0
ring = glob.glob(os.path.join(folder, "rings-*rings1*.json"))
kept = json.load(open(ring[0]))["tiles"] if ring else {}
print(f"{name}: {len(u['frames'])} tiles; ring_places {spent['cpu']:.1f} CPU s in {spent['calls']} call(s) on {spent['tiles']} tiles "
      f"({spent['cpu'] / max(1, spent['tiles']):.2f} s a tile); the layout {whole:.1f} s; "
      f"fitted {sum(1 for v in kept.values() if len(v) > 3 and v[3])}, no match {sum(1 for v in kept.values() if v[2] <= -1)}; "
      f"answers {spent['digest'].hexdigest()[:12]}" + (f"; most held inside ring_places {spent['held']:.0f} MB" if MEM else ""))
