"""
Data for the SPICE section of the "How the pictures are made" page (spice.json): where Cassini and Saturn's major moons
were over three weeks around the Dione frame of the pointing diagram (4 January 2008), seen from above Saturn's
north pole, from the mission's own SPK kernels; and Dione's size and spin from the PCK.

    CASSINI_KERNELS=... python web/cassini-os/how/make_spice_demo.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))

import numpy as np            # noqa: E402
import spiceypy as sp         # noqa: E402

import bootleg_autonav as ba  # noqa: E402

START, END, STEP_H = "2007-12-22T00:00:00", "2008-01-13T00:00:00", 2.0
MOONS = ["MIMAS", "ENCELADUS", "TETHYS", "DIONE", "RHEA", "TITAN"]
FRAME_TIME = "2008-004T02:21:46.612"   # N1578106676_1, the pointing diagram's Dione frame


def main():
    ba.load_kernels(2007, 2008)
    t0, t1 = sp.str2et(START), sp.str2et(END)
    ets = np.arange(t0, t1, STEP_H * 3600)
    # Saturn's equator plane, fixed at the middle of the window: x, y in it, z along Saturn's pole
    rot = np.array(sp.pxform("J2000", "IAU_SATURN", (t0 + t1) / 2))
    pole = rot[2]
    x = np.cross([0, 0, 1.0], pole); x /= np.linalg.norm(x)
    y = np.cross(pole, x)
    basis = np.array([x, y, pole])

    def track(body):
        out = []
        for et in ets:
            p = np.array(sp.spkpos(body, et, "J2000", "NONE", "SATURN")[0])
            q = basis @ p
            out.append([round(q[0] / 1000, 1), round(q[1] / 1000, 1)])   # thousands of km
        return out

    frame_et = sp.str2et(FRAME_TIME)
    data = {
        "start": START, "step_h": STEP_H, "unit": "1000 km",
        "frame_index": int(round((frame_et - t0) / (STEP_H * 3600))),
        "cassini": track("CASSINI"),
        "moons": {m.title(): track(m) for m in MOONS},
        "saturn_radius": round(float(sp.bodvrd("SATURN", "RADII", 3)[1][0]) / 1000, 2),
        "dione": {
            "radii_km": [round(float(r), 1) for r in sp.bodvrd("DIONE", "RADII", 3)[1]],
            "spin_deg_per_day": round(float(sp.gdpool("BODY604_PM", 1, 1)[0]), 4),
        },
    }
    with open(os.path.join(HERE, "spice.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print({k: v for k, v in data.items() if k not in ("cassini", "moons")}, len(data["cassini"]))


if __name__ == "__main__":
    main()
