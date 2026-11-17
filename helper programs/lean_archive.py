#!/usr/bin/env python3
"""
Makes a lean copy of the 8-bit archive (cassini_lut8.zip) that leaves out the PNG of every frame the 12-bit originals
(CASSINI_ORIGINALS, the orig12 folder) cover, and checks it. About 206,000 12BIT frames, 28 of the archive's 73 GB.

Each left out PNG becomes a stub of a few bytes (data_source.lean_stub), and the pipeline makes the frame's codes again
from its original (data_source.lean_codes), exactly as helper programs/convert_archive.py made them. A frame is
stubbed only when that gives its PNG's pixels exactly (and its PNG is plain 8-bit gray, as data_source.imread wants),
so reading the lean archive gives every frame as the full one does. Everything else (labels, prefixes, other PNGs,
FORMAT.txt, the manifests) is copied byte for byte. The existing archive is only read, never changed: the lean archive
is a new file, written as <out>.part and renamed when complete.

  python "helper programs/lean_archive.py" build  --data cassini_lut8.zip --originals orig12 --out cassini_lut8_lean.zip
  python "helper programs/lean_archive.py" verify --data cassini_lut8.zip --originals orig12 --lean cassini_lut8_lean.zip

--frames FILE (frame ids, one a line) only considers those frames; with --subset the new archive then holds only their
members (and the archive's own files), a small trial archive. verify checks the lean archive against the full one:
every member there, kept members with the same size and CRC, every stub read through data_source (imread both ways,
read_bytes) equal to the full archive's PNG; --deep also re-reads every kept member's bytes.
Workers: --workers N (run it through ~/agents/bin/heavy -n N).
"""
import argparse
import multiprocessing
import os
import shutil
import sys
import time
import zipfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FOLDERS = ("nac_data/", "wac_data/")
ds = None


def setup(data, originals):
    """data_source reads CASSINI_DATA and CASSINI_ORIGINALS when it is imported"""
    global ds
    os.environ["CASSINI_DATA"] = os.path.abspath(data)
    os.environ["CASSINI_ORIGINALS"] = os.path.abspath(originals)
    os.environ.setdefault("CASSINI_INDEX_CACHE", os.path.join(os.path.dirname(os.path.abspath(data)), "zip_index"))
    sys.path.insert(0, REPO)
    import data_source
    ds = data_source
    return ds


def frame_png(name):
    """'nac_data/N1234567890_1.png' (the archive's path, lower-cased folders) for a frame PNG member, else None"""
    rel = ds.relative(name.replace("\\", "/"))
    for prefix in ("data/",):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    low = rel.lower()
    if low.startswith(FOLDERS) and low.endswith(".png") and low.count("/") == 1:
        return rel
    return None


def conversion(rel):
    import re
    try:
        text = ds.read_text(rel.rsplit(".", 1)[0] + ".lbl")
    except FileNotFoundError:
        return None
    m = re.search(r"DATA_CONVERSION_TYPE\s*=\s*\"?(\w+)", text)
    return m.group(1) if m else None


def decide(rel):
    """(rel, kind) when the frame's PNG can be left out (kind = its conversion), (rel, None) otherwise, (rel, why)"""
    import cv2
    import numpy as np
    try:
        kind = conversion(rel)
        if kind not in ds.LEAN_KINDS:
            return rel, None, "conversion"
        dn = ds.original_dn(rel)
        if dn is None:
            return rel, None, "no original"
        data = ds.read_bytes(rel)
        if ds.lean_stub(data) is not None or not ds._plain_gray_png(data):
            return rel, None, "not a plain gray PNG"
        stored = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        codes = ds.codes_from_original(dn, kind)
        if stored is None or stored.shape != codes.shape or not np.array_equal(stored, codes):
            return rel, None, f"{kind}: original does not give the PNG"
        return rel, kind, kind
    except Exception as e:   # anything odd keeps the PNG
        return rel, None, f"error {type(e).__name__}: {e}"


def pool(workers):
    return multiprocessing.get_context("fork").Pool(workers)


def read_frames(path):
    if not path:
        return None
    with open(path) as fh:
        return {line.strip().split(".")[0].upper() for line in fh if line.strip() and not line.startswith("#")}


def build(args):
    setup(args.data, args.originals)
    out = os.path.abspath(args.out)
    if os.path.exists(out) or os.path.realpath(out) == os.path.realpath(args.data):
        sys.exit(f"{out} exists already: the lean archive is always a new file")
    info = ds.check_originals() if not args.frames else (ds._originals_index() and dict(ds._originals_info))
    print(f"originals: {info}", flush=True)
    frames = read_frames(args.frames)
    src = zipfile.ZipFile(args.data)
    infos = [i for i in src.infolist() if not i.is_dir()]
    pngs = {}
    for i in infos:
        rel = frame_png(i.filename)
        if rel and (frames is None or os.path.basename(rel).split(".")[0].upper() in frames):
            pngs[i.filename] = rel
    covered = ds._originals_index()
    todo = sorted(rel for rel in pngs.values() if os.path.basename(rel).split(".")[0].upper() in covered)
    print(f"{len(infos)} members, {len(pngs)} frame PNGs considered, {len(todo)} with an original", flush=True)

    stubs, why, t0 = {}, {}, time.time()
    with pool(args.workers) as p:
        for n, (rel, kind, reason) in enumerate(p.imap_unordered(decide, todo, chunksize=32), 1):
            why[reason] = why.get(reason, 0) + 1
            if kind:
                stubs[rel] = kind
            if n % 5000 == 0 or n == len(todo):
                print(f"  checked {n}/{len(todo)} ({time.time() - t0:.0f} s): {why}", flush=True)
    kept_out = sum(i.file_size for i in infos if pngs.get(i.filename) in stubs)
    print(f"{len(stubs)} PNGs left out, {kept_out / 1e9:.2f} GB; kept: "
          f"{ {k: v for k, v in why.items() if k not in ds.LEAN_KINDS} }", flush=True)
    if args.dry_run:
        return

    keep = [i for i in infos if not args.subset or i.filename in pngs
            or "/" not in ds.relative(i.filename).strip("/")
            or ds.relative(i.filename).lower().endswith("format.txt")
            or os.path.basename(i.filename).split(".")[0].upper() in (frames or ())]
    need = sum(i.file_size for i in keep if pngs.get(i.filename) not in stubs) + 200 * len(keep)
    free = shutil.disk_usage(os.path.dirname(out)).free
    if free < need + args.floor_gb * 1e9:
        sys.exit(f"{os.path.dirname(out)} has {free / 1e9:.1f} GB free: the lean archive needs {need / 1e9:.1f} GB and "
                 f"{args.floor_gb} GB stays free")
    part = out + ".part"
    with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for n, i in enumerate(keep, 1):
            zi = zipfile.ZipInfo(i.filename, i.date_time)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr, zi.create_system = i.external_attr, i.create_system
            rel = pngs.get(i.filename)
            z.writestr(zi, ds.lean_stub_bytes(stubs[rel]) if rel in stubs else src.read(i))
            if n % 50000 == 0:
                print(f"  wrote {n}/{len(keep)}", flush=True)
        z.writestr("LEAN_ARCHIVE.txt",
                   f"lean copy of {os.path.basename(args.data)} ({os.path.getsize(args.data)} bytes), made by helper "
                   f"programs/lean_archive.py: {len(stubs)} frame PNGs left out (stubs, read from their 12-bit originals "
                   f"in CASSINI_ORIGINALS: data_source.lean_codes){' (subset)' if args.subset else ''}\n")
    os.replace(part, out)
    print(f"wrote {out}: {os.path.getsize(out) / 1e9:.2f} GB ({os.path.getsize(args.data) / 1e9:.2f} GB before)", flush=True)


def check_stub(item):
    """A stub of the lean archive read through data_source equals the full archive's PNG"""
    import cv2
    import numpy as np
    rel, full_i = item
    try:
        png = ds._read_member(full_i, FULL)
        want = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
        ds._decoded.clear()
        got = ds.imread(rel, cv2.IMREAD_GRAYSCALE)
        color = ds.imread(rel)
        again = cv2.imdecode(np.frombuffer(ds.read_bytes(rel), np.uint8), cv2.IMREAD_GRAYSCALE)
        ok = (got is not None and np.array_equal(got, want) and np.array_equal(again, want)
              and np.array_equal(color, cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)))
        return rel, ok, "" if ok else "pixels differ"
    except Exception as e:
        return rel, False, f"{type(e).__name__}: {e}"


FULL = None


def verify(args):
    global FULL
    import numpy as np
    setup(args.lean, args.originals)
    FULL = os.path.abspath(args.data)
    full = {i.filename: i for i in zipfile.ZipFile(args.data).infolist() if not i.is_dir()}
    lean = {i.filename: i for i in zipfile.ZipFile(args.lean).infolist() if not i.is_dir()}
    subset = "(subset)" in ds.read_text("LEAN_ARCHIVE.txt")
    problems = []
    missing = [n for n in full if n not in lean]
    extra = [n for n in lean if n not in full and n != "LEAN_ARCHIVE.txt"]
    if missing and not subset:
        problems.append(f"{len(missing)} members of the full archive are not in the lean one, e.g. {missing[:3]}")
    if extra:
        problems.append(f"{len(extra)} members are only in the lean archive, e.g. {extra[:3]}")
    keys = ds._zip_index(FULL)["keys"]
    stubs, kept = [], 0
    with zipfile.ZipFile(args.lean) as z:
        for name, i in lean.items():
            if name not in full:
                continue
            f = full[name]
            if i.file_size < 64 and f.file_size >= 64 and frame_png(name):
                data = z.read(i)
                if ds.lean_stub(data) is None:
                    problems.append(f"{name}: shorter than in the full archive and not a stub")
                    continue
                key = ds.relative(name).lower().encode("utf-8")
                at = int(np.searchsorted(keys, key))
                stubs.append((frame_png(name), at))
            elif (i.file_size, i.CRC) != (f.file_size, f.CRC):
                problems.append(f"{name}: size or CRC differs")
            else:
                kept += 1
    print(f"{len(lean)} members: {kept} kept as they were, {len(stubs)} stubs", flush=True)
    bad, t0 = 0, time.time()
    with pool(args.workers) as p:
        for n, (rel, ok, why) in enumerate(p.imap_unordered(check_stub, stubs, chunksize=32), 1):
            if not ok:
                bad += 1
                if bad <= 20:
                    problems.append(f"{rel}: {why}")
            if n % 5000 == 0 or n == len(stubs):
                print(f"  read {n}/{len(stubs)} stubs ({time.time() - t0:.0f} s), {bad} differ", flush=True)
    if bad > 20:
        problems.append(f"... {bad} stubs differ in all")
    if args.deep:
        with zipfile.ZipFile(args.lean) as z:
            broken = z.testzip()
            if broken:
                problems.append(f"{broken}: bad CRC in the lean archive")
    if problems:
        print("FAILED:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print(f"OK: the lean archive reads as the full one ({len(stubs)} frames from their originals)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, help="the full archive (cassini_lut8.zip), only read")
        p.add_argument("--originals", required=True, help="the 12-bit originals folder (orig12)")
        p.add_argument("--workers", type=int, default=2)
        if name == "build":
            p.add_argument("--out", required=True, help="the new lean archive (must not exist)")
            p.add_argument("--frames", help="only these frame ids (a file, one a line)")
            p.add_argument("--subset", action="store_true", help="with --frames: the new archive holds only them")
            p.add_argument("--dry-run", action="store_true", help="check and count, write nothing")
            p.add_argument("--floor-gb", type=float, default=40, help="GB to leave free on the out drive")
        else:
            p.add_argument("--lean", required=True)
            p.add_argument("--deep", action="store_true", help="also re-read every member's bytes (CRC)")
    args = ap.parse_args()
    if args.cmd == "build" and args.subset and not args.frames:
        ap.error("--subset needs --frames")
    {"build": build, "verify": verify}[args.cmd](args)


if __name__ == "__main__":
    main()
