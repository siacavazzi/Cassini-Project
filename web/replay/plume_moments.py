#!/usr/bin/env python3
"""
Writes web/replay/plume_moments.csv: the passes where Enceladus' south polar plumes show clearly, as Moments of type
"plume" (Sam 2026-11-16). One rule for the whole mission, no picking by hand:

  1. plume_scan.py: every picture with Enceladus in it, its SPICE geometry (phase angle, where the column over the south
     pole stands against the limb, Enceladus' size in the frame, sunlight, other bodies near it)
  2. plume_measure.py: in each picture whose geometry can show the plumes, the sky over the south pole against the sky
     the same distance off the other sides (the "jet" score), and whether the picture can be judged (not saturated,
     the disk where SPICE puts it, the camera sent those lines)
  3. here: a pass (observation) is a plume moment when its judged pictures' 75th percentile jet score is at least CUT.
     Passes less than GAP apart are one moment; passes moments.csv already lists are left to it.

  python web/replay/plume_moments.py plume_measured.jsonl [--out web/replay/plume_moments.csv]

build_data.py adds these rows to the Moments list beside moments.csv's.
"""
import argparse
import csv
import datetime
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["date", "label", "body", "obs", "why", "source", "type"]

MIN_PHASE = 140.0     # degrees: the plumes scatter sunlight forward, bright only with the Sun nearly behind Enceladus
MIN_R_PX = 15.0       # Enceladus' radius in full resolution pixels: smaller and the plume is a smudge (2006 mutual
                      # event frames at 11 px)
CUT = 8.0             # a pass's 75th percentile jet score (sky over the pole over the sky's scatter) at least this
GAP = 6 * 3600        # seconds: passes closer than this are one moment


def judged(r):
    """A picture whose geometry can show the plumes and whose sky can be measured: lit, the column over the pole past
    the limb and in the frame, no other body or Saturn's disk behind it, not saturated, the disk where SPICE puts it."""
    return ("jet" in r and r["phase"] >= MIN_PHASE and r["r_px"] >= MIN_R_PX and r["above_px"] > 0 and r["in_frame"]
            and r["lit"] is not False and not r["near"] and not r["on_saturn"] and r["sat"] <= 0.01
            and r["disk_sat"] <= 0.3 and r["on_disk"] >= 0.8)


def passes(rows):
    """{observation: (score, judged pictures, plume pictures)} for every observation with judged pictures."""
    by = {}
    for r in rows:
        if judged(r):
            by.setdefault(r["obs"], []).append(r)
    out = {}
    for o, rs in by.items():
        score = float(np.percentile([r["jet"] for r in rs], 75))
        out[o] = (score, rs, [r for r in rs if r["jet"] >= CUT])
    return out


def first_pictures(obs):
    """The first picture time (UTC) of each observation, all its pictures (Image_index.csv), as build_data dates a
    moment."""
    import pandas as pd
    idx = pd.read_csv(os.path.join(HERE, "..", "..", "Image_index.csv"), usecols=["OBSERVATION_ID", "seconds_1970"],
                      low_memory=False)
    idx = idx[idx["OBSERVATION_ID"].isin(obs)]
    first = idx.groupby("OBSERVATION_ID")["seconds_1970"].min()
    return {o: datetime.datetime.fromtimestamp(float(t), datetime.timezone.utc) for o, t in first.items()}


def where_pole(lat):
    """Where Cassini looks from: lat is its latitude over Enceladus, south negative."""
    if abs(lat) < 10:
        return "the south pole on the limb"
    return f"Cassini {abs(lat):.0f}° {'south' if lat < 0 else 'north'} of Enceladus' equator"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("measured")
    ap.add_argument("--moments", default=os.path.join(HERE, "moments.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "plume_moments.csv"))
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.measured)]
    listed = {o for r in csv.DictReader(open(a.moments, newline="")) for o in r["obs"].split()}
    got = {o: p for o, p in passes(rows).items() if p[0] >= CUT and p[2] and o not in listed}
    first = first_pictures(set(got))
    # passes in time order, those closer than GAP put together
    order = sorted(got, key=lambda o: first[o])
    groups = []
    for o in order:
        end = max(r["et"] for r in got[o][1]) - 64.184 + 946728000   # ET to Unix seconds, near enough
        if groups and first[o].timestamp() - groups[-1]["end"] < GAP:
            groups[-1]["obs"].append(o)
            groups[-1]["end"] = max(groups[-1]["end"], end)
        else:
            groups.append({"obs": [o], "end": end})
    out, labels = [], set()
    for g in groups:
        obs = g["obs"]
        start = min(first[o] for o in obs)
        plume = [r for o in obs for r in got[o][2]]
        allj = [r for o in obs for r in got[o][1]]
        best = max(plume, key=lambda r: r["jet"])
        label = f"Plumes of Enceladus, {start.strftime('%b')} {start.day}, {start.year}"
        if label.lower() in labels:
            label += f", {start.strftime('%H:%M')}"
        labels.add(label.lower())
        cam = {"N": "narrow-angle", "W": "wide-angle"}[best["cam"]]
        why = (f"Backlit at {best['phase']:.0f}° phase with {where_pole(best['sublat'])}: the jets stand out over the "
               f"dark sky in {len(plume)} of {len(allj)} {cam} pictures, Enceladus {2 * best['r_px']:.0f} px across "
               f"(plume score {max(got[o][0] for o in obs):.0f})")
        out.append({"date": start.strftime("%Y-%m-%d"), "label": label, "body": "ENCELADUS", "obs": " ".join(obs),
                    "why": why, "source": "", "type": "plume"})
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"{a.out}: {len(out)} plume moments from {len(got)} passes ({len(listed & set(passes(rows)))} already in "
          f"{os.path.basename(a.moments)})")


if __name__ == "__main__":
    main()
