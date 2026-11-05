import numpy as np, cv2

def stars(img, n=400):
    x = np.nan_to_num(img).astype(np.float32)
    hp = x - cv2.medianBlur(x, 5) * 0 - cv2.GaussianBlur(cv2.medianBlur(x, 5), (0, 0), 8)
    s = 1.4826 * np.median(np.abs(hp - np.median(hp)))
    pk = (hp > 10 * s) & (hp == cv2.dilate(hp, np.ones((7, 7), np.uint8)))
    pk[:6, :] = pk[-6:, :] = pk[:, :6] = pk[:, -6:] = False
    pk &= np.isfinite(img)
    r, c = np.nonzero(pk)
    out = []
    for y, xx in zip(r, c):
        w = hp[y - 3:y + 4, xx - 3:xx + 4].astype(np.float64)
        w = np.clip(w - np.median(hp[y - 6:y + 7, xx - 6:xx + 7]), 0, None)
        tot = w.sum()
        if tot <= 0 or w[3, 3] / tot > 0.6:     # a hot pixel: one pixel holds the light
            continue
        yy, xg = np.mgrid[-3:4, -3:4]
        out.append((xx + (w * xg).sum() / tot, y + (w * yy).sum() / tot, tot))
    out = np.array(out)
    return out[np.argsort(-out[:, 2])][:n]

