"""Movies show complete colour sets and no empty frames (fix plan PR 7, group G; movie spot check round 4):

1. A movie that plays in colour opens on its first complete colour set (set_of): no grey lead-in frames while the
   filters come in (2000 Jupiter, 2004 Saturn approach: 2 to 43 grey frames), and a set updates only once every one
   of its channels is in and shown (a blank or partial member leaves the set before it up).
2. A movie with one colour set among many frames of its grey filter (a Titan cloud watch: CB3 every step, one RED,
   GRN, BL1 set part way) plays its grey filter (plays_colour), and a short run of other filters between them shows
   the grey filter's frame beside it (step_frame): one filter a step, not a strobe of looks.
3. A frame with nothing lit (empty: the 2009 south pole movie's sky past the limb, stretched to a grey square; the
   plume movie's blank GRN frame) or with lines lost past MOVIE_LOST is not shown: the frame before it holds.
4. A colour mosaic movie: a lap's set at a place counts only copies that can be drawn (set_laps: a copy SPICE could not
   place leaves the lap before it up whole), places lie over one another a whole set at a time, and the film opens on
   its first whole colour picture (colour_start).
5. The page's sets (_colour_by) are movie_frame's, and the steady table's "step" is step_frame's (steady-local.html
   shownOf).
Run: python web/test_movie_complete_sets.py"""
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

placed = {"offset": [0.0, 0.0], "box": [-512, -512, 1024, 1024]}


def fr(fs, gap=70):
    return [(f"p{i}", f"N{1600000000 + i}_1", f, 1000.0 + gap * i, 600, 0, 0, 1e6) for i, f in enumerate(fs)]


def unit(fs, gap=70, kind="movie"):
    return {"key": ("TITAN", "OBS", "N", 0), "frames": fr(fs, gap), "z": 1e6, "movie": True, "mosaic": False, "kind": kind}


# ---------- 3. empty and patchy frames ----------
assert om.empty({**placed, "floor": 30, "top": 40})                    # a grey square of sky
assert not om.empty({**placed, "floor": 2, "top": 200})                # a lit body on black sky
assert not om.empty({**placed, "floor": 180, "top": 190})              # a featureless disk filling the frame
assert not om.empty({**placed})                                        # made before the levels were kept
assert not om.empty({"floor": 30, "top": 40})                          # not placed: held as unplaced, not as empty
assert om.patchy({**placed, "lost": 0.05}) and not om.patchy({**placed, "lost": 0.01})
frames = fr(["CL1/CL2"] * 5)
tiles = [dict(placed), dict(placed), {**placed, "floor": 25, "top": 31}, {**placed, "lost": 0.2}, dict(placed)]
tile_of = lambda j: tiles[j]
held = [om.held_of([f[2] for f in frames], n, lambda j: om.unfit(frames, j, tile_of),
                   lambda j: not om.unfit(frames, j, tile_of)) for n in range(5)]
assert held == [0, 1, 1, 1, 4], held
# a grey square among frames of its filter that show the scene (141EN PLMHPHR001's frames 18-23: levels 23-75
# against 0-160 either side) is blank; a pass dimming steadily is not
span = lambda lo, hi: {**placed, "floor": lo, "top": hi}
frames = fr(["GRN", "RED", "GRN", "RED", "GRN"])
tiles = [span(0, 163), span(0, 160), span(23, 75), span(0, 150), span(0, 150)]
assert [om.blank_frame(frames, n, lambda j: tiles[j]) for n in range(5)] == [False, False, True, False, False]
tiles = [span(0, 200), span(0, 160), span(0, 90), span(0, 150), span(0, 40)]
assert not any(om.blank_frame(frames, n, lambda j: tiles[j]) for n in range(5))
print("empty, blank and lost-line frames hold the frame before them; ok")

# ---------- 1. a colour movie opens on its first complete set; sets update whole ----------
# a lead-in of grey frames, then RED GRN BL1 sets (each within SET_GAP)
u = unit(["CL1/CL2", "CL1/CL2", "CL1/CL2", "RED", "GRN", "BL1", "RED", "GRN", "BL1"], gap=20)
want = ["RED", "GRN", "BL1"]
assert om.plays_colour(u, want, "CL1/CL2")
ok = lambda j: True
none = lambda j: False
assert [sorted(om.set_of(u, n, want, none, ok).values()) for n in range(9)] == \
    [[3, 4, 5]] * 8 + [[6, 7, 8]], [om.set_of(u, n, want, none, ok) for n in range(9)]
# the second set's GRN blank (not shown): the first set stays up to the end
bad = lambda j: j == 7
assert [sorted(om.set_of(u, n, want, bad, ok).values()) for n in range(9)] == [[3, 4, 5]] * 9
# its RED not placed by SPICE: the same
assert [sorted(om.set_of(u, n, want, none, lambda j: j != 6).values()) for n in range(9)] == [[3, 4, 5]] * 9
# the newest set does not take in frame n's place (the camera moved on): the next set does, if it covers it
assert sorted(om.set_of(u, 6, want, none, ok, lambda got: min(got.values()) >= 6).values()) == [6, 7, 8]
assert om.set_of(u, 6, want, none, ok, lambda got: False) is None
print("colour from the first frame, sets whole; ok")

# ---------- 2. one filter a step ----------
# 167TI CLOUD001: CB3 three times a cycle and MT1, one RED GRN BL1 set part way: plays CB3
cloud = unit(["CB3", "CB3", "CB3", "MT1"] * 5 + ["MT2", "MT3", "UV3", "CB1", "CB2", "BL1", "GRN", "RED"] + ["CB3", "CB3", "CB3", "MT1"] * 2)
assert not om.plays_colour(cloud, want, "CB3")
# 125TI CLOUD002: one visit, three CB3 among ten filters: its one set is the film
visit = unit(["MT3", "CB3", "CB3", "CB3", "MT1", "CB1", "GRN", "BL2", "MT2", "CB2", "RED", "BL1"])
assert om.plays_colour(visit, want, "CB3")
# a Titan wind stare (Sam 2026-10-30): a set every cycle plays in colour
wind = unit(["CB3", "MT1", "UV1", "CB3", "CB3"] * 3, gap=20)
assert om.plays_colour(wind, ["CB3", "MT1", "UV1"], "CB3")
fs = [f[2] for f in unit(["MT1", "CB3", "CB3", "CB3"] * 3)["frames"]]          # 273TI LRMONITOR002
whole, near = (lambda j: True), (lambda j: True)
assert [om.step_frame(fs, s, "CB3", whole, near) for s in range(12)] == [1, 1, 2, 3, 3, 5, 6, 7, 7, 9, 10, 11]
# a long run of another filter plays as it is (a filter-by-filter pass, C39IC COMPCHECK001)
fs = ["BL1"] * 3 + ["RED"] * (om.STEP_RUN + 1) + ["BL1"] * 3
assert [om.step_frame(fs, s, "BL1", whole, near) for s in range(len(fs))] == list(range(len(fs)))
# the grey frame beside it must cover the frame's place, and be whole
fs = ["CB3", "MT1", "CB3"]
assert om.step_frame(fs, 1, "CB3", whole, lambda j: j == 2) == 2
assert om.step_frame(fs, 1, "CB3", lambda j: j != 0, near) == 2
assert om.step_frame(fs, 1, "CB3", whole, lambda j: False) == 1
a, b = {"offset": [0.0, 0.0], "box": [0, 0, 100, 100]}, {"offset": [60.0, 0.0], "box": [0, 0, 100, 100]}
assert om.box_cover(a, a) == 1.0 and abs(om.box_cover(a, b) - 0.4) < 1e-9
print("one filter a step; ok")

# ---------- the movie frames themselves (movie_frame on a synthetic pass), and the page's sets ----------
cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, "BL1": 1.0}}
seq = ["CL1/CL2", "CL1/CL2", "RED", "GRN", "BL1", "RED", "GRN", "BL1"]
u = {"key": ("JUPITER", "LEADIN", "W", 0), "frames": fr(seq, gap=20), "z": 1e6, "movie": True, "mosaic": False,
     "kind": "movie", "last": 2000}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for i, f in enumerate(seq):
    im = np.zeros((1448, 1448, 4), np.uint8)
    im[..., 3] = 255
    im[400:1000, 400:1000, :3] = {"RED": 150, "GRN": 110, "BL1": 70, "CL1/CL2": 200}[f]
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": u["frames"][i][1], "filter": f, "t": u["frames"][i][3], "offset": [0.0, 0.0],
               "box": [-724, -724, 1448, 1448], "floor": 0, "top": 200}, open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-724, -724, 724, 724], "fixed": True,
           "view": [1448, 1448], "k": 1, "colour": want, "grey": "CL1/CL2", "whole": False},
          open(os.path.join(d, om.PLAN_FILE), "w"))
om.movie_footprint = lambda u, cache, p=None: [-724, -724, 724, 724]
with calibration.looking("balanced"):
    reps = [om.movie_frame(u, n, cache, centre=False)[1] for n in range(len(seq))]
    assert all(r.get("color") == want for r in reps), [r.get("color") for r in reps]
    assert [r["ids"] for r in reps] == [[u["frames"][j][1] for j in (2, 3, 4)]] * 7 + [[u["frames"][j][1] for j in (5, 6, 7)]]
    # colour off: every frame its own
    assert all("held" not in om.movie_frame(u, n, cache, colour=False, centre=False)[1] for n in range(len(seq)))
    p = om.plan(u, cache)
    tiles = {n: om.tile(u, n, cache, scale) for n in range(len(seq))}
    by = om._colour_by(u, want, list(range(len(seq))), tiles, p["grey"])
    assert by == {str(n): [2, 3, 4] for n in range(7)} | {"7": [5, 6, 7]}, by
print("movie frames and the page's sets open on the first set; ok")

# ---------- 4. colour mosaic movies ----------
sys.argv = [sys.argv[0]]
OFFS = [(-380, -380), (380, -380)]
SCALE = {"blacks": {}, "white": 1, "gamma": 2.2}


def make_pass(name, seq, colour, grey, lost=()):
    cache = tempfile.mkdtemp()
    frames = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 20 * i, 600, -OFFS[q][0], -OFFS[q][1], 1e6) for i, (f, q) in enumerate(seq)]
    u = {"key": ("JUPITER", name, "N", 0), "frames": frames, "z": 1e6, "movie": False, "mosaic": True, "last": frames[-1][3],
         "place": [q for _, q in seq], "kind": "mosaic_movie", "repeats": 2}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, (f, q) in enumerate(seq):
        im = np.full((1024, 1024, 4), 255, np.uint8)
        im[..., :3] = {"CL1/CL2": 160, "RED": 170, "GRN": 130, "BL1": 90}[f]
        Image.fromarray(im).save(f"{td}/{i}.png")
        t = {"n": i, "id": frames[i][1], "filter": f, "t": frames[i][3], "offset": list(map(float, OFFS[q])), "box": [-512, -512, 1024, 1024]}
        if i in lost:
            t["lost"] = 0.6
        json.dump(t, open(f"{td}/{i}.json", "w"))
    plan = {"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-900, -900, 900, 900], "fixed": True,
            "view": [1800, 1800], "k": 1024 / 1800, "colour": colour, "grey": grey, "whole": False,
            "luminance": {"filters": [grey] + sorted({f for f, _ in seq} - {grey}), "gains": {}}}
    json.dump(plan, open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
    return u, cache


# two places, three laps of RED GRN BL1 at each; lap 2's GRN at place 0 (frame 7) came down partial
seq = [(f, q) for _ in range(3) for q in range(2) for f in ("RED", "GRN", "BL1")]
u, cache = make_pass("SETS2", seq, want, "RED", lost=(7,))
report = lambda j: om.tile(u, j, cache, SCALE)
held = om.set_laps(u, 11, want, report)
assert sorted(j for (slot, _), j in held.items() if slot == u["place"][0]) == [0, 1, 2], held    # lap 1's whole set
assert sorted(j for (slot, _), j in held.items() if slot == u["place"][3]) == [9, 10, 11], held
held = om.set_laps(u, 14, want, report)
assert sorted(j for (slot, _), j in held.items() if slot == u["place"][0]) == [12, 13, 14], held  # lap 3's
# without the reports (the old rule), the lap with the partial copy counts
assert sorted(j for (slot, _), j in om.set_laps(u, 11, want).items() if slot == u["place"][0]) == [6, 7, 8]
drawn = lambda n: sorted(t["n"] for t in om.rolling_layout(u, n, cache)[1] if t["filter"] in want)
assert drawn(11) == [0, 1, 2, 9, 10, 11], drawn(11)
# the film opens on its first whole colour picture: both places' sets in (frame 5)
assert om.colour_start(u, want, report) == 5
assert all(drawn(n) == [0, 1, 2, 3, 4, 5] for n in range(6)), [drawn(n) for n in range(6)]
# places lie over one another a whole set at a time: a raster taken a filter at a time across the places
seq = [(f, q) for _ in range(2) for f in ("RED", "GRN", "BL1") for q in range(2)]
u, cache = make_pass("RASTER", seq, want, "RED")
order = [t["n"] for t in om.rolling_layout(u, len(seq) - 1, cache)[1] if t["filter"] in want]
rank = {j: max(k for k in order if seq[k][1] == seq[j][1]) for j in order}
assert [rank[j] for j in order] == sorted(rank[j] for j in order), order
print("mosaic movies: whole sets of drawable copies, opening on colour; ok")

# ---------- 5. the page's frame shown (steady-local.html shownOf, from the steady table's "step") ----------
import subprocess  # noqa: E402
cache = tempfile.mkdtemp()
seq = ["MT1", "CB3", "CB3", "CB3"] * 3
u = {"key": ("TITAN", "STEPS", "N", 0), "frames": fr(seq), "z": 1e6, "movie": True, "mosaic": False, "kind": "movie", "last": 2000}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for i, f in enumerate(seq):
    im = np.zeros((1448, 1448, 4), np.uint8)
    im[..., 3] = 255
    im[400:1000, 400:1000, :3] = 120 if f == "CB3" else 60
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": u["frames"][i][1], "filter": f, "t": u["frames"][i][3], "offset": [0.0, 0.0],
               "box": [-724, -724, 1448, 1448], "floor": 0, "top": 120, **({"lost": 0.3} if i == 6 else {})},
              open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-724, -724, 724, 724], "fixed": True,
           "view": [1448, 1448], "k": 1, "colour": None, "grey": "CB3", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))
om._steady_ready = lambda *a: True
om._exposure_ready = lambda *a: False
om.warm_movie = lambda *a, **k: None
om.steady_chain = lambda u, cache, p=None: {n: [0.0, 0.0] for n in range(len(seq))}
with calibration.looking("balanced"):
    reps = [om.movie_frame(u, n, cache, centre=True)[1] for n in range(len(seq))]
    server = [[q[1] for q in u["frames"]].index(r.get("held", r["id"])) for r in reps]
    assert server == [1, 1, 2, 3, 3, 5, 5, 7, 7, 9, 10, 11], server     # 6 lost: CB3 5 held
    for colour in (True, False):
        table = om._steady_table(u, 0, cache, True, colour)
        page = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
        script = page[page.index("<script>") + 8:page.index("</script>")]
        js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), t = " + json.dumps(table) + ";\n"
              "console.log(JSON.stringify(t.n.map(n => M.shownOf(t, n, " + json.dumps(colour) + "))));")
        page_shown = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        if colour:
            assert page_shown == server, (page_shown, server)
        else:
            # colour off: every filter's own frame (the planes a colour set is mixed from), partial ones held
            assert page_shown == [0, 1, 2, 3, 4, 5, 5, 7, 8, 9, 10, 11], page_shown
            assert [[q[1] for q in u["frames"]].index(om.movie_frame(u, n, cache, colour=False, centre=True)[1].get("held", u["frames"][n][1]))
                    for n in range(len(seq))] == page_shown
print("the page shows the frame the server does; ok")
print("ok")
