"""Steady movies on this computer (Settings > Processing, steady-local.html) give the server's stabilized and
exposure-normalized movie frames: the page's arithmetic (cassiniSteadyMath, run here in node) works out the same
places as obs_mosaic.steady_places and the same whole-pixel move of the tile as _place, and the frame drawn at SPICE's
places (steady 0, what the pre-build has) moved by it is the frame the server draws stabilized, pixel for pixel, but
for the strip along the view's edge a moved tile uncovers. Exposure: the page's gains (exposure_gains, evened_gains)
and lookup tables (_shade) are the server's, and the steady-0, exposure-0 frame moved and put through the table is
the frame the server draws with both. Then both through WebP (q95, as served): how far apart the
browser's picture and the server's are. Synthetic pass as web/test_movie_stabilize.py (one textured field the camera
creeps across, SPICE a few px off each frame).
Run: python web/test_steady_local.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import io, json, re, subprocess, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(5)
field = cv2.GaussianBlur(rng.random((2200, 1400)).astype(np.float32), (0, 0), 5)
field = (field - field.min()) / (field.max() - field.min())
S, N = 500, 40
cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, "BL1": 1.0}}
truth = [(300 + 6.0 * n, 400 + 2.0 * n) for n in range(N)]
spice = [[x + rng.uniform(-9, 9), y + rng.uniform(-9, 9)] for x, y in truth]
fr = [(f"p{n}", f"N{1600000000 + 30 * n}_1", "CL1", 30.0 * n, 600, 0, 0, 1e6) for n in range(N)]
u = {"key": ("MIMAS", "ISS_TEST_LOCAL", "N", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
     "track": False, "kind": "movie", "last": fr[-1][3]}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for n, (x, y) in enumerate(truth):
    crop = cv2.warpAffine(field, np.float32([[1, 0, x], [0, 1, y]]), (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    # a flash at frame 9, a step up from frame 25 (what exposure normalization evens)
    im[..., :3] = np.clip(crop * 170 * (1.6 if n == 9 else 1.25 if n >= 25 else 1.0), 0, 255).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": "CL1", "t": fr[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [0, 0, 1800, 1100], "fixed": True,
           "view": [1800, 1100], "k": 1, "colour": None, "grey": "CL1", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))

# a colour pass: RED, GRN, BL1 over and over (natural colour, the NAC's mix), each filter as bright as it is
FILTERS = ["RED", "GRN", "BL1"]
fr2 = [(f"q{n}", f"N{1600100000 + 30 * n}_1", FILTERS[n % 3], 30.0 * n, 600, 0, 0, 1e6) for n in range(N)]
u2 = {"key": ("MIMAS", "ISS_TEST_LOCALC", "N", 0), "frames": fr2, "z": 1e6, "movie": True, "mosaic": False,
      "track": False, "kind": "movie", "last": fr2[-1][3]}
d2, TD2 = om.folder(u2, cache), om._tiles(u2, cache, scale)
os.makedirs(TD2, exist_ok=True)
for n, (x, y) in enumerate(truth):
    crop = cv2.warpAffine(field, np.float32([[1, 0, x], [0, 1, y]]), (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    level = {"RED": 210, "GRN": 170, "BL1": 120}[FILTERS[n % 3]] * (1.5 if n in (13, 14, 15) else 1.0)
    im[..., :3] = np.clip(crop * level, 0, 255).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD2}/{n}.png")
    json.dump({"n": n, "id": fr2[n][1], "filter": FILTERS[n % 3], "t": fr2[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD2}/{n}.json", "w"))
json.dump({"key": list(u2["key"]), "display_scale": scale, "angle": 0, "footprint": [0, 0, 1800, 1100], "fixed": True,
           "view": [1800, 1100], "k": 1, "colour": FILTERS, "grey": "RED", "whole": False}, open(os.path.join(d2, om.PLAN_FILE), "w"))

# the page's arithmetic, as the page has it
page = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = page[page.index("<script>") + 8:page.index("</script>")]
SMOOTHS = (4, 12, 60)
EXPOSURES = (2, 8, 30)
LUTS = [(g / 200, gm) for g in range(50, 801, 7) for gm in (2.2, 1.8, 2.5, "srgb")]
# made-up brightness chains: flashes, steps, stretches of grey frames in a colour pass, short stretches
crng = np.random.default_rng(7)
CHAINS = []
for c in range(12):
    logs, stretch, colour = {}, 0, bool(c % 2)
    for n in range(int(crng.integers(1, 90))):
        if crng.random() < 0.08:
            stretch += 1
        logs[str(n)] = [round(float(crng.normal(0, 0.3) + (0.8 if crng.random() < 0.05 else 0)), 5), stretch,
                        colour and stretch % 3 != 0]
    CHAINS.append({"logs": logs, "flash": om.EXPOSURE_FLASH, "gain": om.EXPOSURE_GAIN, "greyRun": om.EXPOSURE_GREY_RUN})


def server_gains(chain, smooth):
    """om.exposure_gains on a given chain (its measurement swapped for the chain)."""
    kept = om.exposure_chain
    om.exposure_chain = lambda *a, **k: {int(n): v for n, v in chain["logs"].items()}
    try:
        return {str(n): g for n, g in om.exposure_gains(u, cache, {"display_scale": scale}, smooth).items()}
    finally:
        om.exposure_chain = kept


def server_lut(g, gm):
    one = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(4, axis=2)
    return om._shade(one, {"gain": g, "gamma": gm})[0, :, 0].tolist()


def in_node(table):
    js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), t = " + json.dumps(table) + ";\n"
          "const out = {};\nfor (const s of " + json.dumps(SMOOTHS) + ") { const p = M.places(t, s); "
          "out[s] = { places: p, shifts: t.n.map((_, a) => M.shift(t, p, a)) }; }\n"
          "const r = []; for (const x of [0.125, -0.125, 2.5, -2.5, 1.5, -1.5, 0.375, 1.005, 2.675, -3.14159]) r.push([x, M.pyRound(x), M.pyRound2(x)]);\n"
          "out.gains = {}; for (const x of " + json.dumps(EXPOSURES) + ") out.gains[x] = t.exposure ? M.gains(t.exposure, x) : null;\n"
          "out.chains = " + json.dumps(CHAINS) + ".map(c => " + json.dumps(EXPOSURES) + ".map(x => M.gains(c, x)));\n"
          "out.luts = " + json.dumps(LUTS) + ".map(([g, gm]) => Array.from(M.lut(g, gm)));\n"
          "out.rounding = r;\nconsole.log(JSON.stringify(out));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def webp(a):
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").save(buf, "WEBP", quality=om.QUALITY, method=4)
    return np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGBA"))


def moved(a, dx, dy):
    """a's picture drawn dx, dy canvas pixels over (what the page's worker draws: drawImage(bitmap, dx, dy))."""
    out = np.zeros_like(a)
    H, W = a.shape[:2]
    out[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] = a[max(-dy, 0):H - max(dy, 0), max(-dx, 0):W - max(dx, 0)]
    return out


with calibration.looking("balanced"):
    om.steady_chain(u, cache)
    for centre in (True, False):
        table = om._steady_table(u, 0, cache, centre)
        if not table.get("local"):
            print(f"centre={centre}: view follows the frames, the server draws it ({table})")
            continue
        got = in_node(table)
        for x, r0, r2 in got.pop("rounding"):
            assert r0 == round(x) and r2 == round(x, 2), (x, r0, r2, round(x), round(x, 2))
        # exposure: the gains of made-up chains, and every lookup table
        for c, got_c in zip(CHAINS, got.pop("chains")):
            for x, g in zip(EXPOSURES, got_c):
                assert g == server_gains(c, x), (x, c)
        for (g, gm), lut in zip(LUTS, got.pop("luts")):
            assert lut == server_lut(g, gm), (g, gm)
        worst = {"exact": 0, "edge": 0, "psnr": []}
        for s in SMOOTHS:
            want = om.steady_places(u, cache, smooth=s)
            assert [want[n] for n in table["n"]] == got[str(s)]["places"], s
            for a, n in enumerate(table["n"]):
                spiced, _ = om.movie_frame(u, n, cache, colour=False, centre=centre)
                steady, rep = om.movie_frame(u, n, cache, colour=False, centre=centre, steady=s)
                A, B = np.asarray(spiced), np.asarray(steady)
                dx, dy = got[str(s)]["shifts"][a]
                C = moved(A, dx, dy)
                # where the moved frame has picture, it is the server's stabilized frame exactly
                have = C[..., 3] > 0
                same = (C == B).all(axis=2)
                assert same[have].all(), (s, n, int((~same[have]).sum()))
                # what it lacks is the strip the move uncovers (picture the steady-0 view had cut off)
                lack = (B[..., 3] > 0) & ~have
                assert lack.sum() <= (abs(dx) * B.shape[0] + abs(dy) * B.shape[1]), (s, n, int(lack.sum()), dx, dy)
                worst["exact"] += int(have.sum())
                worst["edge"] = max(worst["edge"], int(lack.sum()))
                # as served (both WebP q95): the page moves the decoded steady-0 picture
                Cw, Bw = moved(webp(A), dx, dy).astype(float), webp(B).astype(float)
                m = have & (B[..., 3] > 0)
                mse = ((Cw[m][:, :3] - Bw[m][:, :3]) ** 2).mean()
                worst["psnr"].append(99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse))
        # exposure, with stabilization off and on: the steady-0, exposure-0 frame moved and put through the gain's table
        assert table["exposure"] is None   # the chain is worked out in the background; asked again
        om.exposure_chain(u, cache, None, False, centre, 0)
        table = om._steady_table(u, 0, cache, centre, False)
        assert table["exposure"]["local"], table["exposure"]
        got = in_node(table)
        flat = 0
        for x in EXPOSURES:
            gains = got["gains"][str(x)]
            assert gains == {str(n): g for n, g in om.exposure_gains(u, cache, None, x, False, centre, 0).items()}, x
            flat += sum(g != 1.0 for g in gains.values())
            for s in (0, 12):
                for a, n in enumerate(table["n"]):
                    A = np.asarray(om.movie_frame(u, n, cache, colour=False, centre=centre)[0])
                    B = np.asarray(om.movie_frame(u, n, cache, colour=False, centre=centre, steady=s, exposure=x)[0])
                    dx, dy = got[str(s)]["shifts"][a] if s else (0, 0)
                    C = moved(A, dx, dy)
                    lut = np.array(server_lut(gains[str(n)], table["exposure"]["gamma"]), np.uint8)
                    C[..., :3] = lut[C[..., :3]]
                    have = C[..., 3] > 0
                    # (the server evens every smoothing on the one chain measured at steady 0)
                    assert (C == B)[have].all(), (x, s, n)
        print(f"centre={centre}: exposure gains and lookup tables equal the server's ({flat} frames gained over smoothing "
              f"{EXPOSURES}); the moved, gained frame equals the server's stabilized (0, 12), exposure-normalized frame pixel for pixel")
        print(f"centre={centre}: {table['view']} k={table['k']:.4f}; places and moves equal the server's for smoothing "
              f"{SMOOTHS}; {worst['exact']} pixels equal, at most {worst['edge']} uncovered at an edge; as WebP q95 the "
              f"moved picture is {min(worst['psnr']):.1f} dB (worst) / {np.median(worst['psnr']):.1f} dB (median) from the server's")

def node_mix(cases, sets):
    """The page's colour mix (cassiniSteadyMath.mix) of each case's planes, run in node on the raw bytes."""
    tmp = tempfile.mkdtemp()
    for c, planes in enumerate(cases):
        for q, pl in enumerate(planes):
            pl.tofile(f"{tmp}/{c}_{q}.bin")
    js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), c = " + json.dumps(sets) + ";\n"
          f"for (let i = 0; i < {len(cases)}; i++) {{ const P = [0, 1, 2].map(q => new Uint8ClampedArray(fs.readFileSync('{tmp}/' + i + '_' + q + '.bin')));"
          f" fs.writeFileSync('{tmp}/' + i + '.out', M.mix(P, c)); }}")
    with open(f"{tmp}/mix.js", "w") as fh:
        fh.write(js)
    subprocess.run(["node", f"{tmp}/mix.js"], check=True)
    return [np.fromfile(f"{tmp}/{c}.out", np.uint8).reshape(cases[c][0].shape) for c in range(len(cases))]


with calibration.looking("balanced"):
    # colour: each frame's set of tiles, each moved and gained as above, mixed by the page's port of colour_picture
    om.steady_chain(u2, cache)
    om.exposure_chain(u2, cache, None, True, True, 0)
    table = om._steady_table(u2, 0, cache, True, True)
    assert table["sets"] and table["sets"]["mix"] and table["exposure"]["local"], table.get("sets")
    got = in_node(table)
    cases, wants, alone, labels = [], [], 0, []
    for s, x in ((12, 0), (12, 8)):
        gains = got["gains"][str(x)] if x else {}
        for n in range(N):
            recipe = table["sets"]["by"].get(str(n)) or [n]
            planes = []
            for j in recipe:
                A = np.asarray(om.movie_frame(u2, j, cache, colour=False, centre=True)[0])
                dx, dy = got[str(s)]["shifts"][table["n"].index(j)] if s else (0, 0)
                C = moved(A, dx, dy)
                if gains.get(str(n), 1.0) != 1.0:
                    C[..., :3] = np.array(server_lut(gains[str(n)], table["exposure"]["gamma"]), np.uint8)[C[..., :3]]
                planes.append(C)
            B = np.asarray(om.movie_frame(u2, n, cache, colour=True, centre=True, steady=s, exposure=x)[0])
            if len(planes) == 1:
                assert (planes[0] == B).all(), (s, x, n)
                alone += 1
            else:
                cases.append(planes)
                wants.append(B)
                labels.append((s, x, n, recipe))
    # numpy's 3x3 mix (tensordot) runs through BLAS, whose vector and remainder loops round a few pixels' sums
    # differently by position, and differently again with another BLAS (the Mini's Accelerate): the page sums in
    # order, so a handful of pixels in millions may be a level apart, never more
    off, total = 0, 0
    for out, B, lab in zip(node_mix(cases, table["sets"]), wants, labels):
        diff = np.abs(out.astype(int) - B.astype(int))
        if diff.max() > 1:
            w = np.argwhere(diff > 1)
            print("DIFF", lab, len(w), [(tuple(map(int, i)), int(out[tuple(i)]), int(B[tuple(i)])) for i in w[:4]])
        assert diff.max() <= 1, int(diff.max())
        off += int((diff > 0).sum())
        total += diff.size
    assert off <= total * 1e-6, (off, total)
    print(f"colour: {len(cases)} colour pictures and {alone} frames alone, stabilized (0, 12) and exposure-normalized "
          f"(0, 8): the page's moved, gained and mixed picture equals the server's but for {off} values of {total} a level apart")
def node_trail(table, trails, cases):
    """The page's trail (cassiniSteadyMath.trailOf, then blendTrail over each case's planes, oldest first), in node."""
    tmp = tempfile.mkdtemp()
    for c, planes in enumerate(cases):
        for q, pl in enumerate(planes):
            pl.tofile(f"{tmp}/{c}_{q}.bin")
    js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), t = " + json.dumps(table) + ";\n"
          "const js = {}; for (const T of " + json.dumps(trails) + ") js[T] = t.n.map(n => M.trailOf(t, n, T));\n"
          "fs.writeFileSync('" + tmp + "/js.json', JSON.stringify(js));\n"
          "const L = " + json.dumps([len(c) for c in cases]) + ";\n"
          "L.forEach((k, i) => { const P = []; for (let q = 0; q < k; q++) P.push(new Uint8ClampedArray(fs.readFileSync('" + tmp + "/' + i + '_' + q + '.bin')));"
          " fs.writeFileSync('" + tmp + "/' + i + '.out', M.blendTrail(P.slice(0, -1), P[k - 1])); });")
    with open(f"{tmp}/trail.js", "w") as fh:
        fh.write(js)
    subprocess.run(["node", f"{tmp}/trail.js"], check=True)
    return json.load(open(f"{tmp}/js.json")), [np.fromfile(f"{tmp}/{c}.out", np.uint8).reshape(cases[c][0].shape) for c in range(len(cases))]


with calibration.looking("balanced"):
    # trail: earlier frames of the filter, each moved and gained as above, blended under the newest by the page
    TRAILS = (3, 12)
    table = om._steady_table(u, 0, cache, True, False)
    got = in_node(table)
    order, _ = node_trail(table, TRAILS, [])
    cases, wants, labels = [], [], []
    for s, x in ((0, 0), (12, 8)):
        gains = got["gains"][str(x)] if x else {}
        for T in TRAILS:
            for a, n in enumerate(table["n"]):
                planes = []
                for j in order[str(T)][a] + [n]:
                    A = np.asarray(om.movie_frame(u, j, cache, colour=False, centre=True)[0])
                    dx, dy = got[str(s)]["shifts"][table["n"].index(j)] if s else (0, 0)
                    C = moved(A, dx, dy)
                    if gains.get(str(n), 1.0) != 1.0:
                        C[..., :3] = np.array(server_lut(gains[str(n)], table["exposure"]["gamma"]), np.uint8)[C[..., :3]]
                    planes.append(C)
                im, rep = om.movie_frame(u, n, cache, trail=T, colour=False, centre=True, steady=s, exposure=x)
                assert rep.get("trail", 0) == len(planes) - 1, (s, x, T, n, rep.get("trail"), len(planes) - 1)
                cases.append(planes)
                wants.append(np.asarray(im))
                labels.append((s, x, T, n))
    _, outs = node_trail(table, TRAILS, cases)
    for out, B, lab in zip(outs, wants, labels):
        if not (out == B).all():
            w = np.argwhere(out != B)
            print("DIFF", lab, len(w), [(tuple(map(int, i)), int(out[tuple(i)]), int(B[tuple(i)])) for i in w[:4]])
        assert (out == B).all(), lab
    print(f"trail: {len(cases)} trailed frames (trail {TRAILS}, stabilized and exposure-normalized (0, 0) and (12, 8)): "
          "the page's trail equals the server's pixel for pixel")
print("ok")
