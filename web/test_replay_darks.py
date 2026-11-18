#!/usr/bin/env python3
"""build_data leaves frames that hold no picture (not_pictures: darks, lamp frames) out of the page's catalog, and their
image pointing out of the year's attitude file, so an export made before that rule cannot put them back on the page.
  python web/test_replay_darks.py"""
import json, os, struct, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "replay"), os.path.join(HERE, "frames")]
import build_data as bd
import not_pictures

dark = sorted(not_pictures.ids())[0]
ids = ["N1000000001_1", dark, "N1000000003_1"]
with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "catalog")); os.makedirs(os.path.join(d, "att"))
    cat = {k: [0.0, 0.0, 0.0] for k in bd.CATALOG_KEYS}
    cat.update(id=ids, et=[1.0, 2.0, 3.0], target=["SATURN"] * 3)
    json.dump(cat, open(os.path.join(d, "catalog", "2017.json"), "w"))
    q = b"".join(struct.pack("<4f", i, i, i, i) for i in (1, 2, 3))
    bg = struct.pack("<d", 5.0) + struct.pack("<4f", 9, 9, 9, 9)
    open(os.path.join(d, "att", "2017.bin"), "wb").write(b"CATT" + struct.pack("<HHII", 1, 0, 3, 1) + q + bg)
    slim = bd.slim_catalog(d, 2017)
    assert slim["id"] == [ids[0], ids[2]] and slim["et"] == [1.0, 3.0], slim
    raw = bd.attitude_for(os.path.join(d, "att"), 2017, len(slim["et"]))
    assert raw[:4] == b"CATT" and struct.unpack("<HHII", raw[4:16]) == (1, 0, 2, 1)
    assert raw[16:48] == struct.pack("<4f", 1, 1, 1, 1) + struct.pack("<4f", 3, 3, 3, 3)
    assert raw[48:] == bg
print("ok")
