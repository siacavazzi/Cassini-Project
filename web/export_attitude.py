#!/usr/bin/env python3
"""
Export Cassini's pointing for the browser replay. Needs the CK kernels, so it runs where the
full archive is (the LaCie zip), one year at a time to keep disk use small.

  python web/export_attitude.py --zip /Volumes/LaCie/cassiniprojectJAN05.zip \
      --catalog <replay_data>/catalog --out <replay_data> --tmp /Volumes/LaCie/attitude_tmp

Writes attitude/<year>.bin:
  16-byte header: b"CATT", uint16 version (1), uint16 flags (0), uint32 n_images, uint32 n_background
  float32 image_q[4*n_images]   camera pointing at each image's mid-time, in catalog/<year>.json order
  float64 bg_t[n_background]    ephemeris time of each background sample (every 10 minutes)
  float32 bg_q[4*n_background]  spacecraft body attitude (CASSINI_SC_COORD) at those times
Quaternions are SPICE style (w, x, y, z) for the rotation J2000 -> frame; NaN where the CK has no data.

With --refine, years already exported (header flags 0) get extra background samples wherever the
browser's slerp between neighbouring samples (images and background merged, as tracks.js does it)
misses SPICE by more than --tol degrees; intervals are halved down to MIN_STEP. The file keeps its
layout (bg_t just stops being evenly spaced) and gets header flags 1, so a rerun skips it.

With --update-from <old dir> --old-catalog <old catalog dir>, years whose catalog changed are
rebuilt from the old file instead of from scratch: image quaternions are reused by image id
(for images whose mid-time no other image shares), only the rest are pointed, and the old (already refined) background samples are kept. The
file is written with flags 0, so a following --refine pass checks the merged series again.

With --smith (after --refine), the AACS reconstructed pointing is corrected wherever the image-navigated
("c-smithed", iss_ck/*_ISS.bc) CKs disagree with it. Those CKs only cover a fraction of a second around
each shutter, so outside them SPICE falls back to the AACS CK, which in a few places is badly off (in
23-27 Jan 2001 by ~50 deg: the frames show Jupiter while the AACS CK points the camera far from it).
Every image inside a c-smithed window is an anchor: the rotation from the AACS attitude to the smithed one
there is its offset (offsets under --smith-tol count as none). Background samples and images outside the
windows get the offset slerped between the anchors either side, or the nearer anchor's offset when only
one is within SMITH_REACH. The file keeps its layout and gets header flags 2, so a rerun skips it.
"""

import argparse
import gzip
import json
import os
import re
import shutil
import struct
import zipfile

import numpy as np
import spiceypy as sp

FRAMES = {"N": "CASSINI_ISS_NAC", "W": "CASSINI_ISS_WAC"}
# camera -> CASSINI_SC_COORD, from cas_v41.tf (same numbers as CAM_TO_BODY in tracks.js)
CAM_TO_BODY = {"N": np.array([0.50047271, 0.5002705, 0.49981488, -0.49944126]),
               "W": np.array([0.50048319, 0.4997469, 0.5001258, -0.49964368])}
GAP_S = 3600.0   # tracks.js holds instead of slerping across longer gaps
MIN_STEP = 8.0   # do not split intervals shorter than this (s)
FLAG_REFINED = 1
FLAG_SMITHED = 2
SMITH_REACH = 6 * 3600.0   # an anchor's offset is carried this far (s)
PREFIX = "cassini/cosp_1000/"


def kernels_for_year(z, year):
    names = [n for n in z.namelist() if re.match(rf"{PREFIX}index/cas_{year}(_iss)?_v\d+\.tm$", n)]
    if not names:
        return []
    text = z.read(sorted(names)[-1]).decode()
    keep = ("lsk", "sclk", "fk", "pck", "ck", "iss_ck")
    return [k for k in re.findall(r"\$KERNELS/(\S+?)'", text) if k.split("/")[0] in keep]


def quat(frame, et):
    try:
        return sp.m2q(sp.pxform("J2000", frame, et))
    except Exception:
        return [np.nan] * 4


def qmul(a, b):
    """SPICE qxq: the rotation "b, then a"."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw])


def slerp(a, b, u):
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9999:
        q = (1 - u) * a + u * b
    else:
        th = np.arccos(min(1.0, d))
        q = (np.sin((1 - u) * th) * a + np.sin(u * th) * b) / np.sin(th)
    return q / np.linalg.norm(q)


def qangle(a, b):
    """Rotation angle between two attitudes, degrees. Chord form: arccos of a dot product near 1 turns
    float32 rounding into ~0.05 deg of fake error."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    d = min(np.linalg.norm(a - b), np.linalg.norm(a + b))
    return np.degrees(4 * np.arcsin(min(1.0, d / 2)))


def refine(times, quats, truth, tol_deg):
    """Extra (t, q) samples so slerp between neighbours stays within tol_deg of truth(t).

    times/quats: the merged, time-sorted series the browser interpolates. truth(t) returns the
    SPICE body quaternion or None. Intervals longer than GAP_S are left alone (the browser holds there).
    """
    extra = []
    stack = [(times[i], quats[i], times[i + 1], quats[i + 1]) for i in range(len(times) - 1)
             if 0 < times[i + 1] - times[i] <= GAP_S]
    while stack:
        t0, q0, t1, q1 = stack.pop()
        if t1 - t0 < 2 * MIN_STEP:
            continue
        worst, mid = 0.0, None
        for u in (0.25, 0.5, 0.75):
            q = truth(t0 + u * (t1 - t0))
            if q is None:
                worst = 0.0
                break
            err = qangle(slerp(q0, q1, u), q)
            if err > worst:
                worst = err
            if u == 0.5:
                mid = q
        if worst > tol_deg and mid is not None:
            tm = 0.5 * (t0 + t1)
            extra.append((tm, mid))
            stack.append((t0, q0, tm, mid))
            stack.append((tm, mid, t1, q1))
    return extra


def qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def smith_offsets(anchor_t, anchor_d, times):
    """Offset rotation at each of times from the anchors (sorted times, offsets as quaternions); None = none."""
    out = []
    n = len(anchor_t)
    for t in times:
        j = int(np.searchsorted(anchor_t, t, "right"))   # anchors j-1 (<= t) and j (> t)
        a = j - 1 if j > 0 and t - anchor_t[j - 1] <= SMITH_REACH else None
        b = j if j < n and anchor_t[j] - t <= SMITH_REACH else None
        if a is not None and b is not None:
            da, db = anchor_d[a], anchor_d[b]
            if da is None and db is None:
                out.append(None)
                continue
            ident = np.array([1.0, 0, 0, 0])
            u = (t - anchor_t[a]) / (anchor_t[b] - anchor_t[a]) if anchor_t[b] > anchor_t[a] else 0.0
            out.append(slerp(ident if da is None else da, ident if db is None else db, u))
        elif a is not None or b is not None:
            out.append(anchor_d[a if b is None else b if a is None else
                                (a if t - anchor_t[a] <= anchor_t[b] - t else b)])
        else:
            out.append(None)
    return out


def smith(img_q, cams, ets, smithed, rc_body, bg_t, bg_q, tol_deg, bg_smithed=None):
    """Correct AACS pointing with the c-smithed anchors. smithed[i]: image i lies in a c-smithed window;
    bg_smithed[k]: background sample k does (--refine samples there came from the smithed CK already);
    rc_body(t): the AACS-only body quaternion. Returns new (img_q, bg_q) and the anchors' offsets (deg)."""
    img_q, bg_q = np.array(img_q, dtype=float), np.array(bg_q, dtype=float)
    at, ad, angles = [], [], []
    for i in np.argsort(ets, kind="stable"):
        if not smithed[i] or np.isnan(img_q[i, 0]):
            continue
        rc = rc_body(ets[i])
        if rc is None:
            continue
        d = qmul(qmul(CAM_TO_BODY[cams[i]], img_q[i]), qconj(rc))
        d = d / np.linalg.norm(d) * (1 if d[0] >= 0 else -1)
        ang = qangle(d, [1, 0, 0, 0])
        if at and ets[i] == at[-1]:
            continue
        at.append(ets[i])
        ad.append(d if ang >= tol_deg else None)
        angles.append(ang)
    if not any(d is not None for d in ad):
        return img_q, bg_q, angles
    at = np.array(at)
    for k, d in enumerate(smith_offsets(at, ad, bg_t)):
        if d is not None and not (bg_smithed is not None and bg_smithed[k]):
            bg_q[k] = qmul(d, bg_q[k])
    loose = [i for i in range(len(ets)) if not smithed[i] and not np.isnan(img_q[i, 0])]
    for i, d in zip(loose, smith_offsets(at, ad, [ets[i] for i in loose])):
        if d is not None:
            c = CAM_TO_BODY[cams[i]]
            img_q[i] = qmul(qconj(c), qmul(d, qmul(c, img_q[i])))
    return img_q, bg_q, angles


def merged_series(img_q, cat, bg_t, bg_q):
    """The series tracks.js builds: background samples plus pointed images turned into body pointing."""
    ts, qs = list(bg_t), [np.array(q, dtype=float) for q in bg_q]
    for q, et, cam in zip(img_q, cat["et"], cat["cam"]):
        if np.isnan(q[0]):
            continue
        ts.append(et)
        qs.append(qmul(CAM_TO_BODY[cam], np.array(q, dtype=float)))
    order = np.argsort(ts, kind="stable")
    t_out, q_out = [], []
    for i in order:
        if t_out and ts[i] == t_out[-1]:
            continue
        q = qs[i] / np.linalg.norm(qs[i])
        if q_out and np.dot(q, q_out[-1]) < 0:
            q = -q
        t_out.append(ts[i])
        q_out.append(q)
    return t_out, q_out


def refine_file(path, cat, tol_deg):
    raw = open(path, "rb").read()
    _, ver, flags, n_img, n_bg = struct.unpack("<4sHHII", raw[:16])
    if flags & FLAG_REFINED:
        return None
    img_q = np.frombuffer(raw, "<f4", 4 * n_img, 16).reshape(-1, 4)
    bg_t = np.frombuffer(raw, "<f8", n_bg, 16 + 16 * n_img)
    bg_q = np.frombuffer(raw, "<f4", 4 * n_bg, 16 + 16 * n_img + 8 * n_bg).reshape(-1, 4)
    times, quats = merged_series(img_q, cat, bg_t, bg_q)

    def truth(t):
        q = quat("CASSINI_SC_COORD", t)
        return None if np.isnan(q[0]) else np.array(q, dtype=float)

    extra = refine(times, quats, truth, tol_deg)
    t_all = np.concatenate([bg_t, np.array([t for t, _ in extra], dtype="<f8")])
    q_all = np.concatenate([bg_q, np.array([q for _, q in extra], dtype="<f4").reshape(-1, 4)])
    order = np.argsort(t_all, kind="stable")
    t_all, q_all = t_all[order].astype("<f8"), q_all[order].astype("<f4")
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(b"CATT" + struct.pack("<HHII", ver, flags | FLAG_REFINED, n_img, len(t_all)))
        fh.write(img_q.tobytes())
        fh.write(t_all.tobytes())
        fh.write(q_all.tobytes())
    os.replace(tmp_path, path)
    return len(extra)


def smith_file(path, cat, iss_cks, tol_deg):
    """Apply smith() to an exported year; the full kernel set must be loaded, iss_cks are unloaded here."""
    raw = open(path, "rb").read()
    _, ver, flags, n_img, n_bg = struct.unpack("<4sHHII", raw[:16])
    if flags & FLAG_SMITHED:
        return None
    img_q = np.frombuffer(raw, "<f4", 4 * n_img, 16).reshape(-1, 4)
    bg_t = np.frombuffer(raw, "<f8", n_bg, 16 + 16 * n_img)
    bg_q = np.frombuffer(raw, "<f4", 4 * n_bg, 16 + 16 * n_img + 8 * n_bg).reshape(-1, 4)
    cover = []
    for k in iss_cks:
        for obj in sp.ckobj(k):
            win = sp.ckcov(k, obj, False, "INTERVAL", 0.0, "TDB")
            cover += [sp.wnfetd(win, j) for j in range(sp.wncard(win))]
    cover.sort()
    lo, hi = np.array([c[0] for c in cover]), np.array([c[1] for c in cover])
    ets = np.asarray(cat["et"], dtype=float)
    j = np.searchsorted(lo, ets, "right") - 1
    smithed = (j >= 0) & (ets <= hi[np.maximum(j, 0)]) if len(cover) else np.zeros(len(ets), bool)
    jb = np.searchsorted(lo, bg_t, "right") - 1
    bg_smithed = (jb >= 0) & (bg_t <= hi[np.maximum(jb, 0)]) if len(cover) else np.zeros(len(bg_t), bool)
    for k in iss_cks:
        sp.unload(k)

    def rc_body(t):
        q = quat("CASSINI_SC_COORD", t)
        return None if np.isnan(q[0]) else np.array(q, dtype=float)

    new_img, new_bg, angles = smith(img_q, cat["cam"], ets, smithed, rc_body, bg_t, bg_q, tol_deg, bg_smithed)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(b"CATT" + struct.pack("<HHII", ver, flags | FLAG_SMITHED, n_img, n_bg))
        fh.write(new_img.astype("<f4").tobytes())
        fh.write(bg_t.astype("<f8").tobytes())
        fh.write(new_bg.astype("<f4").tobytes())
    os.replace(tmp_path, path)
    angles = np.array(angles)
    return {"anchors": len(angles), "corrected": int((angles >= tol_deg).sum()),
            "worst_deg": float(angles.max()) if len(angles) else 0.0,
            "bg_changed": int((np.abs(new_bg - bg_q) > 1e-6).any(axis=1).sum()),
            "img_changed": int((np.abs(new_img - img_q) > 1e-6).any(axis=1).sum())}


def load_catalog(path):
    if os.path.exists(path):
        return json.load(open(path))
    if os.path.exists(path + ".gz"):
        return json.load(gzip.open(path + ".gz"))
    return {"id": [], "et": [], "cam": []}


def update_file(old_path, old_cat, new_cat, out_path, point, check=50):
    """Rewrite old_path for new_cat, reusing image quaternions by id; point(et, cam) supplies the rest."""
    raw = open(old_path, "rb").read()
    _, ver, _, n_img, n_bg = struct.unpack("<4sHHII", raw[:16])
    if n_img != len(old_cat["id"]):
        raise ValueError(f"{old_path}: {n_img} images but the old catalog has {len(old_cat['id'])}")
    img_q = np.frombuffer(raw, "<f4", 4 * n_img, 16).reshape(-1, 4)
    bg = raw[16 + 16 * n_img:]
    # frames that share a mid-time with another frame can sit in either order depending on the machine
    # that wrote the old catalog, so only images with a unique time are reused; the rest are re-pointed
    seen = {}
    for et in old_cat["et"]:
        seen[et] = seen.get(et, 0) + 1
    old_ix = {i: k for k, i in enumerate(old_cat["id"]) if seen[old_cat["et"][k]] == 1}
    new_q = np.empty((len(new_cat["id"]), 4), dtype="<f4")
    fresh = 0
    for k, (i, et, cam) in enumerate(zip(new_cat["id"], new_cat["et"], new_cat["cam"])):
        j = old_ix.get(i)
        if j is not None and old_cat["et"][j] == et and old_cat["cam"][j] == cam:
            new_q[k] = img_q[j]
        else:
            new_q[k] = point(et, cam)
            fresh += 1
    # the old file must really be in old_cat's order: re-point a sample of reused images and compare
    reused = [k for k, i in enumerate(new_cat["id"]) if i in old_ix and not np.isnan(new_q[k, 0])]
    rng = np.random.default_rng(0)
    for k in rng.choice(reused, size=min(check, len(reused)), replace=False) if check and reused else []:
        q = np.array(point(new_cat["et"][k], new_cat["cam"][k]), dtype=float)
        if not np.isnan(q[0]) and qangle(q, new_q[k].astype(float)) > 0.01:
            raise ValueError(f"{old_path}: image {new_cat['id'][k]} pointing differs from SPICE; "
                             "the old catalog is not the one this file was made from")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(b"CATT" + struct.pack("<HHII", ver, 0, len(new_q), n_bg))
        fh.write(new_q.tobytes())
        fh.write(bg)
    os.replace(tmp_path, out_path)
    return fresh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--years", default="1997-2017")
    ap.add_argument("--refine", action="store_true", help="add samples where slerp misses SPICE (existing files)")
    ap.add_argument("--tol", type=float, default=0.1, help="refinement tolerance, degrees")
    ap.add_argument("--smith", action="store_true", help="correct AACS pointing with the c-smithed ISS CKs (existing files, after --refine)")
    ap.add_argument("--smith-tol", type=float, default=0.5, help="smaller c-smithed offsets count as none, degrees")
    ap.add_argument("--update-from", help="attitude dir from an earlier export, to reuse for changed catalogs")
    ap.add_argument("--old-catalog", help="the catalog dir that earlier export was made from")
    args = ap.parse_args()
    y0, y1 = (int(x) for x in args.years.split("-"))
    z = zipfile.ZipFile(args.zip)
    members = set(z.namelist())
    os.makedirs(os.path.join(args.out, "attitude"), exist_ok=True)

    for year in range(y0, y1 + 1):
        path = os.path.join(args.out, "attitude", f"{year}.bin")
        cat_path = os.path.join(args.catalog, f"{year}.json")
        if args.update_from:
            old_path = os.path.join(args.update_from, f"{year}.bin")
            if os.path.exists(path) or not os.path.exists(old_path):
                continue
            old_cat, new_cat = load_catalog(os.path.join(args.old_catalog, f"{year}.json")), load_catalog(cat_path)
            if all(old_cat[f] == new_cat[f] for f in ("id", "et", "cam")):
                shutil.copy(old_path, path)
                print(f"{year}: catalog unchanged, copied", flush=True)
                continue
        elif os.path.exists(path) and not (args.refine or args.smith):
            continue
        if args.refine and (not os.path.exists(path) or struct.unpack("<H", open(path, "rb").read(8)[6:8])[0] & FLAG_REFINED):
            continue
        if args.smith and (not os.path.exists(path) or struct.unpack("<H", open(path, "rb").read(8)[6:8])[0] & FLAG_SMITHED):
            continue
        kernels = kernels_for_year(z, year)
        if not kernels:
            continue
        tmp = os.path.join(args.tmp, str(year))
        os.makedirs(tmp, exist_ok=True)
        sp.kclear()
        for k in kernels:
            src = PREFIX + "data/" + k
            if src not in members:
                print(f"  missing {k}")
                continue
            dst = os.path.join(tmp, os.path.basename(k))
            if not os.path.exists(dst):
                with z.open(src) as fin, open(dst, "wb") as fout:
                    shutil.copyfileobj(fin, fout, 1 << 24)
            sp.furnsh(dst)

        cat = load_catalog(cat_path)

        if args.update_from:
            n = update_file(old_path, old_cat, cat, path, lambda et, cam: quat(FRAMES[cam], et))
            print(f"{year}: {len(cat['id'])} images, {n} newly pointed, background kept "
                  f"({os.path.getsize(path) / 1e6:.1f} MB)", flush=True)
            sp.kclear()
            shutil.rmtree(tmp, ignore_errors=True)
            continue

        if args.smith:
            iss = [os.path.join(tmp, os.path.basename(k)) for k in kernels if k.startswith("iss_ck/")]
            r = smith_file(path, cat, [k for k in iss if os.path.exists(k)], args.smith_tol)
            print(f"{year}: smithed, {r}", flush=True)
            sp.kclear()
            shutil.rmtree(tmp, ignore_errors=True)
            continue

        if args.refine:
            n = refine_file(path, cat, args.tol)
            print(f"{year}: refined, {n} samples added ({os.path.getsize(path) / 1e6:.1f} MB)", flush=True)
            sp.kclear()
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        img_q = np.array([quat(FRAMES[c], et) for et, c in zip(cat["et"], cat["cam"])], dtype="<f4").reshape(-1, 4)

        a = sp.str2et(f"{year}-01-01T00:00:00")
        b = sp.str2et(f"{year + 1}-01-01T00:00:00")
        bg_t = np.arange(a, b, 600.0)
        bg_q = np.array([quat("CASSINI_SC_COORD", t) for t in bg_t], dtype="<f4")
        ok = ~np.isnan(bg_q[:, 0])
        bg_t, bg_q = bg_t[ok].astype("<f8"), bg_q[ok]

        with open(path, "wb") as fh:
            fh.write(b"CATT" + struct.pack("<HHII", 1, 0, len(img_q), len(bg_t)))
            fh.write(img_q.tobytes())
            fh.write(bg_t.tobytes())
            fh.write(bg_q.tobytes())
        good = int((~np.isnan(img_q[:, 0])).sum()) if len(img_q) else 0
        print(f"{year}: {good}/{len(img_q)} images pointed, {len(bg_t)} background samples, "
              f"{os.path.getsize(path) / 1e6:.1f} MB", flush=True)
        sp.kclear()
        shutil.rmtree(tmp, ignore_errors=True)  # exFAT ._ AppleDouble files vanish mid-delete


if __name__ == "__main__":
    main()
