#!/usr/bin/env python3
"""
Colour of Titan's ground as the probe saw it, from the DISR spectrometers, and
tinted versions of the (single-band) DISR frames and mosaics.

The DISR imagers record one band (660-1000 nm), so the frames carry brightness
only. The downward-looking visible spectrometer (DLVS) measured the radiance
coming up from below at 477-977 nm all through the descent, and the violet
photometer (DLV) measured its mean over 350-480 nm. Together they cover the
eye's range:

  1. For every DLVS measurement, average the spectra over its zenith angles.
  2. Below 477 nm, fill in a straight line in wavelength that meets the DLVS
     value at 477 nm and whose mean over 350-480 nm equals the DLV radiance
     measured nearest in time.
  3. Integrate against the CIE 1931 2-degree colour matching functions
     (Wyman, Sloan & Shirley 2013 analytic fit) to get XYZ, then linear sRGB
     with the D65 white point and no chromatic adaptation. The Sun is close to
     D65, so a white surface in direct sunlight would come out white; what is
     left is the colour Titan's haze and surface give the light.
  4. Keep only the chromaticity: each tinted pixel keeps the frame's brightness
     (its luminance Y) and takes the hue and saturation of the spectrum.

The probe's lamp switched on at about 700 m and its warm light dominates the
spectra below that, so frames below 700 m and on the surface use the colour
measured between 0.7 and 2 km instead. That choice is recorded in the output.

  python web/huygens/descent_color.py --spec <dir with DLVS_DDP.TAB, DLV_DDP.TAB>
      --replay <replay dir>

writes <replay>/huygens_color.json (colour against altitude), tinted frames
images/huygens_color/<id>.png and tinted mosaics mosaics/color/<s>m.png
(tinted with the near-surface colour).
"""

import argparse
import json
import os

import numpy as np
from PIL import Image

LAMP_ON_KM = 0.7
NEAR_SURFACE_KM = (0.7, 2.0)


def cie_xyz(wl):
    """CIE 1931 2-degree colour matching functions, multi-lobe fit of Wyman et al. (2013)."""
    def g(x, mu, s1, s2):
        s = np.where(x < mu, s1, s2)
        return np.exp(-0.5 * ((x - mu) / s) ** 2)
    x = 1.056 * g(wl, 599.8, 37.9, 31.0) + 0.362 * g(wl, 442.0, 16.0, 26.7) - 0.065 * g(wl, 501.1, 20.4, 26.2)
    y = 0.821 * g(wl, 568.8, 46.9, 40.5) + 0.286 * g(wl, 530.9, 16.3, 31.1)
    z = 1.217 * g(wl, 437.0, 11.8, 36.0) + 0.681 * g(wl, 459.0, 26.0, 13.8)
    return np.stack([x, y, z], axis=-1)


XYZ_TO_SRGB = np.array([[3.2406, -1.5372, -0.4986],
                        [-0.9689, 1.8758, 0.0415],
                        [0.0557, -0.2040, 1.0570]])


def read_table(path, skip):
    lines = open(path, encoding="latin1").read().splitlines()
    return lines, np.array([[float(v) for v in ln.split()] for ln in lines[skip:] if ln.strip()])


def spectra(spec_dir):
    lines, rows = read_table(os.path.join(spec_dir, "DLVS_DDP.TAB"), 3)
    wl = np.array([float(v) for v in lines[1].split()[10:]])
    _, dlv = read_table(os.path.join(spec_dir, "DLV_DDP.TAB"), 2)
    order = np.argsort(wl)
    wl = wl[order]
    mt, alt, rad = rows[:, 3], rows[:, 4], rows[:, 10:][:, order]
    out = []
    for t in np.unique(mt):
        sel = mt == t
        s = np.nanmean(np.where(rad[sel] > 0, rad[sel], np.nan), axis=0)
        if np.isnan(s).any():
            continue
        v = dlv[np.argmin(np.abs(dlv[:, 0] - t)), 2]
        out.append((t, float(alt[sel][0]), s, float(v)))
    return wl, out


def spectrum_to_rgb(wl, s, violet):
    """Linear sRGB (unnormalised) and luminance of one upward radiance spectrum."""
    # blue end: line a + b*(l - 477) with value s0 at 477 and mean `violet` over 350-480
    l0 = wl[0]
    s0 = s[0]
    # mean of the line over [350, 480] = s0 + b * ((350 + 480) / 2 - l0)
    b = (violet - s0) / ((350 + 480) / 2 - l0)
    blue_wl = np.arange(380.0, l0, 1.0)
    blue = np.maximum(s0 + b * (blue_wl - l0), 0)
    red_wl = np.arange(l0, 781.0, 1.0)
    red = np.interp(red_wl, wl, s)
    lam = np.concatenate([blue_wl, red_wl])
    spec = np.concatenate([blue, red])
    xyz = (cie_xyz(lam) * spec[:, None]).sum(axis=0)
    return XYZ_TO_SRGB @ xyz, xyz[1]


def color_table(spec_dir):
    wl, meas = spectra(spec_dir)
    tab = []
    for t, alt, s, v in meas:
        rgb, Y = spectrum_to_rgb(wl, s, v)
        tab.append((t, alt, rgb / Y))  # chromaticity at unit luminance
    tab.sort(key=lambda r: -r[1])
    return tab


def color_at(tab, alt_km):
    """Unit-luminance linear RGB for an altitude (lamp-free above LAMP_ON_KM)."""
    alts = np.array([r[1] for r in tab])
    rgbs = np.array([r[2] for r in tab])
    if alt_km < LAMP_ON_KM:
        sel = (alts >= NEAR_SURFACE_KM[0]) & (alts <= NEAR_SURFACE_KM[1])
        return rgbs[sel].mean(axis=0)
    # median over measurements within +-5% (at least +-0.3 km) of the altitude
    w = max(0.05 * alt_km, 0.3)
    sel = np.abs(alts - alt_km) <= w
    if not sel.any():
        sel = np.abs(alts - alt_km) == np.abs(alts - alt_km).min()
    return np.median(rgbs[sel], axis=0)


def srgb_decode(v):
    v = v / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def srgb_encode(v):
    v = np.clip(v, 0, 1)
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055) * 255.0


LUMA = np.array([0.2126, 0.7152, 0.0722])


def tint(gray8, rgb_unit):
    """Grey 8-bit image -> sRGB 8-bit: keep luminance, take the spectrum's chromaticity.
    Where the tinted colour would leave the sRGB gamut it is desaturated toward grey."""
    Y = srgb_decode(gray8.astype(np.float64))
    c = np.asarray(rgb_unit, float)
    c = np.maximum(c, 0)
    c = c / (LUMA @ c)
    out = Y[..., None] * c
    over = out.max(axis=-1, keepdims=True)
    # blend toward neutral where a channel would clip, keeping luminance
    k = np.clip((over - 1) / np.maximum(over - Y[..., None], 1e-6), 0, 1)
    out = out * (1 - k) + Y[..., None] * k
    return srgb_encode(out).round().astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--replay", required=True)
    a = ap.parse_args()
    tab = color_table(a.spec)
    rows = {"alt_km": [], "rgb_linear_unit_Y": [], "srgb8_mid_grey": []}
    for alt in np.arange(140, -0.01, -1.0):
        c = color_at(tab, float(alt))
        rows["alt_km"].append(float(alt))
        rows["rgb_linear_unit_Y"].append([round(float(x), 4) for x in c])
        rows["srgb8_mid_grey"].append(tint(np.array([[150]], np.uint8), c)[0, 0].tolist())
    meta = {"source": "DISR DLVS_DDP (477-977 nm) + DLV_DDP (350-480 nm), averaged over zenith angles",
            "method": "XYZ (CIE 1931, Wyman 2013 fit) -> linear sRGB, D65 white, no adaptation; "
                      "only chromaticity is applied, luminance comes from the frame",
            "lamp_on_km": LAMP_ON_KM,
            "below_lamp_uses_km": NEAR_SURFACE_KM,
            "measurements": len(tab), **rows}
    json.dump(meta, open(os.path.join(a.replay, "huygens_color.json"), "w"), indent=1)

    c = json.load(open(os.path.join(a.replay, "catalog/huygens.json")))
    od = os.path.join(a.replay, "images/huygens_color")
    os.makedirs(od, exist_ok=True)
    for i in range(c["count"]):
        alt = c["alt_km"][i] if c["alt_km"][i] is not None else 0.0
        g = np.array(Image.open(os.path.join(a.replay, c["file_enh"][i])).convert("L"))
        Image.fromarray(tint(g, color_at(tab, alt if c["phase"][i] == "descent" else 0.0))).save(
            os.path.join(od, c["id"][i] + ".png"), optimize=True)

    m = json.load(open(os.path.join(a.replay, "mosaics/mosaics.json")))
    md = os.path.join(a.replay, "mosaics/color")
    os.makedirs(md, exist_ok=True)
    surf = color_at(tab, 0.0)
    for lv in m["levels"]:
        g = np.array(Image.open(os.path.join(a.replay, lv["file"])).convert("L"))
        Image.fromarray(tint(g, surf)).save(os.path.join(md, f"{lv['m_per_px']}m.png"), optimize=True)
    for alt in (140, 100, 60, 30, 10, 3, 1, 0):
        print(f"{alt:4d} km  sRGB of mid grey {tint(np.array([[150]], np.uint8), color_at(tab, alt))[0, 0]}")


if __name__ == "__main__":
    main()
