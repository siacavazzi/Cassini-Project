import sys, collections
sys.path.insert(0, "web/frames")
import prebuild
P = [u for u in prebuild.all_passes() if u["mosaic"] or u.get("kind") in ("mosaic_movie", "movie") or u.get("movie")]
n = [len(u["frames"]) for u in P]
tot = sum(n)
print(len(P), "mosaic and movie passes,", tot, "frames; median pass", sorted(n)[len(n) // 2], "frames, largest", max(n))
for k in (8, 16, 24, 32, 48, 64, 96, 128):
    print(f"first {k:3d} frames of each pass: {100 * sum(min(x, k) for x in n) / tot:5.1f}% of all pass frames; passes wholly within: {100 * sum(x for x in n if x <= k) / tot:5.1f}% of frames")
