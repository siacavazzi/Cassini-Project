#!/usr/bin/env python3
"""
Lightning on Saturn: the passes where Cassini's camera caught flashes, as Moments, and an enhanced view of their
pictures that makes the flashes plain (Sam 2026-11-16).

Where the flashes are comes from the published list, not from a search here: Dyudina, Ingersoll, Ewald, Porco,
Fischer and Yair 2013, "Saturn's visible lightning, its radio emissions, and the structure of the 2009-2011 lightning
storms", Icarus 226, 1020-1037, Table A1 (open copy https://authors.library.caltech.edu/records/y7mpy-9dw16),
transcribed in web/replay/lightning_flashes.csv. Where the paper gives two estimates of one 2011 flash (two
backgrounds), the row holds their average, as the paper uses. Its one green-filter flash (2011-065T19:05), which the
paper calls highly controversial, is left out. The 2009-229 images are listed there as their _5 versions; the
archive holds the same exposures as _1.

Two views, one rule each, for every picture of a lightning pass (no picture is tuned by hand):

  night  flashes lit the night side, otherwise lit only faintly by the rings. The picture's black and white are set
         from Saturn's night side in the storm's band of latitude (STORM_BAND degrees either side of the flashes),
         so the dim cloud and the flashes fill the range; the site's look sets them from the whole frame, where
         the sunlit rings make white, and the flashes stay a faint smudge.
  day    flashes on the sunlit storm are a few percent over the clouds. The picture is shown as usual, and over it
         what is brighter than in both pictures taken just before and after (same filter): each neighbour is redrawn
         onto this picture by SPICE (reproject.surface_points / canvas_points: the planet turns about 6 degrees in 10
         minutes), its few-pixel pointing error and the clouds' slow drift taken out by a smooth optical flow (a
         window several times a flash), and the smooth change in lighting by a wide blur. Marks on the camera itself (dust rings), which stay put on the
         detector and so look new after redrawing, are found as the spots that do so in many of the pass's pictures
         (fixed_spots) and left out. What stays brighter than
         both neighbours by about DAY_SIGMA times the noise or more is tinted warm. Clouds that change in only one
         neighbour drop out; some cloud edges remain, which is why the flashes are marked.

Markers: each listed flash, placed on its picture by SPICE from its latitude and longitude.

Pictures are calibrated by the pipeline (calibration.calibrate) from the archive's stored codes, and placed by
bootleg_autonav.find_target, as every other picture. Output, into the frame server's cache:
  <cache>/<folder()>/<ID>.webp   the enhanced picture, 1024 px (the frame's own pixels, scaled up)
  <cache>/<folder()>/lightning.json  the passes, their pictures, times, views and markers
which the frame server sends as they are (/frames/lightning.json, /frames/lightning/<ID>.webp): nothing is worked out
at request time. A made picture is not made again.

  python web/frames/lightning.py moments          writes web/replay/lightning_moments.csv
  python web/frames/lightning.py build --cache C  (or prebuild.py lightning --cache C) makes the pictures
"""
import argparse
import contextlib
import csv
import datetime
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPLAY = os.path.join(ROOT, "web", "replay")
FLASHES = os.path.join(REPLAY, "lightning_flashes.csv")
MOMENTS_OUT = os.path.join(REPLAY, "lightning_moments.csv")
LIGHTNING_VERSION = "lightning-v1"


def folder():
    """The cache folder's name: LIGHTNING_VERSION and the processed frames' version, which is bumped whenever the
    calibration changes (frame_server.PROC_VERSIONS), so a calibration change makes these pictures again too."""
    import frame_server
    return f"{LIGHTNING_VERSION}-{frame_server.PROC_VERSIONS['balanced']}"
SOURCE = {"title": "Dyudina et al. 2013, Saturn's visible lightning, its radio emissions, and the structure of the "
                   "2009-2011 lightning storms, Icarus 226, Table A1",
          "url": "https://doi.org/10.1016/j.icarus.2013.07.013",
          "open_copy": "https://authors.library.caltech.edu/records/y7mpy-9dw16"}

PAD = 20 * 60          # s: pictures this long before the first and after the last flash of a pass are shown too
GAP = 24 * 3600        # s: flashes closer than this are one moment
STORM_BAND = 5.0       # degrees of latitude either side of a pass's flashes that set a night picture's black and white
NIGHT_PCT = (1.0, 99.7)   # percentiles of that band that make black and white
FLAT_SIGMA = 0.06      # the night side's smooth background: a blur this share of the frame's width (_flatten)
NIGHT_GAMMA = 0.6      # a gentle lift of the dim cloud (display gamma; the same for every night picture)
DAY_PCT = (0.5, 99.8)  # a day picture's black and white, over Saturn's disk
DAY_SIGMA = 4.5        # how far above both neighbours (in noise) a day pixel is when it is half tinted
DAY_RAMP = 1.5         # noise units either side of DAY_SIGMA over which the tint goes from none to full
FIXED_SHARE = 0.2      # a spot brighter than its neighbours in this share of a pass's pictures is the camera's (fixed_spots)
DAY_EDGE_PX = 24       # px (of 1024) at the frame's edge left untinted
DAY_FLOW = 31          # px: optical flow window (a flash is about 7 px across at these scales)
NEIGHBOUR_S = 40 * 60  # s: a day picture's neighbours are the same filter's pictures within this time
SIZE = 1024
RING_MARGIN_PX = 20        # px (of 1024) the rings' mask is widened by: the pointing's error
RINGS_KM = (74000.0, 140300.0)   # the main rings, inner C ring to outer A ring edge, km from Saturn's centre
TINT = np.array([255, 226, 150], np.float32)   # warm: what a day picture gained over both neighbours


def _path(fid):
    return f"{'nac_data' if fid[0] == 'N' else 'wac_data'}/{fid}.png"


def flashes(path=FLASHES):
    """The listed flashes: dicts with id (the archive's _1 frame), utc, filter, wlon, lat, energy (1e9 J)."""
    out = []
    for r in csv.DictReader(open(path, newline="")):
        out.append({"id": r["image"].rsplit("_", 1)[0] + "_1", "utc": r["utc"], "filter": r["filter"],
                    "wlon": float(r["wlon"]), "lat": float(r["lat"]), "energy": float(r["energy_1e9J"]),
                    "exposure_s": float(r["exposure_s"])})
    return out


def _utc(t):
    """2009-229T03:11:59.185 -> datetime (UTC)"""
    return datetime.datetime.strptime(t[:17], "%Y-%jT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)


def _index():
    import pandas as pd
    idx = pd.read_csv(os.path.join(ROOT, "Image_index.csv"), low_memory=False,
                      usecols=["path", "IMAGE_MID_TIME", "INSTRUMENT_ID", "OBSERVATION_ID", "FILTER_NAME"])
    idx = idx[idx["path"].notna() & idx["IMAGE_MID_TIME"].notna()]
    idx["id"] = idx["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0]
    return idx


def passes(fl=None, idx=None):
    """The lightning passes: flashes less than GAP apart are one. Each: {date, obs (in time order), flashes, view
    ("night" for clear-filter flashes, "day" for blue), frames: [(id, utc, filter)] the narrow-angle pictures of
    those observations from PAD before the first flash to PAD after the last (a day pass: only the flashes' filter)}"""
    fl = fl or flashes()
    idx = _index() if idx is None else idx
    obs_of = dict(zip(idx["id"], idx["OBSERVATION_ID"]))
    groups = []
    for f in sorted(fl, key=lambda f: f["utc"]):
        if groups and (_utc(f["utc"]) - _utc(groups[-1]["flashes"][-1]["utc"])).total_seconds() < GAP:
            groups[-1]["flashes"].append(f)
        else:
            groups.append({"flashes": [f]})
    for g in groups:
        fs = g["flashes"]
        g["obs"] = list(dict.fromkeys(obs_of[f["id"]] for f in fs))
        g["view"] = "night" if all(f["filter"].startswith("CL") for f in fs) else "day"
        g["date"] = _utc(fs[0]["utc"]).strftime("%Y-%m-%d")
        filt = {f["filter"] for f in fs}
        rows = idx[idx["OBSERVATION_ID"].isin(g["obs"]) & (idx["INSTRUMENT_ID"] == "ISSNA")]
        frames = []
        for _, r in rows.sort_values("IMAGE_MID_TIME").iterrows():
            t = _utc(r["IMAGE_MID_TIME"])
            near = min(abs((t - _utc(f["utc"])).total_seconds()) for f in fs)
            names = str(r["FILTER_NAME"]).strip("()").split(",")
            if near <= PAD and (g["view"] == "night" or filt & set(names)):
                frames.append((r["id"], r["IMAGE_MID_TIME"], r["FILTER_NAME"]))
        g["frames"] = frames
    return groups


def label_of(g):
    d = _utc(g["flashes"][0]["utc"])
    return f"Lightning on Saturn, {d.strftime('%b')} {d.day}, {d.year}"


def why_of(g):
    fs = g["flashes"]
    imgs = len({f["id"] for f in fs})
    lat = np.mean([f["lat"] for f in fs])
    where = f"{abs(lat):.0f}° {'south' if lat < 0 else 'north'}"
    top = max(f["energy"] for f in fs)
    if g["view"] == "night":
        side = "on the night side, lit only by the rings"
    else:
        side = "on the sunlit clouds of the great storm, in the blue filter"
    return (f"{len(fs)} lightning flash{'es' if len(fs) > 1 else ''} in {imgs} picture{'s' if imgs > 1 else ''} at "
            f"{where} {side}, each a glow about 200 km across from lightning deep in the water clouds; the brightest "
            f"gave off about {top:.0f} billion joules of light. The Lightning window shows the pictures enhanced, the "
            f"flashes marked")


def write_moments(out=MOMENTS_OUT, moments_csv=os.path.join(REPLAY, "moments.csv")):
    """lightning_moments.csv: one Moment (type lightning) per pass whose observations no moments.csv row lists
    (a pass inside a listed moment, the Great Northern Storm's map of 2011-03-06, still gets its pictures and the
    window, from lightning.json)."""
    listed = {o for r in csv.DictReader(open(moments_csv, newline="")) for o in r["obs"].split()}
    rows = []
    for g in passes():
        if set(g["obs"]) & listed:
            continue
        rows.append({"date": g["date"], "label": label_of(g), "body": "SATURN", "obs": " ".join(g["obs"]),
                     "why": why_of(g), "source": "Dyudina et al. 2013, Icarus 226", "type": "lightning"})
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, ["date", "label", "body", "obs", "why", "source", "type"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{out}: {len(rows)} lightning moments")
    return rows


# ---------------------------------------------------------------- pictures

class Frame:
    """One picture: its I/F (the pipeline's calibration of its stored codes) and its SPICE geometry."""
    _years = set()

    def __init__(self, fid):
        import cv2
        import calibration as cal
        import data_source as ds
        import label_handler as lh
        import bootleg_autonav as ba
        import reproject as rp
        self.id = fid
        lbl = lh.label(_path(fid), as_png=True)
        self.info = lbl.get_info()
        codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
        iof = cal.calibrate(codes, self.info, codes)
        if iof is None:
            raise ValueError(f"{fid}: can't be calibrated")
        self.iof = np.asarray(iof, np.float32)
        year = int(str(self.info["IMAGE_MID_TIME"])[:4])
        if year not in Frame._years:
            ba.load_kernels(year, year)
            Frame._years.add(year)
        with contextlib.redirect_stdout(io.StringIO()):
            ba.find_target(lbl, False, "/tmp")
        self.g = lbl.geometry
        self.v = rp.spice_view(self.g)
        n = self.iof.shape[0]
        k = n / 1024.0
        self.P = np.array([[k, 0, 0], [0, k, 0], [0, 0, 1.0]])   # 1024-px sensor pixel -> this picture's pixel
        gx, gy = np.meshgrid(np.arange(self.iof.shape[1], dtype=np.float64), np.arange(n, dtype=np.float64))
        self.points, self.hit = rp.surface_points(self.g, self.v, self.P, gx, gy)
        self.et = float(self.g["et"])

    def latitude(self):
        p = self.points
        return np.degrees(np.arctan2(p[..., 2], np.hypot(p[..., 0], p[..., 1])))

    def sun_up(self):
        p = self.points
        nrm = p / self.v["radii"] ** 2
        nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-12)
        return nrm @ self.v["sun"] > 0

    def behind_rings(self):
        """Where the line of sight to the disk crosses the main rings (RINGS_KM from Saturn's centre, in its equator
        plane) on the way: those pixels show the rings, not the clouds."""
        o, p = self.v["observer"], self.points
        dz = o[2] - p[..., 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = o[2] / dz                      # 0 at Cassini, 1 at the cloud tops
            r = np.hypot(o[0] + t * (p[..., 0] - o[0]), o[1] + t * (p[..., 1] - o[1]))
        rings = self.hit & (t > 0) & (t < 1) & (r >= RINGS_KM[0]) & (r <= RINGS_KM[1])
        # widened by the pointing's few-pixel error, so no sliver of bright ring is left at their edge
        import cv2
        d = 2 * int(np.ceil(RING_MARGIN_PX * self.iof.shape[1] / 1024)) + 1
        return cv2.dilate(rings.astype(np.uint8), np.ones((d, d), np.uint8)).astype(bool) & self.hit

    def place(self, wlon, lat):
        """Where a planetocentric latitude / west longitude on Saturn is in this picture, in SIZE px; None if it is
        out of sight."""
        import spiceypy as sp
        import reproject as rp
        p = np.asarray(sp.srfrec(699, np.radians(-wlon), np.radians(lat)))
        x, y, vis = rp.canvas_points(self.g, self.v, self.P, p[None])
        if not vis[0]:
            return None
        s = SIZE / self.iof.shape[1]
        return float(x[0] * s), float(y[0] * s)


def _flatten(a, on):
    """a less its smooth background: the glow of ringshine across the night side, which changes over the frame far
    more than the storm's cloud differs from its surroundings (a wide blur, FLAT_SIGMA of the frame's width, of the
    disk alone so the limb does not bleed in). What is left is the cloud and the flashes on a flat floor."""
    import cv2
    s = FLAT_SIGMA * a.shape[1]
    w = on.astype(np.float32)
    if w.sum() < 1000:
        w = np.ones_like(w)
    bg = cv2.GaussianBlur(a * w, (0, 0), s) / np.maximum(cv2.GaussianBlur(w, (0, 0), s), 1e-3)
    return (a - bg).astype(np.float32)


def _to_size(a, interp=None):
    import cv2
    return cv2.resize(a, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR if interp is None else interp)


def night_picture(f, storm_lat):
    """8-bit gray: black and white from the night side within STORM_BAND of the storm's latitude, then NIGHT_GAMMA.
    None when the frame shows too little of that band (then the band is taken as all of the disk at night)."""
    lat = f.latitude()
    disk = f.hit & ~f.behind_rings()
    night = disk & ~f.sun_up()
    band = night & (np.abs(lat - storm_lat) <= STORM_BAND)
    sel = band if band.sum() >= 2000 else night if night.sum() >= 2000 else disk if disk.sum() >= 2000 else None
    a = _flatten(f.iof, disk)
    lo, hi = np.percentile(a[sel] if sel is not None else a, NIGHT_PCT)
    v = np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1) ** NIGHT_GAMMA
    v[~disk] = 0   # off the clouds (sky, the rings in front or past the limb): black, so the stretch shows only them
    return _to_size((v * 255).round().astype(np.uint8))


def _warp_onto(src, dst):
    """src's I/F redrawn onto dst's pixels by SPICE (where both see the same place on Saturn), and where it is valid."""
    import cv2
    import reproject as rp
    sx, sy, vis = rp.canvas_points(src.g, src.v, src.P, dst.points)
    n, m = src.iof.shape
    ok = dst.hit & vis & (sx >= 0) & (sy >= 0) & (sx < m - 1) & (sy < n - 1)
    w = cv2.remap(src.iof, sx.astype(np.float32), sy.astype(np.float32), cv2.INTER_LINEAR)
    return w, ok


def day_gain(f, neighbours):
    """How far f is above each neighbour, in noise units, the smallest over the neighbours (NaN where fewer than one
    neighbour sees the place). Steps in the module docstring."""
    import cv2
    b = f.iof
    lo, hi = np.percentile(b[f.hit] if f.hit.sum() > 1000 else b, (1, 99.5))
    u8 = lambda z: np.clip((z - lo) / max(hi - lo, 1e-12) * 255, 0, 255).astype(np.uint8)
    gx, gy = np.meshgrid(np.arange(b.shape[1], dtype=np.float32), np.arange(b.shape[0], dtype=np.float32))
    zs = []
    for nb in neighbours:
        w, ok = _warp_onto(nb, f)
        if ok.sum() < 5000:
            continue
        flow = cv2.calcOpticalFlowFarneback(u8(b), u8(np.where(ok, w, b)), None, 0.5, 3, DAY_FLOW, 3, 7, 1.5, 0)
        w = cv2.remap(w, gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_LINEAR)
        ok = cv2.remap(ok.astype(np.uint8), gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_NEAREST).astype(bool)
        ok = cv2.erode(ok.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        g = np.median(b[ok]) / max(float(np.median(w[ok])), 1e-12)
        d = np.where(ok, b - g * w, 0).astype(np.float32)
        wt = cv2.GaussianBlur(ok.astype(np.float32), (0, 0), 15)
        d = d - np.where(ok, cv2.GaussianBlur(d, (0, 0), 15) / np.maximum(wt, 1e-3), 0)
        noise = 1.4826 * np.median(np.abs(d[ok] - np.median(d[ok])))
        z = cv2.GaussianBlur((d / max(noise, 1e-12)).astype(np.float32), (0, 0), 1.2)
        zs.append(np.where(ok, z, np.nan))
    if not zs:
        return None
    return np.nanmin(np.stack(zs), 0) if len(zs) > 1 else zs[0]


def fixed_spots(gains):
    """Pixels that come out brighter than their neighbours in FIXED_SHARE or more of a pass's pictures: marks on the
    camera (dust rings, hot pixels), which stay put on the detector while Saturn turns under them, so after redrawing
    they look new in every picture. A flash is in one picture. Widened by a few pixels."""
    import cv2
    shapes = {x.shape for x in gains}
    if len(gains) < 4 or len(shapes) != 1:
        return None
    hits = np.sum([np.nan_to_num(x, nan=0.0) > DAY_SIGMA - DAY_RAMP for x in gains], 0)
    spots = hits >= max(3, FIXED_SHARE * len(gains))
    return cv2.dilate(spots.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)


def day_picture(f, gain):
    """8-bit RGB: the picture (black and white over the disk), tinted warm where it is DAY_SIGMA over both neighbours."""
    a = f.iof
    lo, hi = np.percentile(a[f.hit] if f.hit.sum() > 1000 else a, DAY_PCT)
    v = np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1)
    rgb = np.repeat((v * 255)[..., None], 3, -1).astype(np.float32)
    if gain is not None:
        g = np.nan_to_num(gain, nan=0.0)
        e = max(2, int(round(DAY_EDGE_PX * a.shape[1] / 1024)))   # the frame's own edge: redrawing leaves seams there
        g[:e], g[-e:], g[:, :e], g[:, -e:] = 0, 0, 0, 0
        t = np.clip((g - DAY_SIGMA) / (2 * DAY_RAMP) + 0.5, 0, 1)[..., None] * 0.9
        rgb = rgb * (1 - t) + TINT * t
    return _to_size(np.clip(rgb, 0, 255).round().astype(np.uint8))


def _write_webp(path, img):
    import cv2
    tmp = path + ".tmp.webp"
    bgr = img if img.ndim == 2 else img[..., ::-1]
    cv2.imwrite(tmp, bgr, [cv2.IMWRITE_WEBP_QUALITY, 92])
    os.replace(tmp, path)


def build(cache, only=None, log=print):
    """Makes every lightning pass's pictures and lightning.json in <cache>/<folder()> (see the module
    docstring). only: a date (YYYY-MM-DD) to make one pass."""
    import spiceypy as sp
    out = os.path.join(cache, folder())
    os.makedirs(out, exist_ok=True)
    doc = {"version": folder(), "source": SOURCE, "passes": []}
    for g in passes():
        if only and g["date"] != only:
            continue
        storm_lat = float(np.median([f["lat"] for f in g["flashes"]]))
        frames = {}
        for fid, t, filt in g["frames"]:
            try:
                frames[fid] = Frame(fid)
            except Exception as e:   # noqa: BLE001  (a picture that can't be calibrated or placed is left out)
                log(f"{fid}: left out ({e})")
        order = [fid for fid, _, _ in g["frames"] if fid in frames]
        filt_of = {fid: filt for fid, _, filt in g["frames"]}
        entry = {"label": label_of(g), "date": g["date"], "obs": g["obs"], "view": g["view"], "storm_lat": storm_lat,
                 "flashes": len(g["flashes"]), "frames": []}
        gains, fixed = {}, None
        todo = [fid for fid in order if not os.path.exists(os.path.join(out, f"{fid}.webp"))]
        if g["view"] == "day" and todo:
            for fid in order:
                f = frames[fid]
                nbs = sorted([frames[o] for o in order if o != fid and filt_of[o] == filt_of[fid]
                              and abs(frames[o].et - f.et) <= NEIGHBOUR_S], key=lambda o: abs(o.et - f.et))
                gains[fid] = day_gain(f, [o for o in nbs if o.et < f.et][:1] + [o for o in nbs if o.et > f.et][:1])
            fixed = fixed_spots([x for x in gains.values() if x is not None])
        for k, fid in enumerate(order):
            f = frames[fid]
            name = f"{fid}.webp"
            dest = os.path.join(out, name)
            if fid in todo:
                if g["view"] == "night":
                    img = night_picture(f, storm_lat)
                else:
                    gain = gains.get(fid)
                    if gain is not None and fixed is not None and fixed.shape == gain.shape:
                        gain = np.where(fixed, 0, gain)
                    img = day_picture(f, gain)
                _write_webp(dest, img)
            marks = []
            for fl in g["flashes"]:
                if fl["id"] == fid:
                    at = f.place(fl["wlon"], fl["lat"])
                    if at:
                        marks.append({"x": round(at[0], 1), "y": round(at[1], 1), "energy": fl["energy"],
                                      "lat": fl["lat"], "wlon": fl["wlon"]})
            entry["frames"].append({"id": fid, "et": round(f.et, 3), "utc": sp.et2utc(f.et, "ISOC", 0),
                                    "exposure_s": float(f.info.get("EXPOSURE_DURATION", 0)) / 1000.0,
                                    "filter": filt_of[fid], "file": name, "markers": marks})
        log(f"{entry['label']}: {len(entry['frames'])} pictures, "
            f"{sum(len(x['markers']) for x in entry['frames'])} of {len(g['flashes'])} flashes placed")
        doc["passes"].append(entry)
    if not only:
        tmp = os.path.join(out, "lightning.json.tmp")
        json.dump(doc, open(tmp, "w"), indent=1)
        os.replace(tmp, os.path.join(out, "lightning.json"))
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("moments", "build"))
    ap.add_argument("--cache")
    ap.add_argument("--only", help="build: one pass, by its date (YYYY-MM-DD); lightning.json is not written")
    a = ap.parse_args()
    if a.what == "moments":
        write_moments()
        return
    if not a.cache:
        ap.error("build needs --cache")
    sys.path.insert(0, ROOT)
    sys.path.insert(0, HERE)
    import data_source
    data_source.check_kernels(sorted({int(f["utc"][:4]) for f in flashes()}))
    build(a.cache, a.only)


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.path.insert(0, HERE)
    main()
