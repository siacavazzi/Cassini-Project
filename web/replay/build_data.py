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
    print(f"{len(bodies)} bodies, {len(enc)} encounters, {len(slim['et'])} images")


if __name__ == "__main__":
    main()
