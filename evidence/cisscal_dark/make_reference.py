"""Builds web/test_data/cisscal_dark_ref.npz, the CISSCAL 4.1 reference for web/test_dark_current_idl.py.

1. GDL (apt install gnudatalanguage) with the CISSCAL 4.1 IDL source on !path (scratch branch claude/cisscal-idl-src,
   or /mnt/project-files/black-level/cisscal-idl/src/cisscal) and, in the working folder, makedarkarray.pro = a copy of
   cassimg__subtractdark.pro (so GDL finds makedarkarray by its name) plus dark_ref.pro and lt_grid.pro from here.
2. REFDIR=<folder>/ref with ref/darkcurrent/ holding the camera team's nac_ and wac_dark_parameters.xdr (COISS_0011
   calib/darkcurrent, pds-rings.seti.org; md5 bc5461c9c14c6f744895a7eb98c23cf1 and 373b728b5feaf9278dce7492b1c79630)
   and the hot pixel lists named in CONFIGS.
3. gdl -e "lt_grid, 'lt_grid.txt'"   (cisscal_linetime over 3 summing modes x 2 conversions x 3 compressions x 6
   telemetry rates x 2 cameras x 2 flight software x botsim x readout order, every 7th line: 148,608 times, every 4th kept)
4. for each of CONFIGS: gdl -e "dark_ref, <its arguments>, 'd<n>.f32'"   (makedarkarray and the gain conversion,
   cassimg__subtractdark.pro, written out as float32 [line, sample])
5. python make_reference.py <folder>
"""
import os
import sys

import numpy as np

# (sum, exposure s, conversion, compression, botsim, packets/s, ratio, readout cycle, camera, flight software,
#  gain state, hot pixel list)
CONFIGS = [("SUM4", 46.0, "12BIT", "LOSSLESS", 0, 24, 2.4, 10, "NAC", 1.4, 1, "NAC_hotpix2005.8_140219.tab"),
           ("SUM4", 220.0, "TABLE", "NOTCOMP", 0, 32, 1.0, 4, "WAC", 1.4, 2, "WAC_hotpix2011.5_140219.tab"),
           ("SUM4", 100.0, "TABLE", "LOSSY", 0, 16, 3.1, 2, "NAC", 1.3, 2, "NAC_hotpix2015.7_171204.tab"),
           ("SUM4", 10.0, "12BIT", "NOTCOMP", 1, 40, 1.0, 6, "WAC", 1.4, 0, "WAC_hotpix2015.7_171204.tab"),
           ("SUM2", 68.0, "TABLE", "LOSSLESS", 1, 48, 1.8, 9, "WAC", 1.3, 3, "WAC_hotpix2005.8_140219.tab"),
           ("FULL", 1.2, "TABLE", "LOSSLESS", 0, 24, 2.2, 3, "NAC", 1.4, 2, "NAC_hotpix2011.5_140219.tab")]
COLUMNS = 24        # whole columns kept per dark (a column carries the whole readout sum)
PIXELS = 4000       # and this many pixels drawn at random, plus every hot pixel the list puts in


def main(folder):
    out = {}
    rows = [line.split() for line in open(os.path.join(folder, "lt_grid.txt"))][::4]   # every 4th of the grid
    # columns: summing mode (0 FULL, 1 SUM2, 2 SUM4), exposure s, 8-bit, compression (0 NOTCOMP, 1 LOSSLESS, 2 LOSSY),
    # botsim, packets/s, line (1-based), ratio, readout cycle, WAC, readout order, flight software
    codes = {"FULL": 0, "SUM2": 1, "SUM4": 2, "12BIT": 0, "TABLE": 1, "NOTCOMP": 0, "LOSSLESS": 1, "LOSSY": 2,
             "NAC": 0, "WAC": 1}
    out["lt_args"] = np.array([[codes.get(v, None) if v in codes else float(v) for v in r[:12]] for r in rows],
                              np.float32)
    out["lt_time"] = np.array([float(r[12]) for r in rows], np.float32)
    rng = np.random.default_rng(11)
    for n, c in enumerate(CONFIGS, 1):
        lines = {"FULL": 1024, "SUM2": 512, "SUM4": 256}[c[0]]
        d = np.fromfile(os.path.join(folder, f"d{n}.f32"), "<f4").reshape(lines, lines)
        cols = np.sort(rng.choice(lines, COLUMNS, replace=False))
        ys, xs = rng.integers(0, lines, PIXELS), rng.integers(0, lines, PIXELS)
        text = open(os.path.join(folder, "ref", "darkcurrent", c[-1])).read().split("\\begindata", 1)[-1]
        hxy = np.array([[int(float(v)) for v in r.split()[:2]] for r in text.splitlines()[3:] if r.strip()])
        k = 1024 // lines
        ys = np.concatenate([ys, hxy[:, 1] // k])
        xs = np.concatenate([xs, hxy[:, 0] // k])
        out[f"d{n}_cols"], out[f"d{n}_colvals"] = cols, d[:, cols]
        out[f"d{n}_yx"], out[f"d{n}_vals"] = np.stack([ys, xs]), d[ys, xs]
    out["configs"] = np.array([repr(c) for c in CONFIGS])
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web", "test_data", "cisscal_dark_ref.npz")
    np.savez_compressed(target, **out)
    print(target, os.path.getsize(target))


if __name__ == "__main__":
    main(sys.argv[1])
