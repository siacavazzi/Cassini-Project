# -*- coding: utf-8 -*-
"""
Reads Cassini data either from an unzipped data folder or straight out of data.zip,
so the 97 GB archive never has to be extracted.

Where the data comes from:
* CASSINI_DATA environment variable, if set (path to a data folder or a .zip file)
* otherwise a folder called "data" in the main folder
* otherwise "data.zip" in the main folder

Images and labels are read from the zip in memory. SPICE can only load kernels from
real files, so the kernels for the year being processed are extracted into a small
cache folder and deleted again when the kernels are unloaded.

The lean archive (cassini_lut8.zip) has no SPICE kernels. CASSINI_KERNELS (a data folder
or .zip that has cosp_1000, e.g. the original archive) is where cosp_1000/... is read
from then; everything else still comes from CASSINI_DATA.
"""
import os
import re
import shutil
import struct
import threading
import zipfile
import zlib

import cv2
import numpy as np

try:
    # Windows' built in zip tool can use Deflate64, which zipfile can't read on its own
    import zipfile_deflate64  # noqa: F401
except ImportError:
    pass


wd = os.getcwd()
SPICE_CACHE = os.environ.get("CASSINI_SPICE_CACHE", os.path.join(wd, "spice_cache"))
INDEX_CACHE = os.environ.get("CASSINI_INDEX_CACHE", os.path.join(wd, "zip_index"))
KEEP_SPICE_CACHE = os.environ.get("CASSINI_KEEP_SPICE_CACHE", "").lower() in ("1", "true", "yes")

DATA_FOLDERS = {"nac_data", "nac_labels", "wac_data", "wac_labels", "cosp_1000"}

_source = None
_kernel_source = None
_indexes = {}


"""
Works out where the data lives. Called lazily so importing this module never fails.
"""
def get_source():
    global _source
    if _source is None:
        env = os.environ.get("CASSINI_DATA")
        if env:
            _source = env
        elif os.path.isdir(os.path.join(wd, "data")):
            _source = os.path.join(wd, "data")
        elif os.path.isfile(os.path.join(wd, "data.zip")):
            _source = os.path.join(wd, "data.zip")
        else:
            raise FileNotFoundError("No Cassini data found: put the data folder or data.zip in the main folder, or set CASSINI_DATA")
    return _source


"""
Where the SPICE kernels (cosp_1000/...) come from: CASSINI_KERNELS, or the data itself
"""
def get_kernel_source():
    global _kernel_source
    if _kernel_source is None:
        _kernel_source = os.environ.get("CASSINI_KERNELS") or get_source()
    return _kernel_source


"""
The source a path is read from: the kernel source for cosp_1000/..., the data otherwise
"""
def source_of(path):
    if relative(path).lower().startswith("cosp_1000/"):
        return get_kernel_source()
    return get_source()


def using_zip(source=None):
    return (source or get_source()).lower().endswith(".zip")


"""
Turns any path the program uses ("data/wac_data/x.png", "wac_data/x.png", an absolute
path, Windows slashes...) into a path relative to the data folder.
"""
def relative(path):
    path = str(path).replace("\\", "/")
    root = wd.replace("\\", "/").rstrip("/") + "/"
    if path.startswith(root):
        path = path[len(root):]
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("data/"):
        path = path[len("data/"):]
    return path.lstrip("/")


"""
Index of the zip's members: their paths inside the data folder (lower case, sorted),
their names in the zip, and where their data sits in the zip file. Keys are lower case
because the program was written on case insensitive file systems (labels are referred
to as .lbl while the files may be .LBL).

Reading the zip's own directory takes a while and ~1 GB of memory for the full dataset,
so the index is saved as plain arrays in the INDEX_CACHE folder the first time and then
memory mapped. Every process (including the parallel workers) shares the one copy the
operating system keeps in memory, and later runs skip the indexing.
"""
INDEX_FIELDS = ["keys", "names", "offsets", "compressed", "sizes", "methods"]

def _index_folder(source):
    stat = os.stat(source)
    name = os.path.basename(source)
    return os.path.join(INDEX_CACHE, f"{name}-{stat.st_size}-{int(stat.st_mtime)}")


def _build_index(folder, source):
    print(f"Indexing {source}...")
    members = {}
    with zipfile.ZipFile(source) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("__MACOSX/"):
                continue
            parts = name.split("/")
            # drop whatever folders the data sits in ("data/", "cassini/"...), so paths
            # start at one of the data folders
            roots = [i for i, part in enumerate(parts[:-1]) if part.lower() in DATA_FOLDERS]
            if roots:
                parts = parts[roots[0]:]
            elif "data" in parts[:-1]:
                parts = parts[parts.index("data") + 1:]
            members["/".join(parts).lower()] = (info.filename, info.header_offset, info.compress_size, info.file_size, info.compress_type)
    keys = sorted(members)
    rows = [members[key] for key in keys]
    arrays = {
        "keys": np.array([key.encode("utf-8") for key in keys]),
        "names": np.array([row[0].encode("utf-8") for row in rows]),
        "offsets": np.array([row[1] for row in rows], dtype=np.int64),
        "compressed": np.array([row[2] for row in rows], dtype=np.int64),
        "sizes": np.array([row[3] for row in rows], dtype=np.int64),
        "methods": np.array([row[4] for row in rows], dtype=np.int16),
    }
    # written to a temporary folder and renamed, so a half written index is never used
    part = f"{folder}.{os.getpid()}.part"
    os.makedirs(part, exist_ok=True)
    for field in INDEX_FIELDS:
        np.save(os.path.join(part, field + ".npy"), arrays[field])
    try:
        os.rename(part, folder)
    except OSError:
        shutil.rmtree(part, ignore_errors=True)  # another process finished first
    # indexes of older versions of this zip are no longer needed
    prefix = os.path.basename(source) + "-"
    for old in os.listdir(INDEX_CACHE):
        if old.startswith(prefix) and os.path.join(INDEX_CACHE, old) != folder and not old.endswith(".part"):
            shutil.rmtree(os.path.join(INDEX_CACHE, old), ignore_errors=True)
    print(f"Done! {len(keys)} files")


_index_lock = threading.Lock()

def _zip_index(source=None):
    source = source or get_source()
    if source not in _indexes:
        # threads of one process (the frame server's) build or load it once, not each their own
        with _index_lock:
            if source not in _indexes:
                folder = _index_folder(source)
                if not os.path.isdir(folder):
                    _build_index(folder, source)
                _indexes[source] = {field: np.load(os.path.join(folder, field + ".npy"), mmap_mode="r") for field in INDEX_FIELDS}
    return _indexes[source]


"""
Position of a member in the index, or None if it isn't in the zip
"""
def _find(path):
    keys = _zip_index(source_of(path))["keys"]
    key = relative(path).lower().encode("utf-8")
    i = int(np.searchsorted(keys, key))
    if i < len(keys) and keys[i] == key:
        return i
    return None


def _find_existing(path):
    i = _find(path)
    if i is None:
        raise FileNotFoundError(f"{path} is not in {source_of(path)}")
    return i


"""
The zip file opened by this process (reopened after a fork, so processes never share
a file position)
"""
_files = {}

def _zip_file(source=None):
    source = source or get_source()
    f, pid = _files.get(source, (None, None))
    if f is None or pid != os.getpid():
        f = open(source, "rb")
        _files[source] = (f, os.getpid())
    return f


"""
size bytes of the open file f from offset on. pread doesn't use the file's position, so
threads (the frame server's) and paused generators can read the one file at the same time
without taking turns. Where there is no pread (Windows) they take turns seeking.
"""
_seek_lock = threading.Lock()

def _read_at(f, size, offset):
    if hasattr(os, "pread"):
        return os.pread(f.fileno(), size, offset)
    with _seek_lock:
        f.seek(offset)
        return f.read(size)


"""
Yields the uncompressed data of member i in chunks
"""
def _member_chunks(i, chunk_size=16 * 1024 * 1024, source=None):
    source = source or get_source()
    index = _zip_index(source)
    method = int(index["methods"][i])
    if method not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        # anything else (Deflate64...) goes through zipfile, which has to read the
        # whole zip directory first
        with zipfile.ZipFile(source) as z, z.open(index["names"][i].decode("utf-8")) as src:
            while True:
                data = src.read(chunk_size)
                if not data:
                    return
                yield data
    f = _zip_file(source)
    # the local header before the data has its own name and extra field lengths
    position = int(index["offsets"][i])
    header = _read_at(f, 30, position)
    if header[:4] != b"PK\x03\x04":
        raise zipfile.BadZipFile(f"Bad local header for {index['names'][i]}")
    name_length, extra_length = struct.unpack("<HH", header[26:30])
    position += 30 + name_length + extra_length
    remaining = int(index["compressed"][i])
    inflate = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    while remaining > 0:
        data = _read_at(f, min(chunk_size, remaining), position)
        if not data:
            raise zipfile.BadZipFile(f"{index['names'][i]} is cut short")
        remaining -= len(data)
        position += len(data)
        yield inflate.decompress(data) if inflate else data
    if inflate:
        yield inflate.flush()


def _read_member(i, source=None):
    index = _zip_index(source)
    data = b"".join(_member_chunks(i, source=source))
    if len(data) != int(index["sizes"][i]):
        raise zipfile.BadZipFile(f"{index['names'][i]} has the wrong size")
    return data


_folder_listings = {}

def _folder_path(path):
    if os.path.exists(path):
        return path
    path = os.path.join(source_of(path), relative(path))
    if os.path.exists(path):
        return path
    # case insensitive fallback (.lbl vs .LBL) for case sensitive file systems
    folder, name = os.path.split(path)
    if folder not in _folder_listings:
        try:
            _folder_listings[folder] = {f.lower(): f for f in os.listdir(folder)}
        except OSError:
            _folder_listings[folder] = {}
    return os.path.join(folder, _folder_listings[folder].get(name.lower(), name))


def exists(path):
    if using_zip(source_of(path)):
        return _find(path) is not None
    return os.path.exists(_folder_path(path))


def read_bytes(path):
    source = source_of(path)
    if using_zip(source):
        return _read_member(_find_existing(path), source)
    with open(_folder_path(path), "rb") as f:
        return f.read()


def read_text(path):
    return read_bytes(path).decode("latin-1")


"""
True when the data is the lean archive made by helper programs/convert_archive.py,
whose PNGs hold the camera's 8-bit codes instead of a per frame stretch
"""
_lut8 = None

def lut8():
    global _lut8
    if _lut8 is None:
        _lut8 = exists("wac_data/FORMAT.txt") or exists("nac_data/FORMAT.txt")
    return _lut8


"""
Same as cv2.imread but works for images inside the zip
"""
def imread(path, flags=cv2.IMREAD_COLOR):
    if not using_zip(source_of(path)):
        return cv2.imread(_folder_path(path), flags)
    data = np.frombuffer(read_bytes(path), dtype=np.uint8)
    return cv2.imdecode(data, flags)


"""
Lists the file names directly inside a folder of the data (like os.listdir)
"""
def listdir(path):
    source = source_of(path)
    if not using_zip(source):
        return os.listdir(_folder_path(path))
    index = _zip_index(source)
    prefix = (relative(path).rstrip("/").lower() + "/").encode("utf-8")
    # the keys are sorted, so everything inside the folder is one run of them
    start = int(np.searchsorted(index["keys"], prefix))
    end = int(np.searchsorted(index["keys"], prefix + b"\xff"))
    names = []
    for i in range(start, end):
        if b"/" not in index["keys"][i][len(prefix):]:
            names.append(index["names"][i].decode("utf-8").replace("\\", "/").split("/")[-1])
    return sorted(names)


"""
Pulls the kernel paths out of a SPICE meta-kernel (the files in cosp_1000/index).
Handles $SYMBOL paths and strings continued onto the next line with '+'.
"""
def metakernel_kernels(text):
    data = []
    in_data = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("\\begindata"):
            in_data = True
        elif stripped.startswith("\\begintext"):
            in_data = False
        elif in_data:
            data.append(line)
    data = "\n".join(data)

    match = re.search(r"KERNELS_TO_LOAD\s*\+?=\s*\((.*?)\)", data, re.S)
    if match is None:
        return []
    kernels = []
    pending = ""
    for value in re.findall(r"'((?:[^']|'')*)'", match.group(1)):
        value = value.replace("''", "'")
        if value.endswith("+"):
            pending += value[:-1]
            continue
        kernels.append(pending + value)
        pending = ""
    return kernels


"""
Maps a kernel path from a meta-kernel to its path inside the data folder. Kernels are
written as $SYMBOL/ck/x.bc, SPICE_PATH/ck/x.bc or a full path ending in cosp_1000/data/ck/x.bc.
"""
def kernel_relative(kernel):
    kernel = kernel.replace("\\", "/")
    if "cosp_1000/data/" in kernel:
        return "cosp_1000/data/" + kernel.split("cosp_1000/data/", 1)[1]
    kernel = re.sub(r"^(\$\w+|SPICE_PATH)/", "", kernel)
    return "cosp_1000/data/" + kernel.lstrip("/")


"""
Extracts one file from the zip into the SPICE cache and returns where it was put
"""
def extract_to_cache(path):
    i = _find_existing(path)
    source = source_of(path)
    out = os.path.join(SPICE_CACHE, relative(path))
    if not os.path.exists(out) or os.path.getsize(out) != int(_zip_index(source)["sizes"][i]):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # the part file is named after the process so parallel workers never write into
        # each other's copy; whoever finishes last replaces an identical file
        part = f"{out}.{os.getpid()}.part"
        with open(part, "wb") as dst:
            for data in _member_chunks(i, source=source):
                dst.write(data)
        os.replace(part, out)
    return out


"""
Extracts every kernel a meta-kernel lists into the cache without loading them, so the
parallel workers find them ready instead of all extracting the same files at once
"""
def extract_metakernel(path):
    if not using_zip(get_kernel_source()):
        return
    for kernel in metakernel_kernels(read_text(path)):
        extract_to_cache(kernel_relative(kernel))


"""
Loads a SPICE meta-kernel. From a folder this is just furnsh (create_spice_index must
have been run). From the zip, every kernel it lists is extracted to the cache and
loaded in the same order, so later kernels still take priority.
"""
def furnsh_metakernel(path):
    import spiceypy as sp
    if not using_zip(get_kernel_source()):
        sp.furnsh(_folder_path(path))
        return
    for kernel in metakernel_kernels(read_text(path)):
        sp.furnsh(extract_to_cache(kernel_relative(kernel)))


"""
Deletes the extracted kernels (call after spiceypy.kclear)
"""
def clear_spice_cache():
    if using_zip(get_kernel_source()) and not KEEP_SPICE_CACHE and os.path.isdir(SPICE_CACHE):
        # ignore_errors: on Windows a kernel a worker still has open can't be deleted yet
        shutil.rmtree(SPICE_CACHE, ignore_errors=True)
