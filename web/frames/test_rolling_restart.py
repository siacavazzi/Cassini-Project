#!/usr/bin/env python3
"""obs_mosaic.rolling_restart (#524): a mosaic movie a stopped build left part made is made again from its first
picture; a pass made whole or not begun is left alone; a pass this process is growing is left alone.
python web/frames/test_rolling_restart.py"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obs_mosaic as om  # noqa: E402


def _pass(tmp, n=5):
    u = {"key": ("MIMAS", "ISS_TEST", "N", 0), "frames": [(None, f"N{i}_1") for i in range(n)]}
    calls = []

    def layout(u, i, cache, laps=1, fade=(0, 0), **k):
        calls.append(i)
        return (None,) * 5 + (f"lap-1-{i}",)
    om.rolling_layout = layout
    om._rolling_path = lambda u, made, size, cache, fmt="webp", out=1024: os.path.join(tmp, f"{made[5]}.{fmt}")
    return u, calls


def _make(tmp, idx):
    for i in idx:
        for ext in (".webp", ".hdr.webp", ".json"):
            open(os.path.join(tmp, f"lap-1-{i}{ext}"), "w").close()


def test_part_made_is_cleared():
    with tempfile.TemporaryDirectory() as tmp:
        u, _ = _pass(tmp)
        _make(tmp, [0, 1, 2])
        assert om.rolling_restart(u, 1024, tmp) == 3
        assert os.listdir(tmp) == []


def test_whole_and_unbegun_left_alone_cheaply():
    with tempfile.TemporaryDirectory() as tmp:
        u, calls = _pass(tmp)
        _make(tmp, range(5))
        assert om.rolling_restart(u, 1024, tmp) == 0 and len(os.listdir(tmp)) == 15
        assert calls == [4]                       # (the last picture kept: nothing else laid out)
    with tempfile.TemporaryDirectory() as tmp:
        u, calls = _pass(tmp)
        assert om.rolling_restart(u, 1024, tmp) == 0
        assert calls == [4, 0]                    # (the first missing: none made)


def test_growing_pass_left_alone():
    with tempfile.TemporaryDirectory() as tmp:
        u, _ = _pass(tmp)
        _make(tmp, [0, 1])
        om._rolled[(u["key"], "mode", "L", (0, 0, 1, 1))] = [(frozenset(), None)]
        try:
            assert om.rolling_restart(u, 1024, tmp) == 0 and len(os.listdir(tmp)) == 6
        finally:
            om._rolled.clear()


def test_stretch_only():
    with tempfile.TemporaryDirectory() as tmp:
        u, calls = _pass(tmp)
        _make(tmp, [0, 1])
        assert om.rolling_restart(u, 1024, tmp, last=2) == 2 and calls[0] == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
