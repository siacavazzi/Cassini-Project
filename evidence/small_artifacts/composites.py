"""The colour sets the round-2 colour check found black line holes in (after #192), through the pipeline's colour
path (color_image.load_aligned, as the frame server's set endpoint), with what stays lost drawn black. Run once in
each checkout, then put the PNGs side by side:

    python evidence/small_artifacts/composites.py OUT/<name>

with CASSINI_DATA (and CASSINI_CISSCAL) set, e.g. to the frames fetch_samples.py packs for these sets."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())
import color_image  # noqa: E402

# (name, the set's frames, red to blue)
SETS = [("rhea", ["nac_data/N1521598393_1.png", "nac_data/N1521598356_1.png", "nac_data/N1521598323_1.png"]),
        ("dione", ["nac_data/N1507741123_2.png", "nac_data/N1507741106_2.png", "nac_data/N1507741089_2.png"]),
        ("00bdi", ["nac_data/N1481737960_2.png", "nac_data/N1481737900_2.png", "nac_data/N1481737870_2.png"]),
        ("rings", ["wac_data/W1872488832_1.png", "wac_data/W1872488870_1.png", "wac_data/W1872488798_1.png"])]

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for name, paths in SETS:
    imgs, valid, _, report = color_image.load_aligned(paths)
    gray = [i if i.ndim == 2 else i[..., 0] for i in imgs]
    image = cv2.merge([gray[2], gray[1], gray[0]])
    image = np.where(valid[..., None], image, 0).astype(np.uint8)
    cv2.imwrite(os.path.join(out, name + ".png"), image)
    print(name, "holes", int((~valid).sum()), report.get("lost_px"), flush=True)
