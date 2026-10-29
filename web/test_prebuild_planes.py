"""prebuild.py's movies phase also makes the planes the page's movie steps start from (make_planes): each frame
alone at 1024 (color=0, trail=0), and for a filled pass the same before its detail filter (_d0), under the names the
frame server's movie route looks up for the page's own request (steady-local.html planeUrl, head-quiet.html
movieUrl(id, 1024, 0, 0, 0, 0) + "&detail=0"): asked for afterwards, every one is found, none made. Synthetic
tiles on one still field, one filled pass and one not. Run: python web/test_prebuild_planes.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
from urllib.parse import parse_qs  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402
import prebuild  # noqa: E402

rng = np.random.default_rng(5)
field = cv2.GaussianBlur(rng.random((900, 900)).astype(np.float32), (0, 0), 5)
field = (field - field.min()) / (field.max() - field.min())
S, N = 400, 6
cache = tempfile.mkdtemp()
passes, units = [], {}
FALSE = ["MT3", "MT2", "CB2"]   # a false colour set: the page leaves its exposure normalization to the server
for p, (filled, colour) in enumerate(((True, None), (False, None), (False, FALSE))):
    scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, **{f: 1.0 for f in FALSE}},
             **({"filled": True} if filled else {})}
    fr = [(f"p{n}", f"N{1600000000 + 1000 * p + 30 * n}_1", f, 30.0 * n + 1000 * p, 600, 0, 0, 1e6)
          for n, f in enumerate((colour or ["RED", "GRN"]) * N)][:N]
    u = {"key": ("TITAN" if filled else "SATURN" if colour else "MIMAS", f"ISS_TEST_PLANES{p}", "N", 0), "frames": fr, "z": 1e6,
         "movie": True, "mosaic": False, "track": False, "kind": "movie", "last": fr[-1][3]}
    d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
    os.makedirs(TD, exist_ok=True)
    for n in range(N):
        crop = cv2.warpAffine(field, np.float32([[1, 0, 100 + 5 * n], [0, 1, 100]]), (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
        im = np.zeros((S, S, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = (crop * 200).astype(np.uint8)[..., None]
        Image.fromarray(im).save(f"{TD}/{n}.png")
        json.dump({"n": n, "id": fr[n][1], "filter": fr[n][2], "t": fr[n][3], "offset": [5.0 * n, 0.0], "box": [-S / 2, -S / 2, S, S]},
                  open(f"{TD}/{n}.json", "w"))
    json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-300, -300, 400, 300], "fixed": True,
               "view": [700, 600], "k": 1, "colour": colour, "grey": fr[0][2], "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))
    passes.append((u, filled))
    for n, f in enumerate(fr):
        units[f[1]] = (u, n)
om.unit_of = lambda fid: units.get(fid)
prebuild.all_passes = lambda: [u for u, _ in passes]


def files():
    return {os.path.join(r, f) for r, _, fs in os.walk(cache) for f in fs}


def route(frame_id, query):
    """The movie route's call for a request (frame_server.py, /frames/movie/<ID>.webp, not rolling), its query
    read as the route reads it."""
    q = parse_qs(query)
    return om.movie_webp(frame_id, int(q["size"][0]), cache, int(q.get("trail", ["0"])[0] or 0), q.get("color", ["1"])[0] != "0",
                         centre=q.get("center", ["1"])[0] != "0", steady=int(q.get("steady", ["0"])[0] or 0),
                         exposure=om.exposure_of(q.get("exposure", ["0"])[0]), sharpen=q.get("detail", ["1"])[0] != "0")


# the page's plane requests, Auto center on (cassiniMovieStyle leaves center out) and off
PAGE = "size=1024&color=0&trail=0&laps=1"
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    todo = prebuild.items("movies")
    assert [name for name, _ in todo] == ["_".join(map(str, u["key"])) for u, _ in passes], todo
    for _, work in todo:
        assert work(cache) == N
    built = files()
    d0 = sorted(os.path.basename(f) for f in built if f.endswith("_d0.webp"))
    print("_d0 frames:", d0)
    for u, filled in passes:
        for f in u["frames"]:
            for query in (PAGE, PAGE + "&detail=0"):
                made = route(f[1], query)
                assert made and made[0] is not None, (f[1], query)
    asked = files() - built
    assert not asked, sorted(asked)
    # the filled pass's _d0 frames are its own and differ from the sharpened ones; the other pass has none
    assert len(d0) == N and all(n.endswith("_0_0_c2_d0.webp") for n in d0), d0
    u = passes[0][0]
    a, b = route(u["frames"][2][1], PAGE)[0], route(u["frames"][2][1], PAGE + "&detail=0")[0]
    assert a != b
    print("movies phase: %d planes at 1024 (each frame alone) + %d _d0; the page's requests all found in the cache" %
          (sum(len(u["frames"]) for u, _ in passes), len(d0)))
    # Exposure normalization (on by default): the false colour pass's frames with it at the default smoothing, as the
    # window asks for them, are pre-built; the passes the page evens itself have none
    e8 = sorted(f for f in built if f"_e{om.EXPOSURE_SMOOTH}r{om.EXPOSURE_RULE}" in os.path.basename(f) and f.endswith(".webp"))
    assert e8 and all("ISS_TEST_PLANES2" in f for f in e8) and len(e8) == 2 * N, e8
    assert [om.page_evens(u, cache) for u, _ in passes] == [True, True, False]
    before = files()
    for f in passes[2][0]["frames"]:
        for size in (1024, 512):
            made = route(f[1], f"size={size}&color=1&trail=0&laps=1&exposure={om.EXPOSURE_SMOOTH}")
            assert made and made[0] is not None, f[1]
    assert not files() - before, sorted(files() - before)
    print(f"Exposure normalization: {len(e8)} frames of the false colour pass pre-built at smoothing {om.EXPOSURE_SMOOTH}; "
          "the window's requests for them all found; none for the passes the page evens")
print("ok")
