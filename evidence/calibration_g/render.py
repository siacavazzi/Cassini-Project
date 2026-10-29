"""
Group G evidence: draws frames and color sets the way the frame server's composite() does (color_image.load_aligned:
calibrated, aligned, on the picture's display scale; one id = the frame alone, gray), from whatever checkout it sits
in, so the same script run in a worktree of the old code and in this one gives the before and after.

  python evidence/calibration_g/render.py OUT_DIR ID[,ID...] [ID[,ID...] ...]

Each argument is one picture: a frame id, or the ids of a color set (any order; drawn longest wavelength first, as
the camera windows ask). Writes OUT_DIR/<first id>.png and prints each picture's alignment report.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "web", "frames"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import color_image  # noqa: E402
import reel  # noqa: E402

FOLDERS = {"N": "nac_data", "W": "wac_data"}


def picture(ids):
    idx, _ = reel.load_index()
    rows = idx.set_index("id").loc[ids]
    order = sorted(ids, key=lambda i: -reel.wavelength(rows.loc[i, "INSTRUMENT_ID"],
                                                       str(rows.loc[i, "filter1"]) + str(rows.loc[i, "filter2"])))
    imgs, valid, _, report = color_image.load_aligned([f"{FOLDERS[i[0]]}/{i}.png" for i in order])
    chans = [img[..., 0] if img.ndim == 3 else img for img in imgs]
    if len(chans) == 1:
        chans = chans * 3
    elif len(chans) == 2:
        chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
    rgb = np.dstack(chans[:3])
    rgb[~valid] = 0
    return rgb, order, report


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for arg in sys.argv[2:]:
        rgb, order, report = picture(arg.split(","))
        cv2.imwrite(os.path.join(out, f"{arg.split(',')[0]}.png"), rgb[:, :, ::-1])
        print(arg.split(",")[0], " ".join(order), report.get("aligned"))


if __name__ == "__main__":
    main()
