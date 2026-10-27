"""Synthetic check of obs_mosaic.movie_webp's movie strips: a strip (128) of a frame already kept at 512 is that
picture shrunk, with its report, and draws nothing (no tile is read); a strip of a frame not kept yet, and every
size a window plays, is drawn by movie_frame as before. Run: python web/test_movie_strip.py"""
import io, json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
u = {"key": ("SATURN", "OBS", "ISSNA", 0), "frames": []}
om.unit_of = lambda fid: (u, int(fid))
om._record = lambda u, cache: {"footprint": (0, 0, 1, 1), "plan": {}}
om.folder = lambda u, cache: cache
drawn = []


def movie_frame(u, n, cache, trail=0, colour=True, out=om.OUT, centre=True, steady=0, exposure=0):
    drawn.append(n)
    return Image.new("RGBA", (1024, 1024), (200, 100, 50, 255)), {"movie": True, "n": n, "id": f"N{n}"}


om.movie_frame = movie_frame
data, rep = om.movie_webp("3", 512, cache, ahead=0, wait=True)
assert drawn == [3] and Image.open(io.BytesIO(data)).size == (512, 512)
data, rep = om.movie_webp("3", 128, cache, ahead=0, wait=True)               # kept at 512: shrunk, nothing drawn
assert drawn == [3] and Image.open(io.BytesIO(data)).size == (128, 128) and rep["id"] == "N3"
assert json.load(open(os.path.join(cache, om.MOVIE_DIR, "128", "3_0_1_c2.json")))["id"] == "N3"
om.movie_webp("4", 128, cache, ahead=0, wait=True)                            # not kept: drawn
assert drawn == [3, 4]
om.movie_webp("4", 1024, cache, ahead=0, wait=True)                           # a size a window plays: drawn
assert drawn == [3, 4, 4]
print("ok")
