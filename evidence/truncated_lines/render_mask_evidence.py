# Before/after evidence for the truncated-line mask: the color path of color_image.make_frame up to
# the RGBA merge (auto_center needs SPICE, so it is left out), flattened onto neutral gray so
# transparent pixels show. Run from the repo root with CASSINI_DATA set.
# usage: render_mask_evidence.py OUTDIR B,G,R:name ...
import os, sys
import numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.getcwd())
import calibration as cal, image_correction as ic, stacking

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
alpha_mask = np.asarray(Image.open("mask.png").convert("L"))


def compose(name, paths, masked):
    lbls, imgs = map(list, zip(*[stacking.load_stacked(p, max_frames=1) for p in paths]))
    if masked:
        masks = [l.valid_mask() for l in lbls]
        imgs = [ic.fill_invalid(img, mask) for img, mask in zip(imgs, masks)]
    imgs = cal.load_channels(lbls, imgs)
    order = sorted(range(len(lbls)), key=lambda j: lbls[j].info["IMAGE_TIME"])
    ref = order[len(order) // 2]
    if masked:
        imgs, masks = ic.align_with_masks(imgs, masks, ref)
        alpha = np.where(np.logical_and.reduce(masks), alpha_mask, 0)
    else:
        imgs = ic.align_images(imgs, ref)
        alpha = alpha_mask
    g = [cv2.cvtColor(c, cv2.COLOR_BGR2GRAY) if c.ndim == 3 else c for c in imgs]
    rgb = np.dstack([g[2], g[1], g[0]]).astype(np.float32)  # given blue, green, red
    a = alpha[..., None].astype(np.float32) / 255
    flat = rgb * a + 128 * (1 - a)
    invalid = (alpha == 0).mean() * 100
    return cv2.cvtColor(flat.astype(np.uint8), cv2.COLOR_RGB2BGR), invalid, alpha > 0


def bar(text, width):
    b = np.full((50, width, 3), 255, np.uint8)
    cv2.putText(b, text, (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return b


lines = []
for spec in sys.argv[2:]:
    paths, name = spec.split(":")
    paths = paths.split(",")
    before, inv_b, ok_b = compose(name, paths, False)
    after, inv_a, ok_a = compose(name, paths, True)
    delta = np.abs(before.astype(int) - after.astype(int)).max(2)
    diff = delta > 0
    both = delta[ok_b & ok_a]
    gap = np.full((before.shape[0], 16, 3), 255, np.uint8)
    pan = np.vstack([np.hstack([bar("BEFORE (main)", before.shape[1]), np.full((50, 16, 3), 255, np.uint8),
                                bar("AFTER (truncated-line mask)", after.shape[1])]), np.hstack([before, gap, after])])
    pan = cv2.resize(pan, (1600, int(pan.shape[0] * 1600 / pan.shape[1])), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(out, f"{name}_before_vs_after.png"), pan)
    lines.append(f"{name}: transparent pixels before {inv_b:.2f}%, after {inv_a:.2f}%; pixels changed {diff.mean() * 100:.2f}%; where both are opaque: mean |diff| {both.mean():.2f}, 99th pct {np.percentile(both, 99):.0f}, max {both.max()}")
    print(lines[-1], flush=True)
open(os.path.join(out, "summary.txt"), "w").write("\n".join(lines) + "\n")
