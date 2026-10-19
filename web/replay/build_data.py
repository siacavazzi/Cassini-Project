#!/usr/bin/env python3
"""
Copy one year of exported replay data into web/replay/data for the prototype viewer.

  python web/replay/build_data.py --data <export dir from export_tracks.py> --year 2005 \
      [--attitude <dir with <year>.bin>] [--huygens <huygens replay dir>]

Track files are also written base64-wrapped (.b64.txt), because the artifact host that serves
the prototype does not serve raw binary files. A normal static host can use the .bin files.
"""

import argparse
import base64
import json
import os
import shutil

SATURN_SYSTEM = ["CASSINI", "SUN", "EARTH", "SATURN", "MIMAS", "ENCELADUS", "TETHYS", "DIONE", "RHEA", "TITAN",
                 "HYPERION", "IAPETUS", "PHOEBE", "JANUS", "EPIMETHEUS", "HELENE", "TELESTO", "CALYPSO", "ATLAS",
                 "PROMETHEUS", "PANDORA", "PAN", "METHONE", "PALLENE", "POLYDEUCES", "DAPHNIS"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--year", type=int, default=2005)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--attitude", help="folder with attitude/<year>.bin from export_attitude.py (same catalog export)")
    ap.add_argument("--huygens", help="Huygens replay folder (tracks/huygens, manifest_huygens.json, huygens_descent.json)")
    args = ap.parse_args()
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

    cat = json.load(open(os.path.join(args.data, "catalog", f"{args.year}.json")))
    slim = {k: cat[k] for k in ["id", "et", "cam", "f1", "f2", "target", "obs", "range_km", "km_per_px"]}
    slim["et"] = [round(t, 1) for t in slim["et"]]
    json.dump(slim, open(os.path.join(args.out, "catalog.json"), "w"), separators=(",", ":"))
    if args.attitude:
        src = os.path.join(args.attitude, f"{args.year}.bin")
        raw = open(src, "rb").read()
        n_img = int.from_bytes(raw[8:12], "little")
        if raw[:4] != b"CATT" or n_img != len(slim["et"]):
            raise SystemExit(f"{src}: {n_img} images, catalog has {len(slim['et'])}; re-export one of them")
        shutil.copy(src, os.path.join(args.out, "attitude.bin"))
        with open(os.path.join(args.out, "attitude.b64.txt"), "w") as fh:
            fh.write(base64.b64encode(raw).decode())
    if args.huygens:
        export_huygens(args.huygens, args.year, args.out)
    print(f"{len(bodies)} bodies, {len(enc)} encounters, {len(slim['et'])} images")


def export_huygens(src, year, out):
    """The probe is kept out of bodies.json: its track only covers separation to the day after landing."""
    man = json.load(open(os.path.join(src, "manifest_huygens.json")))["HUYGENS"]
    chunk = next((c for c in man["chunks"] if c["year"] == year), None)
    path = os.path.join(out, "huygens.json")
    if chunk is None:
        if os.path.exists(path):
            os.remove(path)
        return
    raw = open(os.path.join(src, chunk["file"]), "rb").read()
    with open(os.path.join(out, "tracks", "huygens.b64.txt"), "w") as fh:
        fh.write(base64.b64encode(raw).decode())
    shutil.copy(os.path.join(src, chunk["file"]), os.path.join(out, "tracks", "huygens.bin"))
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
