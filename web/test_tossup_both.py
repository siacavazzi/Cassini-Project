"""Synthetic check that the pre-build makes both kinds of a toss-up pass (obs_mosaic._judge's u["tossup"]: the
pointing alone cannot tell a movie from a mosaic), so the window's Movie or Mosaic shows the other one at once: a
movie's mosaic so far at every frame besides its frames, a mosaic's frames besides its mosaics; any other pass, and
a mosaic movie, only its own kind (make_pass).
Run: python web/test_tossup_both.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic  # noqa: E402
import prebuild  # noqa: E402

made = []
obs_mosaic.plan = lambda u, cache: {"display_scale": {}}
obs_mosaic.tile = lambda u, j, cache, scale: None
obs_mosaic._mosaic_at = lambda u, j, size, cache: made.append(("mosaic", j, size))
obs_mosaic.movie_webp = lambda fid, size, cache, *a, **k: made.append(("movie", int(fid[1:]), size))
obs_mosaic.rolling_webp = lambda fid, size, cache, *a, **k: made.append(("rolling", int(fid[1:]), size))


def unit(kind, tossup):
    return {"kind": kind, "mosaic": kind in ("mosaic", "mosaic_movie"), "tossup": tossup,
            "frames": [(None, f"F{j}", "CL1", 100.0 + j) for j in range(3)]}


for kind, tossup, want in (("movie", True, {"movie", "mosaic"}), ("mosaic", True, {"movie", "mosaic"}),
                           ("movie", False, {"movie"}), ("mosaic", False, {"mosaic"}), (None, True, {"movie"}),
                           ("mosaic_movie", True, {"rolling"})):
    made.clear()
    assert prebuild.make_pass(unit(kind, tossup), "/c") == 3
    got = {m[0] for m in made}
    assert got == want, (kind, tossup, got)
    for k in got:   # every frame, at both sizes
        assert sorted((j, z) for m, j, z in made if m == k) == [(j, z) for j in range(3) for z in (512, 1024)], (kind, k)
print("toss-ups made both ways ok")
