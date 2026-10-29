#!/usr/bin/env python3
"""
Cache slices: which stretches of the mission a picture cache holds, so a test build of one year (prebuild.py
--years 2004) can be looked at in the page without the rest of the mission being made on demand.

prebuild.py adds a record to <cache>/slices.json as a phase finishes: the phase, the stretch it built (from, until,
UTC; none for the whole mission) and the picture versions it built them under (the VERSION strings that name the
cache folders). The frame server answers /frames/slices.json with the records made under its own versions, so a
slice built by newer code into a shared cache never narrows a server on older code, whose pictures are in other
folders. The stretches the page keeps to are those every recorded phase covers. No file, or no record under the
server's versions, means the whole mission: a cache built before slices (the live one) stays as it was.

  {"records": [{"phase": "processed", "from": "2004-01-01T00:00:00", "until": "2005-01-01T00:00:00",
                "versions": {"frame_server.COLOR_VERSION": "color-v30", ...}, "items": 41000, "errors": 0,
                "at": "2026-10-28T20:00:00Z"}, ...]}
"""
import datetime
import json
import os
import re
import threading

NAME = "slices.json"
_lock = threading.Lock()


def versions(**modules):
    """The picture makers' version strings ({"frame_server.COLOR_VERSION": "color-v30", ...}), read from the modules
    given by name (frame_server=..., obs_mosaic=...): the server runs frame_server as __main__, so the names are
    passed rather than read from the modules."""
    out = {}
    for name, mod in sorted(modules.items()):
        for key, value in vars(mod).items():
            if not re.match(r"^[A-Z0-9_]*(VERSION|VERSIONS|SUFFIX)$", key) or key == "SERVER_VERSION":   # the code's commit, not a picture's
                continue
            if isinstance(value, str) or (isinstance(value, dict) and all(isinstance(x, str) for x in value.values())):
                out[f"{name}.{key}"] = value
    return out


def parse_years(text):
    """--years 2004, 2004-2006 or 2004,2008 as [(from, until)] UTC strings, until the next year's start."""
    out = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        a, b = int(a), int(b or a)
        if not (1997 <= a <= b <= 2017):
            raise ValueError(f"years run 1997-2017: {part}")
        out.append((f"{a:04d}-01-01T00:00:00", f"{b + 1:04d}-01-01T00:00:00"))
    return merge(out)


def utc(text):
    """A --from/--until time (2004-06-30, 2004-06-30T12:00 or with seconds) as YYYY-MM-DDTHH:MM:SS."""
    t = datetime.datetime.fromisoformat(text.rstrip("Z"))
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def seconds(text):
    """A span end (YYYY-MM-DDTHH:MM:SS, UTC) in seconds since 1970, as the index's seconds_1970."""
    return datetime.datetime.fromisoformat(text).replace(tzinfo=datetime.timezone.utc).timestamp()


def merge(spans):
    """Spans [(from, until)] sorted, touching or overlapping ones joined. None for an end is the mission's."""
    lo, hi = "", "￿"
    out = []
    for a, b in sorted(((a or lo, b or hi) for a, b in spans)):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(None if a == lo else a, None if b == hi else b) for a, b in out]


def intersect(xs, ys):
    """The stretches in both lists of merged spans."""
    lo, hi = "", "￿"
    out = []
    for a, b in xs:
        for c, d in ys:
            s, e = max(a or lo, c or lo), min(b or hi, d or hi)
            if s < e:
                out.append((None if s == lo else s, None if e == hi else e))
    return merge(out)


def read(cache):
    try:
        with open(os.path.join(cache, NAME)) as fh:
            got = json.load(fh)
        return got if isinstance(got.get("records"), list) else {"records": []}
    except (OSError, ValueError, AttributeError):
        return {"records": []}


def record(cache, phase, spans, vers, items=0, errors=0):
    """A finished phase's stretches (None: the whole mission) added to the cache's slices.json, written whole (a
    .part file moved over it) so the server never reads half of one."""
    with _lock:
        got = read(cache)
        at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for a, b in spans or [(None, None)]:
            got["records"].append({"phase": phase, "from": a, "until": b, "versions": vers, "items": items,
                                   "errors": errors, "at": at})
        os.makedirs(cache, exist_ok=True)
        part = os.path.join(cache, NAME + f".part{os.getpid()}")
        with open(part, "w") as fh:
            json.dump(got, fh, indent=1)
        os.replace(part, os.path.join(cache, NAME))


def covered(cache, vers):
    """What the cache holds under these versions: {"spans": [[from, until], ...] (None ends: the mission's), or
    None for the whole mission, "phases": {phase: spans}}. A phase's stretches are joined over its records; the
    spans are those every recorded phase covers."""
    phases = {}
    for r in read(cache)["records"]:
        if not isinstance(r, dict) or r.get("versions") != vers or not r.get("phase"):
            continue
        phases.setdefault(r["phase"], []).append((r.get("from"), r.get("until")))
    phases = {p: merge(s) for p, s in phases.items()}
    spans = None
    for s in phases.values():
        spans = s if spans is None else intersect(spans, s)
    if spans == [(None, None)]:
        spans = None
    return {"spans": [list(s) for s in spans] if spans is not None else None,
            "phases": {p: [list(x) for x in s] for p, s in sorted(phases.items())}}
