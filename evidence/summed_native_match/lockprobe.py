"""Does the repo's channel match (image_correction.find_shift) resolve a sub-camera-pixel shift on 4x4-summed frames?
A full-resolution WAC frame and a copy shifted by a known amount, both summed 4x4 and enlarged as resize_image does
(repeated pixels) or smoothly; the found shift against the true one."""
import os, sys, numpy as np, cv2
WT = os.path.expanduser("~/cassini-build/f7/wt"); os.chdir(WT); sys.path.insert(0, WT); sys.path.insert(0, WT + "/web/frames")
import label_handler as lh, image_correction as ic, color_image as ci
frames = sys.argv[1:]
for fr in frames:
    lbl = lh.label("wac_data/" + fr + ".png", as_png=True)
    im = lbl.resize_image().astype(np.float32)
    im = im if im.ndim == 2 else im[..., 0]
    for true in ((2.0, 1.2), (2.1, -1.4), (0.4, 2.5), (1.0, -3.0), (4.0, -4.0)):
        M = np.float32([[1, 0, true[0]], [0, 1, true[1]]])
        sh = cv2.warpAffine(im, M, im.shape[::-1], flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        a, b = (cv2.resize(x, (256, 256), interpolation=cv2.INTER_AREA) for x in (im, sh))
        rep = [cv2.resize(x, (1024, 1024), interpolation=cv2.INTER_AREA) for x in (a, b)]
        smo = [cv2.resize(x, (1024, 1024), interpolation=cv2.INTER_CUBIC) for x in (a, b)]
        u8 = lambda x: cv2.cvtColor(np.clip(x, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        f_full = ic.find_shift(u8(im), u8(sh)); f_rep = ic.find_shift(u8(rep[0]), u8(rep[1])); f_smo = ic.find_shift(u8(smo[0]), u8(smo[1]))
        f_nat = ic.find_shift(u8(a), u8(b)); f_nat = None if f_nat is None else (f_nat[0] * 4, f_nat[1] * 4)
        (px, py), resp = cv2.phaseCorrelate(a, b, cv2.createHanningWindow(a.shape[::-1], cv2.CV_32F)); f_pc = (px * 4, py * 4)
        fmt = lambda f: "none" if f is None else f"({f[0]:+.2f},{f[1]:+.2f})"
        print(f"{fr} true ({true[0]:+.1f},{true[1]:+.1f}) | full {fmt(f_full)} | 4x4 repeated {fmt(f_rep)} | 4x4 smooth {fmt(f_smo)} | native x4 {fmt(f_nat)} | cv2 phaseCorrelate native x4 {fmt(f_pc)}", flush=True)
