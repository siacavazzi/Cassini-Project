"""
Group G diagnosis (v47 calibration regressions): reads only, writes text to stdout and a few PNGs to --out.

  frames  For each single frame in the list (sky, dark, band and stripes lines of sample_frames.txt): the label's
          readout, then the row profile (the median of each band of 64 rows, DN) of the raw frame (after the bias
          strip mean), of the overclock bias fit and of the dark current model, and of the calibrated I/F in units of
          the frame's grain with every step on (v47), with each of dark / flat / hotpix / the overclock bias off, and
          with all four off (v46, the strip mean only). Then the count of pixels more than 5 grain below the sky
          (pinholes), with the steps on and off, and how many of them are in the hot pixel list or the defect map.
  sets    For each color set in the list (lines "set <id>"; or --sets FILE, one member id per line): the members'
          alignment report (load_aligned's) and phase correlation responses under the same variants.

Run on the Mini, from a worktree of this branch, with the rebuild's environment:
  CASSINI_DATA=/Volumes/LaCie/cassini_lut8.zip CASSINI_CISSCAL=/Volumes/LaCie/cassini_calibration/cisscal \
  python evidence/calibration_g/diagnose.py --out ~/dev/Cassini-Project/web/cassini-os/group-g
Add --only frames or --only sets, --ids N1294638633_1,... to limit it.
"""
import argparse
import contextlib
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "web", "frames"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import dark_current as dc  # noqa: E402
import data_source as ds  # noqa: E402
import image_correction as ic  # noqa: E402
import label_handler as lh  # noqa: E402

FOLDERS = {"N": "nac_data", "W": "wac_data"}
ROWS = 64
_overclock = cal.overclock_bias


@contextlib.contextmanager
def variant(name):
    """The calibration with one change: "v47" every step on; "dark", "flat", "hotpix": that step off; "overclock":
    the strip mean in place of the overclock fit; "v46": all four (the calibration before #153)."""
    off = {"v47": "", "dark": "dark", "flat": "flat", "hotpix": "hotpix", "overclock": "",
           "v46": "dark,flat,hotpix"}[name]
    cal.overclock_bias = (lambda info: None) if name in ("overclock", "v46") else _overclock
    try:
        with cal.stepping(off):
            yield
    finally:
        cal.overclock_bias = _overclock


VARIANTS = ("v47", "dark", "flat", "hotpix", "overclock", "v46")


def load(fid):
    path = f"{FOLDERS[fid[0]]}/{fid}.png"
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    return lbl, info, codes


def raw_dn(codes, info):
    """The frame in DN as calibrate starts from it (after the 12 -> 8 bit table for TABLE frames), minus the strip
    mean bias, at the frame's own size"""
    dn = cal.unstretch(codes, info)
    if dn is None:
        return None
    bias = cal.bias_of(codes, info)
    if cal._value(info, "DATA_CONVERSION_TYPE") == "TABLE":
        dn = np.interp(dn, np.arange(256), cal.LUT)
        bias = cal.LUT[int(min(max(bias, 0), 255))]
    return dn - bias


def bands(rows):
    """medians of each ROWS-row band (of 1024; a summed frame's rows scaled)"""
    rows = np.asarray(rows, np.float64)
    n = max(1, len(rows) * ROWS // 1024)
    return [float(np.nanmedian(rows[i:i + n])) for i in range(0, len(rows), n)]


def row_medians(img, valid=None):
    a = np.asarray(img, np.float64).copy()
    if valid is not None:
        a[~valid] = np.nan
    a[~np.isfinite(a)] = np.nan
    return np.nanmedian(a, axis=1)


def grain_of(img):
    """the pixel to pixel noise (the spread of the frame minus its 3x3 median; the mean absolute value, clipped at
    its 98th percentile, since an 8-bit squeezed sky can have most residuals exactly 0)"""
    a = np.asarray(img, np.float32)
    r = a - cv2.medianBlur(np.nan_to_num(a), 3)
    r = np.abs(r[2:-2:2, 2:-2:2])
    r = r[np.isfinite(r)]
    if not r.size:
        return float("nan")
    r = r[r <= np.percentile(r, 98)]
    return max(1.2533 * float(r.mean()), 1e-12)


def fmt(v, d=1):
    return " ".join(f"{x:+.{d}f}" if np.isfinite(x) else "nan" for x in v)


def readout_text(info):
    keys = ("INSTRUMENT_MODE_ID", "DATA_CONVERSION_TYPE", "INST_CMPRS_TYPE", "INST_CMPRS_RATIO", "INSTRUMENT_DATA_RATE",
            "FLIGHT_SOFTWARE_VERSION_ID", "EXPOSURE_DURATION", "GAIN_MODE_ID", "READOUT_CYCLE_INDEX",
            "DELAYED_READOUT_FLAG", "READOUT_ORDER", "BIAS_STRIP_MEAN", "SHUTTER_STATE_ID", "ANTIBLOOMING_STATE_FLAG",
            "FILTER_NAME", "TARGET_NAME", "OBSERVATION_ID", "IMAGE_TIME")
    return " ".join(f"{k}={cal._value(info, k, '-')}" for k in keys)


def frame_report(fid, out):
    lbl, info, codes = load(fid)
    print(f"\n== {fid} {readout_text(info)}")
    r = dc.readout(info)
    if r is not None:
        lines = r[1]
        t = np.array([dc.line_time(r, i + 1) for i in range(lines)])
        print(f"  line times s: first {t[0]:.2f} 1/4 {t[lines // 4]:.2f} 1/2 {t[lines // 2]:.2f} last {t[-1]:.2f}; "
              f"hot list {r[-1] or '-'}")
    else:
        print("  readout: not modelled (no dark)")
    valid = lbl.valid_mask()
    dn = raw_dn(codes, info)
    if dn is not None:
        v = valid if valid.shape == dn.shape else None
        print(f"  raw DN-bias by {ROWS} rows: {fmt(bands(row_medians(dn, v)))}")
    oc = _overclock(info)
    if oc is not None:
        print(f"  overclock fit - strip mean, DN: top {oc[0] - cal.bias_of(codes, info):+.2f} "
              f"bottom {oc[-1] - cal.bias_of(codes, info):+.2f} (slope {(oc[-1] - oc[0]) / len(oc) * 1024:+.2f} per 1024)")
    dark = dc.dark_dn(info)
    if dark is not None:
        print(f"  dark model DN by {ROWS} rows: {fmt(bands(np.median(dark, axis=1)), 2)}")
        if dn is not None:
            # how much of the model's ramp down the frame the raw frame shows: raw rows = a + k * model rows (k = 1:
            # the model is right; 0: the frame has no such ramp; -1: the ramp runs the other way up the frame)
            rows = row_medians(dn, valid if valid.shape == dn.shape else None)
            model = np.median(dark, axis=1)
            model = np.interp(np.linspace(0, len(model) - 1, len(rows)), np.arange(len(model)), model)
            ok = np.isfinite(rows)
            if ok.sum() > 10 and np.ptp(model[ok]) > 0:
                k, a0 = np.polyfit(model[ok] - model[ok].mean(), rows[ok], 1)
                kf, _ = np.polyfit(model[ok][::-1] - model[ok].mean(), rows[ok], 1)
                print(f"  raw ramp / model ramp: k = {k:+.2f} (model ramp {np.ptp(model):.2f} DN); flipped {kf:+.2f}")
    flat = cal.ff.correction(info)
    if flat is not None:
        print(f"  flat correction by {ROWS} rows (x): {fmt(np.array(bands(np.median(flat, axis=1))) - 1, 4)}")
    made = {}
    for name in VARIANTS:
        with variant(name):
            iof = cal.calibrate(codes, info)
        if iof is None:
            print(f"  {name}: can't calibrate")
            continue
        iof = np.asarray(iof, np.float64)
        v = valid if valid.shape == iof.shape else cv2.resize(valid.astype(np.uint8), iof.shape[::-1],
                                                               interpolation=cv2.INTER_NEAREST).astype(bool)
        iof = np.where(v, iof, np.nan)
        made[name] = iof
        g = grain_of(iof)
        prof = np.array(bands(row_medians(iof)))
        sky = float(np.nanmedian(iof))
        low = int(np.nansum(iof < sky - 5 * g))
        print(f"  {name:9s} rows - median, grains: {fmt((prof - sky) / g)}  | below 5 grain: {low}")
    if "v47" in made:
        iof = made["v47"]
        g = grain_of(iof)
        low = np.argwhere(iof < np.nanmedian(iof) - 5 * g)
        if len(low):
            k = iof.shape[0] // int(cal._value(info, "LINES", "1024") or 1024)
            native = {tuple(p) for p in (low // max(k, 1)).tolist()}
            name = dc.hot_file(cal._value(info, "INSTRUMENT_ID"), dc._year(info), every=True)
            listed = set()
            if name:
                lines = int(cal._value(info, "LINES", "1024") or 1024)
                listed = {(int(y) * lines // 1024, int(x) * lines // 1024) for x, y in dc._hot_spots(name)}
            m = dc.hot_map(info)
            mapped = {(int(a), int(b)) for a, b, s in m} if m is not None else set()
            print(f"  v47 pinholes {len(native)}: in hot list {len(native & listed)}, in defect map {len(native & mapped)}"
                  f", in neither {len(native - listed - mapped)}")
    if out and made:
        picture(fid, made, os.path.join(out, f"{fid}.png"))


def picture(fid, made, path):
    """The variants side by side on one stretch (v46's sky to its 99.5th percentile), 256 px each, and labels."""
    base = made.get("v46", next(iter(made.values())))
    lo, hi = np.nanpercentile(base, 1), np.nanpercentile(base, 99.5)
    tiles = []
    for name, iof in made.items():
        x = np.clip((np.nan_to_num(iof, nan=lo) - lo) / max(hi - lo, 1e-12), 0, 1) ** (1 / 2.2)
        x = cv2.resize((x * 255).astype(np.uint8), (384, 384), interpolation=cv2.INTER_AREA)
        x = cv2.cvtColor(x, cv2.COLOR_GRAY2BGR)
        cv2.putText(x, name, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA)
        tiles.append(x)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, np.hstack(tiles))


def set_report(ids, out):
    import reel
    idx, _ = reel.load_index()
    responses = []
    real = cv2.phaseCorrelate

    def recording(a, b, window=None):
        shift, response = real(a, b, window)
        responses.append(response)
        return shift, response

    for fid in ids:
        row = idx[idx["id"] == fid]
        if not len(row):
            print(f"\n== set {fid}: not in the index")
            continue
        members = idx[idx["set"] == int(row["set"].iloc[0])]["id"].tolist()
        print(f"\n== set of {fid}: {' '.join(members)}")
        for name in VARIANTS:
            responses.clear()
            ic.cv2.phaseCorrelate = recording
            log = io.StringIO()
            try:
                with variant(name), contextlib.redirect_stdout(log):
                    imgs, valid, lbl, report = color_image.load_aligned([f"{FOLDERS[m[0]]}/{m}.png" for m in members])
            except Exception as e:
                print(f"  {name:9s} failed: {e}")
                continue
            finally:
                ic.cv2.phaseCorrelate = real
            print(f"  {name:9s} {' | '.join(report['aligned'])}  responses {' '.join(f'{r:.2f}' for r in responses)}")
            if out:
                rgb = np.dstack([cv2.cvtColor(i, cv2.COLOR_BGR2GRAY) if i.ndim == 3 else i for i in imgs[:3]]) \
                    if len(imgs) >= 3 else None
                if rgb is not None:
                    os.makedirs(out, exist_ok=True)
                    cv2.imwrite(os.path.join(out, f"set_{fid}_{name}.jpg"),
                                cv2.resize(rgb[:, :, ::-1], (512, 512), interpolation=cv2.INTER_AREA))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default=os.path.join(HERE, "sample_frames.txt"))
    ap.add_argument("--sets", help="file with one set member id per line (the sets to check), in place of the list's")
    ap.add_argument("--ids", help="comma list: only these frames / sets")
    ap.add_argument("--only", choices=("frames", "sets"))
    ap.add_argument("--out")
    a = ap.parse_args()
    frames, sets = [], []
    for line in open(a.list):
        if not line.strip() or line.startswith("#"):
            continue
        fid, why = (line.rstrip("\n").split("\t", 1) + [""])[:2]
        if why.startswith("set "):
            first = why.split()[1]
            if first not in sets:
                sets.append(first)
            if "pinholes" in why:
                frames.append(fid)     # the pinhole sets' members, frame by frame too
        else:
            frames.append(fid)
    if a.sets:
        sets = [w.split()[0] for w in open(a.sets) if w.strip() and not w.startswith("#")]
    if a.ids:
        keep = set(a.ids.split(","))
        frames, sets = [f for f in frames if f in keep], [s for s in sets if s in keep]
    print(f"group G diagnosis: {len(frames)} frames, {len(sets)} sets; CISSCAL {cal.ff.ROOT}; hot maps {dc.HOT_MAPS}")
    start = time.time()
    if a.only != "sets":
        for fid in frames:
            try:
                frame_report(fid, a.out)
            except Exception as e:
                print(f"\n== {fid}: failed: {type(e).__name__}: {e}")
    if a.only != "frames":
        set_report(sets, a.out)
    print(f"\ndone in {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
