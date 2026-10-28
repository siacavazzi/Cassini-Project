# -*- coding: utf-8 -*-
"""
Downloads the CISSCAL maps flat_field.py and dark_current.py use (about 1.4 GB) from the USGS ISIS data mirror,
https://asc-isisdata.s3.us-west-2.amazonaws.com/usgs_data/cassini/calibration/

  slope/slope_db_2.tab                       which flat field each camera, temperature and filter pair uses
  slope/flat/flat<NNN>.<full|sum2|sum4>.cub  the flat fields (ground calibration slope files, inverted, normalized)
  dustring/*.cub                             the NAC dust ring maps (one per epoch) and the mottle map
  darkcurrent/*_dark_parameters.*.cub        the dark current model's per pixel maps (dark_current.py)
  darkcurrent/*_hotpix*.tab                  the hot pixel lists, one per epoch

into the folder flat_field.py reads (CASSINI_CISSCAL, default cisscal_calibration in the main folder), keeping the
mirror's layout. Files already there at the listed size are skipped, so it can be stopped and run again.

usage: python "helper programs/fetch_cisscal.py" [folder] [--connections 4]
"""
import argparse
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flat_field  # noqa: E402

BUCKET = "https://asc-isisdata.s3.us-west-2.amazonaws.com"
PREFIX = "usgs_data/cassini/calibration/"
FOLDERS = ("slope/", "dustring/", "darkcurrent/")


def listing(folder):
    """(path under calibration/, size) of every file the mirror has in folder, without macOS's ._ files."""
    out, token = [], None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={PREFIX}{folder}" + (f"&continuation-token={urllib.request.quote(token)}" if token else "")
        with urllib.request.urlopen(url, timeout=60) as r:
            xml = r.read().decode()
        for key, size in re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", xml):
            path = key[len(PREFIX):]
            if not os.path.basename(path).startswith("._"):
                out.append((path, int(size)))
        token = (re.findall(r"<NextContinuationToken>([^<]+)<", xml) or [None])[0]
        if not token:
            return out


def wanted(path):
    return (path == "slope/slope_db_2.tab" or re.fullmatch(r"slope/flat/flat\d+\.(full|sum2|sum4)\.cub", path)
            or re.fullmatch(r"dustring/nac_\w+\.(full|sum2|sum4)\.cub", path)
            or re.fullmatch(r"darkcurrent/(nac|wac)_dark_parameters\.(full|sum2|sum4)\.cub", path)
            or re.fullmatch(r"darkcurrent/(NAC|WAC)_hotpix[\d.]+_\d+\.tab", path))


def fetch(path, size, root):
    out = os.path.join(root, path)
    if os.path.exists(out) and os.path.getsize(out) == size:
        return 0
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with urllib.request.urlopen(f"{BUCKET}/{PREFIX}{path}", timeout=120) as r, open(out + ".part", "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    if os.path.getsize(out + ".part") != size:
        raise IOError(f"{path}: got {os.path.getsize(out + '.part')} bytes of {size}")
    os.replace(out + ".part", out)
    return size


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default=flat_field.ROOT)
    parser.add_argument("--connections", type=int, default=4)
    args = parser.parse_args()
    files = [(p, s) for folder in FOLDERS for p, s in listing(folder) if wanted(p)]
    print(f"{len(files)} files, {sum(s for _, s in files) / 1e9:.2f} GB, into {args.folder}")
    with ThreadPoolExecutor(args.connections) as pool:
        got = sum(pool.map(lambda f: fetch(*f, args.folder), files))
    print(f"downloaded {got / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
