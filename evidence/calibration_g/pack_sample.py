"""
Copies the frames that the group G calibration diagnosis needs out of the lean archive, so the diagnosis can run in
the cloud on the same bytes the Mini calibrates. For every id in a list (default: sample_frames.txt next to this
file; ids are the first word of each line, # lines skipped), every archive member whose name is that id plus an
extension (the PNG, the label, the line prefixes) is written under out/ at its archive path, with the FORMAT.txt
markers that make the folder a lean archive (data_source.lut8). With --text, small text files (.tsv .txt .md .json
.csv up to 20 MB) from those folders are copied under out/text/<folder name>/ as well.

Run on the Mini (reads only; about a hundred frames, a few seconds of LaCie reads):
  python evidence/calibration_g/pack_sample.py --zip /Volumes/LaCie/cassini_lut8.zip --out /tmp/group-g-sample \
      --text ~/Documents/qc-color-scratch
"""
import argparse
import os
import shutil
import sys
import zipfile


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--list", default=os.path.join(here, "sample_frames.txt"))
    ap.add_argument("--text", nargs="*", default=[])
    a = ap.parse_args()
    ids = []
    for line in open(a.list):
        word = line.split()[0] if line.strip() and not line.startswith("#") else ""
        if word and word not in ids:
            ids.append(word)
    want = set(ids)
    found = {}
    with zipfile.ZipFile(a.zip) as z:
        for info in z.infolist():
            base = info.filename.rsplit("/", 1)[-1]
            stem = base.split(".", 1)[0]
            if stem in want or base == "FORMAT.txt":
                target = os.path.join(a.out, info.filename)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                found.setdefault(stem, []).append(info.filename)
    missing = [i for i in ids if i not in found]
    for folder in a.text:
        folder = os.path.expanduser(folder)
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if (os.path.isfile(path) and name.rsplit(".", 1)[-1] in ("tsv", "txt", "md", "json", "csv")
                    and os.path.getsize(path) < 20e6):
                target = os.path.join(a.out, "text", os.path.basename(folder.rstrip("/")), name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy(path, target)
    print(f"{len(ids) - len(missing)} of {len(ids)} frames copied to {a.out}; missing: {' '.join(missing) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
