"""The image benchmark's report and verdict on made-up results (no pipeline): identical bytes, encoder noise, a
change in the target, a change outside it with and without a note, a guard tripped, an item not built.
Run: python -m pytest web/frames/test_image_bench.py"""
import io
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import image_bench  # noqa: E402


def picture(rng, bright=1.0, hole=False, sharp=False):
    a = np.zeros((256, 256, 4), np.uint8)
    yy, xx = np.mgrid[:256, :256]
    disk = (yy - 128) ** 2 + (xx - 128) ** 2 < 90 ** 2
    base = (60 + 80 * np.sin(xx / 9.0) ** 2 + rng.normal(0, 3, (256, 256))) * bright
    if sharp:
        base = base + 40 * np.sign(np.sin(xx / 2.0))
    a[..., :3] = np.clip(base, 0, 255)[..., None]
    a[..., 3] = 255
    a[~disk, :3] = 0
    if hole:
        a[100:160, 100:160, :3] = 0
    return a


def save(folder, name, arr, lossless=True):
    os.makedirs(folder, exist_ok=True)
    Image.fromarray(arr).save(os.path.join(folder, name), lossless=lossless, quality=100)


def results(root, built, pics):
    os.makedirs(root, exist_ok=True)
    for name, arr in pics.items():
        save(os.path.join(root, name), "still.webp", arr)
        json.dump({"name": name, "kind": "still", "seconds": 1}, open(os.path.join(root, name, "meta.json"), "w"))
    json.dump({"commit": os.path.basename(root) * 4, "versions": {}, "resolved": {n: {"time": "2004-01-01T00:00:00"} for n in built},
               "built": built, "failed": {}, "seconds": 60}, open(os.path.join(root, "build.json"), "w"))


def items(names):
    return [{"name": n, "kind": "still", "frame": "N1", "group": "plain", "watch": ""} for n in names]


def test_verdicts(tmp_path, monkeypatch):
    rng = np.random.default_rng(1)
    same = picture(rng)
    target_a, target_b = picture(rng, hole=True), picture(rng)
    moved_a, moved_b = picture(rng), picture(rng, bright=1.3)
    sharp_a, sharp_b = picture(rng), picture(rng, sharp=True)
    noisy = same.copy()
    noisy[50, 50, 0] = min(255, int(noisy[50, 50, 0]) + 1)
    names = ["same", "noise", "fix", "drift", "sharpened", "gone"]
    monkeypatch.setattr(image_bench, "load_items", lambda path=None: items(names))
    results(str(tmp_path / "base"), names, {"same": same, "noise": same, "fix": target_a, "drift": moved_a, "sharpened": sharp_a, "gone": same})
    results(str(tmp_path / "cand"), names[:-1], {"same": same, "noise": noisy, "fix": target_b, "drift": moved_b, "sharpened": sharp_b})
    s = image_bench.compare(str(tmp_path / "base"), str(tmp_path / "cand"), str(tmp_path / "out"), {"fix"}, {}, log=lambda m: None)
    by = {r["name"]: r for r in s["rows"]}
    assert by["same"]["status"] == "identical"
    assert by["noise"]["status"] == "identical"            # one level off: encoder rounding, not a change
    assert by["fix"]["status"] == "changed" and by["fix"]["target"]
    assert "lit" not in by["fix"]["worse"]                  # the hole filled: lit went up, not down
    assert by["drift"]["status"] == "changed" and not by["drift"]["target"]
    assert "detail" in by["sharpened"]["worse"]             # the over-processed look is caught
    assert by["gone"]["status"] == "not built"
    assert s["verdict"] == "FAIL"
    assert any("drift" in f for f in s["fails"]) and any("sharpened" in f for f in s["fails"]) and any("gone" in f for f in s["fails"])
    assert os.path.exists(tmp_path / "out" / "sheets" / "fix.jpg")
    assert os.path.exists(tmp_path / "out" / "index.html") and os.path.exists(tmp_path / "out" / "report.md")

    # explained, built: a change outside the target with a note and no guard tripped needs eyes, not a fail
    monkeypatch.setattr(image_bench, "load_items", lambda path=None: items(["same", "fix", "drift"]))
    results(str(tmp_path / "b2"), ["same", "fix", "drift"], {"same": same, "fix": target_a, "drift": moved_a})
    results(str(tmp_path / "c2"), ["same", "fix", "drift"], {"same": same, "fix": target_b, "drift": moved_b})
    s = image_bench.compare(str(tmp_path / "b2"), str(tmp_path / "c2"), str(tmp_path / "out2"), {"fix"},
                            {"drift": "brighter by the new white point, intended"}, log=lambda m: None)
    assert s["verdict"] == "NEEDS EYES", s["fails"]


def test_guards_one_by_one():
    base = {"clipped": 0.01, "detail": 0.10, "seam": 1.2, "centre": [0, 0], "lit": 0.5}
    assert image_bench.worse("still", base, dict(base)) == {}
    assert "clipped" in image_bench.worse("still", base, {**base, "clipped": 0.02})
    assert "detail" in image_bench.worse("still", base, {**base, "detail": 0.12})
    assert "seam" in image_bench.worse("pass", base, {**base, "seam": 1.4})
    assert "centre" in image_bench.worse("still", base, {**base, "centre": [10, 0]})
    assert "lit" in image_bench.worse("still", base, {**base, "lit": 0.45})
    assert "crushed" in image_bench.worse("still", base, {**base, "crushed": 0.01})


def test_targets(tmp_path, monkeypatch):
    rng = np.random.default_rng(2)
    same, a, b = picture(rng), picture(rng), picture(rng, bright=1.2)
    monkeypatch.setattr(image_bench, "load_items", lambda path=None: items(["same", "fix"]))
    results(str(tmp_path / "b"), ["same", "fix"], {"same": same, "fix": a})
    results(str(tmp_path / "c"), ["same", "fix"], {"same": same, "fix": b})
    quiet = dict(log=lambda m: None, procs=1)
    # a named target that did not change fails: the rule needs it better
    s = image_bench.compare(str(tmp_path / "b"), str(tmp_path / "c"), str(tmp_path / "o1"), {"same"}, {"fix": "x"}, **quiet)
    assert s["verdict"] == "FAIL" and any("did not change" in f for f in s["fails"])
    # --target all: every item is a target; an unchanged one is fine
    s = image_bench.compare(str(tmp_path / "b"), str(tmp_path / "c"), str(tmp_path / "o2"), {"all"}, {}, **quiet)
    assert s["verdict"] == "NEEDS EYES" and not s["collateral"]
    # names not in the list are refused
    try:
        image_bench.compare(str(tmp_path / "b"), str(tmp_path / "c"), str(tmp_path / "o3"), {"fixx"}, {}, **quiet)
        assert False
    except SystemExit as e:
        assert "fixx" in str(e)


def test_missing_picture(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    p = picture(rng)
    monkeypatch.setattr(image_bench, "load_items", lambda path=None: items(["gone"]))
    results(str(tmp_path / "b"), ["gone"], {"gone": p})
    results(str(tmp_path / "c"), ["gone"], {"gone": p})
    save(str(tmp_path / "b" / "gone"), "frame001.webp", p)   # the base makes a second picture the candidate does not
    s = image_bench.compare(str(tmp_path / "b"), str(tmp_path / "c"), str(tmp_path / "o"), set(), {"gone": "x"}, log=lambda m: None, procs=1)
    assert "missing" in s["rows"][0]["worse"]
