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

With --add-missing, frames the drive is missing are downloaded too, label included:
indexed frames whose files are gone, and frames that are in NASA's index but not in
Image_index.csv (for example the days lost from volumes COISS_2009 to COISS_2022).
New frames are listed in <out>/Image_index_added.csv, to be merged into Image_index.csv.

The raw IMG is deleted once converted, so only a few files sit on disk at a time.
It never writes to the old data, so the render pipeline can keep using it while this
runs. Frames already in <out> are skipped, so it can be stopped and restarted.

Usage (from the main folder, with the old data as CASSINI_DATA as usual):
    python "helper programs/convert_archive.py" OUT [--years 2002 2003] [--limit N]
        [--table raw|png] [--downloads 4] [--dry-run] [--add-missing [--volumes COISS_2009 ...]]
"""
import argparse
import csv
import datetime
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
                # read(n) returns b"" when the server drops the connection, so a cut
                # short download only shows up as the wrong size
                expected = r.headers.get("Content-Length")
                if expected is not None and f.tell() != int(expected):
                    raise IOError(f"{url}: got {f.tell()} of {expected} bytes")
            os.replace(path + ".part", path)
            return os.path.getsize(path)
        except Exception as e:
            if attempt == tries - 1:
                raise
            wait = 2 ** (attempt + 1)
            if getattr(e, "code", None) == 429:
                # NASA throttles in bursts; a few seconds isn't enough to get past one
                after = str(e.headers.get("Retry-After") or "")
                wait = max(wait * 15, int(after) if after.isdigit() else 0)
            time.sleep(wait)


"""
NASA's index of every frame: {"W1234567890_1": {"location": "COISS_2001/data/.../W1234567890_1.IMG",
"VOLUME_ID": ..., "FILTER_NAME": "CL1,RED", ...}}. The tables are downloaded once into
<out>/pds_index.
"""
INDEX_COLUMNS = ["FILE_NAME", "FILE_SPECIFICATION_NAME", "VOLUME_ID", "DATA_CONVERSION_TYPE", "FILTER_NAME",
                 "IMAGE_MID_TIME", "INSTRUMENT_ID", "MISSING_LINES", "OBSERVATION_ID", "TARGET_DESC", "TARGET_NAME"]

def pds_index(out, full=True):
    folder = os.path.join(out, "pds_index")
    os.makedirs(folder, exist_ok=True)
    frames = {}
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
        spans = {k: cols[k] for k in INDEX_COLUMNS}
        with open(tab, encoding="latin-1") as f:
            for line in f:
                row = {k: line[s:s + n].replace('"', "").strip() for k, (s, n) in spans.items()}
                row["FILTER_NAME"] = ",".join(x.strip() for x in row["FILTER_NAME"].split(","))
                row["location"] = f"{row['VOLUME_ID']}/{row['FILE_SPECIFICATION_NAME']}"
                if not full:  # ~400k rows: keep memory down when the rest isn't needed
                    row = {k: row[k] for k in ("location", "VOLUME_ID", "DATA_CONVERSION_TYPE")}
                frames[row["location"].split("/")[-1].split(".")[0]] = row
    return frames


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
    def __init__(self, out, table_source, add_missing=False):
        self.out = out
        self.add_missing = add_missing
        self.table_source = table_source
        self.lock = threading.Lock()
        # data_source shares one zip file handle per process, so reads must not overlap
        self.read_lock = threading.Lock()
        self.pds = None
        path = os.path.join(out, "manifest.csv")
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        self.manifest = open(path, "a", newline="")
        self.writer = csv.DictWriter(self.manifest, MANIFEST_FIELDS)
        if new:
            self.writer.writeheader()
            self.manifest.flush()  # a run stopped before its first frame still leaves the header

    def record(self, **row):
        with self.lock:
            self.writer.writerow(row)
            self.manifest.flush()

    def needs_download(self, frame):
        conversion = frame["conversion"]
        return frame.get("missing") or conversion == "12BIT" or (conversion == "TABLE" and self.table_source == "raw")

    def download(self, fid, png_out, ext):
        row = self.pds.get(fid)
        if row is None:
            raise LookupError(f"{fid} is not in the PDS index")
        location = row["location"][:-4] + ext
        return fetch(f"{PDS}/{series_of(location)}/{location}", png_out[:-4] + ext)

    def convert(self, frame):
        png_rel = frame["png"]
        fid = os.path.basename(png_rel).split(".")[0]
        png_out = os.path.join(self.out, png_rel)
        downloaded, note = 0, ""
        lbl_rel = label_path(png_rel)
        lbl_out = os.path.join(self.out, lbl_rel)
        old = None
        if not frame.get("missing"):
            try:
                with self.read_lock:
                    text = ds.read_text(lbl_rel)
            except FileNotFoundError:
                if not self.add_missing:
                    raise FileNotFoundError(f"{lbl_rel} isn't on the drive (rerun with --add-missing to fetch it)")
                frame["missing"] = True  # indexed, but its files aren't on the drive
            else:
                if not os.path.exists(lbl_out):
                    with open(lbl_out + ".tmp", "w", encoding="latin-1") as f:
                        f.write(text)
                    os.replace(lbl_out + ".tmp", lbl_out)
                frame["info"] = parse_label(text)
                with self.read_lock:
                    old = ds.imread(png_rel, 0)
                if old is None:
                    raise ValueError(f"couldn't read {png_rel}")
        if frame.get("missing"):
            # not on the drive: the label comes from NASA too
            downloaded += self.download(fid, png_out, ".LBL")
            frame["info"] = parse_label(open(lbl_out, encoding="latin-1").read())
        frame["conversion"] = frame["info"].get("DATA_CONVERSION_TYPE", "")
        conversion = frame["conversion"]
        if self.needs_download(frame):
            img = png_out[:-4] + ".IMG"
            downloaded += self.download(fid, png_out, ".IMG")
            try:
                image, prefixes = read_img(img)
            finally:
                os.remove(img)
            if conversion in ("12BIT", "TABLE"):
                codes = encode(image, conversion)
            else:
                # 8LSB: only the low 8 bits were sent; stretched like the old PNGs
                codes = cal.display_stretch(image.astype(np.uint8), {"DATA_CONVERSION_TYPE": "TABLE"})
                note = "8LSB: stretched"
            save_prefix(prefixes, png_out[:-4] + ".prefix.gz")
            source = "new from PDS" if frame.get("missing") else "raw"
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
        if frame.get("index_row"):
            self.add_index_row(frame["index_row"])
        self.record(id=fid, conversion=conversion, source=source, lines=codes.shape[0], samples=codes.shape[1],
                    bytes_downloaded=downloaded, png_bytes=os.path.getsize(png_out), note=note)
        return downloaded

    def add_index_row(self, row):
        path = os.path.join(self.out, "Image_index_added.csv")
        with self.lock:
            new = not os.path.exists(path)
            with open(path, "a", newline="") as f:
                writer = csv.DictWriter(f, ADDED_INDEX_FIELDS)
                if new:
                    writer.writeheader()
                writer.writerow(row)


def label_path(png_rel):
    return png_rel.rsplit(".", 1)[0] + ".LBL"  # labels sit next to their PNGs


def parse_label(text):
    info = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            info.setdefault(key.strip(), value.strip().replace('"', ""))
    return info


ADDED_INDEX_FIELDS = ["FILTER_NAME", "IMAGE_MID_TIME", "INSTRUMENT_ID", "MISSING_LINES", "OBSERVATION_ID",
                      "TARGET_DESC", "TARGET_NAME", "filter1", "filter2", "path", "seconds_1970", "year"]

"""
An Image_index.csv row for a frame that is only in NASA's index
"""
def index_row(fid, row):
    mid = datetime.datetime.strptime(row["IMAGE_MID_TIME"][:17], "%Y-%jT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    filters = row["FILTER_NAME"].split(",")
    return {"FILTER_NAME": f"({row['FILTER_NAME']})", "IMAGE_MID_TIME": row["IMAGE_MID_TIME"],
            "INSTRUMENT_ID": row["INSTRUMENT_ID"], "MISSING_LINES": row["MISSING_LINES"],
            "OBSERVATION_ID": row["OBSERVATION_ID"], "TARGET_DESC": row["TARGET_DESC"],
            "TARGET_NAME": row["TARGET_NAME"], "filter1": filters[0], "filter2": filters[-1],
            "path": data_folder(fid) + "/" + fid + ".png", "seconds_1970": float(int(mid.timestamp())),
            "year": float(mid.year)}


def data_folder(fid):
    return "nac_data" if fid.startswith("N") else "wac_data"


"""
The frames to convert. Frames the drive is missing are fetched from NASA when
add_missing is set: indexed ones whose files are gone, and, for the given volumes,
frames that aren't in Image_index.csv at all (added to Image_index_added.csv).
"""
def plan(out, years, limit, add_missing=False, volumes=None, pds=None):
    index = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Image_index.csv"),
                        usecols=["path", "year"])
    known = set(os.path.basename(p).split(".")[0] for p in index["path"].dropna())
    if years:
        index = index[index["year"].isin(years)]
    # one listing per folder: a stat per frame takes hours on a busy external drive
    done = set()
    for folder in ("nac_data", "wac_data"):
        if os.path.isdir(os.path.join(out, folder)):
            done.update(f"{folder}/{name}" for name in os.listdir(os.path.join(out, folder)) if name.endswith(".png"))
    frames = []
    for png_rel in index["path"].dropna():
        if limit and len(frames) >= limit:
            break
        if png_rel in done:
            continue
        # the label is read when the frame is converted (in parallel); the type here is
        # NASA's, for counting
        fid = os.path.basename(png_rel).split(".")[0]
        row = pds.get(fid) if pds else None
        frames.append({"png": png_rel, "conversion": row["DATA_CONVERSION_TYPE"] if row else ""})
    if add_missing and pds is not None:
        for fid, row in pds.items():
            if limit and len(frames) >= limit:
                break
            if fid in known or (volumes and row["VOLUME_ID"] not in volumes):
                continue
            new = index_row(fid, row)
            if (years and new["year"] not in years) or new["path"] in done:
                continue
            frames.append({"png": new["path"], "conversion": row["DATA_CONVERSION_TYPE"], "missing": True,
                           "index_row": new})
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("--years", type=float, nargs="*")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many frames (for testing)")
    parser.add_argument("--table", choices=["raw", "png"], default="raw", help="where TABLE frames come from")
    parser.add_argument("--downloads", type=int, default=4, help="parallel downloads (NASA throttles above ~4)")
    parser.add_argument("--dry-run", action="store_true", help="count what would be done and stop")
    parser.add_argument("--add-missing", action="store_true",
                        help="also fetch frames the drive is missing (labels too), adding new ones to Image_index_added.csv")
    parser.add_argument("--volumes", nargs="*", help="with --add-missing: only add unindexed frames from these "
                        "PDS volumes, e.g. COISS_2009 COISS_2010")
    args = parser.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    for folder in ("nac_data", "wac_data"):
        os.makedirs(os.path.join(out, folder), exist_ok=True)
        # data_source.lut8 looks for this to know the PNGs hold codes
        with open(os.path.join(out, folder, "FORMAT.txt"), "w") as f:
            f.write(FORMAT)

    converter = Converter(out, args.table, args.add_missing)
    # NASA's index says where each frame is and (for the counts below) its type
    converter.pds = pds_index(out, full=args.add_missing)
    frames = plan(out, args.years, args.limit, args.add_missing, args.volumes, converter.pds)
    counts = pd.Series([f["conversion"] or "?" for f in frames]).value_counts().to_dict() if frames else {}
    downloads = sum(bool(converter.needs_download(f)) for f in frames)
    missing = sum(bool(f.get("missing")) for f in frames)
    print(f"{len(frames)} frames to do {counts}, about {downloads} to download "
          f"({missing} not in Image_index.csv)", flush=True)
    if args.dry_run or not frames:
        return

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
