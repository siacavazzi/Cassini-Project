"""CISSCAL's 2 Hz noise and anti-blooming pixel pair steps (cisscal_noise.py; calibration.calibrate's "twohz" and "pairs"
steps), checked against the real CISSCAL 4.1 IDL run in GDL (web/test_data/cisscal_noise_ref.npz, made by
evidence/cisscal_noise/make_reference.py):
- the bias per line and the 2 Hz signal per line of two raw 12-bit frames (N1513700682_1, gain 29; N1510252949_1,
  gain 12, a readout line break at 1248) from their own line prefixes, to float32 rounding
- an 8-bit table frame at gain 29 (N1511812952_1): CISSCAL's strip mean bias and no 2 Hz step
- every pixel the pairs step changed on N1510252949_1 (23 pairs), on the image going into it
- the readout line break of 3,456 full-frame readouts (conversion, compression, telemetry rate, flight software,
  compression ratio, delayed readout, readout cycle) against cisscal_linetime
- the hum filter (Savitzky-Golay less the slow part, split at the line break) on a test signal, NAC and WAC, five
  breaks
And the wiring: calibrate with "twohz" on takes each line's 2 Hz value off that line (on a flat frame whose overclocks
carry a wave), and off leaves it.
Run: python web/test_cisscal_noise.py"""
import gzip
import json
import os
import sys
import tempfile
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("CASSINI_CISSCAL", "/nonexistent")
os.environ.setdefault("CASSINI_HOT_MAPS", "/nonexistent")
import calibration as cal  # noqa: E402
import cisscal_noise as cn  # noqa: E402

REF = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data", "cisscal_noise_ref.npz"))
LABELS = json.loads(str(REF["labels"]))
RATES = {8: 60.5, 16: 121.5, 24: 182.78, 32: 243.5, 40: 304.5, 48: 365.5}


def frame_info(fid, folder):
    """The frame's label as calibration reads it, its prefixes written where overclock_avg looks"""
    info = dict(LABELS[fid])
    path = os.path.join(folder, fid)
    with open(path + ".prefix.gz", "wb") as f:
        f.write(gzip.compress(REF[f"{fid}/prefix"].tobytes()))
    info["path"] = path + ".png"
    return info


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    return ok


def main():
    results = []
    folder = tempfile.mkdtemp()
    with mock.patch.object(cal.ds, "read_bytes", lambda p: open(p, "rb").read()):
        for fid in ("N1513700682_1", "N1510252949_1"):
            info = frame_info(fid, folder)
            bias = cal.overclock_bias(info)
            d = np.abs(bias - REF[f"{fid}/bias"]).max()
            results.append(check(f"{fid} bias per line", d < 1e-3, f"max {d:.2e} DN"))
            hum = cn.two_hz(info, *cal.overclock_avg(info))
            d = np.abs(hum - REF[f"{fid}/hum"]).max()
            results.append(check(f"{fid} 2 Hz per line", d < 1e-4, f"max {d:.2e} DN, signal rms {REF[fid + '/hum'].std():.2f}"))
        fid = "N1511812952_1"
        info = frame_info(fid, folder)
        results.append(check(f"{fid} table frame at gain 29: strip mean bias", cal.overclock_bias(info) is None))
        got = cal.overclock_avg(info)
        results.append(check(f"{fid} table frame at gain 29: no 2 Hz step",
                             cn.two_hz(info, *got) is None and np.abs(REF[f"{fid}/hum"]).max() == 0))

    fid = "N1510252949_1"
    ins, outs = REF[f"{fid}/pairs_in"], REF[f"{fid}/pairs_out"]
    same = 0
    for a, b in zip(ins, outs):
        fixed, _ = cn.bright_dark(a.astype(np.float64))
        same += np.float32(fixed[3, 3]) == b[3, 3]
    results.append(check(f"{fid} pixels the pairs step changed", same == len(ins) and len(ins) == 46,
                         f"{same} of {len(ins)}"))

    bad = 0
    for conv, comp, cdsr, fsw, ratio, btsm, rd, lb in REF["grid"]:
        info = {"INSTRUMENT_MODE_ID": "FULL", "INST_CMPRS_TYPE": comp, "DATA_CONVERSION_TYPE": conv,
                "DELAYED_READOUT_FLAG": "YES" if btsm == "1" else "NO", "INSTRUMENT_DATA_RATE": str(RATES[int(cdsr)]),
                "FLIGHT_SOFTWARE_VERSION_ID": fsw, "INST_CMPRS_RATIO": ratio, "READOUT_CYCLE_INDEX": rd,
                "INSTRUMENT_ID": "ISSNA"}
        bad += cn.line_break(info) != int(lb)
    results.append(check("line breaks", bad == 0, f"{len(REF['grid']) - bad} of {len(REF['grid'])}"))

    v = REF["filterhum"].astype(np.float64)
    signal, k, worst = v[:1024], 1024, 0.0
    for lb in (1024, 300, 600, 975, 52):
        for camera, oc in (("ISSNA", True), ("ISSWA", False)):
            with mock.patch.object(cn, "line_break", lambda info, lb=lb: lb):
                ours = cn.filter_hum(signal, {"INSTRUMENT_ID": camera}, overclocks=oc)
            worst = max(worst, np.abs(ours - v[k:k + 1024]).max())
            k += 1024
    results.append(check("hum filter", worst < 1e-4, f"max {worst:.2e}"))

    # wiring: a flat 12-bit frame whose overclocks carry a 2 Hz wave
    folder = tempfile.mkdtemp()
    lines = np.arange(1024)
    wave = 3.0 * np.sin(2 * np.pi * lines / 40.0)
    prefix = np.zeros((1024, 24), np.uint8)
    prefix[:, 3] = 1                                             # every line has its pixels
    total = np.round(3 * (100 + wave)).astype(">i2")             # (first/2 + last/6)/2 = 100 + wave
    prefix[:, 12:14] = total.view(np.uint8).reshape(-1, 2)
    prefix[:, 22:24] = total.view(np.uint8).reshape(-1, 2)
    info = {"INSTRUMENT_ID": "ISSNA", "INSTRUMENT_MODE_ID": "FULL", "INST_CMPRS_TYPE": "LOSSLESS", "INST_CMPRS_RATIO": "2.5",
            "DATA_CONVERSION_TYPE": "12BIT", "GAIN_MODE_ID": "12 ELECTRONS PER DN", "DELAYED_READOUT_FLAG": "NO",
            "INSTRUMENT_DATA_RATE": "182.783997", "FLIGHT_SOFTWARE_VERSION_ID": "1.4", "READOUT_CYCLE_INDEX": "5",
            "ANTIBLOOMING_STATE_FLAG": "OFF", "BIAS_STRIP_MEAN": "100", "LINES": "1024", "LINE_SAMPLES": "1024",
            "EXPOSURE_DURATION": "1000", "FILTER_NAME": "(CL1,CL2)", "TARGET_NAME": "SKY", "IMAGE_NUMBER": "1600000000",
            "IMAGE_MID_TIME": "2010-001T00:00:00.000", "SHUTTER_STATE_ID": "ENABLED", "path": os.path.join(folder, "f.png")}
    with open(os.path.join(folder, "f.prefix.gz"), "wb") as f:
        f.write(gzip.compress(prefix.tobytes()))
    codes = np.full((1024, 1024), 60, np.uint8)
    with mock.patch.object(cal.ds, "read_bytes", lambda p: open(p, "rb").read()), \
            mock.patch.object(cal.ds, "lut8", lambda: True), \
            mock.patch.object(cal, "sun_distance", lambda info: 9.5):
        hum = cn.two_hz(info, *cal.overclock_avg(info))
        # (the overclock method: the frame is flat, so the sky method finds no bands in it)
        with cal.stepping("dark,flat,hotpix,twohzsky"):
            on = cal.calibrate(codes, info, smooth=False)
        with cal.stepping("dark,flat,hotpix,twohz,twohzsky"):
            off = cal.calibrate(codes, info, smooth=False)
    ratio = (off - on).mean(axis=1) / np.where(np.abs(hum) > 0.5, hum, np.nan)
    ratio = ratio[np.isfinite(ratio)]
    results.append(check("calibrate takes each line's 2 Hz value off it",
                         hum is not None and np.abs(hum).max() > 2 and np.ptp(ratio) < 0.02 * np.abs(ratio).mean(),
                         f"hum amplitude {np.abs(hum).max():.2f} DN"))
    results.append(check("... subtracted, not added", ratio.mean() > 0))
    # the image mean method (cisscal_noise.image_hum) against CISSCAL's, on two 8-bit table frames at gain 29 (with the
    # IDL's skip of those frames taken out), one of them with lines lost in downlink, and a 12-bit frame
    img_ref = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data", "cisscal_image_ref.npz"))
    img_labels = json.loads(str(img_ref["labels"]))
    for fid, lab in img_labels.items():
        raw = img_ref[f"{fid}/raw"].astype(np.int64)
        strip = float(lab["BIAS_STRIP_MEAN"])
        if lab["DATA_CONVERSION_TYPE"] == "TABLE":
            image = cal.LUT[raw] - cal.LUT[int(strip)]
        else:
            image = raw - strip
        missing = cn.missing_pixels(raw)
        image = np.where(missing, 0.0, image)
        want_missing = np.unpackbits(img_ref[f"{fid}/missing"]).reshape(1024, 1024).astype(bool)
        want_mask = np.unpackbits(img_ref[f"{fid}/mask"]).reshape(1024, 1024).astype(bool)
        mask, _ = cn.image_mask(image, missing)
        hum = cn.image_hum(image, missing, lab, guard=False)
        guarded = cn.image_hum(image, missing, lab) is not None
        want = img_ref[f"{fid}/hum"]
        d = np.nanmax(np.abs(hum - want)) if hum is not None else np.inf
        results.append(check(f"{fid} image mean method", (missing == want_missing).all()
                             and (mask.astype(bool) != want_mask).sum() <= 20 and d < 1e-3 and guarded,
                             f"{int(want_missing.sum())} missing pixels, mask {int((mask.astype(bool) != want_mask).sum())} "
                             f"pixels apart, 2 Hz max {d:.1e} DN, signal rms {np.nanstd(want):.2f}"))
    # too little sky (a body over most of the frame): the image method stands aside
    # a frame filled by a body (no dark sky): the image method stands aside, even where the body has horizontal bands of
    # its own (Saturn's belts) that the mask lets through
    rng = np.random.default_rng(8)
    yy = np.arange(1024)[:, None]
    belts = 900 + 300 * np.sin(2 * np.pi * yy / 33.0) + 50 * np.sin(2 * np.pi * yy / 9.0) + rng.normal(0, 3, (1024, 1024))
    belts[:, :30] = rng.normal(0, 1, (1024, 30))          # a strip of sky down one edge, too narrow to measure from
    results.append(check("image method stands aside on a frame filled by Saturn",
                         cn.image_hum(belts, np.zeros((1024, 1024), bool), img_labels["N1511812985_1"]) is None))

    # wiring: an 8-bit table frame at gain 29 (no 2 Hz step in CISSCAL) of dark sky carrying bands, its stars masked
    rng = np.random.default_rng(4)
    sky = 30 + 2.5 * np.sin(2 * np.pi * lines / 37.0)[:, None] + rng.normal(0, 1.0, (1024, 1024))
    sky[rng.integers(0, 1024, 300), rng.integers(0, 1024, 300)] += 200
    table = {**info, "DATA_CONVERSION_TYPE": "TABLE", "GAIN_MODE_ID": "29 ELECTRONS PER DN", "BIAS_STRIP_MEAN": "6.9",
             "INST_CMPRS_TYPE": "LOSSLESS"}
    codes8 = np.clip(np.round(np.interp(sky + cal.LUT[6], cal.LUT, np.arange(256))), 1, 255).astype(np.uint8)
    with mock.patch.object(cal.ds, "read_bytes", lambda p: open(p, "rb").read()), \
            mock.patch.object(cal.ds, "lut8", lambda: True), \
            mock.patch.object(cal, "sun_distance", lambda info: 9.5):
        with cal.stepping("dark,flat,hotpix,pairs"):
            on = cal.calibrate(codes8, table, smooth=False)
        with cal.stepping("dark,flat,hotpix,pairs,twohzsky"):
            off = cal.calibrate(codes8, table, smooth=False)
    rows = lambda x: np.sort(x, axis=1)[:, 100:-100].mean(axis=1)   # noqa: E731  (each line's mean, stars left out)
    band_on, band_off = rows(on).std() / np.median(on), rows(off).std() / np.median(off)
    results.append(check("calibrate takes the bands off an 8-bit low gain frame from its sky", band_on < band_off / 3,
                         f"line to line spread {band_off:.4f} -> {band_on:.4f} of the sky"))
    print(f"{sum(results)} of {len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
