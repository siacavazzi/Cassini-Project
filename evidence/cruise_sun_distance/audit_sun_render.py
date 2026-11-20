"""Audit S3: stills and color sets of the 1999-2000 cruise bodies as today, and with their own Sun distances
(calibration.ORBITS given EARTH, MOON, VENUS, MASURSKY). usage: audit_sun_render.py out_dir set ...  (set = frame ids joined by +)"""
import sys, os, json, datetime
sys.path.insert(0, "."); sys.path.insert(0, "web/frames")
import numpy as np, cv2
import calibration as cal, color_image as ci
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
NEW = {"EARTH": (1.00000, 0.01674, datetime.datetime(1999, 1, 3), 1.00001), "MOON": (1.00000, 0.01674, datetime.datetime(1999, 1, 3), 1.00001),
       "VENUS": (0.72333, 0.00678, datetime.datetime(1999, 4, 20), 0.61520), "MASURSKY": (2.617, 0.0, datetime.datetime(2000, 1, 23), 1.0)}
base = dict(cal.ORBITS)
for s in sys.argv[2:]:
    ids = s.split("+"); paths = [("nac_data/" if f[0] == "N" else "wac_data/") + f + ".png" for f in ids]
    rec = {"set": s}
    try:
        outs = {}
        for key, orbits in (("A", base), ("B", {**base, **NEW})):
            cal.ORBITS.clear(); cal.ORBITS.update(orbits)
            imgs, valid, lbl, rep = ci.load_aligned(paths)
            outs[key] = imgs[0]
            info = lbl.info if hasattr(lbl, "info") else lbl[0].info
            rec[key + "_distance"] = cal.sun_distance(info)
            # the frame's own I/F on the lit body
            import data_source as ds, label_handler as lh
            l0 = lh.label(paths[0], as_png=True)
            iof = cal.calibrate(ds.imread(l0.export(), cv2.IMREAD_GRAYSCALE), l0.get_info(), l0.resize_image() if l0.resize_image().ndim == 2 else cv2.cvtColor(l0.resize_image(), cv2.COLOR_BGR2GRAY))
            lit = iof > 0.2 * np.percentile(iof, 99.9)
            rec[key + "_lit_iof"] = float(np.median(iof[lit])); rec[key + "_p999"] = float(np.percentile(iof, 99.9))
        rec["target"] = str(info.get("TARGET_NAME")); rec["report"] = str(rep)[:300]
        same = outs["A"].shape == outs["B"].shape and np.array_equal(outs["A"], outs["B"])
        d = np.abs(outs["A"].astype(int) - outs["B"].astype(int)) if outs["A"].shape == outs["B"].shape else None
        rec.update(identical=bool(same), max_diff=None if d is None else int(d.max()), mean_diff=None if d is None else float(d.mean()), changed=None if d is None else float((d > 0).mean()))
        np.savez_compressed(f"{OUT}/sun_{ids[0]}.npz", **outs)
    except Exception as e:
        import traceback; rec["err"] = f"{type(e).__name__} {e}"[:200]; rec["tb"] = traceback.format_exc()[-400:]
    finally:
        cal.ORBITS.clear(); cal.ORBITS.update(base)
    with open(f"{OUT}/sun.jsonl", "a") as f: f.write(json.dumps(rec) + "\n")
    print({k: v for k, v in rec.items() if k != "tb"}, flush=True)
