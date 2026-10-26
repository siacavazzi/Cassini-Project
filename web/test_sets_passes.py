"""The one rule for filter sets (web/frames/sets_passes.py) is the page's: the camera windows' own rule
(head-quiet.html findSets and pickChannels, run in node from the built page) finds the same sets, with the same
channels and kind, as sets_passes.filter_sets on the same frames; and the page's data path (dataSets, the ids
build_data.py --groups writes) gives the same sets back. Synthetic frames, plus any catalog files named.
Run: python web/test_sets_passes.py [catalog/<year>.json ...]   (needs node)"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.join(HERE, "replay")]
import json, random, re, subprocess, tempfile  # noqa: E402
import sets_passes  # noqa: E402

page = open(os.path.join(HERE, "cassini-os", "index.html")).read()
code = page[page.index("  const FILTER_NM = "):page.index("  function prep() {")]
NM = json.loads(re.search(r"const FILTER_NM = (\{.*?\});", code).group(1))
JS = """
const fs = require("fs");
const catalog = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const order = Array.from(catalog.et.keys()).sort((a, b) => catalog.et[a] - catalog.et[b]);
const kOf = id => { const m = catalog.kOf = catalog.kOf || new Map(catalog.id.map((v, i) => [v, i])); const k = m.get(id); return k === undefined ? -1 : k; };
%s
const { sets } = findSets();
console.log(JSON.stringify(sets.map(s => [s.kind, s.use.map(k => catalog.id[k]), s.frames.map(k => catalog.id[k]).sort()])));
""" % code


def page_sets(cat):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/t.js", "w").write(JS)
        json.dump(cat, open(f"{d}/c.json", "w"))
        return json.loads(subprocess.run(["node", f"{d}/t.js", f"{d}/c.json"], capture_output=True, text=True, check=True).stdout)


def rule_sets(cat):
    o = sorted(range(len(cat["id"])), key=lambda i: cat["et"][i])
    col = {k: [cat[k][i] for i in o] for k in ("id", "et", "cam", "f1", "f2", "target", "obs")}
    set_of, sets = sets_passes.filter_sets(col["cam"], col["target"], col["obs"], col["f1"], col["f2"], col["et"],
                                           lambda q: NM.get(f"{col['cam'][q]}:{col['f1'][q]}/{col['f2'][q]}", 0))
    return set_of, [[s["kind"], [col["id"][q] for q in s["use"]], sorted(col["id"][q] for q in s["rows"])] for s in sets], col


def with_ids(cat):
    """cat with the ids build_data.add_groups writes (sets by the rule; passes left out of this check)"""
    import build_data
    set_of, sets, col = rule_sets(cat)
    by = dict(zip(col["id"], zip(set_of, [-1] * len(set_of))))
    return build_data.add_groups(dict(cat), (by, {n: [k, use] for n, (k, use, _) in enumerate(sets)}, {}))


def same(a, b):
    key = lambda s: s[2]
    return sorted(a, key=key) == sorted(b, key=key)


def synthetic(seed, n=4000):
    r = random.Random(seed)
    filters = {"N": [("CL1", "CL2")] * 3 + [("CL1", f) for f in ("RED", "GRN", "BL1", "UV3", "IR1", "MT3", "CB3")] + [("BL2", "CL2"), ("CL1", "CB1"), ("P0", "GRN"), ("RED", "GRN"), ("IRP0", "MT2")],
               "W": [("CL1", "CL2")] * 3 + [("CL1", f) for f in ("RED", "GRN", "BL1", "VIO", "MT2", "CB2", "MT3", "IR3")] + [("IR4", "CL2"), ("CL1", "IR2")]}
    cat = {k: [] for k in ("id", "et", "cam", "f1", "f2", "target", "obs", "range_km", "km_per_px")}
    t, target, obs = 0.0, "SATURN", "OBS0"
    for i in range(n):
        t += r.choice([5, 20, 40, 60, 90, 150, 290, 310, 2000])
        if r.random() < 0.05:
            target = r.choice(["SATURN", "TITAN", "RHEA"])
        if r.random() < 0.08:
            obs = f"OBS{r.randrange(9)}"
        cam = r.choice("NW")
        f1, f2 = r.choice(filters[cam])
        cycle = ["RED", "GRN", "BL1", "CB1", "VIO"]
        if r.random() < 0.4:   # colour cycles, the common case
            f1, f2 = "CL1", cycle[i % len(cycle)]
        for k, v in (("id", f"{cam}{1400000000 + i}_1"), ("et", t), ("cam", cam), ("f1", f1), ("f2", f2), ("target", target),
                     ("obs", obs), ("range_km", 1e5), ("km_per_px", 1.0)):
            cat[k].append(v)
    order = list(range(n)); r.shuffle(order)   # the page's catalogs are not in time order (several parts joined)
    return {k: [v[i] for i in order] for k, v in cat.items()}


cats = [synthetic(s) for s in range(4)] + [json.load(open(p)) for p in sys.argv[1:]]
for cat in cats:
    _, rule, _ = rule_sets(cat)
    own = page_sets(cat)
    assert same(own, rule), "the page's own rule and sets_passes differ"
    data = page_sets(with_ids(cat))
    assert same(data, rule), "the page's sets from the ids differ from the rule's"
    kinds = {}
    for k, *_ in rule:
        kinds[k] = kinds.get(k, 0) + 1
    print(f"{len(cat['id'])} frames: {len(rule)} sets {kinds}, page rule = ids = sets_passes")

# a set running on into a month not loaded: the frames there are its set (channels picked from them, as the page's
# own rule would), and a single frame left is none
cat = synthetic(9, 600)
full = with_ids(cat)
o = sorted(range(len(cat["id"])), key=lambda i: cat["et"][i])
half = {k: [full[k][i] for i in o[:300]] for k in ("id", "et", "cam", "f1", "f2", "target", "obs", "range_km", "km_per_px", "set", "pass")}
half["groups"] = full["groups"]
own = page_sets({k: v for k, v in half.items() if k not in ("set", "pass", "groups")})
assert same(page_sets(half), own), "a cut set differs from the page's own rule on the same frames"

# obs_mosaic.colour_sets on frames the index does not have: the rule among themselves (B115's cycle)
b115 = [("", "", f, t) for f, t in [("VIO", 408), ("GRN", 456), ("CB2", 510), ("CB3", 564), ("RED", 621), ("VIO", 828), ("GRN", 876), ("CB2", 930)]]
try:
    import obs_mosaic as om
    assert [[j for _, j in s] for s in om._own_sets(b115)] == [[0, 1, 2, 3, 4], [5, 6, 7]]
except ImportError as e:   # no cv2 here: the rule itself
    print("obs_mosaic not importable here:", e)
    assert sets_passes.runs([("W", "", "", f, t) for _, _, f, t in b115]) == [[0, 1, 2, 3, 4], [5, 6, 7]]

# the frame server's sets (reel.load_index, which prebuild.page_sets and obs_mosaic.colour_sets read) are the rule's,
# on an index made of the same frames
import shutil  # noqa: E402
cat = synthetic(5, 1500)
_, rule, col = rule_sets(cat)
with tempfile.TemporaryDirectory() as d:
    shutil.copy(os.path.join(os.path.dirname(HERE), "filter_calibration.csv"), d)
    with open(f"{d}/Image_index.csv", "w") as fh:
        fh.write("path,INSTRUMENT_ID,TARGET_NAME,OBSERVATION_ID,FILTER_NAME,filter1,filter2,seconds_1970\n")
        for i in range(len(col["id"])):
            fh.write(f"x/{col['id'][i]}.png,{'ISSNA' if col['cam'][i] == 'N' else 'ISSWA'},{col['target'][i]},{col['obs'][i]},,"
                     f"{col['f1'][i]},{col['f2'][i]},{col['et'][i]}\n")
    import reel
    reel.REPO, reel._index, reel._nm = d, None, None
    idx, sets = reel.load_index()
    ids = idx["id"].tolist()
    assert same([[s["kind"], [ids[q] for q in s["use"]], sorted(ids[q] for q in s["rows"])] for s in sets], rule), "reel's sets differ"
    try:
        import obs_mosaic as om
    except ImportError as e:
        om = None
        print("obs_mosaic not importable here:", e)
    if om:
        # a pass's colour sets are the windows' sets, also where units left a repeat exposure out of the pass's tiles
        q0 = next(s for s in sets if len(s["rows"]) >= 3)
        rows = list(range(q0["rows"][0] - 3 if q0["rows"][0] >= 3 else 0, q0["rows"][-1] + 1))
        frames = [("", ids[q], reel.colour_filter(str(idx["filter1"][q]), str(idx["filter2"][q])) or "CL1/CL2", float(idx["seconds_1970"][q])) for q in rows]
        got = [[frames[j][1] for _, j in s] for s in om.colour_sets(frames)]
        want = [[ids[q] for q in s["rows"]] for s in sets if s["rows"][0] >= rows[0] and s["rows"][-1] <= rows[-1]]
        assert got == want, (got, want)
        lost = frames + [("", "nowhere", "RED", frames[-1][3] + 10)]   # a frame the index does not have: the rule among themselves
        assert om.colour_sets(lost) == om._own_sets(lost)
    if om:
        # passes: every frame of the index gets the pass units puts it in (here units splits an observation at an hour's
        # pause and leaves each pass's second frame out as a repeat exposure, as units does with repeats)
        def units(target, ob, cam):
            sel = idx[(idx["TARGET_NAME"] == target) & (idx["OBSERVATION_ID"] == ob) & (idx["INSTRUMENT_ID"] == ("ISSNA" if cam == "N" else "ISSWA"))]
            out = []
            for q, t in zip(sel.index, sel["seconds_1970"]):
                if not out or t - out[-1]["last"] > 1800:
                    out.append({"key": (target, ob, cam, len(out)), "frames": [], "last": t, "kind": "mosaic", "q": []})
                u = out[-1]; u["last"] = t; u["q"].append(q)
                if len(u["q"]) != 2:
                    u["frames"].append(("", ids[q], "", float(t)))
            return out
        om.units = units
        by_id, set_table, pass_table = sets_passes.groups()
        for ob in set(col["obs"]):
            for cam in "NW":
                for tg in set(col["target"]):
                    for u in units(tg, ob, cam):
                        got = {by_id[ids[q]][1] for q in u["q"]}
                        assert len(got) == 1 and pass_table[got.pop()][1:3] == [ob, u["key"][3]], u["key"]
        assert all(by_id[i][0] == s for i, s in zip(ids, idx["set"]))
        assert all(set_table[n][1] == [ids[q] for q in s["use"]] for n, s in enumerate(sets))
        print(f"{len(pass_table)} passes: every frame in its own, repeat exposures too")
print("reel's sets, prebuild's and the movies' are the rule's")

# a feature track (the camera follows a cloud: the filters of a pointing land apart) plays as a movie: a 10-filter
# visit every 900 s that creeps ~135 px over the visit (ISS_191SA_FEATRAK001), or a steady drift all the way through
# (ISS_222SA_FEATRAK001); a colour mosaic (filters of a pointing on one another), a raster that steps a pointing every
# frame through its filters, and a stare cycling filters stay what they were
if om:
    def judged(points, filters, times=None):
        times = times or [1000.0 + 30 * i for i in range(len(points))]
        fr = [("", f"N{1700000000 + i}_1", filters[i % len(filters)], t, 600, -x, -y, 1e6) for i, ((x, y), t) in enumerate(zip(points, times))]
        u = {"key": ("SATURN", "OBS", "N", 0), "frames": fr, "taken": [(f, x, y, z) for _, _, f, _, _, x, y, z in fr], "z": 1e6}
        om._judge(u)
        return u
    ten = ["CB3", "MT3", "CB2", "MT2", "CB1", "MT1", "UV3", "UV1", "UV2", "BL1"]
    visits = [(1500 * (i // 10) + 5 * (i % 10), -2000 * (i // 10) % 7000 + 15 * (i % 10)) for i in range(80)]
    vt = [900.0 * (i // 10) + 62 * (i % 10) for i in range(80)]
    keep = om.TRACK_VISITS; om.TRACK_VISITS = 10 ** 9
    assert judged(visits, ten, vt)["kind"] == "mosaic"   # what it was before the track rule
    om.TRACK_VISITS = keep
    t = judged(visits, ten, vt)
    assert t["track"] and t["kind"] == "movie", (t["kind"], t["track"])
    drift = [(70 * i, -85 * i) for i in range(45)]
    d = judged(drift, ten[:9], [41.0 * i + 900 * (i // 9) for i in range(45)])
    assert d["track"] and d["kind"] == "movie", (d["kind"], d["track"])
    grid = [(900 * (j % 3) + 3 * k, 900 * (j // 3)) for j in range(9) for k in range(3)]
    m = judged(grid, ["RED", "GRN", "BL1"])
    assert not m["track"] and m["kind"] == "mosaic", (m["kind"], m["track"])
    raster = [(900 * (j % 4), 900 * (j // 4)) for j in range(16)]   # one filter per pointing, filters cycling
    r = judged(raster, ["MT1", "CB1", "MT2", "CB2"])
    assert not r["track"] and r["kind"] == "mosaic", (r["kind"], r["track"])
    stare = [(3 * i, 2 * i) for i in range(30)]
    st = judged(stare, ["RED", "GRN", "BL1"])
    assert not st["track"] and st["kind"] == "movie", (st["kind"], st["track"])
    print("tracks (visits that creep, a steady drift): movie; colour mosaic, filter raster: mosaic; stare: movie")
print("ok")
