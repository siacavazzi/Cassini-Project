# Renders evidence through the pipeline's own path for whatever CASSINI_DATA is (run from the repo).
# usage: render_evidence.py TAG OUTDIR rgb:B,G,R:name | single:PATH:name | iof:PATH:name ...
import os, sys
import numpy as np, cv2
sys.path.insert(0, os.getcwd())
import calibration as cal, data_source as ds, stacking, image_correction as ic

tag, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
print("source", ds.get_source(), "lut8", ds.lut8(), flush=True)
for spec in sys.argv[3:]:
    kind, paths, name = spec.split(":")
    if kind == "rgb":
        lbls, imgs = zip(*[stacking.load_stacked(p) for p in paths.split(",")])
        chans = cal.load_channels(list(lbls), list(imgs))
        order = sorted(range(len(lbls)), key=lambda j: lbls[j].info["IMAGE_TIME"])
        try:
            chans = ic.align_images(chans, order[len(order) // 2])
        except Exception as e:
            print("align failed", e)
        g = [c if c.ndim == 2 else cv2.cvtColor(c, cv2.COLOR_BGR2GRAY) for c in chans]
        cv2.imwrite(os.path.join(out, f"{name}_{tag}.png"), cv2.merge(g))  # given blue, green, red
        print(name, tag, [l.info.get("DATA_CONVERSION_TYPE") for l in lbls], flush=True)
    else:
        lbl, img = stacking.load_stacked(paths, max_frames=1)
        if kind == "single":
            chan = cal.load_channels([lbl], [img])[0]
            cv2.imwrite(os.path.join(out, f"{name}_{tag}.png"), chan)
        else:
            png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
            np.save(os.path.join(out, f"{name}_{tag}.npy"), cal.calibrate(png, lbl.get_info(), gray))
        print(name, tag, kind, lbl.info.get("DATA_CONVERSION_TYPE"), lbl.info.get("FILTER_NAME"), flush=True)
