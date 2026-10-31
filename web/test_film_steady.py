"""Additional stabilization of a film (the Movie Editor's Framing, film-steady.html) is web/frames/film_steady.py: the
page's arithmetic (window.cassiniFilmSteady.math, run here in node on the same pictures) finds the same matches the
same way (phase correlation, the centroid, nothing) and moves every picture the same, to 1/100,000 of the picture (the
page's DFT is in doubles, OpenCV's in floats: the matches agree to about 1e-6 px). And it does its job: a small
textured moon that SPICE's centering puts a few pixels off at random from picture to picture, drifting slowly as
well, comes out with the wobble mostly gone and the drift kept; a picture with nothing in it holds its place; a new
target starts a run of its own. And a picture like Atlas's of 2005-08-18 (a moon a few pixels across beside the A
ring's bright edge, in a picture turned north up whose own edge, against the fill, stays where SPICE put it while what
it shows wobbles) is matched only inside what both pictures show (film_steady.window): matched with the edge in, the
wobble hardly comes out. Run: python web/test_film_steady.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, subprocess, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import film_steady as F  # noqa: E402

script = open(os.path.join(HERE, "cassini-os", "src", "film-steady.html")).read()
script = script[script.index("<script>") + 8:script.index("</script>")]


def moon(cx, cy, seed, w=256, h=192, radius=18):
    """A small cratered moon at (cx, cy) on black sky, a little noise, RGBA (the same surface every time)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    u, v = x - cx, y - cy
    r = np.hypot(u, v)
    surface = 150 + 45 * np.sin(u / 2.7) * np.cos(v / 3.4) + 30 * np.sin((u + 2 * v) / 5.1)
    g = np.where(r < radius, surface * np.clip(1.2 - r / radius * 0.5, 0, 1), 0) + rng.normal(0, 2.0, (h, w))
    a = np.zeros((h, w, 4), np.uint8)
    a[..., :3] = np.clip(g, 0, 255).astype(np.uint8)[..., None]
    a[..., 3] = 255
    return a


def ringed(e, seed, w=256, h=256):
    """Atlas's kind of picture: a dot a few px across between a bright ring band's edge and a thin ring, all of it moved
    by e (SPICE's error), in a square turned 35 degrees (the picture turned north up, alpha 0 round it) that stays put."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    u, v = x - w / 2 - e[0], y - h / 2 - e[1]
    t = np.radians(25)
    across = -u * np.sin(t) + v * np.cos(t)
    g = 10 + 170 / (1 + np.exp(-(across - 14) / 1.2)) * (0.9 + 0.1 * np.sin(across / 3.0))
    g += -60 * np.exp(-((across - 40) / 3) ** 2) + 90 * np.exp(-((across + 45) / 1.0) ** 2) + 200 * np.exp(-(u ** 2 + v ** 2) / 2.4)
    g += rng.normal(0, 2.0, (h, w))
    p = np.radians(35)
    X, Y = x - w / 2, y - h / 2
    inside = (np.abs(X * np.cos(p) + Y * np.sin(p)) < 95) & (np.abs(-X * np.sin(p) + Y * np.cos(p)) < 95)
    a = np.zeros((h, w, 4), np.uint8)
    a[..., :3] = np.where(inside, np.clip(g, 0, 255), 0).astype(np.uint8)[..., None]
    a[..., 3] = np.where(inside, 255, 0)
    return a


def in_node(pictures, keys, smooth):
    tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    for i, a in enumerate(pictures):
        open(f"{tmp}/{i}.raw", "wb").write(a.tobytes())
    js = ("const fs = require('fs');\nconst window = {};\n" + script + "\nconst M = window.cassiniFilmSteady.math;\n"
          f"const shapes = {json.dumps([list(a.shape[:2]) for a in pictures])}, keys = {json.dumps(keys)};\n"
          "const pics = shapes.map(([h, w], i) => { const d = new Uint8Array(fs.readFileSync(`" + tmp + "/${i}.raw`)); return { g: M.grey(d, w, h), v: M.valid(d, w, h), w, h, key: keys[i] }; });\n"
          f"const how = [], moves = M.offsets(pics, {smooth}, how);\n"
          "console.log(JSON.stringify({ moves, how, greys: pics.map(p => Array.from(p.g.slice(0, 64))) }));")
    open(f"{tmp}/run.js", "w").write(js)
    return json.loads(subprocess.run(["node", f"{tmp}/run.js"], capture_output=True, text=True, check=True).stdout)


def main():
    rng = np.random.default_rng(7)
    n = 40
    drift = np.stack([np.linspace(0, 10, n), np.linspace(0, -6, n)], 1)     # the moon really moves this much
    wobble = rng.normal(0, 2.5, (n, 2))                                      # SPICE's centering off by this much
    where = np.array([128.0, 96.0]) + drift + wobble
    pictures = [moon(x, y, seed=100 + i) for i, (x, y) in enumerate(where)]
    # a picture with nothing in it (a lost frame) and then the moon again; then another target
    pictures[25] = moon(-500, -500, seed=1)
    pictures += [moon(90 + 1.5 * k, 80, seed=300 + k, radius=30) for k in range(8)]
    keys = ["N|ATLAS|movie"] * n + ["N|PAN|movie"] * 8
    fails = []

    for smooth in (4, F.SMOOTH, F.SMOOTH_MOST):
        greys = [F.grey(a) for a in pictures]
        how = []
        py = F.offsets(greys, keys, smooth, how, [F.valid(a) for a in pictures])
        js = in_node(pictures, keys, smooth)
        if any(list(g.ravel()[:64]) != j for g, j in zip(greys, js["greys"])):
            fails.append("grey differs")
        if how != js["how"]:
            fails.append(f"smooth {smooth}: hows differ {[(i, a, b) for i, (a, b) in enumerate(zip(how, js['how'])) if a != b]}")
        worst = max(abs(a - b) for p, j in zip(py, js["moves"]) for a, b in zip(p, j))
        print(f"smooth {smooth}: page vs Python, worst move difference {worst:.1e} of the picture ({worst * 256:.1e} px); hows {sorted(set(how))}")
        if worst > 1.5e-5:
            fails.append(f"smooth {smooth}: moves differ by {worst}")
        if how[25] != "not aligned" or how[26] != "phase to 2 before" or how[n] != "first":
            fails.append(f"smooth {smooth}: lost frame / new target not handled: {how[24:28]} {how[n]}")
        # it steadies: where the moon is drawn after the moves (a move takes the picture its way, export.framed), against a smooth line through where it really is
        moved = np.array([[x + mx * 256, y + my * 192] for (x, y), (mx, my) in zip(where, py[:n])])
        keep = [i for i in range(n) if i != 25]

        def jitter(p):
            d = np.diff(p[keep], axis=0)
            return float(np.sqrt(((d - np.diff(drift[keep], axis=0)) ** 2).sum(1).mean()))
        before, after = jitter(where), jitter(moved)
        trend = np.polyfit(np.arange(n)[keep], moved[keep, 0], 1)[0] * (n - 1)
        print(f"  frame to frame wobble {before:.2f} px -> {after:.2f} px; drift kept {trend:.1f} of 10 px")
        if after > 0.35 * before:
            fails.append(f"smooth {smooth}: wobble only {before:.2f} -> {after:.2f}")
        if smooth <= F.SMOOTH and abs(trend - 10) > 3:
            fails.append(f"smooth {smooth}: drift {trend:.1f} px, not 10")

    # Atlas's kind of picture: matched inside what both show, against matched with the picture's edge in
    m = 19
    drift = np.stack([np.linspace(0, 4, m), np.linspace(0, -3, m)], 1)
    where = drift + np.random.default_rng(3).normal(0, 2.5, (m, 2))
    pictures = [ringed(p, 50 + i) for i, p in enumerate(where)]
    keys = ["N|ATLAS|movie"] * m
    greys, valids = [F.grey(a) for a in pictures], [F.valid(a) for a in pictures]
    if F.window(valids[0], valids[1]) != (60, 60, 196, 196):
        fails.append(f"window {F.window(valids[0], valids[1])}")

    def wobble(p):
        return float(np.sqrt(((np.diff(p, axis=0) - np.diff(drift, axis=0)) ** 2).sum(1).mean()))
    how = []
    py = F.offsets(greys, keys, F.SMOOTH, how, valids)
    js = in_node(pictures, keys, F.SMOOTH)
    worst = max(abs(a - b) for p, j in zip(py, js["moves"]) for a, b in zip(p, j))
    if how != js["how"] or worst > 1.5e-5:
        fails.append(f"ringed: page and Python differ ({worst}, {how} {js['how']})")
    edge = F.offsets(greys, keys, F.SMOOTH)
    before, after, with_edge = (wobble(np.array([[x + mx * 256, y + my * 256] for (x, y), (mx, my) in zip(where, mv)]))
                                for mv in ([[0, 0]] * m, py, edge))
    print(f"ringed (Atlas's kind): page vs Python {worst:.1e}; wobble {before:.2f} px -> {after:.2f} px "
          f"(matched with the picture's edge in: {with_edge:.2f} px)")
    if after > 0.2 * before:
        fails.append(f"ringed: wobble only {before:.2f} -> {after:.2f}")

    # on by itself for a small body: Atlas at 7.9 km/px (15 km: 2 px), not Mimas filling a third of the frame
    cases = [[15.8 / 7.9] * 19, [198 / 0.6] * 10, [40.0, 60.0, 50.0, None], [None, None], [], [53.0, 54.0, 10.0]]
    py_auto = [F.auto(r) for r in cases]
    js_auto = json.loads(subprocess.run(["node", "-e", "const window = {};\n" + script + "\nconsole.log(JSON.stringify("
                                         + json.dumps(cases).replace("NaN", "null") + ".map(r => window.cassiniFilmSteady.math.auto(r))))"],
                                        capture_output=True, text=True, check=True).stdout)
    print(f"on by itself: {py_auto} (page {js_auto})")
    if py_auto != js_auto or py_auto != [True, False, True, False, False, False]:
        fails.append(f"auto: {py_auto} page {js_auto}")
    if F.offsets([F.grey(a) for a in pictures], keys, 0) is not None or in_node(pictures[:3], keys[:3], 0)["moves"] is not None:
        fails.append("smooth 0 is not off")
    print("FAIL\n  " + "\n  ".join(fails) if fails else "ok")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
