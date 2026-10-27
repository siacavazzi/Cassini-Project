"""Image stabilization on this computer (Settings > Movie > Stabilize on this computer, steady-local.html) gives the
server's stabilized movie frames: the page's arithmetic (cassiniSteadyMath, run here in node) works out the same
places as obs_mosaic.steady_places and the same whole-pixel move of the tile as _place, and the frame drawn at SPICE's
places (steady 0, what the pre-build has) moved by it is the frame the server draws stabilized, pixel for pixel, but
for the strip along the view's edge a moved tile uncovers. Then both through WebP (q95, as served): how far apart the
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
    im[..., :3] = (crop * 230).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": "CL1", "t": fr[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [0, 0, 1800, 1100], "fixed": True,
           "view": [1800, 1100], "k": 1, "colour": None, "grey": "CL1", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))

# the page's arithmetic, as the page has it
page = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = page[page.index("<script>") + 8:page.index("</script>")]
SMOOTHS = (4, 12, 60)


def in_node(table):
    js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), t = " + json.dumps(table) + ";\n"
          "const out = {};\nfor (const s of " + json.dumps(SMOOTHS) + ") { const p = M.places(t, s); "
          "out[s] = { places: p, shifts: t.n.map((_, a) => M.shift(t, p, a)) }; }\n"
          "const r = []; for (const x of [0.125, -0.125, 2.5, -2.5, 1.5, -1.5, 0.375, 1.005, 2.675, -3.14159]) r.push([x, M.pyRound(x), M.pyRound2(x)]);\n"
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
        print(f"centre={centre}: {table['view']} k={table['k']:.4f}; places and moves equal the server's for smoothing "
              f"{SMOOTHS}; {worst['exact']} pixels equal, at most {worst['edge']} uncovered at an edge; as WebP q95 the "
              f"moved picture is {min(worst['psnr']):.1f} dB (worst) / {np.median(worst['psnr']):.1f} dB (median) from the server's")
print("ok")
