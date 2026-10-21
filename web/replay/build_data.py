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

Both layouts add the moments in web/replay/moments.csv to encounters.json: notable imaging sessions
(long Saturn sessions, famous mosaics, the last pictures) that are not flybys. Each row names its
observations; the time window, frame count and colour sets are measured from the catalog, so a row
the archive has no pictures for stops the build instead of pointing the viewer at nothing.

It also writes the same data cut into months, data/months/<YYYY-MM>.json (that month's catalog)
and data/months/<YYYY-MM>.bin (every body's track and the pointing for that month, see
write_months), listed in mission.json under "months". A viewer that knows them loads the month
on screen first and its neighbours after, instead of three whole years before showing anything.
"""

import argparse
import base64
import csv
import datetime
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
MOMENTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moments.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--year", type=int, default=2005)
    ap.add_argument("--years", help="whole-mission layout for a span of years, e.g. 1997-2017")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--attitude", help="folder with attitude/<year>.bin from export_attitude.py (same catalog export)")
    ap.add_argument("--huygens", help="Huygens replay folder (tracks/huygens, manifest_huygens.json, huygens_descent.json)")
    ap.add_argument("--moments", default=MOMENTS, help="curated imaging sessions for the Moments list (default: %(default)s)")
    ap.add_argument("--scores", help="observations_scored.csv from the highlight scoring, for each moment's photo score")
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
    enc = sorted(enc + moments(args, [args.year]), key=lambda e: e["et"])
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


def moments(args, years):
    """
    The rows of the moments file that fall in these years, as encounters.json entries:
      {"kind": "observation", "label", "body", "obs": [OBSERVATION_ID, ...], "et", "utc", "start", "end",
       "end_et", "frames", "rgb_sets", "why", "source", "photo_score" (with --scores)}
    et/utc is the first picture of the listed observations and end the last, both from the catalog.
    rgb_sets counts 30 minute spans with red, green and blue (or violet) pictures, as the highlight
    scoring does. A row in these years with no pictures in the catalog is an error.
    """
    if not args.moments or not os.path.exists(args.moments):
        return []
    rows = list(csv.DictReader(open(args.moments, newline="")))
    if not rows:
        return []
    scores = {}
    if args.scores:
        for r in csv.DictReader(open(args.scores, newline="")):
            scores[r["OBSERVATION_ID"]] = max(scores.get(r["OBSERVATION_ID"], 0), float(r["score"]))
    want = {}
    for r in rows:
        if int(r["date"][:4]) in years:
            for o in r["obs"].split():
                want[o] = []
    for y in years:
        path = os.path.join(args.data, "catalog", f"{y}.json")
        if not want or not os.path.exists(path):
            continue
        cat = json.load(open(path))
        for i, o in enumerate(cat["obs"]):
            if o in want:
                want[o].append((cat["et"][i], cat["f1"][i] + "," + cat["f2"][i]))
    j2000 = datetime.datetime(2000, 1, 1, 12)
    out = []
    for r in rows:
        if int(r["date"][:4]) not in years:
            continue
        obs = r["obs"].split()
        pics = sorted(p for o in obs for p in want[o])
        if not pics:
            raise SystemExit(f"{args.moments}: no pictures in the catalog for {r['label']!r} ({' '.join(obs)})")
        spans = {}
        for t, f in pics:
            s = spans.setdefault(int(t // 1800), set())
            s.update(c for c, k in (("R", "RED"), ("G", "GRN"), ("B", "BL1"), ("B", "VIO")) if k in f)
        # UTC labels from ET, near enough for display (the leap seconds since 2000, 5 at most, are left out)
        utc = lambda t: (j2000 + datetime.timedelta(seconds=t - 64.184)).strftime("%Y-%m-%dT%H:%M:%S")
        e = {"kind": "observation", "label": r["label"], "body": r["body"], "obs": obs,
             "et": round(pics[0][0], 2), "utc": utc(pics[0][0]), "start": utc(pics[0][0]), "end": utc(pics[-1][0]),
             "end_et": round(pics[-1][0], 2), "frames": len(pics), "rgb_sets": sum(len(s) == 3 for s in spans.values()),
             "why": r["why"], "source": r["source"]}
        if any(o in scores for o in obs):
            e["photo_score"] = round(max(scores.get(o, 0) for o in obs), 1)
        out.append(e)
    return out


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
    enc = sorted(enc + moments(args, years), key=lambda e: e["et"])
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
               "frames_per_day": {"start_et": day0, **per_day}, "months": write_months(out, years, bodies, attitude)}
    json.dump(mission, open(os.path.join(out, "mission.json"), "w"), separators=(",", ":"))
    if args.huygens:
        export_huygens(args.huygens, years, out)
    n = sum(c["images"] for c in catalogs.values())
    print(f"{years[0]}-{years[-1]}: {len(bodies)} bodies, {len(enc)} encounters, {n} images, pointing for {len(attitude)} years")


def month_et(year, month):
    """The start of a month as ET (seconds past J2000), near enough for cutting the data: leap seconds
    after 2000 are left out, so an edge can sit up to ~5 s early. That is harmless, since the viewer only
    uses the values written to mission.json and never works them out itself."""
    return (datetime.datetime(year, month, 1) - datetime.datetime(2000, 1, 1, 12)).total_seconds() + 64.184


def _blob(parts, data):
    """Appends data to parts at an 8-byte boundary (the viewer reads Float64Arrays straight from it)."""
    offset = sum(len(p) for p in parts)
    parts.append(data + b"\0" * (-len(data) % 8))
    return [offset, len(data)]


def write_months(out, years, bodies, attitude):
    """
    Cuts the year files just written into months. For each month with any data:
      data/months/<YYYY-MM>.json  the catalog rows taken that month, in the year file's order
      data/months/<YYYY-MM>.bin   "CMON", version, length of a JSON directory, 0 (4 x uint32), the
                                  directory {"tracks": {body: [offset, length]}, "attitude": [offset,
                                  length] or null} and the parts it points at (offsets from the start
                                  of the file, each part at an 8-byte boundary): each body's CTRK track
                                  for the month, and a CATT pointing file for the month's catalog rows
    A track part runs from the last sample at or before the month's start to the first sample after its
    end, so neighbouring months share a sample or two at the boundary (the viewer drops the repeats when
    it joins them). Background pointing samples get the same margin; the viewer drops repeated times.
    Returns the list for mission.json: {key, start, end, file, catalog, images}.
    """
    import numpy as np
    os.makedirs(os.path.join(out, "months"), exist_ok=True)
    months = []
    for y in years:
        tracks = {}
        for name, b in bodies.items():
            if str(y) in b["years"]:
                raw = open(os.path.join(out, b["years"][str(y)].split("data/", 1)[1]), "rb").read()
                n = struct.unpack_from("<I", raw, 8)[0]
                tracks[name] = (raw[:8], np.frombuffer(raw, "<f8", n, 16), np.frombuffer(raw, "<f8", 3 * n, 16 + 8 * n).reshape(n, 3),
                                np.frombuffer(raw, "<f4", 3 * n, 16 + 32 * n).reshape(n, 3))
        cat = json.load(open(os.path.join(out, "catalog", f"{y}.json")))
        et = np.array(cat["et"], float)
        att = None
        if str(y) in attitude:
            raw = open(os.path.join(out, "attitude", f"{y}.bin"), "rb").read()
            n_img, n_bg = struct.unpack_from("<II", raw, 8)
            att = (raw[:8], np.frombuffer(raw, "<f4", 4 * n_img, 16).reshape(n_img, 4), np.frombuffer(raw, "<f8", n_bg, 16 + 16 * n_img),
                   np.frombuffer(raw, "<f4", 4 * n_bg, 16 + 16 * n_img + 8 * n_bg).reshape(n_bg, 4))
        for m in range(1, 13):
            t0, t1 = month_et(y, m), month_et(y + (m == 12), m % 12 + 1)
            parts, directory = [], {"tracks": {}, "attitude": None}
            for name, (head, t, pos, vel) in tracks.items():
                i0 = max(int(np.searchsorted(t, t0, "right")) - 1, 0)
                i1 = min(int(np.searchsorted(t, t1, "right")) + 1, len(t))
                if i1 - i0 < 2 or t[i1 - 1] < t0 or t[i0] > t1:
                    continue
                k = i1 - i0
                data = head + struct.pack("<II", k, 0) + t[i0:i1].tobytes() + pos[i0:i1].tobytes() + vel[i0:i1].tobytes()
                directory["tracks"][name] = _blob(parts, data)
            if not directory["tracks"]:
                continue
            rows = np.flatnonzero((et >= t0) & (et < t1))
            key = f"{y}-{m:02d}"
            json.dump({k: [cat[k][i] for i in rows] for k in CATALOG_KEYS}, open(os.path.join(out, "months", key + ".json"), "w"),
                      separators=(",", ":"))
            if att is not None:
                head, img_q, bg_t, bg_q = att
                j0 = max(int(np.searchsorted(bg_t, t0, "right")) - 1, 0)
                j1 = min(int(np.searchsorted(bg_t, t1, "right")) + 1, len(bg_t))
                data = head + struct.pack("<II", len(rows), j1 - j0) + img_q[rows].tobytes() + bg_t[j0:j1].tobytes() + bg_q[j0:j1].tobytes()
                directory["attitude"] = _blob(parts, data)
            # offsets so far count from the first part; the parts follow the header and the directory, whose
            # length depends on the offsets, so it is padded to a fixed size first
            text = json.dumps(directory, separators=(",", ":")).encode()
            slack = 16 * (len(directory["tracks"]) + 2)   # each offset grows by a few digits
            size = len(text) + slack + (-(len(text) + slack) % 8)
            base = 16 + size
            directory["tracks"] = {k: [o + base, n] for k, (o, n) in directory["tracks"].items()}
            if directory["attitude"]:
                directory["attitude"] = [directory["attitude"][0] + base, directory["attitude"][1]]
            text = json.dumps(directory, separators=(",", ":")).encode()
            assert len(text) <= size
            text += b" " * (size - len(text))
            with open(os.path.join(out, "months", key + ".bin"), "wb") as fh:
                fh.write(b"CMON" + struct.pack("<III", 1, len(text), 0))
                fh.write(text)
                for p in parts:
                    fh.write(p)
            months.append({"key": key, "start": t0, "end": t1, "file": f"data/months/{key}.bin",
                           "catalog": f"data/months/{key}.json", "images": len(rows)})
    return months


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
