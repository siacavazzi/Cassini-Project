"""A movie whose view follows its frames holds still what the camera followed (obs_mosaic.followed_point, taste call
30 C): the camera following a moon's shadow across the rings (108RI MNRNGSHAD005), 600 px a frame with its own tracking
error, is played with the shadow's place held, the camera's slow drift kept and its frame-to-frame error and a
correction taken out; a sweep that follows nothing keeps the frames as taken.
Made-up tiles and points. Run: python web/test_follow_held.py"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(4)
N = 30
shadow = np.stack([np.arange(N) * -500.0, np.arange(N) * 300.0], axis=1)            # the shadow's place, moving fast
framing = np.stack([np.linspace(-500, -900, N), np.linspace(80, -60, N)], axis=1)   # the camera's slow drift off it
error = rng.normal(0, 25, (N, 2))                                                   # its tracking error
error[14:] += (0.0, 120.0)                                                          # and a correction
mids = shadow + framing + error


def run(points):
    u = {"key": ("SATURN", "TEST", "N", 0), "frames": [("p", f"N{i}_1", "CL1/CL2", float(i), 0, 0, 0, 1e6) for i in range(N)],
         "z": 1e6}
    was = (om.tile, om.other_bodies, om._shadow_points, om._ets, om.folder)
    om.tile = lambda u_, n, cache, scale=None: {"offset": list(mids[n]), "id": u_["frames"][n][1]}
    om.other_bodies = lambda u_, names=False: {}
    om._shadow_points = lambda u_, frames, ets: points
    om._ets = lambda ids: {f: 0.0 for f in ids}
    om.folder = lambda u_, cache: str(id(points))
    try:
        om._followed.clear()
        return om.followed_point(u, "cache", {"display_scale": {}})
    finally:
        om.tile, om.other_bodies, om._shadow_points, om._ets, om.folder = was


held, inset = run({"MIMAS": {f"N{i}_1": tuple(shadow[i]) for i in range(N)}})
assert held.get("_name") == "shadow of MIMAS", held.get("_name")
view = np.array([held[n] for n in range(N)])
where = shadow - view                                  # where the shadow sits in the view
steps = np.hypot(*np.diff(where, axis=0).T)
print(f"shadow in the view: frame-to-frame move median {np.median(steps):.1f} px, largest {steps.max():.1f} "
      f"(as taken: median {np.median(np.hypot(*np.diff(shadow - mids, axis=0).T)):.1f}); inset {inset:.0f} px")
assert steps.max() < 25 and inset <= om.FOLLOW_INSET_MOST * om.FRAME
# a sweep following nothing (the shadow far off and moving like everything else): the frames as taken
held, inset = run({"MIMAS": {f"N{i}_1": (float(i * 37.0), float(-i * 911.0)) for i in range(N)}})
assert held == {} and inset == 0.0, held
print("ok")
