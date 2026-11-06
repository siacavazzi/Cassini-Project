"""render.py TREE CACHE OUT NAME SEED [K] [START]: a run of K frames of the seed's movie pass drawn by TREE's own pipeline
(obs_mosaic.movie_webp, the frame server's /frames/movie route; the page's defaults: color on, centred, exposure 8),
saved as OUT/NAME/NNN_<id>.webp with each frame's report in OUT/NAME/log.txt."""
import json, os, sys, time
tree, cache, out, name, seed = sys.argv[1:6]
cache, out = os.path.abspath(cache), os.path.abspath(out)
os.chdir(tree)   # (the pipeline reads some files from the repo root, as the frame server runs)
K = int(sys.argv[6]) if len(sys.argv) > 6 else 30
START = int(sys.argv[7]) if len(sys.argv) > 7 else 0
sys.path.insert(0, os.path.join(tree, "web", "frames"))
import obs_mosaic as om
found = om.unit_of(seed)
u, _ = found
ids = [fr[1] for fr in u["frames"]]
d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
log = open(os.path.join(d, "log.txt"), "w")
print(f"{name} {u['key']} n={len(ids)} run={START}..{START+K-1}", file=log, flush=True)
for k, fid in enumerate(ids[START:START + K]):
    t0 = time.time()
    got = om.movie_webp(fid, 512, cache, colour=True, wait=True, ahead=0, centre=True, exposure=8)
    data, rep = got if got else (None, {"why": "no pass"})
    if data:
        open(os.path.join(d, f"{k:03d}_{fid}.webp"), "wb").write(data)
    print(f"{k:03d} {fid} {u['frames'][START + k][2]} {'ok' if data else 'none'} {time.time() - t0:.1f}s "
          f"{json.dumps({x: rep.get(x) for x in ('color', 'ids', 'tint', 'held') if x in rep})}", file=log, flush=True)
print("done", file=log, flush=True)
