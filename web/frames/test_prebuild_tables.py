#!/usr/bin/env python3
"""
Tests of the tables phase (tables.py, prebuild.py tables / fullview).

  python web/frames/test_prebuild_tables.py
      no data needed: the schema checks, pass ids and shards, pass_tables on a made-up pass (obs_mosaic's functions
      stood in for), finish()'s shards and coverage

  python web/frames/test_prebuild_tables.py --out <cache>/public-tables --server http://127.0.0.1:PORT [--passes 40]
      against a tables phase's output and a frame server on the same cache, at the same commit: for sample passes
      (every kind there is, spread over the slice), each part equals the server's route answer once keys are
      sorted (info with the frame's n added back), asked for several frames of the pass; every frame of the pass's
      filmstrip is in its alias shard with the n the server gives it; every part and shard validates; coverage.json
      lists no pass without its tables
"""
import argparse
import json
import os
import random
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("FAIL", what, flush=True)


# ---------- without data ----------

def offline():
    import types
    # tables imports obs_mosaic for its functions only: a stand-in module, so this runs anywhere
    fake = types.ModuleType("obs_mosaic")
    sys.modules.setdefault("obs_mosaic", fake)
    import tables
    real = sys.modules["obs_mosaic"] is not fake

    ok(tables.pass_id({"key": ["SATURN", "ISS_123/AB", "N", 0]}) == "SATURN_ISS_123-AB_N_0", "pass id")
    ok(tables.shard_of("N1500060789_2") == "N15000", "shard rule")
    ok(tables.part_of("table/pass/X/steady/c1k0.json") == "steady", "part of steady")
    ok(tables.part_of("table/pass/X/maps/CL1_2_0_0_10_10.json") == "maps", "part of maps")
    ok(tables.part_of("table/alias/N15000.json") == "alias_shard", "part of alias")

    info = {"observation": "O", "target": "T", "camera": "N", "pass": 0, "movie": True, "mosaic": False,
            "cadence": 30.0, "frames": [["N1500060789_2", 1.5e9, "CL1-CL2"]]}
    ok(tables.check(info, tables.schema()["$defs"]["info"]) is None, "info validates")
    ok(tables.check(dict(info, n=0), tables.schema()["$defs"]["info"]) is not None, "info with n refused")
    ok(tables.check({"working": True, "local": False}, tables.schema()["$defs"]["steady"]) is not None, "working refused")
    ok(tables.check({"local": False}, tables.schema()["$defs"]["steady"]) is None, "local false is a table")
    ok(tables.check({"shard": "N15000", "frames": {"N1500060789_2": {"p": "a b", "n": 0}}},
                    tables.schema()["$defs"]["alias_shard"]) is not None, "bad pass id refused")
    ok(tables.check({"kind": "x", "mosaic": True, "movie": False}, tables.schema()["$defs"]["kind"]) is not None,
       "bad kind refused")
    if real:
        print("obs_mosaic is loaded: skipping the stand-in pass")
        return

    # a made-up mosaic movie pass of three frames and a repeat exposure, every function the routes call stood in for
    ids = ["W1500000000_1", "W1500000010_1", "W1500000015_1", "W1500000020_1"]
    u = {"key": ("SATURN", "ISS_200RI_TEST001_PRIME", "W", 1), "frames": [[0, ids[0], "CL1", 1.5e9], [1, ids[1], "CL1", 1.5e9 + 10],
         [3, ids[3], "CL1", 1.5e9 + 20]], "last": 1.5e9 + 20, "mosaic": True, "movie": False, "kind": "mosaic_movie"}
    n_of = {ids[0]: 0, ids[1]: 1, ids[2]: 1, ids[3]: 2}
    tables._by_obs = {u["key"][:3]: [(i, 1.5e9 + k) for i, k in zip(ids, (0, 10, 15, 20))]}
    fake.unit_of = lambda f: (u, n_of[f]) if f in n_of else None
    fake.pass_info = lambda f, c: {"observation": u["key"][1], "target": "SATURN", "camera": "W", "pass": 1, "n": n_of[f],
                                   "movie": False, "mosaic": True, "cadence": 10.0, "frames": [[fr[1], fr[3], fr[2]] for fr in u["frames"]]}
    fake.kind_of = lambda f, c: {"mosaic": True, "movie": False, "kind": "mosaic_movie", "repeats": 1, "lap_ends": [ids[3]]}
    from PIL import Image
    import io

    def webp(w, h):
        b = io.BytesIO()
        Image.new("RGB", (w, h)).save(b, "WEBP")
        return b.getvalue()
    fake.rolling_webp = lambda f, size, c, laps=1: (webp(size, size * 3 // 4), {})
    fake.fade_table = lambda f, c, laps, W, H: {"local": True, "laps": laps, "W": W, "H": H, "frames": []}
    fake.layout = lambda u_, n, c: (None, None, None, None, None, f"CL1{n + 1}_0_0_100_80")
    fake.tile_map = lambda f, c: {"observation": "O", "pointings": [{"n": 1}], "for": n_of[f]}
    fake.folder = lambda u_, c: "/nowhere"
    fake.MAPS_DIR = "maps-1"
    parts, alias, notes, missing = tables.pass_tables(u, "/nowhere")
    names = sorted(k.split("/", 3)[3] for k in parts)
    ok(names == ["fade/l1_1024x768.json", "fade/l1_512x384.json", "info.json", "kind.json", "maps/CL11_0_0_100_80.json",
                 "maps/CL12_0_0_100_80.json", "maps/CL13_0_0_100_80.json"], f"parts of a mosaic movie: {names}")
    ok(set(alias) == set(ids), "every frame, the repeat exposure too, has an alias")
    ok(alias[ids[2]] == {"p": tables.pass_id(u), "n": 1, "m": "CL12_0_0_100_80"}, f"repeat exposure's alias {alias[ids[2]]}")
    ok("n" not in json.loads(parts[f"table/pass/{tables.pass_id(u)}/info.json"]), "info has no n")
    ok(not missing, f"nothing missing: {missing}")

    # a movie pass: steady tables, the first answer working until the chains are made
    made = []
    fake.plan = lambda u_, c: {"display_scale": {}}
    fake.steady_chain = lambda u_, c, p: made.append("steady")
    fake.exposure_chain = lambda u_, c, p, colour, centre, steady: made.append((colour, centre))
    fake.steady_table = lambda f, c, centre, colour: {"local": True, "exposure": {"logs": {}}} if (colour, centre) in made \
        else {"working": True}
    m = dict(u, kind="movie", mosaic=False, movie=True)
    fake.unit_of = lambda f: (m, n_of[f]) if f in n_of else None
    parts, alias, notes, missing = tables.pass_tables(m, "/nowhere", movie=True, uncentred=True)
    names = sorted(k.split("/", 3)[3] for k in parts)
    ok(names == ["info.json", "kind.json", "steady/c0k0.json", "steady/c0k1.json", "steady/c1k0.json", "steady/c1k1.json"],
       f"parts of an uncentred movie: {names}")
    ok(len(notes) == 4 and not missing, f"chains made, nothing missing: {notes} {missing}")
    fake.steady_table = lambda f, c, centre, colour: {"working": True}
    parts, alias, notes, missing = tables.pass_tables(m, "/nowhere", movie=True)
    ok(missing == ["steady/c1k0", "steady/c1k1"] and not any("steady" in k for k in parts),
       f"a steady table still working is not written: {missing}")

    # make_pass and finish: shards, coverage, found-not-made
    with tempfile.TemporaryDirectory() as out:
        fake.steady_table = lambda f, c, centre, colour: {"local": False}
        n = tables.make_pass(m, "/nowhere", out, movie=True, versions={"v": 1})
        ok(n == 4, "make_pass counts the pass's frames")
        calls = []
        fake.pass_info = lambda f, c: calls.append(f)
        tables.make_pass(m, "/nowhere", out, movie=True, versions={"v": 1})
        ok(not calls, "a pass written under the same versions is found, not made")
        rep = tables.finish(out, [tables.pass_id(m), "SATURN_ISS_NOT_THERE_N_0"])
        ok(rep["without_tables"] == ["SATURN_ISS_NOT_THERE_N_0"], f"coverage lists a pass not written: {rep['without_tables']}")
        with open(os.path.join(out, "table", "alias", "W15000.json")) as fh:
            shard = json.load(fh)
        ok(sorted(shard["frames"]) == ids and tables.validate_part("alias", shard) is None, "shard holds every frame")
        for root, _, files in os.walk(os.path.join(out, "table")):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), out)
                with open(os.path.join(root, f)) as fh:
                    ok(tables.validate_part(rel, json.load(fh)) is None, f"{rel} validates")
                ok(not f.endswith(".part"), f"no part file left: {rel}")


# ---------- against a server and a phase's output ----------

def get(server, path):
    try:
        with urllib.request.urlopen(server.rstrip("/") + path, timeout=600) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def norm(doc):
    return json.loads(json.dumps(doc, sort_keys=True))


def online(out, server, how_many, seed):
    import tables
    with open(os.path.join(out, "coverage.json")) as fh:
        cov = json.load(fh)
    ok(not cov["without_tables"], f"coverage: passes without tables {cov['without_tables'][:5]}")
    ok(not cov["errors"], f"coverage: errors {list(cov['errors'])[:5]}")
    work = os.path.join(out, "work")
    passes = []
    for name in sorted(os.listdir(work)):
        with open(os.path.join(work, name)) as fh:
            passes.append(json.load(fh))
    # every kind there is, then spread over the rest
    rnd = random.Random(seed)
    by_kind = {}
    for w in passes:
        by_kind.setdefault((w["kind"], any(p.startswith("steady/c0") for p in w["parts"])), []).append(w)
    pick = [rnd.choice(v) for v in by_kind.values()]
    rest = [w for w in passes if w not in pick]
    pick += rnd.sample(rest, max(0, min(len(rest), how_many - len(pick))))
    print(f"{len(pick)} of {len(passes)} passes: " + ", ".join(sorted({str(k) for k in by_kind})), flush=True)
    shards = {}
    checked = 0
    for w in pick:
        pid, base = w["pass"], os.path.join(out, "table", "pass", w["pass"])
        frames = sorted(w["alias"], key=lambda f: (w["alias"][f]["n"], f))
        drawn = [f for f in frames if w["alias"][f]["n"] >= 0]
        sample = sorted({frames[0], frames[len(frames) // 2], frames[-1]} | ({drawn[len(drawn) // 3]} if drawn else set()))
        parts = {}
        for rel in w["parts"]:
            with open(os.path.join(base, rel)) as fh:
                parts[rel] = json.load(fh)
            ok(tables.validate_part(f"table/pass/{pid}/{rel}", parts[rel]) is None, f"{pid}/{rel} validates")
        for f in sample:
            n = w["alias"][f]["n"]
            code, got = get(server, f"/frames/movie/{f}.json")
            ok(code == 200 and norm(got) == norm(dict(parts["info.json"], n=n)), f"{pid} info at {f}")
            code, got = get(server, f"/frames/mosaic/{f}.webp?warm=1")
            ok(code == 200 and norm(got) == norm(parts["kind.json"]), f"{pid} kind at {f}")
            if n < 0:
                continue
            for rel, doc in parts.items():
                if rel.startswith("steady/"):
                    c, k = rel[8], rel[10]
                    code, got = get(server, f"/frames/movie/{f}.steady.json?center={c}&color={k}")
                    ok(code == 200 and norm(got) == norm(doc), f"{pid} {rel} at {f}")
                elif rel.startswith("fade/"):
                    W, H = rel[8:-5].split("x")
                    code, got = get(server, f"/frames/movie/{f}.fade.json?laps=1&w={W}&h={H}")
                    ok(code == 200 and norm(got) == norm(doc), f"{pid} {rel} at {f}")
            m = w["alias"][f].get("m")
            code, got = get(server, f"/frames/mosaic/{f}.json")
            if m:
                ok(code == 200 and norm(got) == norm(parts[f"maps/{m}.json"]), f"{pid} maps/{m} at {f}")
            else:
                ok(code == 404, f"{pid} no map at {f} and the server has none ({code})")
            checked += 1
        # every frame of the filmstrip in its shard, with the server's n
        for fid, *_ in parts.get("info.json", {}).get("frames", []):
            s = tables.shard_of(fid)
            if s not in shards:
                with open(os.path.join(out, "table", "alias", s + ".json")) as fh:
                    shards[s] = json.load(fh)
                ok(tables.validate_part("alias", shards[s]) is None, f"shard {s} validates")
            ok(shards[s]["frames"].get(fid, {}).get("p") == pid, f"{pid}: {fid} in shard {s}")
    print(f"{checked} frames checked against {server}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="a tables phase's output folder (<cache>/public-tables)")
    ap.add_argument("--server", help="a frame server on the same cache, at the same commit")
    ap.add_argument("--passes", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    if args.out and args.server:
        online(args.out, args.server, args.passes, args.seed)
    else:
        offline()
    print(f"{len(FAILS)} failed" if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
