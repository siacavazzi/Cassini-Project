"""The dark current step (dark_current.py) against the camera team's CISSCAL 4.1 IDL, run in GDL
(web/test_data/cisscal_dark_ref.npz, made by evidence/cisscal_dark/make_reference.py):
- cisscal_linetime's time from erase to readout for 37,152 lines: every summing mode, conversion, compression and
  telemetry rate, both cameras, both flight software versions, botsim or not, either readout order
- the dark in DN (makedarkarray and the gain conversion of cassimg__subtractdark.pro, hot pixel lists in, on the
  camera team's parameter maps) for six frames: SUM4, SUM2 and FULL, both cameras, 12-bit and table, all three
  compressions, botsim, 16 to 48 packets/s, the four gains, three hot pixel epochs; 24 whole columns and about 4,000
  pixels of each (every listed hot pixel among them)
The darks need the real maps (CASSINI_CISSCAL's darkcurrent/*_dark_parameters.full.cub and the hot pixel lists,
"helper programs/fetch_cisscal.py"); without them that part is skipped. The first and last two lines are left out:
GDL's MEDIAN(x, 5) filters an array's ends with shorter windows where IDL's leaves them as they are, so the reference's
spike lift differs there.
Run: python web/test_dark_current_idl.py"""
import ast
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("CASSINI_HOT_MAPS", "/nonexistent")
import dark_current as dc  # noqa: E402
import flat_field as ff  # noqa: E402

REF = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data", "cisscal_dark_ref.npz"))
RATES = {8: "60.5", 16: "121.5", 24: "182.783997", 32: "243.5", 40: "304.5", 48: "365.5"}
GAINS = ("215", "95", "29", "12")


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    return ok


def main():
    results = []
    worst, bad = 0.0, 0
    for args, want in zip(REF["lt_args"], REF["lt_time"]):
        s, e, conv, comp, btsm, cdsr, line, ratio, rd, wac, roo, fsw = args.tolist()
        comp = ("NotCompressed", "Lossless", "Lossy")[int(comp)]
        r = ("ISSWA" if wac else "ISSNA", (1024, 512, 256)[int(s)], 29, comp,
             1.0 if comp == "NotCompressed" else float(np.float32(ratio)), "8Bit" if conv else "12Bit",
             round(fsw, 1), int(cdsr), int(rd), int(btsm), int(roo), float(np.float32(e)) * 1000, "")
        d = abs(dc.line_time(r, int(line)) - want) / max(1.0, abs(float(want)))
        worst = max(worst, d)
        bad += d > 1e-5
    results.append(check("line times", bad == 0, f"{len(REF['lt_time']) - bad} of {len(REF['lt_time'])}, "
                                                 f"worst {worst:.1e} of the time"))

    maps = os.path.join(ff.ROOT, "darkcurrent")
    if not all(os.path.exists(os.path.join(maps, f"{c}_dark_parameters.full.cub")) for c in ("nac", "wac")):
        print(f"skip darks: no dark parameter maps in {maps}")
    else:
        dc.HOT_PIXEL_CAMERAS = ("ISSNA", "ISSWA")      # cisscal's model as it is (both cameras' lists, no 3x3 median)
        dc.SMOOTH_MAP_CAMERAS = ()
        for n, text in enumerate(REF["configs"], 1):
            s, e, conv, comp, btsm, cdsr, ratio, rd, cam, fsw, gain, hot = ast.literal_eval(str(text))
            if not os.path.exists(os.path.join(maps, hot)):
                print(f"skip dark {n}: no {hot}")
                continue
            year, frac = hot[10:16].split(".")
            info = {"INSTRUMENT_ID": "ISSNA" if cam == "NAC" else "ISSWA", "INSTRUMENT_MODE_ID": s,
                    "GAIN_MODE_ID": GAINS[gain] + " ELECTRONS PER DN", "INST_CMPRS_TYPE": comp,
                    "INST_CMPRS_RATIO": str(ratio), "INSTRUMENT_DATA_RATE": RATES[cdsr], "READOUT_CYCLE_INDEX": str(rd),
                    "DELAYED_READOUT_FLAG": "YES" if btsm else "NO", "FLIGHT_SOFTWARE_VERSION_ID": str(fsw),
                    "DATA_CONVERSION_TYPE": conv, "EXPOSURE_DURATION": str(e * 1000),
                    "IMAGE_TIME": f"{year}-{int(int(frac) * 36.5) + 1:03d}T00:00:00"}
            r = dc.readout(info)
            if r is None or r[-1] != hot:
                results.append(check(f"dark {n} hot pixel list", False, f"{r and r[-1]} not {hot}"))
                continue
            ours = dc.dark_dn(info)
            lines = len(ours)
            cols = REF[f"d{n}_cols"]
            got = np.concatenate([ours[2:-2, cols].ravel(), ours[tuple(REF[f"d{n}_yx"])]])
            want = np.concatenate([REF[f"d{n}_colvals"][2:-2].ravel(), REF[f"d{n}_vals"]])
            inner = np.concatenate([np.ones((lines - 4) * len(cols), bool),
                                    (REF[f"d{n}_yx"][0] >= 2) & (REF[f"d{n}_yx"][0] < lines - 2)])
            d = np.abs(got - want)[inner]
            off = d > np.maximum(0.01, 1e-4 * np.abs(want[inner]))
            # one or two pixels may sit where the spike lift's 10 electron test falls between float32 and float64
            results.append(check(f"dark {n} ({s} {cam} {conv} {comp}{' botsim' if btsm else ''}, {e:g} s)",
                                 off.sum() <= 2, f"{inner.sum() - off.sum()} of {inner.sum()} pixels, "
                                                 f"median {np.median(want):.2f} DN, worst other {np.sort(d)[-3]:.1e} DN"))
    print(f"{sum(results)} of {len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
