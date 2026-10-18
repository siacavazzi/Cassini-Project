# -*- coding: utf-8 -*-
"""
Builds filter_calibration.csv, the per filter sensitivity table calibration.py uses.

It follows CISSCAL's DivideByAreaPixel, DivideByEfficiency and CorrectionFactors steps
(Porco et al. 2004, West et al. 2010, Knowles et al. 2020) using CISSCAL's calibration
files, which are mirrored by USGS at
https://asc-isisdata.s3.us-west-2.amazonaws.com/usgs_data/cassini/calibration/

Needs these folders from there, downloaded into calib_dir:
  efficiency/systrans/*.tab, efficiency/solarflux.tab,
  correction/correctionfactors_qecorr.tab, correction/nac_qe_correction.tab,
  correction/wac_qe_correction.tab

usage: python make_filter_calibration.py calib_dir > ../filter_calibration.csv
"""
import os
import sys
import numpy as np

trapezoid = getattr(np, "trapezoid", None) or np.trapz  # renamed in numpy 2

# camera constants from CISSCAL (cassimg__dntoelectrons.pro, cassimg__dividebyareapixel.pro)
CAMERAS = {
    "ISSNA": {"gain2": 30.27, "area": 284.86, "solid_angle": 3.58885e-11},
    "ISSWA": {"gain2": 27.68, "area": 29.43, "solid_angle": 3.56994e-9},
}


def read_spectrum(path):
    rows = []
    in_data = False
    for line in open(path):
        if "\\begindata" in line:
            in_data = True
            continue
        if in_data:
            parts = line.replace(",", " ").split()
            if len(parts) >= 2:
                rows.append((float(parts[0]), float(parts[1])))
    rows = np.array(rows).reshape(-1, 2)
    return rows[:, 0], rows[:, 1]


def correction_factors(path):
    factors = {}
    in_data = False
    for line in open(path):
        if "\\begindata" in line:
            in_data = True
            continue
        parts = line.split()
        if in_data and len(parts) == 4:
            factors[(parts[0], parts[1], parts[2])] = float(parts[3])
    return factors


def main(calib_dir):
    lam_sun, sun = read_spectrum(os.path.join(calib_dir, "efficiency/solarflux.tab"))
    lam_sun = lam_sun / 10.0  # angstrom -> nm
    sun = sun * 10.0          # per angstrom -> per nm
    factors = correction_factors(os.path.join(calib_dir, "correction/correctionfactors_qecorr.tab"))
    qe = {"ISSNA": read_spectrum(os.path.join(calib_dir, "correction/nac_qe_correction.tab")),
          "ISSWA": read_spectrum(os.path.join(calib_dir, "correction/wac_qe_correction.tab"))}

    # filters are keyed like CISSCAL's systrans file names: the two filter names run
    # together (CL1RED, BL1CL2...), so no need to know where one name ends
    print("camera,filters,wavelength_nm,correction_factor,iof_per_dn_per_s")
    systrans = os.path.join(calib_dir, "efficiency/systrans")
    for name in sorted(os.listdir(systrans)):
        if not name.endswith("_systrans.tab") or name.startswith("."):
            continue
        lam_t, trans = read_spectrum(os.path.join(systrans, name))
        if len(lam_t) == 0:
            continue  # a few placeholder files have no data
        combo = name[:-len("_systrans.tab")].upper()
        camera, filters = combo[:5], combo[5:]
        lam_q, qecorr = qe[camera]
        lo = max(lam_t.min(), lam_sun.min(), lam_q.min())
        hi = min(lam_t.max(), lam_sun.max(), lam_q.max())
        lam = np.unique(np.concatenate([lam_t, lam_sun, lam_q]))
        lam = lam[(lam >= lo) & (lam <= hi)]
        weight = np.interp(lam, lam_t, trans) * np.interp(lam, lam_q, qecorr)
        flux = np.interp(lam, lam_sun, sun) / np.pi
        efficiency = trapezoid(weight * flux, lam)
        wavelength = trapezoid(lam * weight * flux, lam) / efficiency
        # CISSCAL skips the correction when a combination has no factor
        factor = 1.0
        for split in range(1, len(filters)):
            factor = factors.get((camera, filters[:split], filters[split:]), factor)
        c = CAMERAS[camera]
        # I/F per DN/s at 1 AU, gain state 2, full resolution pixels
        k = c["gain2"] / (c["area"] * c["solid_angle"] * efficiency * factor)
        print(f"{camera},{filters},{wavelength:.1f},{factor:.6g},{k:.6e}")

if __name__ == "__main__":
    main(sys.argv[1])
