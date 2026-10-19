#!/usr/bin/env python3
"""
Evidence figures and movie for the Huygens replay export.

  evidence/handover_before_after.png     raw SPK + DTWG stitch vs the blended track around entry interface
  evidence/trajectory_overview.png       probe and Cassini around Titan, descent profile with image times
  evidence/frames_raw_vs_processed.png   raw EDR next to the exported PNGs at six altitudes
  evidence/descent_movie.mp4 / .gif      every descent frame in time order, then the surface frames
  evidence/contact_sheet.jpg             all exported frames (shared stretch), plus contact_sheet_enh.jpg

Usage: python tools/make_evidence.py --root /Users/sam/Development/huygens-data
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import spiceypy as sp  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from build_huygens_track import Source, R_REF  # noqa: E402
from verify_huygens_track import Track  # noqa: E402

CAM_COLORS = {"SLI": "#1f77b4", "MRI": "#2ca02c", "HRI": "#d62728", "UHH": "#9467bd", "LHH": "#9467bd"}
TIFF_DIR = "raw/psa/DISR/HP-SSA-DISR-2-3-EDR-RDR-V1.3/DATA/IMAGER/TIFF_FORMAT"


def font(size):
    for f in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def utc_minutes(src, ets, ref):
    return (np.asarray(ets) - ref) / 60.0


def handover(src, tr, out):
    tE = src.t_ei
    ts = np.arange(tE - 1200, tE + 300, 1.0)
    titan = np.array([src.titan(t)[:3] for t in ts])
    raw = np.array([(src.spk_rel(t)[:3] if t < tE else src.spline(t)) for t in ts])
    blend = tr.at(ts) - titan
    alt = lambda p: np.linalg.norm(p, axis=1) - R_REF
    v_raw = np.linalg.norm(np.gradient(raw, ts, axis=0), axis=1)
    v_bl = np.linalg.norm(tr.at(ts, True) - np.array([src.titan(t)[3:] for t in ts]), axis=1)
    after = ts >= tE
    off_dtwg = np.full(len(ts), np.nan)
    off_dtwg[after] = np.linalg.norm(blend[after] - np.array([src.spline(t) for t in ts[after]]), axis=1)
    m = utc_minutes(src, ts, tE)

    fig, ax = plt.subplots(3, 2, figsize=(13, 10), sharex="col")
    for col, (lo, hi) in enumerate([(-20, 5), (-0.5, 0.5)]):
        k = (m >= lo) & (m <= hi)
        a = ax[0, col]
        a.plot(m[k], alt(raw)[k], color="#d62728", lw=1.5, label="before: SPK, then DTWG (raw stitch)")
        a.plot(m[k], alt(blend)[k], color="#1f77b4", lw=1.5, label="after: exported track (blended)")
        a.set_ylabel("altitude above 2575 km sphere (km)")
        a = ax[1, col]
        a.plot(m[k], v_raw[k], color="#d62728", lw=1.2, label="before")
        a.plot(m[k], v_bl[k], color="#1f77b4", lw=1.2, label="after")
        a.set_ylabel("Titan-relative speed (km/s)")
        if col == 0:
            a.set_ylim(min(v_bl[k].min(), 5.9), max(v_bl[k].max(), 6.1) + 0.05)
            a.text(0.02, 0.92, f"raw stitch speed spike: {v_raw.max():.1f} km/s (off scale)",
                   transform=a.transAxes, color="#d62728", fontsize=9)
        a = ax[2, col]
        kk = k & (ts < tE)
        a.plot(m[kk], np.linalg.norm(blend[kk] - raw[kk], axis=1), color="#1f77b4", lw=1.5,
               label="after minus SPK (fade-in of the offset)")
        kk = k & after
        a.plot(m[kk], off_dtwg[kk], color="#2ca02c", lw=1.5, label="after minus DTWG")
        a.set_ylabel("offset (km)")
        a.set_xlabel("minutes from entry interface (2005-01-14 09:05:52.5 UTC)")
        for r in ax[:, col]:
            r.axvline(0, color="k", lw=0.6, ls=":")
            if col == 0:
                r.axvline(-10, color="gray", lw=0.6, ls=":")
            r.grid(alpha=0.3)
        ax[0, col].set_title("20 minutes before to 5 after" if col == 0 else "zoom: 30 s either side")
    ax[0, 0].legend(loc="upper right", fontsize=9)
    ax[2, 0].legend(loc="upper left", fontsize=9)
    fig.suptitle(f"Huygens handover at entry interface: SPK and DTWG differ by {src.raw_jump_km:.1f} km "
                 f"({src.raw_dv_kms * 1000:.1f} m/s); the exported track fades the offset in over the last 10 minutes",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "handover_before_after.png"), dpi=130)
    plt.close(fig)


def overview(src, tr, cat, prof, out):
    fig = plt.figure(figsize=(16, 9))
    # Titan-centred J2000, projected on the plane of the probe's approach (x toward Titan at entry)
    ts = np.linspace(src.t_sep, src.t_land, 4000)
    titan = np.array([src.titan(t)[:3] for t in ts])
    probe = tr.at(ts) - titan
    cas = np.array([sp.spkpos("-82", t, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")[0] for t in ts]) - titan
    n = np.cross(probe[0], probe[-1]); n /= np.linalg.norm(n)
    e1 = probe[-1] / np.linalg.norm(probe[-1]); e2 = np.cross(n, e1)
    proj = lambda p: np.c_[p @ e1, p @ e2]
    t_img_end = sp.str2et("2005-01-14T12:46:15")
    for i, (t_a, t_b, title) in enumerate([(src.t_sep, src.t_land, "separation (2004-12-25 02:00) to landing, Titan-centred km"),
                                           (src.t_land - 6 * 3600, t_img_end, "6 h before landing to end of surface imaging (12:46)")]):
        a = fig.add_subplot(2, 2, 1 + 2 * i)
        tt = np.linspace(t_a, t_b, 3000)
        tit = np.array([src.titan(t)[:3] for t in tt])
        P = proj(tr.at(tt) - tit)
        C = proj(np.array([sp.spkpos("-82", t, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")[0] for t in tt]) - tit)
        a.plot(C[:, 0], C[:, 1], color="#ff7f0e", lw=1, label="Cassini")
        a.plot(P[:, 0], P[:, 1], color="#1f77b4", lw=1.2, label="Huygens")
        a.add_patch(plt.Circle((0, 0), R_REF, color="#c8a04a", alpha=0.8, label="Titan"))
        a.plot(*P[0], "o", color="#1f77b4", ms=5); a.plot(*C[0], "o", color="#ff7f0e", ms=5)
        a.plot(*C[-1], "s", color="#ff7f0e", ms=5)
        a.annotate("separation" if i == 0 else "T-6 h", P[0], fontsize=8, xytext=(5, 5), textcoords="offset points")
        a.annotate("Cassini at " + ("landing" if i == 0 else "12:46"), C[-1], fontsize=8, xytext=(5, -12), textcoords="offset points")
        a.set_aspect("equal", adjustable="datalim"); a.grid(alpha=0.3); a.set_title(title, fontsize=10)
        a.legend(fontsize=8, loc="best")
        a.set_xlabel("km (x toward the landing point)"); a.set_ylabel("km")
    a = fig.add_subplot(1, 2, 2)
    t0 = sp.str2et("2005-01-14T09:00:00")
    m = (np.array(prof["et"]) - t0) / 60
    a.plot(m, prof["alt_km"], color="k", lw=1.2, label="DTWG V2.0 altitude")
    et = np.array([e if e is not None else np.nan for e in cat["et"]])
    alt = np.array(cat["alt_km"], dtype=float)
    for cam in ("SLI", "MRI", "HRI", "UHH"):
        k = np.array([c == cam or (cam == "UHH" and c == "LHH") for c in cat["cam"]]) & np.isfinite(et)
        a.scatter((et[k] - t0) / 60, alt[k], s=10,
                  color=CAM_COLORS[cam], label=f"{cam if cam != 'UHH' else 'UHH/LHH'} frames ({k.sum()})", zorder=3)
    a.set_xlabel("minutes after 2005-01-14 09:00 UTC"); a.set_ylabel("altitude (km)")
    a.set_ylim(-5, 160); a.grid(alpha=0.3)
    land = (sp.str2et("2005-01-14T11:38:10.769") - t0) / 60
    a.axvline(land, color="gray", ls=":"); a.text(land + 1, 140, "landing 11:38:10", fontsize=9, color="gray")
    a.set_title("descent profile with every DISR frame (surface frames continue to 12:46 at 0 km)", fontsize=10)
    a.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "trajectory_overview.png"), dpi=120)
    plt.close(fig)


def raw_vs_processed(root, cat, out):
    targets = [140, 80, 40, 20, 8, 1.5]
    ok = [i for i, (c, f) in enumerate(zip(cat["cam"], cat["flags"])) if c == "HRI" and not f and cat["phase"][i] == "descent"]
    pick = [min(ok, key=lambda i: abs(cat["alt_km"][i] - t)) for t in targets]
    fig, ax = plt.subplots(3, 6, figsize=(15, 11))
    for j, i in enumerate(pick):
        seq = int(cat["id"][i][5:])
        raw = np.array(Image.open(glob.glob(os.path.join(root, TIFF_DIR, f"*/TIFIMG_{seq:04d}_*.TIF"))[0])).astype(float)[::-1]
        lo, hi = np.percentile(raw, [0.5, 99.5])
        ax[0, j].imshow(np.clip((raw - lo) / (hi - lo), 0, 1), cmap="gray", vmin=0, vmax=1)
        ax[1, j].imshow(Image.open(os.path.join(root, "replay", cat["file"][i])), cmap="gray", vmin=0, vmax=255)
        ax[2, j].imshow(Image.open(os.path.join(root, "replay", cat["file_enh"][i])), cmap="gray", vmin=0, vmax=255)
        ax[0, j].set_title(f"{cat['id'][i]}  {cat['alt_km'][i]:.1f} km\n{cat['utc'][i][11:19]} UTC", fontsize=10)
        for r in range(3):
            ax[r, j].set_xticks([]); ax[r, j].set_yticks([])
    ax[0, 0].set_ylabel("raw EDR (TIFF, flipped\nup/down, own stretch)")
    ax[1, 0].set_ylabel("exported: set E, DN/ms,\nshared HRI stretch")
    ax[2, 0].set_ylabel("exported _enh: set E,\nper-frame stretch")
    fig.suptitle("HRI frames at six altitudes: raw EDR vs exported PNGs. The shared stretch keeps the real "
                 "brightness drop with altitude; the _enh set shows the surface detail", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "frames_raw_vs_processed.png"), dpi=110)
    plt.close(fig)


def movie(root, cat, out):
    W, H, S = 720, 660, 2
    f_big, f_small = font(26), font(18)
    order = [i for i in range(len(cat["id"])) if "bad_time" not in cat["flags"][i] and "zero_exposure" not in cat["flags"][i]]
    order.sort(key=lambda i: (cat["phase"][i] != "descent", cat["et"][i]))
    tmp = tempfile.mkdtemp(dir=out)
    for n, i in enumerate(order):
        im = Image.open(os.path.join(root, "replay", cat["file_enh"][i]))
        im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
        fr = Image.new("RGB", (W, H), (12, 12, 16))
        fr.paste(im.convert("RGB"), ((W - im.width) // 2, 104))
        d = ImageDraw.Draw(fr)
        alt = cat["alt_km"][i]
        alt_s = f"{alt:7.2f} km" if alt >= 1 else f"{alt * 1000:5.0f} m"
        d.text((20, 18), f"{cat['utc'][i][:10]}  {cat['utc'][i][11:21]} UTC", font=f_big, fill=(235, 235, 235))
        d.text((20, 56), f"{'SURFACE' if cat['phase'][i] == 'surface' else 'altitude ' + alt_s}", font=f_big,
               fill=(255, 200, 90))
        d.text((W - 260, 22), f"{cat['cam'][i]}  {cat['id'][i]}", font=f_small, fill=CAM_COLORS.get(cat["cam"][i], "#ccc"))
        flags = [f for f in cat["flags"][i] if f in ("saturated", "half_frame")]
        if flags:
            d.text((W - 260, 50), ", ".join(flags), font=f_small, fill=(200, 120, 120))
        d.text((20, H - 30), "Huygens DISR, Karkoschka set E, per-frame stretch", font=f_small, fill=(130, 130, 140))
        fr.save(os.path.join(tmp, f"f{n:05d}.png"))
    mp4 = os.path.join(out, "descent_movie.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "10", "-i", os.path.join(tmp, "f%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", mp4], check=True)
    gif = os.path.join(out, "descent_movie.gif")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "10", "-i", os.path.join(tmp, "f%05d.png"),
                    "-vf", "scale=360:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse",
                    gif], check=True)
    shutil.rmtree(tmp)
    return len(order)


def contact(root, cat, out, key, name):
    order = sorted(range(len(cat["id"])), key=lambda i: (cat["et"][i] is None, cat["et"][i] or 0))
    tw, th, cols = 64, 112, 32
    rows = (len(order) + cols - 1) // cols
    sheet = Image.new("L", (cols * (tw + 2), rows * (th + 2)), 40)
    for n, i in enumerate(order):
        im = Image.open(os.path.join(root, "replay", cat[key][i]))
        im.thumbnail((tw, th))
        sheet.paste(im, ((n % cols) * (tw + 2), (n // cols) * (th + 2)))
    sheet.save(os.path.join(out, name), quality=88)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    out = os.path.join(root, "evidence")
    os.makedirs(out, exist_ok=True)
    src = Source(root)
    tr = Track([os.path.join(root, f"replay/tracks/huygens/{y}.bin") for y in (2004, 2005)])
    cat = json.load(open(os.path.join(root, "replay/catalog/huygens.json")))
    prof = json.load(open(os.path.join(root, "replay/huygens_descent.json")))
    only = set(filter(None, args.only.split(",")))
    run = lambda k: not only or k in only
    if run("handover"): handover(src, tr, out); print("handover_before_after.png")
    if run("overview"): overview(src, tr, cat, prof, out); print("trajectory_overview.png")
    if run("frames"): raw_vs_processed(root, cat, out); print("frames_raw_vs_processed.png")
    if run("movie"): print("movie frames:", movie(root, cat, out))
    if run("contact"):
        contact(root, cat, out, "file", "contact_sheet.jpg")
        contact(root, cat, out, "file_enh", "contact_sheet_enh.jpg")
        print("contact sheets")


if __name__ == "__main__":
    main()
