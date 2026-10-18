#!/usr/bin/env python3
"""
Place every DISR frame on the ground around the landing site, and render the
descent as a fly-down over Karkoschka's mosaic with each frame's footprint.

Camera model (DISR instrument catalog, Table 1): the long side of each frame
(256 px) runs in nadir angle, the short side in azimuth.

  HRI  nadir  6.5 - 21.5 deg, azimuth width  9.6 deg
  MRI  nadir 15.75 - 46.25 deg, azimuth width 21.1 deg
  SLI  nadir 45.2 - 96 deg,   azimuth width 25.6 deg

Row 0 of a processed (set E) frame is the smallest nadir angle; azimuth grows
to the right. The frame centre points at the label's azimuth from North plus
AZ_OFFSET. Both conventions and the offset were fitted against Karkoschka's
mosaics: over 16 HRI/MRI frames at 6-14 km the projected frames correlate with
the mosaic at r = 0.80 (median), against r <= 0.54 for any other convention.
Frame by frame (fit_r) the match is best for MRI at 1-14 km (median r 0.75-0.85)
and HRI at 6-14 km (0.47). Below 5 km HRI frames cover only a few hundred metres,
smaller than the error of the probe's position, so their footprints are
approximate; high SLI frames are dominated by haze.
The ground is a plane at the landing site (Titan's curvature is < 0.5% of the
distance within 60 deg of nadir below 30 km); the probe's horizontal position
comes from the DTWG descent table.

Painting the frames themselves into a map was tried and rejected: with only
the label attitude, frames from different altitudes disagree by tens of pixels
and the result is a radial patchwork. Karkoschka's mosaics fitted every frame's
attitude by hand and are the legible view; the per-frame geometry here is for
showing where each frame looked.

  python web/huygens/project_frames.py --replay <replay dir> [--movie out.mp4]

writes <replay>/catalog/huygens_projection.json: the camera model, and per
frame its nadir point, ground footprint outline (metres east/north of the
landing site) and how well the projected frame matches the mosaic (fit_r).
"""

import argparse
import json
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CAMS = {"HRI": (6.5, 21.5, 9.6), "MRI": (15.75, 46.25, 21.1), "SLI": (45.2, 96.0, 25.6)}
PIXEL_DEG = {"HRI": 0.06, "MRI": 0.12, "SLI": 0.20}
AZ_OFFSET = 4.0  # deg, fitted
MAX_NADIR = 65.0  # beyond this the side-looking frames are mostly haze
R_TITAN = 2575.0e3
SCALES = [60, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1]


class Replay:
    def __init__(self, root):
        self.root = root
        self.c = json.load(open(os.path.join(root, "catalog/huygens.json")))
        d = json.load(open(os.path.join(root, "huygens_descent.json")))
        self.d = d
        self.lat0 = d["landing_site"]["lat_deg"]
        self.lonw0 = d["landing_site"]["lon_w_deg"]
        self.et = np.array(d["et"])
        self.lat = np.array(d["lat_deg"])
        self.lonw = np.array(d["lon_w_deg"])
        self.alt = np.array(d["alt_km"]) * 1e3
        m = json.load(open(os.path.join(root, "mosaics/mosaics.json")))
        self.mcx, self.mcy = m["landing_px"]
        self.mos = {lv["m_per_px"]: np.array(Image.open(os.path.join(root, lv["file"]))).astype(np.float32)
                    for lv in m["levels"]}
        self.imgs = {}

    def nadir_xy(self, t):
        """Probe nadir in metres east and north of the landing site."""
        lat = np.interp(t, self.et, self.lat)
        lonw = np.interp(t, self.et, self.lonw)
        gy = (lat - self.lat0) * math.pi / 180 * R_TITAN
        gx = -(lonw - self.lonw0) * math.pi / 180 * R_TITAN * math.cos(math.radians(self.lat0))
        return gx, gy

    def frame(self, i):
        if i not in self.imgs:
            self.imgs[i] = np.array(Image.open(os.path.join(self.root, self.c["file_enh"][i])).convert("L")).astype(np.float32)
        return self.imgs[i]

    def usable(self, i):
        c = self.c
        return (c["cam"][i] in CAMS and c["et"][i] is not None and c["phase"][i] == "descent"
                and not ({"bad_time", "zero_exposure", "saturated", "half_frame"} & set(c["flags"][i])))

    def project(self, i, gx, gy):
        """Frame i sampled at ground points (gx east, gy north, metres). Returns values and a
        feather weight (0 outside the frame, rising to 1 a few pixels inside)."""
        c = self.c
        t0, t1, azw = CAMS[c["cam"][i]]
        img = self.frame(i)
        h_, w_ = img.shape
        px, py = self.nadir_xy(c["et"][i])
        h = c["alt_km"][i] * 1e3
        dx, dy = gx - px, gy - py
        th = np.degrees(np.arctan2(np.hypot(dx, dy), h))
        ph = np.degrees(np.arctan2(dx, dy))
        row = (th - t0) / (t1 - t0) * h_ - 0.5
        dphi = (ph - c["az_north_deg"][i] - AZ_OFFSET + 540) % 360 - 180
        col = w_ / 2 + dphi / azw * w_ - 0.5
        v = cv2.remap(img, col.astype(np.float32), row.astype(np.float32), cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_REPLICATE)
        # feather: distance (in frame pixels) to the nearest frame edge, ramped over 12 px
        e = np.minimum.reduce([row, h_ - 1 - row, col, w_ - 1 - col])
        wgt = np.clip(e / 12.0, 0, 1) * (th < MAX_NADIR)
        # ground size of one pixel, metres (radial direction, flat ground)
        gsd = math.radians(PIXEL_DEG[c["cam"][i]]) * h / np.cos(np.radians(np.minimum(th, 89))) ** 2
        return v, wgt.astype(np.float32), gsd.astype(np.float32)

    def mosaic(self, gx, gy, px):
        """Karkoschka mosaic at ground points, finest level with pixels >= px/2. NaN outside."""
        out = np.full(gx.shape, np.nan, np.float32)
        for s in SCALES:
            if s < px / 2 and not np.isnan(out).all():
                break
            mx = (self.mcx + gx / s).astype(np.float32)
            my = (self.mcy - gy / s).astype(np.float32)
            H, W = self.mos[s].shape
            inside = (mx >= 0) & (mx <= W - 1) & (my >= 0) & (my <= H - 1)
            v = cv2.remap(self.mos[s], mx, my, cv2.INTER_AREA if s < px else cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)
            out = np.where(inside, v, out)
        return out


def footprint(rp, i, n=8):
    """Ground outline of frame i (metres east, north of the landing site), clipped at MAX_NADIR."""
    c = rp.c
    t0, t1, azw = CAMS[c["cam"][i]]
    t1 = min(t1, MAX_NADIR)
    if t1 <= t0:
        return []
    h = c["alt_km"][i] * 1e3
    px, py = rp.nadir_xy(c["et"][i])
    az = c["az_north_deg"][i] + AZ_OFFSET
    edge = ([(t0, az + azw * (k / n - 0.5)) for k in range(n + 1)] +
            [(t0 + (t1 - t0) * k / n, az + azw / 2) for k in range(1, n + 1)] +
            [(t1, az + azw * (0.5 - k / n)) for k in range(1, n + 1)] +
            [(t1 - (t1 - t0) * k / n, az - azw / 2) for k in range(1, n)])
    pts = []
    for th, ph in edge:
        d = h * math.tan(math.radians(th))
        pts.append((px + d * math.sin(math.radians(ph)), py + d * math.cos(math.radians(ph))))
    return pts


def match_quality(rp, i):
    """Correlation of the projected frame with the mosaic where they overlap (None if < 400 px)."""
    c = rp.c
    h = c["alt_km"][i] * 1e3
    px, py = rp.nadir_xy(c["et"][i])
    rad = h * math.tan(math.radians(min(CAMS[c["cam"][i]][1], MAX_NADIR)))
    N = 200
    ys, xs = np.mgrid[0:N, 0:N]
    gx = px + (xs - N / 2) * 2 * rad / N
    gy = py - (ys - N / 2) * 2 * rad / N
    v, w, _ = rp.project(i, gx, gy)
    m = rp.mosaic(gx, gy, 2 * rad / N)
    ok = (w > 0.5) & ~np.isnan(m)
    if ok.sum() < 400 or v[ok].std() == 0 or m[ok].std() == 0:
        return None
    return float(np.corrcoef(v[ok], m[ok])[0, 1])


def write_json(rp, path):
    c = rp.c
    rows = {"id": [], "nadir_e_m": [], "nadir_n_m": [], "footprint_en_m": [], "fit_r": []}
    for i in range(c["count"]):
        if not rp.usable(i):
            continue
        px, py = rp.nadir_xy(c["et"][i])
        r = match_quality(rp, i)
        rows["id"].append(c["id"][i])
        rows["nadir_e_m"].append(round(float(px), 1))
        rows["nadir_n_m"].append(round(float(py), 1))
        rows["footprint_en_m"].append([[round(x, 1), round(y, 1)] for x, y in footprint(rp, i)])
        rows["fit_r"].append(None if r is None else round(r, 3))
    out = {"model": {"cams_nadir_min_max_azwidth_deg": CAMS, "pixel_deg": PIXEL_DEG,
                     "az_offset_deg": AZ_OFFSET, "max_nadir_deg": MAX_NADIR,
                     "rows": "row 0 = smallest nadir angle",
                     "cols": "azimuth increases to the right; centre = az_north_deg + az_offset_deg",
                     "ground": "plane through the landing site; x east, y north, metres"},
           **rows}
    json.dump(out, open(path, "w"))
    return rows


def to8(x, bg=36):
    out = np.clip(np.nan_to_num(x, nan=bg), 0, 255).astype(np.uint8)
    return out


CLAHE = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))


def local_contrast(img8, empty, bg=36):
    """Adaptive histogram equalisation for display, so dark plains and bright
    highlands both show their texture; empty areas stay flat grey."""
    fill = img8.astype(np.float32)
    if (~empty).sum() > 100:
        lo, hi = np.percentile(fill[~empty], [1, 99])
        fill = np.clip((fill - lo) / max(hi - lo, 1) * 255, 0, 255)
        fill[empty] = np.median(fill[~empty])
    fill = fill.astype(np.uint8)
    out = CLAHE.apply(fill)
    out[empty] = bg
    return out


CAM_COLOR = {"HRI": (255, 90, 60), "MRI": (255, 200, 40), "SLI": (80, 200, 255)}


def movie(rp, path, size=600, fps=24, seconds=50, end_alt=400.0):
    """Two panels: the newest raw frame (before) and Karkoschka's mosaic under the
    probe with the newest frames' footprints outlined (after)."""
    c = rp.c
    usable = sorted([i for i in range(c["count"]) if rp.usable(i)], key=lambda i: c["et"][i])
    ets = np.array([c["et"][i] for i in usable])
    a0 = rp.alt
    la = np.log(np.maximum(a0, 1.0))
    i_start = int(np.argmax(a0 < 140e3))
    i_end = int(np.argmax(a0 < end_alt))
    targets = np.linspace(la[i_start], la[i_end], fps * seconds)
    steps = [i_start + int(np.argmin(np.abs(la[i_start:i_end + 1] - t))) for t in targets]
    steps += [i_end] * (fps * 2)  # hold the last view
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 19)
    except OSError:
        font = big = ImageFont.load_default()
    feet = {j: footprint(rp, j) for j in usable}
    tmp = tempfile.mkdtemp()
    ys, xs = np.mgrid[0:size, 0:size]
    for k, s in enumerate(steps):
        t = rp.et[s]
        h = rp.alt[s]
        n = int(np.searchsorted(ets, t, side="right"))
        cx, cy = rp.nadir_xy(t)
        span = max(2.6 * h, 1200.0)
        px = span / size
        gx = cx + (xs - size / 2 + 0.5) * px
        gy = cy - (ys - size / 2 + 0.5) * px
        mos = rp.mosaic(gx, gy, px)
        p_mos = Image.fromarray(local_contrast(to8(mos), np.isnan(mos))).convert("RGB")
        dr = ImageDraw.Draw(p_mos)
        to_px = lambda e, nn: (size / 2 + (e - cx) / px, size / 2 - (nn - cy) / px)
        # the last few frames' footprints, newest brightest
        recent = usable[max(0, n - 4):n]
        for age, j in enumerate(reversed(recent)):
            pts = [to_px(e, nn) for e, nn in feet[j]]
            if len(pts) > 2:
                col = tuple(int(v * (1.0 - 0.25 * age)) for v in CAM_COLOR[c["cam"][j]])
                dr.line(pts + [pts[0]], fill=col, width=3 if age == 0 else 1)
        m = size / 2
        dr.line([m - 9, m, m + 9, m], fill=(255, 255, 255), width=1)
        dr.line([m, m - 9, m, m + 9], fill=(255, 255, 255), width=1)
        lx, ly = to_px(0.0, 0.0)
        if 0 <= lx < size and 0 <= ly < size:
            dr.ellipse([lx - 6, ly - 6, lx + 6, ly + 6], outline=(120, 255, 140), width=2)
        bar = 10 ** math.floor(math.log10(span / 4))
        bl = bar / px
        dr.line([size - 20 - bl, size - 16, size - 20, size - 16], fill=(255, 255, 255), width=3)
        dr.text((size - 20 - bl, size - 38), f"{bar / 1000:g} km" if bar >= 1000 else f"{bar:g} m",
                fill=(255, 255, 255), font=font)
        p_raw = Image.new("RGB", (size, size), (20, 20, 20))
        if n:
            j = usable[n - 1]
            fr = Image.open(os.path.join(rp.root, c["file_enh"][j])).convert("RGB")
            sc = (size - 50) / fr.height
            fr = fr.resize((int(fr.width * sc), size - 50), Image.BILINEAR)
            p_raw.paste(fr, ((size - fr.width) // 2, 12))
            ImageDraw.Draw(p_raw).text((14, size - 30), f"{c['id'][j]}  {c['cam'][j]}  taken at {c['alt_km'][j]:.2f} km",
                                       fill=CAM_COLOR[c["cam"][j]], font=font)
        frame = Image.new("RGB", (size * 2 + 12, size + 74), (0, 0, 0))
        frame.paste(p_raw, (0, 64))
        frame.paste(p_mos, (size + 12, 64))
        dr = ImageDraw.Draw(frame)
        atxt = f"{h / 1e3:.2f} km" if h >= 1000 else f"{h:.0f} m"
        dr.text((12, 8), f"Huygens descent   {rp.d['utc'][s][11:19]} UTC   altitude {atxt}",
                fill=(255, 255, 255), font=big)
        dr.text((12, 38), "before: newest DISR frame on its own", fill=(220, 220, 220), font=font)
        dr.text((size + 24, 38), f"after: the ground below, {span / 1e3:.1f} km across, outlines = frames", fill=(220, 220, 220), font=font)
        frame.save(os.path.join(tmp, f"{k:05d}.png"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                    os.path.join(tmp, "%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "20", path], check=True)
    return tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--movie")
    ap.add_argument("--seconds", type=int, default=50)
    a = ap.parse_args()
    rp = Replay(a.replay)
    rows = write_json(rp, os.path.join(a.replay, "catalog/huygens_projection.json"))
    rs = [r for r in rows["fit_r"] if r is not None]
    print(f"{len(rows['id'])} frames placed, {len(rs)} overlap the mosaic, median r {np.median(rs):.2f}")
    alt = {cid: rp.c["alt_km"][i] for i, cid in enumerate(rp.c["id"])}
    for lo, hi in ((0, 1), (1, 5), (5, 20), (20, 60), (60, 150)):
        sel = [r for cid, r in zip(rows["id"], rows["fit_r"]) if r is not None and lo <= alt[cid] < hi]
        if sel:
            print(f"  {lo:3d}-{hi:3d} km: {len(sel):3d} frames, median r {np.median(sel):.2f}")
    if a.movie:
        print("frames in", movie(rp, a.movie, seconds=a.seconds))


if __name__ == "__main__":
    main()
