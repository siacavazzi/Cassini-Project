#!/usr/bin/env python3
"""
The export's timing (web/frames/export.py timing, boomerang, mirror): the film ends as it plays, with no held pause
after its last picture (Sam, 2026-11-04: "dead space at the end of the movie"), and a Boomerang film plays forward,
then back to its first picture, each picture held as long both ways.

  python web/test_export_timing.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import export  # noqa: E402

FPS = export.FPS


def pics(times):
    return [{"id": f"N{i}", "cam": "N", "t": float(t)} for i, t in enumerate(times)]


# fixed rate: every picture, the last one too, holds 1/fps; the film lasts count/fps
for fps in (2, 10, 12, 24, 30):
    p = pics(range(0, 10 * 60, 60))
    export.timing(p, fps)
    secs = sum(e["frames"] for e in p) / FPS
    assert abs(secs - len(p) / fps) <= 1 / FPS, (fps, secs)
    assert abs(p[-1]["frames"] - FPS / fps) <= 1, (fps, p[-1]["frames"])

# adaptive: the last picture holds the film's median hold, not 1.5 s
p = pics([0, 30, 60, 90, 120, 150, 180, 2000])
export.timing(p, "auto")
holds = [e["hold"] for e in p[:-1]]
assert p[-1]["hold"] <= max(holds), (p[-1]["hold"], holds)
assert abs(p[-1]["hold"] - sorted(holds)[len(holds) // 2]) < 1e-3, (p[-1]["hold"], holds)

# a film of one picture still shows it a moment
p = pics([0])
export.timing(p, 12)
assert p[0]["frames"] == round(export.ONLY * FPS), p

# Boomerang: a b c d -> a b c d c b a, each picture held as long on the way back, starts in order
p = pics([0, 60, 120, 180])
export.timing(p, 12)
fwd = sum(e["frames"] for e in p)
b = export.boomerang(p)
assert [e["id"] for e in b] == ["N0", "N1", "N2", "N3", "N2", "N1", "N0"], [e["id"] for e in b]
assert [bool(e.get("back")) for e in b] == [False] * 4 + [True] * 3
assert all(b[n]["hold"] == b[export.mirror(n, 4)]["hold"] for n in range(len(b)))
assert all(b[n]["id"] == b[export.mirror(n, 4)]["id"] for n in range(len(b)))
assert [export.mirror(n, 4) for n in range(7)] == [0, 1, 2, 3, 2, 1, 0]
assert abs(sum(e["frames"] for e in b) - (2 * fwd - p[-1]["frames"])) <= 1
ats = [e["at"] for e in b]
assert ats == sorted(ats) and ats[0] == 0, ats
assert not any(e.get("back") for e in p), "boomerang changed the forward pictures"
# too few pictures to turn: left as they are
assert export.boomerang(pics([0, 1])) == pics([0, 1])

# options and the film's name: boom=1 is a choice of its own, off by default
q = {"from": ["2005-01-01T00:00:00"], "until": ["2005-01-01T01:00:00"]}
off, on = export.options(q), export.options(dict(q, boom=["1"]))
assert not off["boom"] and on["boom"]
assert export.job_id(off) != export.job_id(on)
print("ok")
