#!/usr/bin/env python3
"""Frames that hold no picture, from their labels (unused-metadata M5, 11-16): taken with the shutter disabled
(SHUTTER_STATE_ID = DISABLED: a dark, the camera read out with no light let in) or with the calibration lamp on
(CALIBRATION_LAMP_STATE_FLAG = ON: the lamp lights the detector, not the scene). Drawn, a dark is its read noise
stretched to fill the range and a lamp frame a glow. They are left out of the frames the pipeline and the page take
from Image_index.csv (reel.load_index, export_tracks' catalog), the archive kept as it is. Written once to
not_pictures.csv beside this file:

  python web/frames/not_pictures.py --data <the archive zip, CASSINI_DATA>
"""
import argparse, csv, os, re, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = os.path.join(HERE, "not_pictures.csv")


def why(label):
    """Why a frame's label (bytes) says it holds no picture, or None."""
    shutter = re.search(rb"^\s*SHUTTER_STATE_ID\s*=\s*\"?(\w+)", label, re.M)
    lamp = re.search(rb"^\s*CALIBRATION_LAMP_STATE_FLAG\s*=\s*\"?(\w+)", label, re.M)
    if shutter and shutter.group(1).upper() == b"DISABLED":
        return "dark"
    if lamp and lamp.group(1).upper() == b"ON":
        return "lamp"
    return None


def ids():
    """{frame id: why} of the list (empty without it)."""
    if not os.path.exists(LIST):
        return {}
    with open(LIST, newline="") as fh:
        return {r["id"]: r["why"] for r in csv.DictReader(fh)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("CASSINI_DATA"))
    ap.add_argument("--index", default=os.path.join(HERE, "..", "..", "Image_index.csv"))
    args = ap.parse_args()
    with open(args.index, newline="") as fh:
        paths = [r["path"] for r in csv.DictReader(fh) if r.get("path")]
    out = []
    with zipfile.ZipFile(args.data) as z:
        by_rel = {}
        for n in z.namelist():
            if n.upper().endswith(".LBL"):
                parts = n.split("/")
                by_rel["/".join(parts[-2:])] = n
        for p in paths:
            lbl = by_rel.get(os.path.splitext(p)[0] + ".LBL")
            if lbl is None:
                continue
            w = why(z.read(lbl))
            if w:
                out.append((os.path.splitext(os.path.basename(p))[0], w))
    out.sort()
    with open(LIST, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["id", "why"])
        wr.writerows(out)
    print(f"{len(out)} frames hold no picture ({sum(w == 'dark' for _, w in out)} dark, {sum(w == 'lamp' for _, w in out)} lamp) of {len(paths)}")


if __name__ == "__main__":
    main()
