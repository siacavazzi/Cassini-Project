"""tossup_check.py CACHE NAME: for a built toss-up movie pass, the mosaic-so-far picture a fresh process (a server)
asks for at each frame, and whether the build made it."""
import os, sys
wt = os.environ["WT"]; sys.path.insert(0, os.path.join(wt, "web", "frames"))
import prebuild, calibration, obs_mosaic
cache, name = sys.argv[1], sys.argv[2]
u = next(u for u in prebuild.all_passes() if "_".join(map(str, u["key"])) == name)
print(name, "kind", u.get("kind"), "tossup", u.get("tossup"), "mosaic", u["mosaic"], "frames", len(u["frames"]))
have = miss = none = 0
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    there = set(os.listdir(os.path.join(obs_mosaic.drawn(u, cache), "1024"))) if os.path.isdir(os.path.join(obs_mosaic.drawn(u, cache), "1024")) else set()
    print(len([f for f in there if f.endswith('.webp') and not f.endswith('.hdr.webp')]), "mosaic pictures at 1024 in the cache")
    for j in range(len(u["frames"])):
        made = obs_mosaic.layout(u, j, cache)
        if not made:
            none += 1; continue
        p = obs_mosaic._mosaic_path(u, made, 1024, cache)
        ok = os.path.exists(p) or obs_mosaic.is_blank(p)
        have += ok; miss += not ok
        if not ok and miss <= 4:
            print("  frame", j, "asks for", os.path.basename(p)[:90], "- not in the cache")
print(f"asked by a fresh process: {have} found, {miss} not made, {none} with no mosaic yet")
