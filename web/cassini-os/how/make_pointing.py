"""
The pointing diagram's real frames (web/cassini-os/how/pointing.json): for each frame, where the pipeline's own
bootleg_autonav.find_target puts its target on the sensor, the range, and what the page needs to draw the body with
its real surface map: the turn from the diagram's axes (sensor right, sensor up, out along the boresight) into the
body's IAU frame at the moment the light left it, the Sun's direction and the body's mean radius, all from SPICE.

    CASSINI_KERNELS=... python web/cassini-os/how/make_pointing.py N1578106676_1 N1546290562_1
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

import numpy as np            # noqa: E402
import spiceypy as sp         # noqa: E402

import bootleg_autonav as ba  # noqa: E402
import label_handler as lh    # noqa: E402

FOLDERS = {"N": "nac_data", "W": "wac_data"}
LOADED = set()


def frame_facts(frame_id):
    lbl = lh.label(f"{FOLDERS[frame_id[0]]}/{frame_id}.png", as_png=True)
    year = int(lbl.info["IMAGE_TIME"][:4])
    if year not in LOADED:
        ba.load_kernels(year, year)
        LOADED.add(year)
    x, y, z, angle = ba.find_target(lbl, False, None)
    g = lbl.geometry
    et, camera, target, scale = g["et"], g["camera"], g["target"], g["scale"]
    pos, lt = sp.spkpos(target, et, "J2000", ba.ABCORR, "CASSINI")
    cam = np.array(sp.pxform("J2000", camera, et))
    body = np.array(sp.pxform("J2000", f"IAU_{target}", et - lt))
    sun = np.array(sp.spkpos("SUN", et - lt, "J2000", "LT+S", target)[0])
    radii = sp.bodvrd(target, "RADII", 3)[1]
    # the diagram's axes from the camera frame: samples grow towards -X and lines towards -Y (cas_iss_v10.ti), so
    # right = -X, up = +Y, out = +Z
    flip = np.diag([-1.0, 1.0, 1.0])
    world_to_body = body @ cam.T @ flip            # a direction in the diagram's axes -> the body's IAU frame
    sun_world = flip @ cam @ (sun / np.linalg.norm(sun))
    return {
        "id": frame_id, "target": target.title(), "time": lbl.info["IMAGE_TIME"][:19].replace("T", " "),
        "date": datetime.datetime.strptime(lbl.info["IMAGE_TIME"][:8], "%Y-%j").strftime("%-d %b %Y"),
        "sample": round(ba.CCD_CENTER - x, 1), "line": round(ba.CCD_CENTER - y, 1), "km": round(z),
        "radius_km": round(float(np.mean(radii)), 1), "scale": round(scale, 1), "north": round(angle, 2),
        "light_s": round(lt, 2), "world_to_body": np.round(world_to_body, 6).tolist(),
        "sun": np.round(sun_world, 6).tolist(), "texture": f"../data/textures/1k/{target.lower()}.webp",
    }


def main():
    out = [frame_facts(i) for i in sys.argv[1:]]
    path = os.path.join(HERE, "pointing.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1)[:1500])


if __name__ == "__main__":
    main()
