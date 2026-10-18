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
"""
import os
import re
import shutil
import zipfile

import cv2
import numpy as np

try:
    # Windows' built in zip tool can use Deflate64, which zipfile can't read on its own
    import zipfile_deflate64  # noqa: F401
except ImportError:
    pass


wd = os.getcwd()
SPICE_CACHE = os.environ.get("CASSINI_SPICE_CACHE", os.path.join(wd, "spice_cache"))
KEEP_SPICE_CACHE = os.environ.get("CASSINI_KEEP_SPICE_CACHE", "").lower() in ("1", "true", "yes")

DATA_FOLDERS = {"nac_data", "nac_labels", "wac_data", "wac_labels", "cosp_1000"}

_source = None
_zip = None
_members = None


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


def using_zip():
    return get_source().lower().endswith(".zip")


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
Opens the zip and indexes its members by their path inside the data folder. Keys are
lower case because the program was written on case insensitive file systems
(labels are referred to as .lbl while the files may be .LBL).
"""
def _zip_members():
    global _zip, _members
    if _members is None:
        print(f"Indexing {get_source()}...")
        _zip = zipfile.ZipFile(get_source())
        _members = {}
        for info in _zip.infolist():
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
            _members["/".join(parts).lower()] = info
        print(f"Done! {len(_members)} files")
    return _members


def _zip_info(path):
    info = _zip_members().get(relative(path).lower())
    if info is None:
        raise FileNotFoundError(f"{path} is not in {get_source()}")
    return info


_folder_listings = {}

def _folder_path(path):
    if os.path.exists(path):
        return path
    path = os.path.join(get_source(), relative(path))
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
    if using_zip():
        return relative(path).lower() in _zip_members()
    return os.path.exists(_folder_path(path))


def read_bytes(path):
    if using_zip():
        info = _zip_info(path)
        return _zip.read(info)
    with open(_folder_path(path), "rb") as f:
        return f.read()


def read_text(path):
    return read_bytes(path).decode("latin-1")


"""
Same as cv2.imread but works for images inside the zip
"""
def imread(path, flags=cv2.IMREAD_COLOR):
    if not using_zip():
        return cv2.imread(_folder_path(path), flags)
    data = np.frombuffer(read_bytes(path), dtype=np.uint8)
    return cv2.imdecode(data, flags)


"""
Lists the file names directly inside a folder of the data (like os.listdir)
"""
def listdir(path):
    if not using_zip():
        return os.listdir(_folder_path(path))
    prefix = relative(path).rstrip("/").lower() + "/"
    names = []
    for key, info in _zip_members().items():
        if key.startswith(prefix) and "/" not in key[len(prefix):]:
            names.append(info.filename.replace("\\", "/").split("/")[-1])
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
    info = _zip_info(path)
    out = os.path.join(SPICE_CACHE, relative(path))
    if not os.path.exists(out) or os.path.getsize(out) != info.file_size:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # the part file is named after the process so parallel workers never write into
        # each other's copy; whoever finishes last replaces an identical file
        part = f"{out}.{os.getpid()}.part"
        with _zip.open(info) as src, open(part, "wb") as dst:
            shutil.copyfileobj(src, dst, 16 * 1024 * 1024)
        os.replace(part, out)
    return out


"""
Extracts every kernel a meta-kernel lists into the cache without loading them, so the
parallel workers find them ready instead of all extracting the same files at once
"""
def extract_metakernel(path):
    if not using_zip():
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
    if not using_zip():
        sp.furnsh(_folder_path(path))
        return
    for kernel in metakernel_kernels(read_text(path)):
        sp.furnsh(extract_to_cache(kernel_relative(kernel)))


"""
Deletes the extracted kernels (call after spiceypy.kclear)
"""
def clear_spice_cache():
    if using_zip() and not KEEP_SPICE_CACHE and os.path.isdir(SPICE_CACHE):
        # ignore_errors: on Windows a kernel a worker still has open can't be deleted yet
        shutil.rmtree(SPICE_CACHE, ignore_errors=True)
