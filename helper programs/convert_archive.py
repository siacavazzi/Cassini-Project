# -*- coding: utf-8 -*-
"""
Builds the lean archive: every frame stored as the camera's own 8-bit square-root
code (calibration.LUT), with no per-frame stretch, so every frame can be calibrated.

Today's dataset PNGs were stretched min..max -> 0..254 frame by frame. That can be
undone for 8-bit (TABLE) frames but not for 12-bit ones, so 12-bit frames are
downloaded again from NASA's archive (PDS Ring-Moon Systems Node) and re-encoded.

Output is a data folder with the same layout as today's (nac_data, wac_data), so
CASSINI_DATA can point straight at it:
    <out>/wac_data/W1234567890_1.png      8-bit LUT codes (plain grayscale PNG)
    <out>/wac_data/W1234567890_1.prefix.gz  24-byte binary prefix of every line
                                            (overclocked pixels, for 2 Hz noise removal)
    <out>/wac_data/W1234567890_1.LBL       the label, unchanged
    <out>/wac_data/FORMAT.txt              says the PNGs hold LUT codes (also in nac_data)
    <out>/manifest.csv                     one row per frame: how it was made

How each frame is made (DATA_CONVERSION_TYPE from its label):
    12BIT  raw IMG downloaded, DN -> nearest LUT code
    TABLE  raw IMG downloaded (exact), or with --table png the old PNG un-stretched
           (no download; exact when the frame has dark sky, see calibration.unstretch)
    8LSB   the old PNG is copied (only the low 8 bits were sent, nothing to recover)

The raw IMG is deleted once converted, so only a few files sit on disk at a time.
It never writes to the old data, so the render pipeline can keep using it while this
runs. Frames already in <out> are skipped, so it can be stopped and restarted.

Usage (from the main folder, with the old data as CASSINI_DATA as usual):
    python "helper programs/convert_archive.py" OUT [--years 2002 2003] [--limit N]
        [--table raw|png] [--downloads 4] [--dry-run]
"""
import argparse
import csv
import gzip
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402

PDS = "https://pds-rings.seti.org/holdings/volumes"
# cumulative indexes of the last volume of each series list every frame of the series
INDEXES = {
    "COISS_1xxx": f"{PDS}/COISS_1xxx/COISS_1009/index/cumindex",
    "COISS_2xxx": f"{PDS}/COISS_2xxx/COISS_2116/index/cumindex",
}
FORMAT = "lut8 v1\nPNG values are Cassini ISS 8-bit codes; DN = calibration.LUT[code]. No stretch.\n"
USER_AGENT = "Cassini-Project archive converter (github.com/siacavazzi/Cassini-Project)"
MIDS = (cal.LUT[:-1] + cal.LUT[1:]) / 2
MANIFEST_FIELDS = ["id", "conversion", "source", "lines", "samples", "bytes_downloaded", "png_bytes", "note"]


def fetch(url, path, tries=5):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as r, open(path + ".part", "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(path + ".part", path)
            return os.path.getsize(path)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


"""
Where each frame lives in the PDS volumes: {"W1234567890_1": "COISS_2001/data/.../W1234567890_1.IMG"}
The index tables are downloaded once into <out>/pds_index.
"""
def pds_locations(out):
    folder = os.path.join(out, "pds_index")
    os.makedirs(folder, exist_ok=True)
    locations = {}
    for series, url in INDEXES.items():
        lbl, tab = os.path.join(folder, series + ".lbl"), os.path.join(folder, series + ".tab")
        for ext, path in ((".lbl", lbl), (".tab", tab)):
            if not os.path.exists(path):
                print(f"Downloading {url}{ext}", flush=True)
                fetch(url + ext, path)
        cols = {}
        for block in re.findall(r"OBJECT\s*=\s*COLUMN(.*?)END_OBJECT", open(lbl, encoding="latin-1").read(), re.S):
            name = re.search(r"NAME\s*=\s*(\S+)", block).group(1)
            cols[name] = (int(re.search(r"START_BYTE\s*=\s*(\d+)", block).group(1)) - 1,
                          int(re.search(r"BYTES\s*=\s*(\d+)", block).group(1)))
        spans = [cols[k] for k in ("FILE_NAME", "FILE_SPECIFICATION_NAME", "VOLUME_ID")]
        with open(tab, encoding="latin-1") as f:
            for line in f:
                name, spec, volume = (line[s:s + n].replace('"', "").strip() for s, n in spans)
                locations[name.split(".")[0]] = f"{volume}/{spec}"
    return locations


def series_of(location):
    return location.split("_")[0] + "_" + location.split("_")[1][0] + "xxx"


"""
Reads a raw ISS IMG: (8- or 16-bit image as stored, line prefixes [lines, prefix bytes]).
The PDS label is detached; the IMG starts with its own VICAR label, which has the layout.
"""
def read_img(path):
    raw = np.fromfile(path, dtype=np.uint8)
    head = raw[:4096].tobytes().decode("latin-1")
    g = lambda key: re.search(rf"\b{key}=\s*'?([^\s']+)", head).group(1)
    label_size, record = int(g("LBLSIZE")), int(g("RECSIZE"))
    lines, samples = int(g("NL")), int(g("NS"))
    prefix, header_records = int(g("NBB")), int(g("NLB"))
    sample_bytes = 2 if g("FORMAT") == "HALF" else 1
    assert record == prefix + samples * sample_bytes, path
    start = label_size + header_records * record
    rows = raw[start:start + lines * record].reshape(lines, record)
    dtype = ">i2" if sample_bytes == 2 else "u1"
    image = rows[:, prefix:].copy().view(dtype).reshape(lines, samples).astype(np.int32)
    return image, rows[:, :prefix].copy()


def encode(image, conversion):
    if conversion == "12BIT":
        return np.searchsorted(MIDS, image).astype(np.uint8)
    return image.astype(np.uint8)  # TABLE frames were sent as LUT codes already


def save_png(codes, path):
    Image.fromarray(codes).save(path + ".tmp.png", optimize=True)
    os.replace(path + ".tmp.png", path)


def save_prefix(prefixes, path):
    with gzip.open(path + ".tmp", "wb", compresslevel=9) as f:
        f.write(prefixes.tobytes())
    os.replace(path + ".tmp", path)


class Converter:
    def __init__(self, out, table_source):
        self.out = out
        self.table_source = table_source
        self.lock = threading.Lock()
        self.locations = None
        path = os.path.join(out, "manifest.csv")
        new = not os.path.exists(path)
        self.manifest = open(path, "a", newline="")
        self.writer = csv.DictWriter(self.manifest, MANIFEST_FIELDS)
        if new:
            self.writer.writeheader()

    def record(self, **row):
        with self.lock:
            self.writer.writerow(row)
            self.manifest.flush()

    def needs_download(self, conversion):
        return conversion == "12BIT" or (conversion == "TABLE" and self.table_source == "raw")

    def convert(self, frame):
        png_rel, conversion = frame["png"], frame["conversion"]
        fid = os.path.basename(png_rel).split(".")[0]
        png_out = os.path.join(self.out, png_rel)
        old = ds.imread(png_rel, 0)
        downloaded, note = 0, ""
        if self.needs_download(conversion):
            location = self.locations.get(fid)
            if location is None:
                raise LookupError(f"{fid} is not in the PDS index")
            img = png_out[:-4] + ".IMG"
            downloaded = fetch(f"{PDS}/{series_of(location)}/{location}", img)
            try:
                image, prefixes = read_img(img)
            finally:
                os.remove(img)
            codes = encode(image, conversion)
            save_prefix(prefixes, png_out[:-4] + ".prefix.gz")
            source = "raw"
        elif conversion == "TABLE":
            codes = cal.unstretch(old.astype(np.float64), frame["info"])
            if cal.recover_span(old.astype(np.float64)) is None:
                note = "span not recovered; assumed 254"
            codes = np.clip(codes, 0, 255).astype(np.uint8)
            source = "png"
        else:
            codes, source, note = old, "old png", "8LSB: copied"
        if old is not None and codes.shape != old.shape:
            raise ValueError(f"{fid}: new frame is {codes.shape}, old PNG is {old.shape}")
        save_png(codes, png_out)
        self.record(id=fid, conversion=conversion, source=source, lines=codes.shape[0], samples=codes.shape[1],
                    bytes_downloaded=downloaded, png_bytes=os.path.getsize(png_out), note=note)
        return downloaded


def label_path(png_rel):
    return png_rel.rsplit(".", 1)[0] + ".LBL"  # labels sit next to their PNGs


def plan(out, years, limit):
    index = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Image_index.csv"),
                        usecols=["path", "year"])
    if years:
        index = index[index["year"].isin(years)]
    frames = []
    for png_rel in index["path"]:
        if limit and len(frames) >= limit:
            break
        if os.path.exists(os.path.join(out, png_rel)):
            continue
        lbl_rel = label_path(png_rel)
        try:
            text = ds.read_text(lbl_rel)
        except FileNotFoundError:
            continue  # ~450 frames are indexed but missing from the drive
        lbl_out = os.path.join(out, lbl_rel)
        os.makedirs(os.path.dirname(lbl_out), exist_ok=True)
        if not os.path.exists(lbl_out):
            with open(lbl_out, "w", encoding="latin-1") as f:
                f.write(text)
        info = {}
        for line in text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info.setdefault(key.strip(), value.strip().replace('"', ""))
        frames.append({"png": png_rel, "conversion": info.get("DATA_CONVERSION_TYPE", ""), "info": info})
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("--years", type=float, nargs="*")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many frames (for testing)")
    parser.add_argument("--table", choices=["raw", "png"], default="raw", help="where TABLE frames come from")
    parser.add_argument("--downloads", type=int, default=4, help="parallel downloads (NASA throttles above ~4)")
    parser.add_argument("--dry-run", action="store_true", help="count what would be done and stop")
    args = parser.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    for folder in ("nac_data", "wac_data"):
        os.makedirs(os.path.join(out, folder), exist_ok=True)
        # data_source.lut8 looks for this to know the PNGs hold codes
        with open(os.path.join(out, folder, "FORMAT.txt"), "w") as f:
            f.write(FORMAT)

    frames = plan(out, args.years, args.limit)
    converter = Converter(out, args.table)
    counts = pd.Series([f["conversion"] for f in frames]).value_counts().to_dict() if frames else {}
    downloads = sum(converter.needs_download(f["conversion"]) for f in frames)
    print(f"{len(frames)} frames to do {counts}, {downloads} to download", flush=True)
    if args.dry_run or not frames:
        return
    if downloads:
        converter.locations = pds_locations(out)

    start, done, failed, total_bytes = time.time(), 0, 0, 0
    errors = open(os.path.join(out, "errors.txt"), "a")
    with ThreadPoolExecutor(max(1, args.downloads)) as pool:
        futures = {pool.submit(converter.convert, f): f for f in frames}
        for future in as_completed(futures):
            frame = futures[future]
            try:
                total_bytes += future.result()
                done += 1
            except Exception as e:
                failed += 1
                errors.write(f"{frame['png']}\t{type(e).__name__}: {e}\n")
                errors.flush()
            if (done + failed) % 100 == 0 or done + failed == len(frames):
                elapsed = time.time() - start
                rate = total_bytes / max(elapsed, 1e-9) / 1e6
                left = (len(frames) - done - failed) * elapsed / (done + failed)
                print(f"{done + failed}/{len(frames)} done, {failed} failed, {total_bytes / 1e9:.2f} GB at "
                      f"{rate:.1f} MB/s, about {left / 3600:.1f} h left", flush=True)
    print(f"Finished: {done} converted, {failed} failed (see errors.txt; rerun to retry them)")


if __name__ == "__main__":
    main()
