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
# (two sources in one sequence: one frame held on SPICE's step among frames the pictures place)
p.meta["collected"] = {"pointing_sources": {"frames": 3, "auto": True, "linked": 2, "smoothed": 1, "on_spice": 0, "mixed": 1}}
r = bc.CHECKS["pointing_sources"](p)
assert not r.ok and r.value == 1, r.as_dict()
print(r.detail)


# every frame measurable (no blank first pair): the worst move's frame is named, never past the last frame
r = bc.CHECKS["pointing_jitter"](movie([(128.0 + (9.0 if i == 23 else 0.0), 128.0) for i in range(24)]))
assert r.where == "frame023.webp" or r.ok, r.as_dict()
print("worst frame named within the film: ok")

# channel_registration measures the channels' offset itself: a tan moon with a clipped red core and a glow passes,
# the same moon with its blue channel 2 px off fails, and a not-made movie is not judged by pointing_sources
def colour_movie(blue_off, frames=4):
    d = tempfile.mkdtemp()
    for i in range(frames):
        def disc(dx):
            r = np.hypot(xx - 128 - dx, yy - 128)
            tex = 150 + 50 * np.sin((xx - dx) / 3.0) * np.cos(yy / 4.0)
            return np.clip((r < 50) * tex + 40 * np.exp(-np.maximum(r - 50, 0) / 12.0) + rng.normal(0, 1, r.shape), 0, 255)
        red = np.minimum(disc(0) * 1.6, 255)   # (clipped: a flat core)
        a = np.dstack([red, disc(0) * 1.1, disc(blue_off) * 0.7, np.full_like(red, 255)]).astype(np.uint8)
        Image.fromarray(a).save(os.path.join(d, f"frame{i:03d}.webp"), lossless=True)
    return bc.Pictures(d, {"name": "c", "kind": "pass"}, {"pass_kind": "movie"})


r = bc.CHECKS["channel_registration"](colour_movie(0.0))
print("lined up:", r.detail)
assert r.ok and r.value < 0.4, r.as_dict()
r = bc.CHECKS["channel_registration"](colour_movie(2.0))
print("blue 2 px off:", r.detail)
assert not r.ok and 1.5 < r.value < 2.5, r.as_dict()
# a colour mixed from two filters, one of them 12 px off (#606's 241TI blue): half the blue channel is off, which the
# edges' own match reads as under a pixel; the colour along the edges does not (channel_drift)
def mixed_movie(off, frames=3):
    d = tempfile.mkdtemp()
    for i in range(frames):
        def disc(dx):
            r = np.hypot(xx - 128 - dx, yy - 128)
            return np.clip(200 * (r < 60) * (1 - (r / 70) ** 2) + rng.normal(0, 1, r.shape), 0, 240)
        a = np.dstack([disc(0) * 1.0, disc(0) * 0.8, 0.5 * disc(0) * 0.5 + 0.5 * disc(off) * 0.5,
                       np.full_like(disc(0), 255)]).astype(np.uint8)
        Image.fromarray(a).save(os.path.join(d, f"frame{i:03d}.webp"), lossless=True)
    return bc.Pictures(d, {"name": "m", "kind": "pass"}, {"pass_kind": "movie"})


r = bc.CHECKS["channel_registration"](mixed_movie(0.0))
print("mixed, lined up:", r.detail)
assert r.ok, r.as_dict()
r = bc.CHECKS["channel_registration"](mixed_movie(12.0))
print("mixed, half of blue 12 px off:", r.detail)
assert not r.ok and r.value > 2, r.as_dict()
p = movie(still[:1])
p.meta["collected"] = {"pointing_sources": {"frames": 97, "auto": False, "linked": 1, "smoothed": 0, "on_spice": 97}}
r = bc.CHECKS["pointing_sources"](p)
assert r.ok and r.value is None, r.as_dict()
print(r.detail)
print("ok")
