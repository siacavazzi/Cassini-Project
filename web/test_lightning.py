#!/usr/bin/env python3
"""
Checks for the lightning passes (web/frames/lightning.py) that need no data or kernels: the transcribed flash list
(Dyudina et al. 2013, Table A1), how it groups into passes and Moments, and that the frame server only sends what the
pre-build made (404 before). The pictures themselves are checked by eye (evidence/lightning).

  python web/test_lightning.py
"""
import csv, json, os, sys, tempfile, threading, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
sys.path.insert(0, os.path.dirname(HERE))
import lightning  # noqa: E402


def main():
    ok = 0
    fl = lightning.flashes()
    # the table: 30 flashes (the paper's 33 rows, three 2011 flashes listed twice with two backgrounds averaged; its
    # one green-filter flash left out), all clear or blue, all in storm alley's latitudes
    assert len(fl) == 30, len(fl)
    assert {f["filter"] for f in fl} == {"CL1", "BL1"}
    assert all(30 <= abs(f["lat"]) <= 37 for f in fl)
    assert all(f["id"].endswith("_1") for f in fl)
    ok += 1
    idx = lightning._index()
    ps = lightning.passes(fl, idx)
    assert [p["date"] for p in ps] == ["2009-08-17", "2009-11-30", "2011-02-26", "2011-03-06"], [p["date"] for p in ps]
    assert [p["view"] for p in ps] == ["night", "night", "day", "day"]
    assert ps[2]["obs"] == ["ISS_145SA_WIND5HR005_PRIME", "ISS_145SA_WIND5HR006_PRIME"]
    # every flash's picture is among its pass's pictures; a day pass shows only its flashes' filter
    for p in ps:
        ids = {f[0] for f in p["frames"]}
        assert {f["id"] for f in p["flashes"]} <= ids
        if p["view"] == "day":
            assert all("BL1" in f[2] for f in p["frames"])
    ok += 1
    # Moments: one per pass, except the one inside a moments.csv row (Great Northern Storm, 2011-03-06)
    with tempfile.TemporaryDirectory() as d:
        rows = lightning.write_moments(os.path.join(d, "m.csv"))
    assert [r["date"] for r in rows] == ["2009-08-17", "2009-11-30", "2011-02-26"]
    committed = list(csv.DictReader(open(lightning.MOMENTS_OUT, newline="")))
    assert [r["label"] for r in committed] == [r["label"] for r in rows], "lightning_moments.csv is out of date"
    ok += 1
    # the frame server: 404 until the pre-build made the files, then the files as they are
    import frame_server
    with tempfile.TemporaryDirectory() as cache:
        srv = frame_server.Server(("127.0.0.1", 0), frame_server.make_handler(None, cache, None))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        for path in ("/frames/lightning.json", "/frames/lightning/N1638307355_1.webp"):
            try:
                urllib.request.urlopen(url + path); raise AssertionError(path + " answered before it was made")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        os.makedirs(os.path.join(cache, lightning.LIGHTNING_VERSION))
        json.dump({"version": lightning.LIGHTNING_VERSION, "passes": []}, open(os.path.join(cache, lightning.LIGHTNING_VERSION, "lightning.json"), "w"))
        open(os.path.join(cache, lightning.LIGHTNING_VERSION, "N1638307355_1.webp"), "wb").write(b"RIFFxxxxWEBP")
        assert json.load(urllib.request.urlopen(url + "/frames/lightning.json"))["version"] == lightning.LIGHTNING_VERSION
        r = urllib.request.urlopen(url + "/frames/lightning/N1638307355_1.webp")
        assert r.headers["Content-Type"] == "image/webp" and r.read() == b"RIFFxxxxWEBP"
        try:
            urllib.request.urlopen(url + "/frames/lightning/..%2Fx.webp"); raise AssertionError("bad name answered")
        except urllib.error.HTTPError as e:
            assert e.code in (400, 404)
        srv.shutdown()
    ok += 1
    print(f"{ok} checks ok")


if __name__ == "__main__":
    main()
