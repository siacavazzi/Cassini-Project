"""A pass's tile reports kept in one file by the pre-build (obs_mosaic.keep_reports, REPORTS_FILE) and read back by a
server's first look at the pass (plan, into the pass's record): the same reports as each tile's own file gives, to the
JSON text, with no tile's file read; a pass without the file reads each tile's as before. Made-up reports with the
values tiles carry (floats, nested lists, None, text, booleans). Run: python web/test_reports_file.py"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

K = 12
root = tempfile.mkdtemp()
try:
    cache = os.path.join(root, "cache")
    u = {"key": ("MIMAS", "ISS_TEST_REPORTS", "N", 0), "frames": [(f"x/N{1500000000 + j}_1.png", f"N{1500000000 + j}_1",
                                                                     "CL1", 1.1e9 + j, 0, 0, 0, 1.0) for j in range(K)]}
    p = {"display_scale": {"test": "reports"}, "key": list(u["key"])}
    os.makedirs(om.folder(u, cache), exist_ok=True)
    with open(os.path.join(om.folder(u, cache), om.PLAN_FILE), "w") as fh:
        json.dump(p, fh)
    there = om._tiles(u, cache, p["display_scale"])
    os.makedirs(there)
    for j in range(K):
        rep = {"n": j, "id": u["frames"][j][1], "filter": "CL1", "t": 1.1e9 + j + 0.123456789, "stacked": None,
               "calibrated": j % 3 != 0, "native_offset": [j * 1.0000000001, -j / 3], "offset": [j / 7, 1e-17 * j],
               "box": [-512.5, -511.0, 1024, 1023], "outline": [[0.1 * j, 2.0], [3.0, 4.25], [5.5, -6.0], [7.0, 8.0]]}
        if j == 4:
            rep = {"n": j, "id": u["frames"][j][1], "filter": "CL1", "t": 1.1e9 + j, "why": "not placed by SPICE"}
        with open(os.path.join(there, f"{j}.json"), "w") as fh:
            fh.write(json.dumps(rep, default=str))

    def fresh():
        om._passes.clear()
        p2 = om.plan(u, cache)
        return p2, om._reports(u, cache, p2, range(K))

    p1, want = fresh()                        # each tile's own file
    assert not os.path.exists(om._reports_path(there))
    om.keep_reports(u, cache, p1)
    assert os.path.exists(om._reports_path(there)) and not os.path.exists(os.path.join(there, "reports.json"))
    made = om._tile_made
    om._tile_made = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a tile's own file read"))
    p2, got = fresh()                         # the reports file, no tile's own file
    om._tile_made = made
    assert got == want and json.dumps(got) == json.dumps(want)
    assert om._all_made(u, cache, p2, 0, K - 1), "every tile known made without looking"
    # a pass whose reports file is missing (made before it, or not whole) reads each tile's file as before
    os.remove(om._reports_path(there))
    _, again = fresh()
    assert again == want and json.dumps(again) == json.dumps(want)
    print(f"{K} reports: from one file the same as from their own, to the JSON text")
finally:
    shutil.rmtree(root, ignore_errors=True)
print("reports file: ok")
