"""solve_replay.py MAIN_CACHE_CLONE NAME: a toss-up movie pass's layouts as main's pre-build works them out, a frame
at a time on the tiles so far (the clone's kept solves and mosaics are removed first, its tiles stay), against the
layout of the whole pass. For each tile: where it was when it was first drawn into the growing mosaic (the solve on
the tiles up to it) and where the whole-pass solve puts it. The mosaic names of the replay are checked against the
pictures main's build left (MAIN_BUILT: the build's own cache, read only), to show the replay is that build's order.
  WT=checkout python solve_replay.py CLONE NAME MAIN_BUILT"""
import glob, json, math, os, shutil, sys
wt = os.environ["WT"]; sys.path.insert(0, os.path.join(wt, "web", "frames"))
import prebuild, calibration, obs_mosaic as om
cache, name, built = sys.argv[1:4]
u = next(u for u in prebuild.all_passes() if "_".join(map(str, u["key"])) == name)
n = len(u["frames"])
folder = glob.glob(os.path.join(cache, "obs-*", name + "*"))[0]
for f in sorted(set(glob.glob(os.path.join(folder, "*global*.json")) + glob.glob(os.path.join(folder, "rings-*.json"))
                    + glob.glob(os.path.join(folder, "under*.json")))):
    os.remove(f)
shutil.rmtree(os.path.join(folder, "seams10-blend-level"), ignore_errors=True)
bf = glob.glob(os.path.join(built, "obs-*", name + "*"))[0]
have = set(os.listdir(os.path.join(bf, "seams10-blend-level", "1024"))) if os.path.isdir(os.path.join(bf, "seams10-blend-level", "1024")) else set()
first, names, found = {}, [], 0
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    for j in range(n):
        made = om.layout(u, j, cache)
        if not made:
            names.append(None)
            continue
        p, tiles, rect = made[0], made[1], made[2]
        path = om._mosaic_path(u, made, 1024, cache)
        nm = os.path.basename(path)
        names.append(nm)
        found += nm in have
        for t in tiles:
            if "offset" in t and t["n"] not in first:
                first[t["n"]] = (j, t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1])
        last = {t["n"]: (t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1]) for t in tiles if "offset" in t}
s = 1024 / max(rect[2], rect[3])
print(f"{name}: {n} frames; the replay's mosaic names found among the pictures main's build made: {found} of {sum(x is not None for x in names)}")
print(f"1,024 px view = {s:.4f} px a reference px")
print("| tile | first drawn at frame | where the solve on the tiles so far put it (ref px) | where the whole pass's solve puts it | baked off by, ref px | off by, px of the 1,024 view |")
print("|---|---|---|---|---|---|")
worst, moved = 0.0, 0
for k in sorted(first):
    j, x, y = first[k]
    fx, fy = last[k]
    d = math.hypot(fx - x, fy - y)
    worst = max(worst, d * s); moved += d > 0.005
    print(f"| {k} | {j + 1} | {x:.2f}, {y:.2f} | {fx:.2f}, {fy:.2f} | {x - fx:+.2f}, {y - fy:+.2f} | {(x - fx) * s:+.2f}, {(y - fy) * s:+.2f} |")
print(f"{moved} of {len(first)} tiles were first drawn somewhere else than the whole pass's solve puts them; the furthest {worst:.2f} px of the 1,024 px view")
