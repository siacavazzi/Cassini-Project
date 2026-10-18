#!/usr/bin/env python3
"""
Copy one year of exported replay data into web/replay/data for the prototype viewer.

  python web/replay/build_data.py --data <export dir from export_tracks.py> --year 2005

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
    json.dump(info, open(path, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
