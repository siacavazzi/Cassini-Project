"""The Movie Editor's film plan worked out in the page (web/cassini-os/src/plan-local.js, window.cassiniPlanLocal.plan)
is the frame server's (/export/plan.json: export.options, export.plan, export.public_plan), field for field: the page
reads the replay data's catalogs (build_data.slim_catalog with --groups: each frame's set and pass, ut/tr/raw_target)
and the passes' kind tables, the server its index and obs_mosaic, and both give the same pictures, tries, sets, color
mixes, timing, boomerang, size and cut.

Stretches: a busy Saturn day, a Titan flyby (T5, 2005-04-16), a mosaic movie pass, a stretch across New Year
(2005-12-31 to 2006-01-01, a leap second), each with the editor's options in turn (pictures shown, mosaics whole /
tiles / off, complete color pictures off, complete mosaics, fixed and adaptive timing, one camera, a cut, boomerang,
a picture size). Also export.options on the editor's queries, the wavelength table, and Python's set order.

Passes: with the geometry cache (CASSINI_GEOMETRY_CACHE, the Macs) obs_mosaic's own passes; without it (the cloud)
every frame would be in no kind of pass, so the test stands in a made-up pass rule (obs_mosaic.units replaced, as
web/test_sets_passes.py does: each observation's frames cut where the camera pauses half an hour, each pass given a
kind, toss-up and lap ends by a hash of its name) that both sides read the same way. --synthetic forces it.

  python web/test_plan_local.py [--data <export dir with catalog/<year>.json>] [--synthetic]
"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.join(HERE, "replay"), os.path.dirname(HERE)]
import argparse, calendar, json, math, subprocess, tempfile, time, zlib  # noqa: E401,E402

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=os.environ.get("CASSINI_REPLAY_EXPORT", "/mnt/project-files/web-replay/data"),
                help="export_tracks.py's folder (catalog/<year>.json), as build_data.py --data")
ap.add_argument("--synthetic", action="store_true", help="the made-up pass rule even with a geometry cache")
args, _ = ap.parse_known_args()

import reel  # noqa: E402
import obs_mosaic as om  # noqa: E402
import export  # noqa: E402
import sets_passes  # noqa: E402
import build_data  # noqa: E402

PLAN_JS = os.path.join(HERE, "cassini-os", "src", "plan-local.js")
SYNTHETIC = args.synthetic or not os.environ.get("CASSINI_GEOMETRY_CACHE")
YEARS = (2004, 2005, 2006)
idx, _ = reel.load_index()

if SYNTHETIC:
    # the made-up pass rule: (target, observation, camera) frames, cut at half-hour pauses; kind by a hash of the
    # pass's name; every seventh frame left out of the pass's tiles (a repeat exposure: in the pass, not drawn), the
    # pass's third frame dropped as a stray (in no pass); lap ends every fourth tile and the last
    t_all, ids_all = idx["seconds_1970"].to_numpy(), idx["id"].tolist()
    filt = (idx["filter1"].astype(str) + "/" + idx["filter2"].astype(str)).tolist()
    groups_rows = {}
    for (tg, ob, inst), rows in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices.items():
        groups_rows[(tg, ob, "N" if inst == "ISSNA" else "W")] = sorted(rows)
    KINDS = (None, "movie", "mosaic", "mosaic_movie", "movie", "mosaic", "mosaic_movie")
    _units = {}

    def units(target, obs, cam):
        if not isinstance(obs, str):
            return []
        k = (target, obs, cam)
        if k in _units:
            return _units[k]
        out = []
        for q in groups_rows.get(k, []):
            if not out or t_all[q] - out[-1]["last"] > 1800:
                out.append({"key": (target, obs, cam, len(out)), "frames": [], "last": float(t_all[q]), "rows": []})
            u = out[-1]
            u["last"] = float(t_all[q]); u["rows"].append(q)
            if len(u["rows"]) % 7 != 0 or len(u["rows"]) == 1:
                u["frames"].append(("", ids_all[q], filt[q], float(t_all[q]), 0, None, None, None))
        for u in out:
            h = zlib.crc32(f"{target}|{obs}|{cam}|{u['key'][3]}".encode())
            u["kind"] = KINDS[h % len(KINDS)]
            u["movie"], u["mosaic"] = u["kind"] == "movie", u["kind"] in ("mosaic", "mosaic_movie")
            u["tossup"] = u["kind"] == "movie" and h % 3 == 0
            if len(u["rows"]) > 5 and h % 4 == 0:
                u["off"] = {ids_all[u["rows"][2]]}
        _units[k] = out
        return out

    def lap_ends(u):
        if u.get("kind") != "mosaic_movie" or not u["frames"]:
            return []
        n = len(u["frames"])
        return sorted({j for j in range(3, n, 4)} | {n - 1})
    om.units = units
    om.lap_ends = lambda u: lap_ends(u)


def kind_table(fid):
    """The pass kind table the page reads for a frame (obs_mosaic.kind_of, the windows' warm=1 answer)."""
    if not SYNTHETIC:
        return om.kind_of(fid, None)
    found = om.unit_of(fid)
    if not found:
        return {"mosaic": False, "movie": False, "kind": None}
    us = om.units(*found[0]["key"][:3])
    ends = [v["frames"][j][1] for v in us for j in om.lap_ends(v)]
    return {"mosaic": bool(found[0]["mosaic"]), "movie": bool(found[0]["movie"]), "kind": found[0]["kind"], **({"lap_ends": ends} if ends else {})}


print(f"passes: {'made up (no geometry cache)' if SYNTHETIC else 'obs_mosaic with the geometry cache'}", flush=True)
groups = sets_passes.groups()
tmp = tempfile.mkdtemp()
parts = []
for y in YEARS:
    slim = build_data.slim_catalog(args.data, y, groups)
    assert "ut" in slim and "tr" in slim, "build_data.py without the index columns (PR #417)"
    path = os.path.join(tmp, f"{y}.json")
    json.dump(slim, open(path, "w"), separators=(",", ":"))
    parts.append({"start": calendar.timegm((y, 1, 1, 0, 0, 0)), "end": calendar.timegm((y + 1, 1, 1, 0, 0, 0)), "file": path})


def utc(s):
    return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M"))


# the four stretches
t = idx["seconds_1970"].to_numpy()
lo, hi = utc("2004-07-01T00:00"), utc("2007-01-01T00:00")
sat = idx[(t >= lo) & (t < hi) & (idx["TARGET_NAME"] == "SATURN")]
day = sat["seconds_1970"].floordiv(86400).value_counts().index[0] * 86400
STRETCHES = {"busy Saturn day": (day + 6 * 3600, day + 14 * 3600), "Titan flyby T5": (utc("2005-04-16T15:00"), utc("2005-04-16T23:00")),
             "New Year 2006": (utc("2005-12-31T20:00"), utc("2006-01-01T04:00"))}
# a mosaic movie pass with a few dozen frames (the first one found in 2005)
for (tg, ob, inst), rows in idx[(t >= utc("2005-03-01T00:00")) & (t < utc("2006-01-01T00:00"))].groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices.items():
    us = [u for u in om.units(tg, ob, "N" if inst == "ISSNA" else "W") if u.get("kind") == "mosaic_movie" and 20 <= len(u["frames"]) <= 200]
    if us:
        u = us[0]
        STRETCHES["mosaic movie " + ob] = (int(u["frames"][0][3]) - 1800, int(u["last"]) + 1800)
        break
assert len(STRETCHES) == 4, "no mosaic movie pass found"
iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(s))

# the kind tables of every frame of a mosaic movie pass in the stretches (the page asks for one frame of each)
kinds = {}
for a, b in STRETCHES.values():
    for fid in idx["id"][(t >= a - 86400) & (t <= b + 86400)]:
        f = om.unit_of(fid)
        if f and f[0].get("kind") == "mosaic_movie":
            kinds[fid] = kind_table(fid)


def norm(x):
    """JSON as both sides answer it: whole floats as ints, tuples as lists."""
    return json.loads(json.dumps(x), parse_float=lambda s: int(float(s)) if float(s).is_integer() else float(s))


if __name__ == "__main__":
    VARIANTS = [{}, {"pictures": "color"}, {"pictures": "processed"}, {"pictures": "raw"}, {"mos": "whole"}, {"mos": "tiles"},
                {"mos": "off"}, {"sets": "0"}, {"complete": "1"}, {"fps": "12"}, {"cams": "W"}, {"cams": "N", "boom": "1"},
                {"list": "1", "boom": "1"}, {"size": "512", "caption": "0"}, {"whole": "1", "pictures": "color"},
                {"mos": "off", "sets": "0", "pictures": "movie", "fps": "7.9"}]
    runs = []
    for name, (a, b) in STRETCHES.items():
        for v in VARIANTS:
            q = {"from": iso(a), "until": iso(b), "cams": "NW", "fps": "auto", "size": "1024", **v}
            runs.append({"name": name, "q": q})
        # a cut: the stretch's two commonest targets kept, its first three frames dropped, one filter pair taken out
        p = export.plan(export.options({k: [v] for k, v in runs[-len(VARIANTS)]["q"].items()}))
        pics = p["pictures"]
        if pics:
            tg = sorted({e["target"] for e in pics}, key=lambda x: -sum(e["target"] == x for e in pics))[:2]
            fl = sorted({e["filters"] for e in pics})
            runs.append({"name": name, "q": {**runs[-len(VARIANTS)]["q"], "targets": ",".join(x.lower() for x in tg),
                                              "drop": ",".join(e["id"] for e in pics[:3]), "filters": ",".join(fl[1:] or fl)}})

    # the server's answers
    want = []
    for r in runs:
        opt = export.options({k: [v] for k, v in r["q"].items()})
        want.append(norm(export.public_plan(export.plan(opt))))

    job = os.path.join(tmp, "job.json")
    json.dump({"parts": parts, "kinds": kinds, "runs": runs}, open(job, "w"))
    NODE = r"""
    const fs = require('fs'), vm = require('vm');
    const [file, jobFile] = process.argv.slice(1);
    const m = { exports: {} };
    vm.runInNewContext(fs.readFileSync(file, 'utf8'), { module: m, globalThis: {}, console }, { filename: file });
    const P = m.exports, job = JSON.parse(fs.readFileSync(jobFile, 'utf8'));
    let loads = 0;
    P.source.allMonths = async () => job.parts.map(p => ({ start: p.start, end: p.end, key: p.file, catalog: () => { loads++; return JSON.parse(fs.readFileSync(p.file, 'utf8')); } }));
    P.source.kind = async id => { if (!(id in job.kinds)) throw new Error('no kind table for ' + id); return job.kinds[id]; };
    (async () => {
      const out = [];
      for (const r of job.runs) out.push(await P.plan(r.q));
      process.stdout.write(JSON.stringify({ out, loads }));
    })();
    """
    got = json.loads(subprocess.run(["node", "-e", NODE, PLAN_JS, job], capture_output=True, text=True, check=True).stdout)
    bad = 0
    for r, w, g in zip(runs, want, got["out"]):
        g = norm(g)
        if g != w:
            bad += 1
            if "error" in g:
                print(f"FAIL {r['name']} {r['q']}: page error {g['error']}")
                continue
            diff = [k for k in set(w) | set(g) if k != "pictures" and w.get(k) != g.get(k)]
            wp, gp = w["pictures"], g["pictures"]
            first = next((i for i, (a, b) in enumerate(zip(wp, gp)) if a != b), min(len(wp), len(gp)))
            print(f"FAIL {r['name']} {r['q']}: fields {diff}, pictures {len(wp)} vs {len(gp)}, first differing #{first}:"
                  f"\n  server {wp[first] if first < len(wp) else None}\n  page   {gp[first] if first < len(gp) else None}")
    counts = [len(w["pictures"]) for w in want]
    print(f"{len(runs) - bad} of {len(runs)} plans the same ({sum(counts):,} pictures; {sum(1 for w in want for e in w['pictures'] if e['first'] in ('mosaic', 'rolling', 'movie')):,} "
          f"from passes, {sum(1 for w in want for e in w['pictures'] if 'set' in e):,} color sets)")
    for name in STRETCHES:
        print(f"  {name}: {iso(STRETCHES[name][0])} to {iso(STRETCHES[name][1])}, {next(len(w['pictures']) for r, w in zip(runs, want) if r['name'] == name)} pictures by default")

    # export.options on the editor's queries (the fields the plan and the levels read, and the framing)
    QS = [{"from": "2005-04-16T15:00", "until": "2005-04-16 23:00:00Z", "fps": "auto", "size": "700", "cams": "w",
           "levels": "N1492358399_1:0.333,N1492358581_1:-3,bad,W1:x", "even": "12.7", "drop": "b,a,a", "targets": "titan,Titan,saturn",
           "crop": "0.1_0.1_0.9_0.85", "crop2": "0_0_1_1", "nudge": "N1:0.1:-0.7,N2:0:0", "steadied": "N1:120:-5,N3:9:9", "ctr": "0",
           "mos": "whole", "laps": "3", "trail": "4", "fade": "30", "bg": "#FF8800", "off": "dark,align,nope", "steady": "8",
           "exposure": "4", "cs": "40", "pictures": "nope", "boom": "1", "look": "classic", "colors": "eye"},
          {"from": "2005-04-16", "until": "2005-04-16T00:00:01", "fps": "60", "size": "2000", "sets": "0", "complete": "1",
           "whole": "1", "crop2": "0.2_0.2_0.6_0.6", "levels": "N1:1e1,N2:0.125,N3:-0.005", "even": "0"}]
    skip = {"edit", "fedit"}
    for q in QS:
        w = norm({k: v for k, v in export.options({k: [v] for k, v in q.items()}).items() if k not in skip})
        js = r"""const fs=require('fs'),vm=require('vm');const m={exports:{}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{module:m,globalThis:{},console},{});
    const o=m.exports._.options(JSON.parse(process.argv[2]));delete o.edit;delete o.fedit;process.stdout.write(JSON.stringify(o));"""
        g = norm(json.loads(subprocess.run(["node", "-e", js, PLAN_JS, json.dumps(q)], capture_output=True, text=True, check=True).stdout))
        assert g == w, f"options differ:\n  server {w}\n  page   {g}"
    print(f"export.options: {len(QS)} editor queries the same")

    # the wavelength table is filter_calibration.csv's, and Python's set order is the page's
    nm = json.loads(subprocess.run(["node", "-e", "const fs=require('fs'),vm=require('vm');const m={exports:{}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{module:m,globalThis:{},console},{});"
                                    "const w=m.exports._.wavelength;process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(([c,f])=>w(c,f))))",
                                    PLAN_JS, json.dumps([[c, f] for c, f in reel._nm] + [["ISSNA", "NOPE"]])], capture_output=True, text=True, check=True).stdout)
    assert nm == [reel.wavelength(c, f) for c, f in reel._nm] + [0], "wavelength table differs from filter_calibration.csv"
    import random  # noqa: E402
    random.seed(3)
    cases = [[random.randrange(0, 60000) for _ in range(n)] for n in (1, 5, 40, 300, 3000, 20000)]
    cases_file = os.path.join(tmp, "sets.json")
    json.dump(cases, open(cases_file, "w"))
    order = json.loads(subprocess.run(["node", "-e", "const fs=require('fs'),vm=require('vm');const m={exports:{}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{module:m,globalThis:{},console},{});"
                                       "process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(process.argv[2],'utf8')).map(L=>m.exports._.pySetOrder(L))))",
                                       PLAN_JS, cases_file], capture_output=True, text=True, check=True).stdout)
    assert order == [list({int(v) for v in L}) for L in cases], "set order differs"
    print(f"wavelength table ({len(reel._nm)} filter pairs) and set order the same")
    assert bad == 0, f"{bad} plans differ"
    print("ok")
