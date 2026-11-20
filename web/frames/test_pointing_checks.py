"""bench_checks/pointing.py on made-up movies: a moon that holds still or pans smoothly passes pointing_jitter; one
whose frames scatter by SPICE's 6 to 12 px fails it; pointing_sources reads the build's facts.
Run: python web/frames/test_pointing_checks.py"""
import os
import sys
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import bench_checks as bc  # noqa: E402

bc.load()
rng = np.random.default_rng(2)
yy, xx = np.mgrid[0:256, 0:256].astype(np.float32)


def movie(places):
    d = tempfile.mkdtemp()
    for i, (x, y) in enumerate(places):
        r = np.hypot(xx - x, yy - y)
        g = np.clip((r < 30) * (150 + 60 * np.sin(xx / 4.0) * np.cos(yy / 5.0)) + rng.normal(0, 2, r.shape), 0, 255)
        a = np.dstack([g, g, g, np.full_like(g, 255)]).astype(np.uint8)
        Image.fromarray(a).save(os.path.join(d, f"frame{i:03d}.webp"), lossless=True)
    return bc.Pictures(d, {"name": "t", "kind": "pass"}, {"pass_kind": "movie"})


n = 24
still = [(128.0, 128.0)] * n
pan = [(90.0 + 3.0 * i, 128.0 + 1.0 * i) for i in range(n)]
shaky = [(128.0 + rng.normal(0, 7), 128.0 + rng.normal(0, 7)) for _ in range(n)]
for name, places, ok in (("still", still, True), ("pan", pan, True), ("shaky", shaky, False)):
    r = bc.CHECKS["pointing_jitter"](movie(places))
    print(name, r.value, r.detail)
    assert r.ok == ok, (name, r.as_dict())

p = movie(still[:3])
p.meta["collected"] = {"pointing_sources": {"frames": 3, "auto": False, "linked": 3, "smoothed": 0, "on_spice": 3}}
r = bc.CHECKS["pointing_sources"](p)
print(r.detail)
assert not r.ok and r.value == 3, r.as_dict()
p.meta["collected"] = {"pointing_sources": {"frames": 3, "auto": True, "linked": 2, "smoothed": 1, "on_spice": 0}}
assert bc.CHECKS["pointing_sources"](p).ok


# every frame measurable (no blank first pair): the worst move's frame is named, never past the last frame
r = bc.CHECKS["pointing_jitter"](movie([(128.0 + (9.0 if i == 23 else 0.0), 128.0) for i in range(24)]))
assert r.where == "frame023.webp" or r.ok, r.as_dict()
print("worst frame named within the film: ok")
print("ok")
