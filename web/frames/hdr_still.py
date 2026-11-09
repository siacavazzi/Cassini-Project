#!/usr/bin/env python3
"""HDR stills from the cache: a picture the frame server made (its 1024 px WebP) and its recovery map (frame_server
HDR_DIR, calibration.recovery_map) as a 10-bit PQ AVIF (Rec.2020) or a 16-bit PQ PNG (cICP), with no pipeline run.

The display curve (the one new choice HDR makes; calibration draws the SDR picture as before):
- up to MID of white, the SDR picture's own brightness, SDR white at SDR_WHITE nits (ITU-R BT.2408)
- above it, a power curve reaching HIGHLIGHT nits at the pipeline's white (one curve for every picture, so a movie's
  frames and a mosaic's pictures keep one brightness)
- then a soft roll-off from KNEE to PEAK nits, where what the camera saturated lands
Colors keep their ratios (the brightness curve is on each pixel's brightest channel).

  python web/frames/hdr_still.py PICTURE.webp MAP.webp OUT.avif|OUT.png [--highlight 600]
"""
import argparse
import os
import struct
import subprocess
import sys
import zlib

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import calibration as cal  # noqa: E402

SDR_WHITE = 203.0
HIGHLIGHT = 600.0
KNEE, PEAK = 500.0, 1000.0
MID = 0.5
REC709_TO_2020 = np.array([[0.6274, 0.3293, 0.0433], [0.0691, 0.9195, 0.0114], [0.0164, 0.0880, 0.8956]], np.float32)


def pq(nits):
    """SMPTE ST 2084 code (0-1) of a luminance in nits"""
    y = np.clip(nits / 10000.0, 0, 1)
    m1, m2, c1, c2, c3 = 2610 / 16384, 2523 / 4096 * 128, 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
    p = np.power(y, m1)
    return np.power((c1 + c2 * p) / (1 + c3 * p), m2)


def nits(linear, highlight=HIGHLIGHT):
    """Per channel nits (3 x H x W) of a linear picture (H x W x 3, white = 1)"""
    x = np.moveaxis(np.maximum(linear, 0), -1, 0)
    lum = np.maximum(x.max(axis=0), 1e-9)
    m = MID
    base = SDR_WHITE * lum
    k = max(np.log(highlight / (SDR_WHITE * m)) / np.log(1 / m), 1.0) if m < 0.99 else 1.0
    out = np.where(lum > m, SDR_WHITE * m * np.power(lum / m, k), base)
    out = np.where(out > KNEE, KNEE + (PEAK - KNEE) * np.tanh((out - KNEE) / (PEAK - KNEE)), out)
    return x * (out / lum)[None]


def pq_rgb(linear, highlight=HIGHLIGHT):
    """H x W x 3, 0-1 PQ codes, Rec.2020"""
    return np.moveaxis(pq(np.maximum(np.tensordot(REC709_TO_2020, nits(linear, highlight), axes=1), 0)), 0, -1)


def save_png(rgb, path):
    """16-bit PNG with a cICP chunk (BT.2020, PQ, RGB, full range)"""
    ok, buf = cv2.imencode(".png", (np.clip(rgb, 0, 1) * 65535 + 0.5).astype(np.uint16)[..., ::-1].copy())
    b = buf.tobytes()
    data = bytes([9, 16, 0, 1])
    chunk = struct.pack(">I", 4) + b"cICP" + data + struct.pack(">I", zlib.crc32(b"cICP" + data) & 0xffffffff)
    with open(path, "wb") as fh:
        fh.write(b[:33] + chunk + b[33:])   # after the signature and IHDR


def save_avif(rgb, path, crf=8, preset=6):
    """10-bit 4:2:0 AVIF, BT.2020 / PQ, by ffmpeg (SVT-AV1)"""
    h, w = rgb.shape[:2]
    raw = (np.clip(rgb, 0, 1) * 65535 + 0.5).astype("<u2").tobytes()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{w}x{h}", "-i", "-",
                    "-vf", "scale=out_color_matrix=bt2020:out_range=tv,format=yuv420p10le", "-c:v", "libsvtav1",
                    "-crf", str(crf), "-preset", str(preset), "-color_primaries", "bt2020", "-color_trc", "smpte2084",
                    "-colorspace", "bt2020nc", "-color_range", "tv", "-frames:v", "1", path], input=raw, check=True, stderr=subprocess.DEVNULL)


HDR_TAGS = ["-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-color_range", "tv"]


def x265_params(maxcll=1000, maxfall=200):
    """HDR10 for x265: BT.2020, PQ, a 1,000 nit P3 master and its light levels"""
    md = "G(8500,39850)B(6550,2300)R(35400,14600)WP(15635,16450)L(10000000,1)"
    return (f"colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:hdr10=1:"
            f"master-display={md}:max-cll={maxcll},{maxfall}:repeat-headers=1:log-level=error")


def linear_of(picture, stops):
    """The cached picture (PIL, RGB/RGBA or L/LA) and its map (PIL L) as a linear picture (H x W x 3) and its alpha"""
    a = np.asarray(picture.convert("RGBA"))
    m = np.asarray(stops.convert("L"))
    if m.shape != a.shape[:2]:
        m = cv2.resize(m, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    return cal.recover(a[..., :3], m), a[..., 3]


def make_avif(picture, stops, out, size=1024, highlight=HIGHLIGHT):
    """The frame server's HDR still: picture and its map (paths) as an AVIF at size px (longest side), written to out
    (by way of a temporary file, so a half-made one is never served)"""
    im, m = Image.open(picture), Image.open(stops)
    linear, _ = linear_of(im, m)
    if max(linear.shape[:2]) > size:
        f = size / max(linear.shape[:2])
        linear = cv2.resize(linear, (round(linear.shape[1] * f), round(linear.shape[0] * f)), interpolation=cv2.INTER_AREA)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = f"{out}.{os.getpid()}.tmp.avif"
    try:
        save_avif(pq_rgb(linear, highlight), tmp, crf=10, preset=10)
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture")
    ap.add_argument("map")
    ap.add_argument("out")
    ap.add_argument("--highlight", type=float, default=HIGHLIGHT)
    args = ap.parse_args()
    linear, _ = linear_of(Image.open(args.picture), Image.open(args.map))
    rgb = pq_rgb(linear, args.highlight)
    (save_png if args.out.endswith(".png") else save_avif)(rgb, args.out)


if __name__ == "__main__":
    main()
