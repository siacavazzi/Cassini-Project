"""One source of pointing for a whole movie (Sam 2026-11-18): obs_mosaic._chain_links places every tile the pictures can
match by the pictures, and a tile they cannot (its target hidden behind another body, a blank frame) goes on from its
neighbours along SPICE's smoothed path, never at SPICE's own raw place: 293EN ENCSET001 (Enceladus setting behind Saturn)
played 34 of its 48 frames at SPICE's places, 3 to 26 px from where the pictures put the moon. And another body is
drawn by its shape toward the target (_limb_toward), and one over the square round a small target but not over the
target is left out of the match, not the match (_shift_onto, STEADY_HIDDEN).
Synthetic tiles. Run: python web/test_steady_one_source.py"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(5)
N, R, HALF = 30, 20, 64
truth = np.cumsum(rng.normal(0, 0.4, (N, 2)), axis=0)              # where the moon really is (its slow motion)
scatter = rng.normal(0, 6.0, (N, 2))                                  # SPICE's frame-to-frame pointing scatter
spice = truth + scatter
yy, xx = np.mgrid[0:2 * HALF, 0:2 * HALF].astype(np.float32)
hidden = set(range(12, 18))                                           # the moon behind another body: a blank frame


def picture(n):
    # (a tile's picture has its corner at its place plus box, SPICE's target at 0: the moon really is at truth)
    # from the target's SPICE place, in the tile's own pixels round its middle
    if n in hidden:
        return np.zeros((2 * HALF, 2 * HALF, 4), np.uint8)
    cx, cy = HALF + truth[n][0], HALF + truth[n][1]
    r = np.hypot(xx - cx, yy - cy)
    g = np.clip(200 * (r < R) * (0.8 + 0.2 * np.sin(xx / 3.0 + yy / 5.0)) + rng.normal(0, 1.5, r.shape), 0, 255)
    a = np.zeros((2 * HALF, 2 * HALF, 4), np.uint8)
    a[..., :3] = g.astype(np.uint8)[..., None]
    a[..., 3] = 255
    return a


pics = {n: picture(n) for n in range(N)}
made = [{"n": n, "offset": [float(-spice[n][0]), float(-spice[n][1])], "box": [-HALF, -HALF, 2 * HALF, 2 * HALF],
         "filter": "CL1/CL2"} for n in range(N)]
there = os.path.join(os.environ.get("TMPDIR", "/tmp"), "one-source-tiles")
os.makedirs(there, exist_ok=True)
for n in range(N):
    open(os.path.join(there, f"{n}.png"), "wb").close()
places, hows = om._chain_links(made, lambda n: pics[n], there, 0.5 * 2 * HALF)
p = np.array([places[n] for n in range(N)])
off = -p - truth                                     # where the moon sits in the movie, from a fixed place
off -= off[0]
jumps = np.hypot(*np.diff(off, axis=0).T)
linked = [n for n in range(N) if str(hows[n]).startswith("linked")]
raw = [n for n in range(N) if np.allclose(places[n], made[n]["offset"], atol=0.05) and n not in linked and n != 0]
print("hows:", sorted(set(str(h).split(" [")[0] for h in hows.values())))
print(f"moon's frame-to-frame jump in the movie: median {np.median(jumps):.2f} max {jumps.max():.2f} px "
      f"(SPICE alone: median {np.median(np.hypot(*np.diff(scatter, axis=0).T)):.1f})")
assert not raw, f"tiles left at SPICE's own place: {raw}"
assert all(n not in linked for n in hidden)
seen = [i for i in range(1, N) if i not in hidden and i - 1 not in hidden]
assert max(jumps[i - 1] for i in seen) < 1.0, jumps
across = [jumps[i - 1] for i in range(1, N) if i in hidden or i - 1 in hidden]
assert max(across) < 6.0, across            # across the hidden frames: SPICE's smoothed path, not its 6 px scatter
print("no tile at SPICE's own place; hidden frames on the smoothed path: ok")

# Saturn's limb under a small moon's square but not over the moon: matched (left out), not "other body"
a = picture(0)
holes = [(0.0, HALF + 30.0, 40.0, False)]        # a disk whose edge crosses the square's lower part, under the moon
moon_at = (-made[0]["offset"][0], -made[0]["offset"][1])
s, how = om._shift_onto(made[0], a, (0.0, 0.0), made[0], a, (0.0, 0.0), around=(moon_at[0], moon_at[1], HALF - 4),
                        holes=holes, kept=(moon_at[0], moon_at[1], R + 1))
assert s is not None and abs(s[0]) < 0.1 and abs(s[1]) < 0.1, (s, how)
holes = [(moon_at[0], moon_at[1] + R + 10.0, 25.0, False)]   # a disk over a third of the moon: not matched
s, how = om._shift_onto(made[0], a, (0.0, 0.0), made[0], a, (0.0, 0.0), around=(moon_at[0], moon_at[1], HALF - 4),
                        holes=holes, kept=(moon_at[0], moon_at[1], R + 1))
assert s is None and how == "other body", (s, how)
print("another body under the square but not the moon is left out; over the moon, no match: ok")


# a retarget (the camera moving on 20,000 px between two propellers, 287RI PROPRETRG001) is not smoothed across: the
# smoothed path keeps the jump where SPICE has it and smooths each run on its own
path = np.array([[0.0, 0.0]] * 10 + [[20000.0, 300.0]] * 10) + rng.normal(0, 5, (20, 2))
sm = om._smoothed_path(path)
assert np.abs(sm[:10] - path[:10].mean(axis=0)).max() < 12 and np.abs(sm[10:] - path[10:].mean(axis=0)).max() < 12, sm
print("a retarget is not smoothed across: ok")

# a fast steady drift with SPICE's scatter is one run, not broken into one-frame pieces (each of which would keep
# SPICE's raw step): its smoothed path is within a few px of the true motion
for speed in (20.0, 45.0, 60.0):
    true = np.stack([np.arange(40) * speed, np.arange(40) * speed * 0.3], axis=1)
    raw = true + rng.normal(0, 8.0, true.shape)
    err = np.hypot(*np.diff(om._smoothed_path(raw) - true, axis=0).T)
    assert np.percentile(err, 90) < 3.0, (speed, np.percentile(err, 90))
print("a fast drift stays one smoothed run: ok")
print("ok")
