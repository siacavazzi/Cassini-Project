#!/usr/bin/env python3
"""
Copy exported replay data into web/replay/data for the viewer: one year, or the whole mission.

  python web/replay/build_data.py --data <export dir from export_tracks.py> --year 2005 \
      [--attitude <dir with <year>.bin>] [--huygens <huygens replay dir>]
  python web/replay/build_data.py --data <export dir> --years 1997-2017 \
      [--attitude <dir with <year>.bin>] [--huygens <huygens replay dir>]

One year: track files are also written base64-wrapped (.b64.txt), because the artifact host that
serves the prototype does not serve raw binary files. A normal static host can use the .bin files.

Whole mission (--years): writes data/mission.json, which the viewer looks for first, plus
data/tracks/<year>/<body>.bin, data/catalog/<year>.json and data/attitude/<year>.bin. The viewer
loads the year on screen and its neighbours as the clock moves. Raw .bin files only, so this
layout needs a normal static host (the frame server), not the artifact host.
"""

import argparse
import base64
import json
import os
import shutil
import struct

SATURN_SYSTEM = ["CASSINI", "SUN", "EARTH", "SATURN", "MIMAS", "ENCELADUS", "TETHYS", "DIONE", "RHEA", "TITAN",
                 "HYPERION", "IAPETUS", "PHOEBE", "JANUS", "EPIMETHEUS", "HELENE", "TELESTO", "CALYPSO", "ATLAS",
                 "PROMETHEUS", "PANDORA", "PAN", "METHONE", "PALLENE", "POLYDEUCES", "DAPHNIS"]
# the cruise: Venus twice, Earth and the Moon, Jupiter and its large moons
CRUISE = ["VENUS", "MOON", "JUPITER", "IO", "EUROPA", "GANYMEDE", "CALLISTO"]
CATALOG_KEYS = ["id", "et", "cam", "f1", "f2", "target", "obs", "range_km", "km_per_px"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--year", type=int, default=2005)
    ap.add_argument("--years", help="whole-mission layout for a span of years, e.g. 1997-2017")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--attitude", help="folder with attitude/<year>.bin from export_attitude.py (same catalog export)")
    ap.add_argument("--huygens", help="Huygens replay folder (tracks/huygens, manifest_huygens.json, huygens_descent.json)")
    args = ap.parse_args()
    if args.years:
        return build_mission(args)
    os.makedirs(os.path.join(args.out, "tracks"), exist_ok=True)
    man = json.load(open(os.path.join(args.data, "manifest.json")))

    bodies = {}
    for name in SATURN_SYSTEM:
        body = man["bodies"][name]
        chunk = next(c for c in body["chunks"] if c["year"] == args.year)
        slug = name.lower().replace(" ", "_")
        src = os.path.join(args.data, chunk["file"])
        shutil.copy(src, os.path.join(args.out, "tracks", f"{slug}.bin"))
        with open(os.path.join(args.out, "tracks", f"{slug}.b64.txt"), "w") as fh:
            fh.write(base64.b64encode(open(src, "rb").read()).decode())
        rot = body.get("iau_rotation", {})
        bodies[name] = {"naif": body["naif_id"], "file": f"data/tracks/{slug}.b64.txt", "radii": rot.get("RADII"),
                        "pole_ra": rot.get("POLE_RA"), "pole_dec": rot.get("POLE_DEC"), "pm": rot.get("PM")}
    json.dump(bodies, open(os.path.join(args.out, "bodies.json"), "w"))

    enc = [e for e in json.load(open(os.path.join(args.data, "encounters.json"))) if e["utc"].startswith(str(args.year))]
    json.dump(enc, open(os.path.join(args.out, "encounters.json"), "w"))

    slim = slim_catalog(args.data, args.year)
    json.dump(slim, open(os.path.join(args.out, "catalog.json"), "w"), separators=(",", ":"))
    if args.attitude:
        raw = attitude_for(args.attitude, args.year, len(slim["et"]))
        shutil.copy(os.path.join(args.attitude, f"{args.year}.bin"), os.path.join(args.out, "attitude.bin"))
        with open(os.path.join(args.out, "attitude.b64.txt"), "w") as fh:
            fh.write(base64.b64encode(raw).decode())
    if args.huygens:
        export_huygens(args.huygens, [args.year], args.out)
    print(f"{len(bodies)} bodies, {len(enc)} encounters, {len(slim['et'])} images")


def slim_catalog(data, year):
    path = os.path.join(data, "catalog", f"{year}.json")
    if not os.path.exists(path):   # no camera frames before 1999
        return {k: [] for k in CATALOG_KEYS}
    cat = json.load(open(path))
    slim = {k: cat[k] for k in CATALOG_KEYS}
    slim["et"] = [round(t, 1) for t in slim["et"]]
    return slim


def attitude_for(folder, year, n_catalog):
    """The year's pointing file, checked against the catalog it must come from."""
    src = os.path.join(folder, f"{year}.bin")
    raw = open(src, "rb").read()
    n_img = int.from_bytes(raw[8:12], "little")
    if raw[:4] != b"CATT" or n_img != n_catalog:
        raise SystemExit(f"{src}: {n_img} images, catalog has {n_catalog}; re-export one of them")
    return raw


def build_mission(args):
    y0, _, y1 = args.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))
    man = json.load(open(os.path.join(args.data, "manifest.json")))
    out = args.out
    bodies, start, end = {}, None, None
    for name in SATURN_SYSTEM + CRUISE:
        body = man["bodies"][name]
        slug = name.lower().replace(" ", "_")
        files = {}
        for c in body["chunks"]:
            if c["year"] not in years:
                continue
            os.makedirs(os.path.join(out, "tracks", str(c["year"])), exist_ok=True)
            shutil.copy(os.path.join(args.data, c["file"]), os.path.join(out, "tracks", str(c["year"]), f"{slug}.bin"))
            files[str(c["year"])] = f"data/tracks/{c['year']}/{slug}.bin"
            if name == "CASSINI":
                lo, hi = c["coverage_et"][0][0], c["coverage_et"][-1][1]
                start = lo if start is None else min(start, lo)
                end = hi if end is None else max(end, hi)
        if not files:
            continue
        rot = body.get("iau_rotation", {})
        bodies[name] = {"naif": body["naif_id"], "years": files, "radii": rot.get("RADII"),
                        "pole_ra": rot.get("POLE_RA"), "pole_dec": rot.get("POLE_DEC"), "pm": rot.get("PM")}

    enc = [e for e in json.load(open(os.path.join(args.data, "encounters.json"))) if int(e["utc"][:4]) in years]
    json.dump(enc, open(os.path.join(out, "encounters.json"), "w"))

    # frames per day over the whole span, so the timeline can show years that are not loaded
    day0 = start - start % 86400
    ndays = int((end - day0) // 86400) + 1
    per_day = {"N": [0] * ndays, "W": [0] * ndays}
    catalogs, attitude = {}, {}
    os.makedirs(os.path.join(out, "catalog"), exist_ok=True)
    for y in years:
        slim = slim_catalog(args.data, y)
        json.dump(slim, open(os.path.join(out, "catalog", f"{y}.json"), "w"), separators=(",", ":"))
        catalogs[str(y)] = {"file": f"data/catalog/{y}.json", "images": len(slim["et"])}
        for t, cam in zip(slim["et"], slim["cam"]):
            d = int((t - day0) // 86400)
            if 0 <= d < ndays:
                per_day["N" if cam == "N" else "W"][d] += 1
        if args.attitude and slim["et"] and os.path.exists(os.path.join(args.attitude, f"{y}.bin")):
            attitude_for(args.attitude, y, len(slim["et"]))
            os.makedirs(os.path.join(out, "attitude"), exist_ok=True)
            shutil.copy(os.path.join(args.attitude, f"{y}.bin"), os.path.join(out, "attitude", f"{y}.bin"))
            attitude[str(y)] = f"data/attitude/{y}.bin"
    mission = {"years": years, "coverage": [start, end], "bodies": bodies, "catalog": catalogs, "attitude": attitude,
               "frames_per_day": {"start_et": day0, **per_day}}
    json.dump(mission, open(os.path.join(out, "mission.json"), "w"), separators=(",", ":"))
    if args.huygens:
        export_huygens(args.huygens, years, out)
    n = sum(c["images"] for c in catalogs.values())
    print(f"{years[0]}-{years[-1]}: {len(bodies)} bodies, {len(enc)} encounters, {n} images, pointing for {len(attitude)} years")


def merge_tracks(raws):
    """Join consecutive yearly CTRK chunks into one track (neighbouring chunks share their boundary sample)."""
    ts, ps, vs = [], [], []
    for raw in raws:
        n = struct.unpack_from("<I", raw, 8)[0]
        t = struct.unpack_from(f"<{n}d", raw, 16)
        p = struct.unpack_from(f"<{3 * n}d", raw, 16 + 8 * n)
        v = struct.unpack_from(f"<{3 * n}f", raw, 16 + 32 * n)
        k = 1 if ts and t[0] <= ts[-1] else 0
        ts += t[k:]; ps += p[3 * k:]; vs += v[3 * k:]
    n = len(ts)
    return raws[0][:8] + struct.pack("<II", n, 0) + struct.pack(f"<{n}d", *ts) + struct.pack(f"<{3 * n}d", *ps) + struct.pack(f"<{3 * n}f", *vs)


def export_huygens(src, years, out):
    """The probe is kept out of bodies.json: its track only covers separation to the day after landing."""
    man = json.load(open(os.path.join(src, "manifest_huygens.json")))["HUYGENS"]
    chunks = [c for c in man["chunks"] if c["year"] in years]
    path = os.path.join(out, "huygens.json")
    if not chunks:
        if os.path.exists(path):
            os.remove(path)
        return
    raw = merge_tracks([open(os.path.join(src, c["file"]), "rb").read() for c in sorted(chunks, key=lambda c: c["year"])])
    os.makedirs(os.path.join(out, "tracks"), exist_ok=True)
    with open(os.path.join(out, "tracks", "huygens.b64.txt"), "w") as fh:
        fh.write(base64.b64encode(raw).decode())
    open(os.path.join(out, "tracks", "huygens.bin"), "wb").write(raw)
    d = json.load(open(os.path.join(src, "huygens_descent.json")))
    step = 10  # every 20 s is plenty for the altitude readout
    info = {"file": "data/tracks/huygens.b64.txt", "events": man["events_et"], "landing_site": man["landing_site"],
            "descent": {"et": [round(t, 1) for t in d["et"][::step]], "alt_km": [round(a, 3) for a in d["alt_km"][::step]]}}
    info["descent"]["et"].append(round(d["et"][-1], 1)); info["descent"]["alt_km"].append(d["alt_km"][-1])
    # landing-site map (Karkoschka DISR mosaics, nested levels) and per-frame ground footprints
    mos = os.path.join(src, "mosaics", "mosaics.json")
    proj = os.path.join(src, "catalog", "huygens_projection.json")
    if os.path.exists(mos) and os.path.exists(proj):
        m = json.load(open(mos))
        os.makedirs(os.path.join(out, "huygens_map"), exist_ok=True)
        levels = []
        for lv in m["levels"]:
            name = os.path.basename(lv["file"])
            colour = os.path.join(src, "mosaics", "color", name)
            shutil.copy(colour if os.path.exists(colour) else os.path.join(src, lv["file"]), os.path.join(out, "huygens_map", name))
            levels.append({"m_per_px": lv["m_per_px"], "file": f"data/huygens_map/{name}"})
        p = json.load(open(proj))
        cat = json.load(open(os.path.join(src, "catalog", "huygens.json")))
        et_of = dict(zip(cat["id"], cat["et"]))
        fp = sorted((et_of[i], [[round(e), round(n)] for e, n in pts]) for i, pts in zip(p["id"], p["footprint_en_m"]) if i in et_of)
        info["map"] = {"width": m["width"], "height": m["height"], "landing_px": m["landing_px"], "levels": levels,
                       "footprints": {"et": [round(t, 2) for t, _ in fp], "en_m": [pts for _, pts in fp]}}
    json.dump(info, open(path, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
