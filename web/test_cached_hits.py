"""Synthetic check that the pictures of a pass already in the cache are answered at the cost of one file each
(obs_mosaic's pass records): played again, every pass mosaic and mosaic movie picture opens only its own picture,
reads no tile report or plan file and starts no background thread, as many stats at the pass's last frame as at its
first; a plan made again (the cache cleared) is read afresh; a tile made by another server sharing the cache is
found. Run: python web/test_cached_hits.py"""
import builtins, collections, json, os, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

cache = tempfile.mkdtemp()
N = 40
SCALE = {"blacks": {}, "white": 1, "gamma": 3}
by_id = {}


def make_pass(name, places=None, made=N):
    """A pass of N frames along a strip (a mosaic, or with places a mosaic movie going round them), its plan and
    its first `made` tiles in the cache as the server leaves them."""
    fr = [(f"p{i}", f"N{1500000000 + 100 * len(by_id) + i}_1", "CB2", 1000.0 + 30 * i, 600, 0, 0, 1e6) for i in range(N)]
    u = {"key": ("JUPITER", name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": 1000 + 30 * N}
    if places:
        u.update(place=[i % places for i in range(N)], kind="mosaic_movie", repeats=N // places)
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i in range(made):
        put_tile(u, td, i, places)
    json.dump({"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-3200, -200, 3200, 200], "fixed": True,
               "view": [6400, 400], "k": 0.1, "colour": None, "grey": "CB2", "whole": False},
              open(os.path.join(om.folder(u, cache), om.PLAN_FILE), "w"))
    for i, f in enumerate(fr):
        by_id[f[1]] = (u, i)
    return u, fr


def put_tile(u, td, i, places=None):
    x = ((i % places) if places else i) * 150.0 - 3000
    im = np.zeros((200, 200, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = 40 + (i * 5) % 200
    Image.fromarray(im).save(f"{td}/{i}.png")
    json.dump({"n": i, "id": u["frames"][i][1], "filter": "CB2", "t": u["frames"][i][3], "offset": [x, 0.0], "box": [-100, -100, 200, 200],
               "outline": [[x - 100, -100], [x + 100, -100], [x + 100, 100], [x - 100, 100]]}, open(f"{td}/{i}.json", "w"))


om.unit_of = lambda fid: by_id.get(fid)


def settle():
    """Waits for the background work (tiles and pictures made ahead, tile maps) to finish."""
    t0 = time.time()
    while threading.active_count() > 1 and time.time() - t0 < 120:
        time.sleep(0.05)
    assert threading.active_count() == 1, threading.enumerate()


# what each request does with the cache: files opened and looked for (by kind), threads started
counts = collections.Counter()
_open, _stat, _start = builtins.open, os.stat, threading.Thread.start


def kind(path):
    p = str(path)
    if not p.startswith(cache):
        return None
    return "tile" if "/tiles-" in p else "plan" if os.path.basename(p).startswith(("plan", "movie_footprint")) else "picture"


def counted_open(f, mode="r", *a, **k):
    if isinstance(f, (str, os.PathLike)) and "r" in mode and kind(f):
        counts["open " + kind(f)] += 1
    return _open(f, mode, *a, **k)


def counted_stat(p, *a, **k):
    if isinstance(p, (str, os.PathLike)) and kind(p):
        counts["stat " + kind(p)] += 1
    return _stat(p, *a, **k)


def counted_start(self):
    counts["threads"] += 1
    return _start(self)


def play(fr, ask):
    """Each frame of the pass asked for in turn, counted: [(frame, counts)]."""
    builtins.open, os.stat, threading.Thread.start = counted_open, counted_stat, counted_start
    try:
        out = []
        for n, f in enumerate(fr):
            counts.clear()
            got = ask(f[1])
            assert got and got[0], (n, got)
            out.append((n, dict(counts)))
        return out
    finally:
        builtins.open, os.stat, threading.Thread.start = _open, _stat, _start


def check(name, rounds):
    for n, c in rounds:
        assert c.get("open picture", 0) <= 1 and not c.get("open tile") and not c.get("open plan"), (name, n, c)
        assert not c.get("threads"), (name, n, c)
    stats = [sum(v for k, v in c.items() if k.startswith("stat")) for _, c in rounds]
    assert max(stats) <= 12 and max(stats[-5:]) <= max(stats[:5]) + 2, (name, stats)
    print(f"{name}: played again, each frame opens {max(c.get('open picture', 0) for _, c in rounds)} file and looks for "
          f"{min(stats)}-{max(stats)}, reads no tile report or plan, starts no thread (first and last frame alike)")


# a pass mosaic: made once in order (the server's first time through), then played again from the cache
u, fr = make_pass("MOSAIC")
for f in fr:
    assert om.mosaic_webp(f[1], 512, cache, ahead=0)
settle()
for f in fr:   # the windows' look-ahead and tile maps as a playing window starts them, made
    om.mosaic_webp(f[1], 512, cache)
settle()
check("pass mosaic", play(fr, lambda fid: om.mosaic_webp(fid, 512, cache)))
check("tile map", [(n, c) for n, c in play(fr, lambda fid: (om.tile_map(fid, cache),))])

# a mosaic movie (8 places, 5 laps): made once (with the pictures made ahead), then played again from the cache
um, frm = make_pass("ROLLING", places=8)
for f in frm:
    assert om.rolling_webp(f[1], 512, cache, 1)[0]
settle()
check("mosaic movie", play(frm, lambda fid: om.rolling_webp(fid, 512, cache, 1)))

# a server started on a cache made earlier (another server, or the pre-built cache): the first time through it reads
# each tile report and the plan once, with a few background workers at a time, and then plays the pass as above
def forget():
    for d in (om._passes, om._grown_last, om._rolled, om._parts, om._centre_views, om._centre_of, om._outlines, om._maps,
              om._made, om._blank, om._upto, om._from, om.reel._reports):
        d.clear()


for name, fr_, ask in (("pass mosaic", fr, lambda fid: om.mosaic_webp(fid, 512, cache)),
                       ("mosaic movie", frm, lambda fid: om.rolling_webp(fid, 512, cache, 1))):
    forget()
    first = play(fr_, ask)
    settle()
    read = collections.Counter()
    for _, c in first:
        read.update(c)
    assert read["open tile"] <= N and read["open plan"] <= 2, (name, dict(read))
    # and asked by six connections at once (a browser), it works ahead with a few workers at a time (tiles,
    # pictures and tile maps, one each per pass), not one per picture waiting its turn
    forget()
    todo, alive = list(fr_), []

    def connection():
        while todo:
            try:
                f = todo.pop(0)
            except IndexError:
                return
            ask(f[1])
            alive.append(threading.active_count() - 7)
    conns = [threading.Thread(target=connection) for _ in range(6)]
    for c in conns:
        c.start()
    for c in conns:
        c.join()
    settle()
    assert max(alive) <= 6, (name, max(alive))
    print(f"{name}, restarted: the first time through reads {read['open tile']} tile reports and the plan "
          f"{read['open plan']} time(s); six connections at once, at most {max(alive)} background thread(s) at a time")
    check(name + ", restarted", play(fr_, ask))

# a plan made again (its folder cleared and the pass worked out anew, here with another footprint) is read afresh
name = om.layout(u, 5, cache)[5]
path = os.path.join(om.folder(u, cache), om.PLAN_FILE)
p = json.load(open(path))
p["footprint"] = [-3300, -200, 3300, 200]
json.dump(p, open(path + ".new", "w"))
os.replace(path + ".new", path)
again = om.layout(u, 5, cache)[5]
assert again != name and again.endswith("_".join(str(round(v)) for v in (-3300, -200, 6600, 400))), (name, again)
print("a plan made again is read afresh:", name, "->", again)

# a tile another server sharing the cache made (not in this server's memory) is found there
uo, fro = make_pass("OTHER", made=N - 1)
p = om.plan(uo, cache)
assert len(om.layout(uo, N - 2, cache)[1]) == N - 1 and not om._has_tile(uo, N - 1, cache, p)
put_tile(uo, om._tiles(uo, cache, SCALE), N - 1)
assert om._has_tile(uo, N - 1, cache, p) and om.layout(uo, N - 1, cache)[3]["CB2"] == N
print("a tile made by another server is found in the cache")
print("ok")
