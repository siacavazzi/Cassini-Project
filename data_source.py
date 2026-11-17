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
import collections
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
LOCAL_EXTRA = 64   # bytes of a local header's extra field read ahead with it (zip64 and timestamp fields are 9 to 28)


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
    # the local header before the data has its own name and extra field lengths. It is read together with the start
    # of the data (its name is the directory's, its extra field seldom more than LOCAL_EXTRA bytes), so a member is
    # one read instead of two: on the Mini's spinning disk, shared with other servers, the second was often a seek
    position = int(index["offsets"][i])
    remaining = int(index["compressed"][i])
    data = _read_at(f, 30 + len(index["names"][i]) + LOCAL_EXTRA + min(chunk_size, remaining), position)
    header = data[:30]
    if header[:4] != b"PK\x03\x04":
        raise zipfile.BadZipFile(f"Bad local header for {index['names'][i]}")
    name_length, extra_length = struct.unpack("<HH", header[26:30])
    start = 30 + name_length + extra_length
    position += start
    data = data[start:start + remaining]   # empty when the header was longer than LOCAL_EXTRA allowed for
    inflate = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    while remaining > 0:
        if not data:
            data = _read_at(f, min(chunk_size, remaining), position)
            if not data:
                raise zipfile.BadZipFile(f"{index['names'][i]} is cut short")
        remaining -= len(data)
        position += len(data)
        yield inflate.decompress(data) if inflate else data
        data = b""
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


def _stored_bytes(path):
    """The member's bytes as the archive holds them (a lean archive's stub too, lean_stub)"""
    source = source_of(path)
    if using_zip(source):
        return _read_member(_find_existing(path), source)
    with open(_folder_path(path), "rb") as f:
        return f.read()


def read_bytes(path):
    data = _stored_bytes(path)
    kind = lean_stub(data)
    if kind is not None:
        # a frame a lean archive left out: its PNG made again from its original (the same pixels; the bytes are cv2's)
        ok, png = cv2.imencode(".png", lean_codes(path, kind))
        return png.tobytes()
    return data


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
Same as cv2.imread but works for images inside the zip.
The last DECODED_KEEP plain 8-bit gray PNGs read are kept decoded, so a frame asked for again soon (a composite reads
each of its frames three times: label.resize_image in color, then its calibration and the classic guide's in gray) is
read from the zip and decoded once. Only PNGs whose gray decode is the picture as stored and whose color decode is
that gray in all three channels (8-bit gray with nothing but image data and text: the archive's), so the pixels are
what cv2.imdecode would give
"""
DECODED_KEEP = 16
_decoded = collections.OrderedDict()
_decoded_lock = threading.Lock()
# the chunks that leave a gray PNG's pixels as stored; any other (transparency, gamma, color profile, orientation)
# and the PNG is decoded as it always was
_PLAIN_CHUNKS = {b"IHDR", b"IDAT", b"IEND", b"tEXt", b"zTXt", b"iTXt", b"tIME", b"pHYs"}


def _plain_gray_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR" or len(data) < 26 or data[24] != 8 or data[25] != 0:
        return False
    at = 8
    while at + 8 <= len(data):
        kind = data[at + 4:at + 8]
        if kind not in _PLAIN_CHUNKS:
            return False
        if kind == b"IEND":
            return True
        at += 12 + int.from_bytes(data[at:at + 4], "big")
    return False


def imread(path, flags=cv2.IMREAD_COLOR):
    if not using_zip(source_of(path)):
        return cv2.imread(_folder_path(path), flags)
    if flags not in (cv2.IMREAD_COLOR, cv2.IMREAD_GRAYSCALE):
        return cv2.imdecode(np.frombuffer(read_bytes(path), dtype=np.uint8), flags)
    key = (source_of(path), relative(path).lower())
    with _decoded_lock:
        gray = _decoded.get(key)
        if gray is not None:
            _decoded.move_to_end(key)
    if gray is None:
        data = _stored_bytes(path)
        kind = lean_stub(data)
        if kind is not None:
            # (a frame a lean archive left out: lean_archive.py stubbed only frames whose PNG was plain 8-bit gray and
            # held exactly these codes, so this is what the PNG decoded to)
            gray = lean_codes(path, kind)
        elif not _plain_gray_png(data):
            return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
        else:
            gray = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return None
        # the kept picture is never handed out, only copies of it
        gray.flags.writeable = False
        with _decoded_lock:
            _decoded[key] = gray
            while len(_decoded) > DECODED_KEEP:
                _decoded.popitem(last=False)
    if flags == cv2.IMREAD_GRAYSCALE:
        return gray.copy()
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


"""
The camera's original values of a frame the lean archive could not keep at full depth, where CASSINI_ORIGINALS names
a folder of them: the PDS IMG files re-downloaded (helper programs/convert_archive.py read the same files when it made
the archive, and squeezed every 12BIT frame to 256 square-root codes, calibration.stored_values; 8LSB frames it copied
from the old stretched PNGs). The folder holds zips (one per PDS volume) and/or plain files, each frame as
<frame id>.IMG, optionally xz-compressed (<frame id>.IMG.xz), anywhere inside; read_img_bytes reads its VICAR layout.
calibration.full_values reads these in place of the stored codes.
path = the frame's path in the archive (nac_data/<ID>.png or its label), shape = its stored codes' shape: an original
of another shape is not the frame's and is left unread. Returns the image as the IMG stores it (int32: DN for 12BIT,
the low 8 bits for 8LSB, codes for TABLE), or None when there is none (no CASSINI_ORIGINALS, or not in it).
The last ORIGINALS_KEEP read are kept decoded (calibrate asks for a frame's values more than once).
"""
ORIGINALS = os.environ.get("CASSINI_ORIGINALS") or None
ORIGINALS_OFF = ORIGINALS is not None and ORIGINALS.lower() == "off"   # a deliberate build on the squeezed codes alone
ORIGINALS_VOLUMES = 125     # PDS volumes holding 12BIT and 8LSB frames (COISS_1001-1009, 2001-2116): the complete set
ORIGINALS_KEEP = 8
_originals = None
_originals_info = {}
_originals_lock = threading.Lock()
_original_zips = {}
_original_kept = collections.OrderedDict()
_ORIGINAL_NAME = re.compile(r"([NW]\d{10}_\d+)\.IMG(\.XZ)?$")


class OriginalsMissing(RuntimeError):
    pass


def _manifest_ok(path):
    """The frame ids a volume's manifest (orig12's manifest/<volume>.csv) marks ok, or None when it has none yet (the
    volume is still being written: only a volume with its manifest is complete)."""
    import csv
    if not os.path.exists(path):
        return None
    with open(path, newline="") as fh:
        return {row["fid"].upper() for row in csv.DictReader(fh) if row.get("status") == "ok"}


def _originals_index():
    global _originals
    with _originals_lock:
        if _originals is None:
            found, volumes = {}, 0
            for root, _, files in os.walk(ORIGINALS):
                for name in sorted(files):
                    full = os.path.join(root, name)
                    if name.lower().endswith(".zip"):
                        # a volume's zip counts once its manifest is written, and only its frames marked ok (an
                        # out-of-range or checksum-failed frame stays on the stored codes)
                        ok = _manifest_ok(os.path.join(os.path.dirname(root), "manifest", name[:-4] + ".csv"))
                        if ok is None:
                            continue
                        try:
                            with zipfile.ZipFile(full) as z:
                                for member in z.namelist():
                                    m = _ORIGINAL_NAME.search(os.path.basename(member).upper())
                                    if m and m.group(1) in ok:
                                        found.setdefault(m.group(1), (full, member))
                        except (zipfile.BadZipFile, OSError):
                            continue
                        volumes += 1
                    else:
                        m = _ORIGINAL_NAME.search(name.upper())
                        if m:
                            found.setdefault(m.group(1), (None, full))
            _originals = found
            _originals_info.update(frames=len(found), volumes=volumes)
            print(f"Originals: {len(found)} frames indexed from {volumes} complete volumes in {ORIGINALS}", flush=True)
    return _originals


"""
The pre-build's guard, as check_kernels: on the lean archive a build calibrates every 12BIT and 8LSB frame from its
original (calibration.full_values), so it refuses to start without CASSINI_ORIGINALS, or with fewer than
ORIGINALS_VOLUMES complete volumes in it (CASSINI_ORIGINALS_PARTIAL=1 allows that for test passes): picture versions
do not say whether originals were used, and a made picture is kept, so a cache built half on the squeezed codes would
stay so. CASSINI_ORIGINALS=off is a deliberate build on the squeezed codes (a test pass). Returns what was indexed.
"""
def check_originals():
    if not lut8():
        return None
    if ORIGINALS is None:
        raise OriginalsMissing("CASSINI_ORIGINALS is not set: the 12-bit originals (the orig12 folder) are needed for a "
                               "build; CASSINI_ORIGINALS=off builds on the squeezed codes (test passes only)")
    if ORIGINALS_OFF and lean():
        raise OriginalsMissing(f"{get_source()} is a lean archive (helper programs/lean_archive.py): its frames the "
                               f"originals cover are read from them, so CASSINI_ORIGINALS=off can't be used with it "
                               f"(use the full archive for a build on the squeezed codes)")
    if ORIGINALS_OFF:
        print("Originals: off (CASSINI_ORIGINALS=off): 12BIT frames calibrated from the archive's squeezed codes", flush=True)
        return {"frames": 0, "volumes": 0}
    _originals_index()
    if _originals_info.get("volumes", 0) < ORIGINALS_VOLUMES and lean():
        # (a lean archive's left-out frames are read from the originals: one missing would stop the build at that
        # frame, or be dropped by a caller that carries on without it, so a partial download is never enough)
        raise OriginalsMissing(f"{get_source()} is a lean archive and {ORIGINALS} holds {_originals_info.get('volumes', 0)} "
                               f"of {ORIGINALS_VOLUMES} complete volumes: it needs them all (CASSINI_ORIGINALS_PARTIAL "
                               f"does not apply)")
    if (_originals_info.get("volumes", 0) < ORIGINALS_VOLUMES
            and os.environ.get("CASSINI_ORIGINALS_PARTIAL", "") not in ("1", "yes", "true")):
        raise OriginalsMissing(f"{ORIGINALS} holds {_originals_info.get('volumes', 0)} of {ORIGINALS_VOLUMES} complete "
                               f"volumes ({_originals_info.get('frames', 0)} frames): the download is not done "
                               f"(CASSINI_ORIGINALS_PARTIAL=1 for a test pass)")
    return dict(_originals_info)


"""
A raw ISS IMG (bytes, as the PDS has it): its image as stored, int32 (lines x samples), after its VICAR label and
binary header, each line's prefix (NBB bytes) left off. As convert_archive.read_img.
"""
def read_img_bytes(data):
    raw = np.frombuffer(data, dtype=np.uint8)
    head = raw[:4096].tobytes().decode("latin-1")
    g = lambda key: re.search(rf"\b{key}=\s*'?([^\s']+)", head).group(1)
    label_size, record = int(g("LBLSIZE")), int(g("RECSIZE"))
    lines, samples = int(g("NL")), int(g("NS"))
    prefix, header_records = int(g("NBB")), int(g("NLB"))
    sample_bytes = 2 if g("FORMAT") == "HALF" else 1
    if record != prefix + samples * sample_bytes:
        return None
    start = label_size + header_records * record
    rows = raw[start:start + lines * record].reshape(lines, record)
    dtype = ">i2" if sample_bytes == 2 else "u1"
    return rows[:, prefix:].copy().view(dtype).reshape(lines, samples).astype(np.int32)


def original_dn(path, shape=None):
    if not ORIGINALS or ORIGINALS_OFF or not path:
        return None
    frame = os.path.basename(str(path)).split(".")[0].upper()
    with _originals_lock:
        dn = _original_kept.get(frame)
        if dn is not None:
            _original_kept.move_to_end(frame)
    if dn is None:
        where = _originals_index().get(frame)
        if where is None:
            return None
        archive, member = where
        try:
            if archive is None:
                with open(member, "rb") as f:
                    data = f.read()
            else:
                with _originals_lock:
                    z = _original_zips.get(archive)
                    if z is None:
                        z = _original_zips[archive] = zipfile.ZipFile(archive)
                    data = z.read(member)
            if member.upper().endswith(".XZ"):
                import lzma
                data = lzma.decompress(data)
            dn = read_img_bytes(data)
        except Exception as e:
            print(f"Can't read the original of {frame}: {e}")
            return None
        if dn is None:
            return None
        dn.flags.writeable = False
        with _originals_lock:
            _original_kept[frame] = dn
            while len(_original_kept) > ORIGINALS_KEEP:
                _original_kept.popitem(last=False)
    if shape is not None and tuple(dn.shape) != tuple(shape[:2]):
        return None
    return dn


"""
Lean archives (helper programs/lean_archive.py): a copy of the lean archive that leaves out the PNG of every frame the
12-bit originals cover, about 28 of its 73 GB. Such a frame's PNG is replaced by a stub, a few bytes that name its
conversion, and its codes are made again from its original exactly as convert_archive.py made them: a 12BIT frame's
DN squeezed to the 256 square-root codes (encode, calibration.ORIGINAL_MIDS), an 8LSB frame's low 8 bits stretched as
the old PNGs were (calibration.display_stretch). The tool stubs a frame only when what this gives equals its PNG pixel
for pixel, so every reader (imread, read_bytes) sees the frame as before; its label and prefix stay in the archive.
Reading a stub needs CASSINI_ORIGINALS (the folder): without it, or with it off, it stops with LeanFrameMissing.
"""
LEAN_STUB = b"CASSINI-LEAN-STUB v1 "   # + the frame's DATA_CONVERSION_TYPE (12BIT or 8LSB) + newline
LEAN_KINDS = ("12BIT", "8LSB")


class LeanFrameMissing(OriginalsMissing):
    pass


def lean():
    """True when the data is a lean archive (it has the tool's LEAN_ARCHIVE.txt)"""
    try:
        return exists("LEAN_ARCHIVE.txt")
    except FileNotFoundError:   # (no data at all: not a lean archive)
        return False


def lean_stub(data):
    """The conversion a lean archive's stub names, or None when data is not a stub"""
    if len(data) < 64 and data.startswith(LEAN_STUB):
        kind = data[len(LEAN_STUB):].split(b"\n")[0].decode("ascii", "replace")
        if kind not in LEAN_KINDS:
            raise ValueError(f"unknown lean archive stub {data!r}")
        return kind
    return None


def lean_stub_bytes(kind):
    assert kind in LEAN_KINDS
    return LEAN_STUB + kind.encode("ascii") + b"\n"


def codes_from_original(dn, kind):
    """A frame's stored codes as convert_archive.py made them from its original's DN (dn, as original_dn reads it)"""
    import calibration as cal
    if kind == "12BIT":
        return np.searchsorted(cal.ORIGINAL_MIDS, dn).astype(np.uint8)
    return cal.display_stretch(np.asarray(dn).astype(np.uint8), {"DATA_CONVERSION_TYPE": "TABLE"})


def lean_codes(path, kind):
    """The codes of a frame whose PNG a lean archive left out (a fresh, writable array)"""
    if not ORIGINALS or ORIGINALS_OFF:
        raise LeanFrameMissing(f"{relative(path)} is left out of the lean archive {source_of(path)}: it is read from its "
                               f"12-bit original, so CASSINI_ORIGINALS must name the originals folder (it is "
                               f"{os.environ.get('CASSINI_ORIGINALS')!r}); use the full archive otherwise")
    dn = original_dn(path)
    if dn is None:
        raise LeanFrameMissing(f"{relative(path)} is left out of the lean archive {source_of(path)}, and its original is "
                               f"not in {ORIGINALS} (or can't be read)")
    return codes_from_original(dn, kind)


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
        # never swap a whole kernel under a process that has it loaded (several builds share the cache): a file
        # already there whole (another process finished first) is kept and the part dropped; only a wrong one is
        # replaced. SPICE reopening a loaded kernel whose file was replaced failed "reconnect logical unit" (11-17),
        # and that failure was stored as frames' geometry (bootleg_autonav.transient)
        size = int(_zip_index(source)["sizes"][i])
        try:
            os.link(part, out)
        except FileExistsError:
            if os.path.getsize(out) != size:
                os.replace(part, out)
                part = None
        except OSError:
            # (a volume without hard links, exFAT and some mounts: the old replace)
            os.replace(part, out)
            part = None
        if part and os.path.exists(part):
            os.remove(part)
    return out


"""
Extracts every kernel a meta-kernel lists into the cache without loading them, so the
parallel workers find them ready instead of all extracting the same files at once
"""
def extract_metakernel(path):
    if not using_zip(get_kernel_source()):
        return
    for kernel in metakernel_kernels(read_text(path)):
        try:
            extract_to_cache(kernel_relative(kernel))
        except FileNotFoundError:
            pass  # furnsh_metakernel says which kernels are missing


"""
Loads a SPICE meta-kernel. From a folder this is just furnsh (create_spice_index must
have been run). From the zip, every kernel it lists is extracted to the cache and
loaded in the same order, so later kernels still take priority.
"""
class KernelsMissing(BaseException):
    """The SPICE kernels a year needs cannot be loaded (no meta-kernel for it, or more of its kernels missing than
    MISSING_KERNELS_OK): pictures worked out without them would be placed, calibrated and grouped wrongly, so the work
    stops instead (Sam 2026-11-08: the 2017 test build's M5 months ran with 3 of 109 kernels and no warning). A
    BaseException, as KeyboardInterrupt is, so the pipeline's many "except Exception: carry on without SPICE" fallbacks
    (an uncentred picture, no surface redraw) never swallow it: a build or a render stops with this message."""


# the archive lacks a few kernels a meta-kernel lists (2015's ck/15201_15201ra_hf.bc): up to this many missing are
# skipped, more stop the load (KernelsMissing)
MISSING_KERNELS_OK = 2


def furnsh_metakernel(path):
    import spiceypy as sp
    if not using_zip(get_kernel_source()):
        sp.furnsh(_folder_path(path))
        return
    kernels = metakernel_kernels(read_text(path))
    if not kernels:
        raise KernelsMissing(f"meta-kernel {path} lists no kernels (CASSINI_KERNELS={os.environ.get('CASSINI_KERNELS')!r})")
    missing = []
    for kernel in kernels:
        try:
            cached = extract_to_cache(kernel_relative(kernel))
        except FileNotFoundError as e:
            print(f"Skipping missing kernel: {e}")
            missing.append(kernel)
            if len(missing) > MISSING_KERNELS_OK:
                raise KernelsMissing(f"{path}: more than {MISSING_KERNELS_OK} of its {len(kernels)} kernels are missing "
                                     f"from {get_kernel_source()} (CASSINI_KERNELS={os.environ.get('CASSINI_KERNELS')!r})")
            continue
        sp.furnsh(cached)


"""
Checks, without loading anything, that every year in years has its meta-kernel (cosp_1000/index/cas_<year>_*.tm)
and, from a zip, that at most MISSING_KERNELS_OK of the kernels it lists are missing; raises KernelsMissing otherwise.
A build checks this before it starts (prebuild.py), so a machine without the kernels archive stops at once.
"""
def check_kernels(years):
    index = "cosp_1000/index"
    try:
        metas = listdir(index)
    except (FileNotFoundError, KeyError):
        metas = []
    by_year = {}
    for m in metas:
        try:
            by_year[int(m.split("_")[1])] = f"{index}/{m}"
        except (IndexError, ValueError):
            continue
    lacking = [y for y in years if y not in by_year]
    if lacking:
        raise KernelsMissing(f"no SPICE meta-kernel for {', '.join(map(str, lacking))} in {get_kernel_source()} "
                             f"(set CASSINI_KERNELS to the kernels archive)")
    if not using_zip(get_kernel_source()):
        return
    for y in years:
        kernels = metakernel_kernels(read_text(by_year[y]))
        missing = [k for k in kernels if _find(kernel_relative(k)) is None]
        if not kernels or len(missing) > MISSING_KERNELS_OK:
            raise KernelsMissing(f"{by_year[y]}: {len(missing)} of its {len(kernels)} kernels are missing from "
                                 f"{get_kernel_source()}")


"""
Deletes the extracted kernels (call after spiceypy.kclear)
"""
def clear_spice_cache():
    if using_zip(get_kernel_source()) and not KEEP_SPICE_CACHE and os.path.isdir(SPICE_CACHE):
        # ignore_errors: on Windows a kernel a worker still has open can't be deleted yet
        shutil.rmtree(SPICE_CACHE, ignore_errors=True)
