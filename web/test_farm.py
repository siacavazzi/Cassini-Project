#!/usr/bin/env python3
"""Build farm (web/frames/farm.py): units and their order, claims shared by two machines (heavy end and light end,
pinned units, a restart resuming its own claim), the prebuild commands a unit runs, shipping with freeing, and
verify / compare / merge of the machines' caches.

  python web/test_farm.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import farm  # noqa: E402
import slices  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def test_units():
    months = {(2004, 3): 100, (2004, 9): 300, (2005, 1): 40, (2007, 2): 500, (2007, 8): 500, (1999, 1): 5}
    units = farm.make_units(months, split_share=0.3)
    names = [u["unit"] for u in units]
    assert names == ["2007a", "2007b", "2004", "2005", "1999"], names        # 2007 is >30%: two halves
    u = units[0]
    assert (u["from"], u["until"], u["pictures"]) == ("2007-01-01", "2007-07-01", 500)
    assert units[2]["years"] == "2004" and units[2]["pictures"] == 400
    costly = farm.make_units(months, year_cost={"2005": 30}, split_share=0.9)
    assert costly[0]["unit"] == "2005", costly                               # 40 pictures at 30x outweigh 1000
    assert farm.unit_spans(units[0]) == [("2007-01-01T00:00:00", "2007-07-01T00:00:00")]
    assert farm.unit_spans(units[2]) == [("2004-01-01T00:00:00", "2005-01-01T00:00:00")]
    return 1


def test_estimate():
    plan = {"units": [{"unit": "all-frames", "only": "mini", "hours": 1.0, "weight": 0},
                      {"unit": "a", "weight": 3600}, {"unit": "b", "weight": 3600}, {"unit": "c", "weight": 3600}]}
    f = {"s_per_picture": 1.0, "machines": {"mini": {"speed": 1, "end": "light"}, "mbp": {"speed": 2, "end": "heavy"}}}
    est = farm.estimate(plan, f)
    assert abs(est["machines"]["mbp"] - 1.0) < 1e-9 and abs(est["machines"]["mini"] - 2.0) < 1e-9, est
    assert abs(est["hours"] - 2.0) < 1e-9
    return 1


def test_claims(tmp):
    shared = farm.Shared(os.path.join(tmp, "farm"))
    plan = {"units": [{"unit": "all-frames", "only": "mini", "phases": ["frames"]},
                      {"unit": "2007", "weight": 9}, {"unit": "2005", "weight": 5}, {"unit": "2003", "weight": 1}]}
    mini, mbp = {"end": "light"}, {"end": "heavy"}
    assert farm.next_unit(shared, plan, "mbp", mbp)["unit"] == "2007"       # heaviest; never the pinned one
    assert farm.next_unit(shared, plan, "mini", mini)["unit"] == "all-frames"
    # mini restarted before finishing all-frames: it resumes its own claim, it doesn't take another
    assert farm.next_unit(shared, plan, "mini", mini)["unit"] == "all-frames"
    shared.write("{}", "done", "all-frames.json")
    assert farm.next_unit(shared, plan, "mini", mini)["unit"] == "2003"     # the lightest left
    shared.write("{}", "done", "2007.json")
    assert farm.next_unit(shared, plan, "mbp", mbp)["unit"] == "2005"
    shared.write("{}", "done", "2005.json")
    shared.write("{}", "done", "2003.json")
    assert farm.next_unit(shared, plan, "mbp", mbp) is None
    assert json.loads(shared.read("claims", "2005", "owner.json"))["machine"] == "mbp"
    assert shared.claim("2005") is False
    return 1


def test_commands():
    m = {"name": "mbp", "cache": "/c", "status": "/s", "pause": "/p", "procs": 16, "max_load": 40, "min_free": 50}
    cmd = farm.prebuild_cmd(m, {"unit": "2007a", "from": "2007-01-01", "until": "2007-07-01"}, "movies", "py")
    s = " ".join(cmd)
    assert cmd[0] == "py" and cmd[2].endswith("prebuild.py") and cmd[3] == "movies", cmd
    for want in ("--cache /c", "--status /s", "--pause /p", "--procs 16 --balanced", "--watched-first",
                 "--from 2007-01-01 --until 2007-07-01", "--max-load 40", "--min-free 50"):
        assert want in s, (want, s)
    cmd = farm.prebuild_cmd(dict(m, procs=1), {"unit": "all-frames", "phases": ["frames"]}, "frames", "py")
    assert "--years" not in cmd and "--from" not in cmd and "--procs" not in cmd and "--watched-first" not in cmd
    assert "--years" in farm.prebuild_cmd(m, {"unit": "2004", "years": "2004"}, "processed", "py")
    return 1


def test_ship_and_free(tmp):
    cache, hub = os.path.join(tmp, "mbp-cache"), os.path.join(tmp, "hub", "incoming-mbp")
    os.makedirs(hub)
    write(os.path.join(cache, "processed", "v1", "1024", "A.webp"), "a")
    write(os.path.join(cache, "obs", "SAT_1", "plan.json"), "{}")
    write(os.path.join(cache, "processed", "v1", "1024", "B.webp.part123"), "half")
    slices.record(cache, "processed", [("2004-01-01T00:00:00", "2005-01-01T00:00:00")], {"v": "1"})
    m = {"name": "mbp", "cache": cache, "ship_to": hub, "free": True}
    sh = farm.Shipper(m, os.path.join(tmp, "ship.log"))
    sh.boundary()                       # after unit 1: copies in the background
    sh.thread.join()
    assert os.path.exists(os.path.join(hub, "processed", "v1", "1024", "A.webp"))
    assert not os.path.exists(os.path.join(hub, "processed", "v1", "1024", "B.webp.part123"))
    assert os.path.exists(os.path.join(cache, "processed", "v1", "1024", "A.webp"))   # not freed yet
    write(os.path.join(cache, "processed", "v1", "1024", "C.webp"), "c")              # unit 2 makes C
    sh.boundary(final=True)             # frees unit 1's files, ships and frees unit 2's
    assert not os.path.exists(os.path.join(cache, "processed", "v1", "1024", "A.webp"))
    assert not os.path.exists(os.path.join(cache, "processed", "v1", "1024", "C.webp"))
    assert os.path.exists(os.path.join(hub, "processed", "v1", "1024", "C.webp"))
    assert os.path.exists(os.path.join(cache, "slices.json"))                         # kept: later records join it
    assert json.load(open(os.path.join(hub, "slices.json")))["records"][0]["phase"] == "processed"
    # a file missing on the hub is never freed
    write(os.path.join(cache, "x", "D.webp"), "d")
    path, n = sh._manifest()
    assert n == 1
    sh.manifests = [path]
    sh.free()
    assert os.path.exists(os.path.join(cache, "x", "D.webp")) and sh.manifests == [path]
    return 1


def test_merge_compare_verify(tmp):
    a, b = os.path.join(tmp, "mini"), os.path.join(tmp, "incoming")
    write(os.path.join(a, "obs", "NY_PASS", "512", "f1.webp"), "same")
    write(os.path.join(a, "obs", "NY_PASS", "512", "f2.webp"), "mini")
    write(os.path.join(b, "obs", "NY_PASS", "512", "f1.webp"), "same")      # New Year pass: both built it
    write(os.path.join(b, "obs", "NY_PASS", "512", "f2.webp"), "mbp!")
    write(os.path.join(b, "obs", "NY_PASS", "512", "f3.webp"), "new")
    write(os.path.join(b, "processed", "v1", "1024", "Z.webp"), "z")        # a whole folder mini lacks
    vers = {"frame_server.PROC_VERSION": "proc-v19"}
    slices.record(a, "processed", [("2003-01-01T00:00:00", "2004-01-01T00:00:00")], vers)
    slices.record(b, "processed", [("2004-01-01T00:00:00", "2005-01-01T00:00:00")], vers, errors=0)
    got = farm.compare(a, b)
    assert got["common"] == 2 and got["differ"] == [os.path.join("obs", "NY_PASS", "512", "f2.webp")], got
    units = [{"unit": "2003", "years": "2003"}, {"unit": "2004", "years": "2004"}]
    assert farm.check_cache(a, units, ["processed"], vers) == ["2004 processed: not recorded"]
    out = farm.merge(a, b, move=True)
    assert out["same"] == 1 and out["differ"] == [os.path.join("obs", "NY_PASS", "512", "f2.webp")], out
    assert out["moved"] == 2, out
    assert open(os.path.join(a, "obs", "NY_PASS", "512", "f2.webp")).read() == "mini"   # the target's is kept
    assert os.path.exists(os.path.join(a, "processed", "v1", "1024", "Z.webp"))
    assert not os.path.exists(os.path.join(b, "processed"))                              # moved, not copied
    assert farm.join_slices(a, [b]) == 1 and farm.join_slices(a, [b]) == 0               # joined once
    assert farm.check_cache(a, units, ["processed"], vers) == []
    assert slices.covered(a, vers)["spans"] == [["2003-01-01T00:00:00", "2005-01-01T00:00:00"]]
    slices.record(a, "processed", [("2004-01-01T00:00:00", "2005-01-01T00:00:00")], {"other": "v"}, errors=3)
    probs = farm.check_cache(a, units, ["processed"], vers)
    assert any("other version" in p for p in probs), probs
    c = os.path.join(tmp, "copy")
    out = farm.merge(c, a)
    assert out["copied"] == 4 and os.path.exists(os.path.join(a, "obs", "NY_PASS", "512", "f3.webp"))
    return 1


def test_job(tmp):
    """Units register with the Mini's job helper; a missing or failing helper never stops the build."""
    log = os.path.join(tmp, "job.log")
    fake = os.path.join(tmp, "job")
    write(fake, f"#!/bin/sh\necho \"$@\" >> {log}\n")
    os.chmod(fake, 0o755)
    shared = farm.Shared(os.path.join(tmp, "jobfarm"))
    f = {"job": {"cmd": fake}, "s_per_picture": 1.0}
    farm.job(shared, f, "start", "farm-mini-2004", "cache build: unit 2004", "--pct", 0)
    farm.job(shared, f, "done", "farm-mini-2004", "all 6 phases")
    lines = open(log).read().splitlines()
    assert lines == ["start farm-mini-2004 cache build: unit 2004 --pct 0", "done farm-mini-2004 all 6 phases"], lines
    farm.job(shared, {"job": {"cmd": os.path.join(tmp, "missing")}}, "start", "x", "y")   # no helper: no error
    farm.job(shared, {}, "start", "x", "y")                                               # no "job": nothing
    eta = farm.unit_eta(f, {"speed": 2}, {"weight": 7200})
    assert len(eta) == 16 and eta[4] == "-" and eta[13] == ":", eta
    return 1


def test_cli_plan(tmp):
    """plan writes plan.json from farm.json and a catalogue, and prints an estimate."""
    sh = os.path.join(tmp, "cli")
    os.makedirs(sh)
    idx = os.path.join(tmp, "index.csv")
    with open(idx, "w") as fh:
        fh.write("id,seconds_1970\n")
        for k in range(50):
            fh.write(f"N{k},{1100000000 + k * 3000000}\n")
    cfg = {"s_per_picture": 1, "whole_mission": [{"phase": "frames", "only": "mini"}],
           "machines": {"mini": {"speed": 1, "end": "light"}, "mbp": {"speed": 2, "end": "heavy"}}}
    write(os.path.join(sh, "farm.json"), json.dumps(cfg))
    out = subprocess.run([sys.executable, farm.__file__, "plan", "--shared", sh, "--index", idx],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    plan = json.load(open(os.path.join(sh, "plan.json")))
    assert plan["units"][0]["unit"] == "all-frames" and sum(u["pictures"] for u in plan["units"][1:]) == 50
    assert "whole build" in out.stdout, out.stdout
    return 1


def main():
    ok = 0
    with tempfile.TemporaryDirectory() as tmp:
        ok += test_units()
        ok += test_estimate()
        ok += test_claims(tmp)
        ok += test_commands()
        ok += test_ship_and_free(tmp)
        ok += test_merge_compare_verify(tmp)
        ok += test_job(tmp)
        ok += test_cli_plan(tmp)
    print(f"farm: {ok} tests passed")


if __name__ == "__main__":
    main()
