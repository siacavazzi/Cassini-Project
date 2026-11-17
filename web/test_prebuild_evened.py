"""The evened phase (prebuild.py evened) keeps every movie frame's evened copy (exposure=EXPOSURE_SMOOTH, 1024 and 512),
whether or not the page evens the pass itself, and a toss-up mosaic pass's movie frames too: the pictures the Movie
Editor, a Pre-process (make_pass with the page's style) and a film ask the server for. Kept only for the passes the page
cannot even, every such request on a finished cache drew its frame (a 999-frame stretch took 131 s to open in the
editor, 2026-11-15). The movies phase keeps them in a new build.
Run: python web/test_prebuild_evened.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402
import prebuild  # noqa: E402

frames = lambda n, cam="N": [(None, f"{cam}{1000000000 + j}_1", "CL1/CL2", float(j)) for j in range(n)]
movie = {"key": ("TITAN", "ISS_133TI_CLOUD002_PRIME", "N", 0), "kind": "movie", "movie": True, "mosaic": False, "frames": frames(3)}
tossup = {"key": ("SATURN", "ISS_000SA_TOSSUP001_PRIME", "W", 0), "kind": "mosaic", "movie": False, "mosaic": True, "tossup": True, "frames": frames(2, "W")}
mosaic = {"key": ("SATURN", "ISS_000SA_MOSAIC001_PRIME", "N", 0), "kind": "mosaic", "movie": False, "mosaic": True, "frames": frames(4)}
rolling = {"key": ("SATURN", "ISS_000SA_ROLL001_PRIME", "N", 0), "kind": "mosaic_movie", "movie": False, "mosaic": False, "frames": frames(4)}
prebuild.all_passes = lambda: [movie, tossup, mosaic, rolling]

# the passes: the movie passes and the toss-up mosaics (make_pass's movie()), never a plain mosaic or a mosaic movie
assert prebuild.evened_passes() == [movie, tossup], prebuild.evened_passes()
assert "evened" in prebuild.PHASES and "evened" in prebuild.ADDED and "evened" in prebuild.PASS_PHASES

made = []
om.movie_webp = lambda fid, size, cache, trail, colour, **k: made.append((fid, size, trail, colour, k)) or (b"", {})
om.page_evens = lambda u, cache, colour=True, centre=True: True   # the page evens every pass here

# the evened phase: every frame of each pass, at both sizes, as the editor asks (colour on, no trail, centred,
# no stabilization, the default smoothing), waited for
todo = prebuild.items("evened")
assert [name for name, _ in todo] == ["TITAN_ISS_133TI_CLOUD002_PRIME_N_0", "SATURN_ISS_000SA_TOSSUP001_PRIME_W_0"], todo
for _, work in todo:
    work("/nowhere")
assert len(made) == (3 + 2) * 2, made
assert {(m[1], m[2], m[3]) for m in made} == {(1024, 0, True), (512, 0, True)}, made
assert all(m[4] == {"wait": True, "ahead": 0, "centre": True, "exposure": om.EXPOSURE_SMOOTH} for m in made), made
assert {m[0] for m in made} == {f[1] for u in (movie, tossup) for f in u["frames"]}

# make_evened alone still leaves a pass the page evens to the page (the planes and plain frames it starts from)
made.clear()
prebuild.make_evened(movie, "/nowhere")
assert made == [], made
prebuild.make_evened(movie, "/nowhere", every=True)
assert len(made) == 6, made

# the movies phase keeps them too, so a new build needs no evened run
made.clear()
prebuild.make_pass = lambda u, c, *a, **k: 0
prebuild.make_planes = lambda u, c, *a, **k: 0
for name, work in prebuild.items("movies"):
    work("/nowhere")
assert len(made) == 6 and {m[4]["exposure"] for m in made} == {om.EXPOSURE_SMOOTH}, made

# and the mosaics phase a toss-up pass's (its frames play as a movie too), none for a plain mosaic or a mosaic movie
made.clear()
for name, work in prebuild.items("mosaics"):
    work("/nowhere")
assert len(made) == 4 and {m[0] for m in made} == {f[1] for f in tossup["frames"]}, made
print("ok")
