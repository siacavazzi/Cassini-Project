"""
Re-encodes raw Cassini ISS IMG files into the proposed lean archive format and measures it.

For each frame in sequence.json:
  new/<id>.png          8-bit codes: 12BIT -> nearest entry of the camera's 12->8 bit LUT,
                        TABLE -> the raw 8-bit codes. No stretch.
  new/<id>.prefix.gz    the 24-byte binary prefix of every line, gzipped
  new16/<id>.png        lossless 16-bit PNG of the raw DN (size comparison only)
Writes metrics.json with sizes and quantisation error per frame.

Usage: python -I scripts/encode.py <raw_test dir>
"""
import gzip
import json
import os
import re
import sys
import types

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.modules.setdefault("data_source", types.ModuleType("data_source"))  # calibration imports it
sys.path.insert(0, HERE)
import calibration  # noqa: E402

LUT = calibration.LUT
MIDS = (LUT[:-1] + LUT[1:]) / 2
# Fallback read noise for frames with too little sky to measure it (median of this batch)
READ_NOISE_DN = 0.75
GAIN_E_PER_DN = {"215": 215.0, "95": 95.0, "29": 29.0, "12": 12.0}


def parse_label(path):
    info = {}
    for line in open(path, encoding="latin1"):
        m = re.match(r"^\s*(\^?[A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) not in info:
            info[m.group(1)] = m.group(2)
    return info


def read_img(img_path, lbl_path):
    """Returns (info, image array as stored, prefixes uint8 [lines, prefix_bytes])."""
    info = parse_label(lbl_path)
    # The IMAGE object's keys appear after the top-level ones; reparse that block
    text = open(lbl_path, encoding="latin1").read()
    block = re.search(r"OBJECT\s*=\s*IMAGE\s*\n(.*?)END_OBJECT\s*=\s*IMAGE\b", text, re.S).group(1)
    g = lambda k: re.search(rf"{k}\s*=\s*(\S+)", block).group(1)
    lines, samples, bits = int(g("LINES")), int(g("LINE_SAMPLES")), int(g("SAMPLE_BITS"))
    prefix = int(g("LINE_PREFIX_BYTES"))
    record_bytes = int(info["RECORD_BYTES"])
    start_record = int(re.search(r",\s*(\d+)\s*\)", info["^IMAGE"]).group(1))
    raw = np.fromfile(img_path, dtype=np.uint8)
    offset = (start_record - 1) * record_bytes
    line_bytes = prefix + samples * bits // 8
    rows = raw[offset:offset + lines * line_bytes].reshape(lines, line_bytes)
    prefixes = rows[:, :prefix].copy()
    dtype = ">i2" if bits == 16 else "u1"
    image = rows[:, prefix:].copy().view(dtype).reshape(lines, samples).astype(np.int32)
    return info, image, prefixes


def clean(v):
    return v.replace('"', "").strip()


def encode(image, conversion):
    if conversion == "12BIT":
        return np.searchsorted(MIDS, image).astype(np.uint8)
    if conversion == "TABLE":
        return image.astype(np.uint8)
    raise ValueError(conversion)


def decode(codes, conversion):
    return LUT[codes] if conversion == "12BIT" else codes.astype(np.float64)


def main(root):
    seq = json.load(open(os.path.join(root, "sequence.json")))
    for d in ("new", "new16"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    out = []
    for row in seq:
        fid = row["FILE_NAME"].replace(".IMG", "")
        img = os.path.join(root, "img", fid + ".IMG")
        info, image, prefixes = read_img(img, os.path.join(root, "img", fid + ".LBL"))
        conv = clean(info["DATA_CONVERSION_TYPE"])
        codes = encode(image, conv)
        new_png = os.path.join(root, "new", fid + ".png")
        Image.fromarray(codes).save(new_png, optimize=True)
        pre = os.path.join(root, "new", fid + ".prefix.gz")
        with gzip.open(pre, "wb", compresslevel=9) as f:
            f.write(prefixes.tobytes())
        npz = os.path.join(root, "new", fid + ".prefix.npz")
        np.savez_compressed(npz, prefix=prefixes)
        png16 = os.path.join(root, "new16", fid + ".png")
        Image.fromarray(image.astype(np.uint16)).save(png16, optimize=True)

        # round trip checks
        back = np.array(Image.open(new_png))
        assert (back == codes).all()
        assert (np.array(Image.open(png16)).astype(np.int32) == image).all()

        gain = GAIN_E_PER_DN[clean(info["GAIN_MODE_ID"]).split()[0]]
        bias = float(info["BIAS_STRIP_MEAN"])
        if conv == "TABLE":
            dn, bias_dn = LUT[image], LUT[int(min(max(round(bias), 0), 255))]
            err = np.zeros(image.shape)
        else:
            dn, bias_dn = image.astype(np.float64), bias
            err = np.abs(decode(codes, conv) - dn)
        noise = np.sqrt(np.maximum(dn - bias_dn, 1) / gain)
        lit = dn > bias_dn + 0.5  # exclude pixels at bias
        ratio = (err / noise)[lit]
        signal = (dn - bias_dn)[lit]
        bands = {}
        for lo, hi in ((1, 10), (10, 100), (100, 1000), (1000, 5000)):
            m = (signal >= lo) & (signal < hi)
            if m.any():
                bands[f"{lo}-{hi}"] = dict(n=int(m.sum()), p99=float(np.percentile(ratio[m], 99)), max=float(ratio[m].max()))
        # read noise, from pixel-to-pixel differences in the dark sky (no 2 Hz banding
        # within a line), then the error against total noise
        a = dn
        dark = (a[:, 1:] < bias_dn + 8) & (a[:, :-1] < bias_dn + 8)
        diffs = (a[:, 1:] - a[:, :-1])[dark]
        read_noise = None
        if diffs.size > 1000:
            d = diffs[np.abs(diffs) <= 8]  # drop stars, cosmic rays, ring edges
            read_noise = float(d.std() / np.sqrt(2))
            if read_noise < 0.3:  # a frame with filled (zero) gaps, not real sky
                read_noise = None
        rn = read_noise if read_noise is not None else READ_NOISE_DN
        ratio_rn = (err / np.sqrt(noise ** 2 + rn ** 2))[lit]
        old_png = os.path.join(root, "old_png", fid + ".png")
        rec = dict(
            id=fid, conversion=conv, filter=clean(info["FILTER_NAME"]),
            exposure_ms=float(info["EXPOSURE_DURATION"]), gain=gain, bias=bias,
            dn_min=int(image.min()), dn_max=int(image.max()), codes_used=int(len(np.unique(codes))),
            size_img=os.path.getsize(img), size_lbl=os.path.getsize(img[:-4] + ".LBL"),
            size_old_png=os.path.getsize(old_png) if os.path.exists(old_png) else None,
            size_new_png=os.path.getsize(new_png), size_prefix_gz=os.path.getsize(pre),
            size_prefix_npz=os.path.getsize(npz), size_png16=os.path.getsize(png16),
            err_dn_max=float(err.max()), lit_fraction=float(lit.mean()),
            ratio_max=float(ratio.max()) if ratio.size else 0.0,
            ratio_p99=float(np.percentile(ratio, 99)) if ratio.size else 0.0,
            ratio_rms=float(np.sqrt(np.mean(ratio ** 2))) if ratio.size else 0.0,
            read_noise_dn=read_noise,
            ratio_rn_max=float(ratio_rn.max()) if ratio.size else 0.0,
            ratio_rn_p99=float(np.percentile(ratio_rn, 99)) if ratio.size else 0.0,
            ratio_rn_rms=float(np.sqrt(np.mean(ratio_rn ** 2))) if ratio.size else 0.0,
            ratio_bands=bands,
        )
        out.append(rec)
        print(fid, conv, rec["filter"], rec["dn_min"], rec["dn_max"], rec["size_img"], rec["size_old_png"],
              rec["size_new_png"], rec["size_prefix_gz"], rec["size_png16"],
              f"max={rec['ratio_max']:.2f} p99={rec['ratio_p99']:.2f} rms={rec['ratio_rms']:.2f} RN={read_noise} withRN p99={rec['ratio_rn_p99']:.2f} max={rec['ratio_rn_max']:.2f}", flush=True)
    json.dump(out, open(os.path.join(root, "metrics.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
