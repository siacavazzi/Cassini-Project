"""The image benchmark's defect checks (bench_checks) on made-up pictures: each check fails on a picture with its
defect and passes on a clean one; the verdict rules (pass, fixed, known, REGRESSION); a regression fails the
benchmark's verdict, a known failure does not.
Run: python web/frames/test_bench_checks.py   (or python -m pytest web/frames/test_bench_checks.py)"""
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import image_bench  # noqa: E402

bc = image_bench.checks_module()


def disk(cx=128, cy=128, r=60, rgb=(150, 150, 150), size=256, halo=0.0, ghost=None):
    a = np.zeros((size, size, 4), np.uint8)
    a[..., 3] = 255
    yy, xx = np.mgrid[:size, :size]
    d = np.hypot(yy - cy, xx - cx)
    shade = 0.75 + 0.25 * np.cos(xx / 7.0)          # a little texture on the body
    for k in range(3):
        ch = np.where(d < r, rgb[k] * shade, 0.0)
        if halo:                                     # a black gap then a glow ring past the limb
            ch = ch + np.where((d > r + 5) & (d < r + 12), halo * rgb[k], 0.0)
        if ghost is not None:                        # a second, dimmer copy of the body moved by ghost
            gx, gy = ghost
            dg = np.hypot(yy - cy - gy, xx - cx - gx)
            ch = np.maximum(ch, np.where(dg < r, 0.4 * rgb[k], 0.0))
        a[..., k] = np.clip(ch, 0, 255)
    return a


def write(folder, pics, meta):
    os.makedirs(folder, exist_ok=True)
    for name, arr in pics.items():
        Image.fromarray(arr).save(os.path.join(folder, name), lossless=True, quality=100)
    json.dump(meta, open(os.path.join(folder, "meta.json"), "w"))
    return folder


def judge(folder, item, pics, meta=None):
    meta = meta or {"kind": item["kind"], "reports": {}}
    write(folder, pics, meta)
    return bc.judge(folder, item)


MOVIE = {"name": "m", "kind": "pass", "frame": "N1", "group": "plain", "watch": ""}
MOVIE_META = {"kind": "pass", "pass_kind": "movie", "mosaic": False, "reports": {}}


def test_repeat_frames(tmp_path):
    a, b, c = disk(120), disk(128), disk(136)
    frames = {"frame000.webp": a, "frame001.webp": a, "frame002.webp": b, "frame003.webp": c}
    # every frame played (a commit without movie_shown): frame001 repeats frame000
    r = judge(str(tmp_path / "x"), MOVIE, frames, MOVIE_META)["repeat_frames"]
    assert not r["ok"] and r["value"] == 1, r
    # the commit says frame001 is held (same key as frame000): not played again, no repeat
    meta = {**MOVIE_META, "collected": {"repeat_frames": {"rule": "movie_shown", "keys": ["k0", "k0", "k1", "k2"]}}}
    r = judge(str(tmp_path / "y"), MOVIE, frames, meta)["repeat_frames"]
    assert r["ok"] and r["value"] == 0, r
    # the commit says frame001 is another picture, but it is the same pixels: a repeat
    meta = {**MOVIE_META, "collected": {"repeat_frames": {"rule": "movie_shown", "keys": ["k0", "k9", "k1", "k2"]}}}
    r = judge(str(tmp_path / "z"), MOVIE, frames, meta)["repeat_frames"]
    assert not r["ok"], r


def test_odd_frame(tmp_path):
    good = {f"frame{j:03d}.webp": disk(100 + j) for j in range(7)}
    r = judge(str(tmp_path / "g"), MOVIE, good, MOVIE_META)["odd_frame"]
    assert r["ok"], r
    bad = dict(good)
    bad["frame003.webp"] = disk(103, ghost=(-40, 0))          # a doubled body in one frame
    r = judge(str(tmp_path / "b"), MOVIE, bad, MOVIE_META)["odd_frame"]
    assert not r["ok"] and r["where"] == "frame003.webp", r
    jump = dict(good)
    jump["frame003.webp"] = disk(60, 200, 30)                 # one frame of another place
    r = judge(str(tmp_path / "j"), MOVIE, jump, MOVIE_META)["odd_frame"]
    assert not r["ok"], r


def test_gray_colour(tmp_path):
    item = {"name": "c", "kind": "composite", "frame": "N1", "group": "plain", "watch": ""}
    r = judge(str(tmp_path / "c"), item, {"composite.webp": disk(rgb=(180, 150, 110))})["gray_colour"]
    assert r["ok"], r
    meta = {"kind": "composite", "reports": {"composite.webp": {"grey": "not aligned"}}}
    r = judge(str(tmp_path / "g"), item, {"composite.webp": disk()}, meta)["gray_colour"]
    assert not r["ok"] and "not aligned" in r["detail"], r
    # a movie that should play in colour: two of three frames gray against max_gray 0.5
    mv = {**MOVIE, "checks": {"gray_colour": {"max_gray": 0.5}}}
    frames = {"frame000.webp": disk(rgb=(180, 150, 110)), "frame001.webp": disk(130), "frame002.webp": disk(140)}
    r = judge(str(tmp_path / "m"), mv, frames, MOVIE_META)["gray_colour"]
    assert not r["ok"] and abs(r["value"] - 2 / 3) < 0.01, r
    # a gray movie is not judged unless it asks
    assert "gray_colour" not in judge(str(tmp_path / "n"), MOVIE, frames, MOVIE_META)


def test_body_tint(tmp_path):
    item = {"name": "e", "kind": "still", "frame": "N1", "group": "plain", "watch": "", "checks": {"body_tint": {}}}
    r = judge(str(tmp_path / "o"), item, {"still.webp": disk(rgb=(190, 170, 131))})["body_tint"]   # [1.12, 1, 0.77]
    assert not r["ok"], r
    r = judge(str(tmp_path / "g"), item, {"still.webp": disk(rgb=(173, 170, 167))})["body_tint"]   # [1.02, 1, 0.98]
    assert r["ok"], r


def test_clipped_white(tmp_path):
    item = {"name": "w", "kind": "still", "frame": "N1", "group": "plain", "watch": "", "checks": {"clipped_white": {"max": 0.01}}}
    r = judge(str(tmp_path / "w"), item, {"still.webp": disk(rgb=(255, 255, 255))})["clipped_white"]
    assert not r["ok"], r
    r = judge(str(tmp_path / "g"), item, {"still.webp": disk(rgb=(200, 200, 200))})["clipped_white"]
    assert r["ok"], r


def test_limb_halo(tmp_path):
    item = {"name": "l", "kind": "still", "frame": "N1", "group": "plain", "watch": "", "checks": {"limb_halo": {}}}
    r = judge(str(tmp_path / "h"), item, {"still.webp": disk(r=50, halo=0.12)})["limb_halo"]
    assert not r["ok"], r
    r = judge(str(tmp_path / "g"), item, {"still.webp": disk(r=50)})["limb_halo"]
    assert r["ok"], r


def test_verdicts():
    ok, bad, worse = {"ok": True, "value": 0, "limit": 1}, {"ok": False, "value": 2, "limit": 1}, {"ok": False, "value": 9, "limit": 1}
    assert bc.verdict("odd_frame", ok, ok) == "pass"
    assert bc.verdict("odd_frame", bad, ok) == "fixed"
    assert bc.verdict("odd_frame", ok, bad) == "REGRESSION"
    assert bc.verdict("odd_frame", bad, bad) == "known"
    assert bc.verdict("odd_frame", bad, worse) == "REGRESSION"
    assert bc.verdict("odd_frame", ok, {"ok": False, "error": "x"}) == "error"


def test_compare_fails_on_a_check_regression(tmp_path, monkeypatch=None):
    """A movie that starts repeating a frame fails the run, though nothing else is worse by measure; a defect on
    both sides (known) does not."""
    a, b = disk(120), disk(128)
    items = [{"name": "rep", "kind": "pass", "frame": "N1", "group": "plain", "watch": ""},
             {"name": "gray", "kind": "composite", "frame": "N2", "group": "plain", "watch": ""}]
    orig = image_bench.load_items
    image_bench.load_items = lambda path=None: items
    try:
        for side, rep in (("b", {"frame000.webp": a, "frame001.webp": b, "frame002.webp": disk(136)}),
                          ("c", {"frame000.webp": a, "frame001.webp": a, "frame002.webp": disk(136)})):
            root = str(tmp_path / side)
            write(os.path.join(root, "rep"), rep, {**MOVIE_META, "name": "rep"})
            write(os.path.join(root, "gray"), {"composite.webp": disk()}, {"kind": "composite", "reports": {}})
            json.dump({"commit": side * 40, "versions": {}, "resolved": {}, "built": ["rep", "gray"], "failed": {}, "seconds": 1},
                      open(os.path.join(root, "build.json"), "w"))
        s = image_bench.compare(str(tmp_path / "b"), str(tmp_path / "c"), str(tmp_path / "o"), set(), {"rep": "a frame moved"},
                                log=lambda m: None, procs=1)
        assert "rep: repeat_frames" in s["checks"]["regressions"], s["checks"]
        assert "gray: gray_colour" in s["checks"]["known"], s["checks"]
        assert s["verdict"] != "FAIL"          # explained by --notes
        s = image_bench.compare(str(tmp_path / "b"), str(tmp_path / "c"), str(tmp_path / "o2"), set(), {},
                                log=lambda m: None, procs=1)
        assert s["verdict"] == "FAIL" and any("repeat_frames" in f for f in s["fails"]), s["fails"]
        assert not any("gray_colour" in f for f in s["fails"])
    finally:
        image_bench.load_items = orig


def test_items_resolve():
    """Every item's named checks exist and a module's ITEMS do not collide with the list."""
    for it in image_bench.load_items():
        bc.checks_for(it, {"pass_kind": "movie"} if it["kind"] == "pass" else None)


if __name__ == "__main__":
    import pathlib
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                args = [pathlib.Path(d)] if fn.__code__.co_argcount else []
                fn(*args)
            n += 1
            print("ok", name)
    print(f"{n} tests passed")
