#!/usr/bin/env python3
"""Before/after of Additional stabilization (film_steady, the Movie Editor's Framing) from the stage frames
web/test_film_steady_page.cjs saved (off-NN.png, on-NN.png): where the moon is drawn in each (its lit area's centroid,
as image_correction.centroid_shift finds it), how far it jumps from frame to frame against a smooth line through it,
and a side-by-side movie (off left, on right) with a trace of the moon's place under each.
usage: python web/frames/film_steady_evidence.py DIR OUT.mp4 [FPS]"""
import glob, os, subprocess, sys, tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def centre(path):
    g = cv2.GaussianBlur(np.asarray(Image.open(path).convert("L")).astype(np.float32), (0, 0), 3)
    lit = g > 0.2 * g.max()
    ys, xs = np.nonzero(lit)
    w = g[ys, xs]
    return float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum())


def jitter(p):
    """Frame-to-frame jumps (px) less the smooth motion: the RMS of the second difference over sqrt(6)."""
    d2 = np.diff(np.asarray(p), 2, axis=0)
    return float(np.sqrt((d2 ** 2).sum(1).mean() / 6))


def main(folder, out, fps=4):
    offs, ons = sorted(glob.glob(f"{folder}/off-*.png")), sorted(glob.glob(f"{folder}/on-*.png"))
    a, b = [centre(p) for p in offs], [centre(p) for p in ons]
    ja, jb = jitter(a), jitter(b)
    print(f"{len(a)} frames: wobble {ja:.2f} px -> {jb:.2f} px on the stage")
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    tmp = tempfile.mkdtemp()
    # a window round where the moon is on average, blown up ZOOM times, the same window in both
    mx, my = np.mean(a + b, axis=0)
    half = int(max(60, 3 * max(np.ptp(np.array(a + b), axis=0))))
    box = (int(mx) - half, int(my) - half, int(mx) + half, int(my) + half)
    side = 480
    k = side / (2 * half)
    for i, (pa, pb) in enumerate(zip(offs, ons)):
        A = Image.open(pa).convert("RGB").crop(box).resize((side, side), Image.LANCZOS)
        B = Image.open(pb).convert("RGB").crop(box).resize((side, side), Image.LANCZOS)
        w = h = side
        canvas = Image.new("RGB", (2 * w + 12, h + 60), (12, 14, 18))
        canvas.paste(A, (0, 60)); canvas.paste(B, (w + 12, 60))
        d = ImageDraw.Draw(canvas)
        d.text((14, 16), f"Auto center only: wobble {ja:.1f} px", fill=(230, 230, 230), font=font)
        d.text((w + 26, 16), f"+ Additional stabilization: {jb:.1f} px", fill=(138, 182, 255), font=font)
        # the moon's middle so far, as a trace
        for x0, pts, col in ((0, a, (255, 170, 120)), (w + 12, b, (138, 182, 255))):
            P = [(x0 + (x - box[0]) * k, 60 + (y - box[1]) * k) for x, y in pts[:i + 1]]
            if len(P) > 1:
                d.line(P, fill=col, width=2)
            d.ellipse([P[-1][0] - 3, P[-1][1] - 3, P[-1][0] + 3, P[-1][1] + 3], fill=col)
        canvas.save(f"{tmp}/{i:03d}.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{tmp}/%03d.png", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out], check=True)
    Image.open(f"{tmp}/{len(offs) - 1:03d}.png").save(os.path.splitext(out)[0] + ".png")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(v) for v in sys.argv[3:4]))
