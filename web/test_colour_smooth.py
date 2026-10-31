"""Color smoothing on this computer (Settings > Processing, colour-smooth.html) is web/frames/colour_smooth.py: the
page's arithmetic (window.cassiniColourSmooth.math, run here in node on the same bytes) measures the same palettes,
wants the same medians and moves every pixel the same, byte for byte. And it does its job: a run of color pictures,
four in five of one palette and the fifth of another (as the WAC Saturn stares' MT3/CB2/MT2 sets with an MT3/MT2/BL1
set now and then), comes out with the fifth's palette next to the others', each pixel's brightness kept; a run of
one palette is left almost as it is, a grey picture and black sky not at all.
Optional: COLOUR_SMOOTH_REAL=<folder of color pictures in play order> runs the conformance check on those too.
Run: python web/test_colour_smooth.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames")]
import glob, json, subprocess, tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import colour_smooth as C  # noqa: E402

script = open(os.path.join(HERE, "cassini-os", "src", "colour-smooth.html")).read()
script = script[script.index("<script>") + 8:script.index("</script>")]


def body(tint, seed, size=300):
    """A banded disk on black sky with a little noise, its channels scaled by tint (a palette), RGBA."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    r = np.hypot(x - size / 2, y - size * 0.55)
    disk = r < size * 0.38
    bands = 0.65 + 0.25 * np.sin(y / 9.0) + 0.1 * np.sin(x / 23.0)
    a = np.zeros((size, size, 4), np.uint8)
    for k in range(3):
        v = np.where(disk, 255 * bands * tint[k] * (0.9 + 0.2 * y / size), 0) + rng.normal(0, 1.5, (size, size))
        a[..., k] = np.clip(v, 0, 255).astype(np.uint8)
    a[..., 3] = 255
    return a


def in_node(pictures, strength):
    """The page's palettes, wants (SPAN either side) and smoothed bytes of the pictures in play order."""
    tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    for i, a in enumerate(pictures):
        open(f"{tmp}/{i}.raw", "wb").write(a.tobytes())
    js = ("const fs = require('fs');\nconst window = {};\n" + script + "\nconst M = window.cassiniColourSmooth.math, SPAN = window.cassiniColourSmooth.SPAN;\n"
          f"const shapes = {json.dumps([list(a.shape[:2]) for a in pictures])};\n"
          "const data = shapes.map((s, i) => new Uint8ClampedArray(fs.readFileSync(`" + tmp + "/${i}.raw`)));\n"
          "const st = data.map((d, i) => M.palette(d, shapes[i][1], shapes[i][0]));\n"
          "const want = st.map((_, i) => M.wanted(st, i, SPAN));\n"
          f"data.forEach((d, i) => {{ if (M.smoothed(d, st[i], want[i], {strength})) fs.writeFileSync(`{tmp}/${{i}}.out`, d); }});\n"
          "console.log(JSON.stringify({ st, want }));")
    open(f"{tmp}/run.js", "w").write(js)
    got = json.loads(subprocess.run(["node", f"{tmp}/run.js"], capture_output=True, text=True, check=True).stdout)
    outs = []
    for i, a in enumerate(pictures):
        p = f"{tmp}/{i}.out"
        outs.append(np.frombuffer(open(p, "rb").read(), np.uint8).reshape(a.shape) if os.path.exists(p) else a)
    return got, outs


def python(pictures, strength):
    st = [C.palette(a) for a in pictures]
    want = [C.wanted(st, i, C.SPAN) for i in range(len(st))]
    return st, want, [C.smoothed(a, st[i], want[i], strength) for i, a in enumerate(pictures)]


def same(pictures, strength, name):
    st, want, outs = python(pictures, strength)
    got, js = in_node(pictures, strength)
    for i in range(len(pictures)):
        for a, b in ((st[i], got["st"][i]), (want[i], got["want"][i])):
            assert (a is None) == (b is None), (name, i, a, b)
            if a is not None:
                assert np.abs(np.array(a) - np.array(b)).max() < 1e-12, (name, i, a, b)
        diff = np.abs(outs[i].astype(int) - js[i].astype(int))
        assert diff.max() == 0, (name, i, int(diff.max()), int((diff > 0).sum()))
    print(f"{name}: {len(pictures)} pictures, page == python byte for byte (strength {strength})")
    return st, want, outs


GREEN, PEACH = (0.82, 0.95, 0.70), (0.95, 0.88, 0.80)


def test_bridges_the_odd_set():
    run = [body(PEACH if i % 5 == 1 else GREEN, i) for i in range(15)]
    st, want, outs = same(run, 1.0, "stare")
    after = [C.palette(a) for a in outs]
    for i in range(15):
        # (where neither picture clips at white)
        lit = (run[i][..., :3].sum(axis=2) > 120) & (run[i][..., :3].max(axis=2) < 255) & (outs[i][..., :3].max(axis=2) < 255)
        g0 = np.exp(np.log(np.maximum(run[i][..., :3].astype(float), 1)).mean(axis=2))
        g1 = np.exp(np.log(np.maximum(outs[i][..., :3].astype(float), 1)).mean(axis=2))
        # each pixel's (geometric mean) brightness kept, to rounding
        assert np.abs(g1 - g0)[lit].max() < 1.5, (i, np.abs(g1 - g0)[lit].max())
        gap0 = np.abs(np.array(st[i][:3]) - np.array(st[0][:3])).max()
        gap1 = np.abs(np.array(after[i][:3]) - np.array(after[0][:3])).max()
        if i % 5 == 1:
            assert gap0 > 0.05 and gap1 < 0.15 * gap0, (i, gap0, gap1)
        else:
            assert gap1 < 0.01, (i, gap1)
    print("stare: the odd sets' palette within 15% of the others' gap, brightness kept")


def test_half_strength_and_off():
    run = [body(PEACH if i == 2 else GREEN, i) for i in range(5)]
    st, _, half = same(run, 0.5, "half")
    _, _, full = python(run, 1.0)
    p0, ph, pf = (np.array(C.palette(x[2])[:3]) for x in (run, half, full))
    assert np.abs(ph - (p0 + pf) / 2).max() < 0.01, (p0, ph, pf)
    _, _, off = python(run, 0.0)
    assert all(o is a for o, a in zip(off, run))
    print("half strength goes half way; off leaves every picture as it is")


def test_grey_and_sky():
    grey = body((0.9, 0.9, 0.9), 1)
    grey[..., 1] = grey[..., 2] = grey[..., 0]
    assert C.palette(grey) is None
    sky = np.zeros((200, 200, 4), np.uint8)
    sky[..., 3] = 255
    assert C.palette(sky) is None
    run = [body(GREEN, 3), grey, body(PEACH, 4), body(GREEN, 5)]
    _, want, outs = same(run, 1.0, "grey")
    assert outs[1] is run[1] and want[1] is None
    # black sky stays black
    assert (outs[2][..., :3][run[2][..., :3].max(axis=2) == 0] == 0).all()
    print("a grey picture has no palette and is left alone; black stays black")


def test_real():
    folder = os.environ.get("COLOUR_SMOOTH_REAL")
    if not folder:
        return
    run = [np.asarray(Image.open(f).convert("RGBA")) for f in sorted(glob.glob(os.path.join(folder, "*")))[:20]]
    same(run, 1.0, f"real ({folder})")


if __name__ == "__main__":
    test_bridges_the_odd_set()
    test_half_strength_and_off()
    test_grey_and_sky()
    test_real()
    print("ok")
