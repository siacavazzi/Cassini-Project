"""Call 24 evidence from the real code: each frame as a still (color_image.load_aligned) with the rule off
(calibration.OVEREXPOSED_GAIN = 1: the white as it was) and on (4). usage: audit_c24_evidence.py out_dir frame ..."""
import sys, os, json
sys.path.insert(0, "."); sys.path.insert(0, "web/frames")
import numpy as np, cv2
import calibration as cal, color_image as ci
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)


def tag(img, lines):
    bar = np.zeros((26 * len(lines) + 8, img.shape[1]), np.uint8)
    for i, t in enumerate(lines):
        cv2.putText(bar, t, (6, 22 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1, cv2.LINE_AA)
    return np.vstack([bar, img])


gain = cal.OVEREXPOSED_GAIN
for n, fid in enumerate(sys.argv[2:], 1):
    path = ("nac_data/" if fid[0] == "N" else "wac_data/") + fid + ".png"
    outs = {}
    for key, g in (("before", 1.0), ("after", gain)):
        cal.OVEREXPOSED_GAIN = g
        imgs, valid, lbl, rep = ci.load_aligned([path])
        outs[key] = imgs[0] if imgs[0].ndim == 2 else cv2.cvtColor(imgs[0], cv2.COLOR_BGR2GRAY)
    cal.OVEREXPOSED_GAIN = gain
    info = lbl.info
    sat = cal.saturated_of(lbl, outs["before"].shape[:2])
    share = float(sat.mean()) if sat is not None else 0.0
    d = np.abs(outs["before"].astype(int) - outs["after"].astype(int))
    same = int(d.max()) == 0
    a = cv2.resize(outs["before"], (640, 640), interpolation=cv2.INTER_AREA)
    b = cv2.resize(outs["after"], (640, 640), interpolation=cv2.INTER_AREA)
    exp = cal.expected_maximum(info)
    rule = "applies" if (exp or 0) > cal.OVEREXPOSED and 0 < share < cal.OVEREXPOSED_SATURATED else "does not apply"
    sheet = np.hstack([tag(a, [f"before  {str(info.get('TARGET_NAME')).title()} {fid}",
                               f"label forecast {exp:,.0f}% of full well; {share * 100:.2f}% of the frame saturated"]),
                       np.zeros((700, 12), np.uint8),
                       tag(b, [f"after (this PR): rule {rule}",
                               "identical to before" if same else f"mean brightness {outs['before'].mean():.1f} -> {outs['after'].mean():.1f} of 255"])])
    cv2.imwrite(f"{OUT}/overexposed_{n:02d}_{fid}.jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    rec = dict(n=n, frame=fid, target=str(info.get("TARGET_NAME")), obs=str(info.get("OBSERVATION_ID")), expected=exp, saturated=share,
               rule=rule, identical=same, mean_before=float(outs["before"].mean()), mean_after=float(outs["after"].mean()),
               changed=float((d > 0).mean()))
    with open(f"{OUT}/overexposed.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec, flush=True)
