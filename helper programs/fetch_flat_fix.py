"""
Makes the flat field maps the USGS mirror of CISSCAL's files has broken, from the PDS's own slope files, into a folder
of their own (flat_field.FIX: CASSINI_CISSCAL_FIX, default cisscal-fix beside CASSINI_CISSCAL; CISSCAL's folder is never
written to). flat129 (the NAC's UV2/CL2, at every temperature) was read as the wrong number type when it was brought
into ISIS, so the mirror's map is 20 everywhere (full) or runs from 1e-11 to 4e12 (summed): 2,257 NAC UV2 frames went
without a flat field and kept their dust rings. The PDS calibration volume COISS_0011 has the slope file itself.

A map is the mirror's own recipe, checked on a good one (flat113 from SLOPE113.IMG, within 1e-7 at full size, 0.5%
summed): the slope file's median over its middle 400 x 400 pixels over the slope file, the summed modes from the slope
file averaged over 2 x 2 or 4 x 4 pixels. Writes <out>/flat/flat<NNN>.<full|sum2|sum4>.npy (float32) and keeps the
slope file in <out>/slope.
Run: python "helper programs/fetch_flat_fix.py" [--out FOLDER]
"""
import argparse
import hashlib
import os
import sys
import urllib.request

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import flat_field  # noqa: E402

PDS = "https://pds-rings.seti.org/holdings/volumes/COISS_0xxx/COISS_0011/calib/slope/"
BROKEN = {"slope129.img": 4198400}   # slope file: its size in bytes (4096 byte VICAR label + 1024 x 1024 float32)


def slope(path):
    """A slope file (VICAR, 4096 byte label, 1024 x 1024 big-endian float32)"""
    return np.fromfile(path, dtype=">f4", offset=4096).reshape(1024, 1024).astype(np.float64)


def maps(s):
    out = {}
    for mode, k in (("full", 1), ("sum2", 2), ("sum4", 4)):
        binned = s.reshape(1024 // k, k, 1024 // k, k).mean(axis=(1, 3))
        c, w = binned.shape[0] // 2, 200 // k
        out[mode] = (np.median(binned[c - w:c + w, c - w:c + w]) / binned).astype(np.float32)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=flat_field.FIX)
    a = ap.parse_args()
    for name, size in BROKEN.items():
        path = os.path.join(a.out, "slope", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not (os.path.exists(path) and os.path.getsize(path) == size):
            req = urllib.request.Request(PDS + name, headers={"User-Agent": "cassini-project-calibration"})
            with urllib.request.urlopen(req, timeout=300) as r, open(path + ".part", "wb") as f:
                f.write(r.read())
            if os.path.getsize(path + ".part") != size:
                sys.exit(f"{name}: {os.path.getsize(path + '.part')} bytes, expected {size}")
            os.replace(path + ".part", path)
        flat = "flat" + name[5:8]
        os.makedirs(os.path.join(a.out, "flat"), exist_ok=True)
        for mode, m in maps(slope(path)).items():
            assert flat_field.usable_flat(m), (flat, mode)
            np.save(os.path.join(a.out, "flat", f"{flat}.{mode}.npy"), m)
        md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
        print(f"{flat}: made from {name} (md5 {md5}) into {os.path.join(a.out, 'flat')}")


if __name__ == "__main__":
    main()
