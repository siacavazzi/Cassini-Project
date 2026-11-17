"""The lean 8-bit archive (helper programs/lean_archive.py, data_source.lean_codes): a copy of the archive that leaves
out the PNG of every frame the 12-bit originals cover reads every frame exactly as the full archive does. Synthetic:
a small full archive (12BIT, 8LSB stretched and copied, TABLE frames, one whose original is only 'check', one whose
original does not give its PNG) and an originals folder as orig12 writes it; the tool builds the lean copy, which
leaves out only the frames it can make again, its verify passes, and data_source reads every frame of it (imread gray
and color, read_bytes, exists, listdir) as from the full one. Without the originals a left-out frame stops with
LeanFrameMissing instead of reading as something else.
Run: python web/test_lean_archive.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lzma
import subprocess
import tempfile
import zipfile
import cv2
import numpy as np
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "helper programs", "lean_archive.py")
rng = np.random.default_rng(7)
LABEL = 'PDS_VERSION_ID = PDS3\r\nINSTRUMENT_ID = "ISSNA"\r\nDATA_CONVERSION_TYPE = "{conv}"\r\nLINES = 64\r\nEND\r\n'


def img_bytes(dn, half=True):
    """A raw ISS IMG (VICAR label, 24-byte line prefixes), as test_full_depth makes them"""
    lines, samples = dn.shape
    prefix, size = 24, 2 if half else 1
    record = prefix + samples * size
    head = f"LBLSIZE={record * 4} FORMAT='{'HALF' if half else 'BYTE'}' RECSIZE={record} NL={lines} NS={samples} NBB={prefix} NLB=0 "
    head = head.encode().ljust(record * 4, b" ")
    body = np.zeros((lines, record), np.uint8)
    body[:, prefix:] = np.frombuffer(dn.astype(">i2" if half else "u1").tobytes(), np.uint8).reshape(lines, -1)
    return head + body.tobytes()


def png(codes):
    return cv2.imencode(".png", codes)[1].tobytes()


dn12 = rng.integers(0, 4096, (64, 64)).astype(np.int32)
dn12_b = rng.integers(0, 4096, (64, 48)).astype(np.int32)
dn8 = rng.integers(5, 60, (64, 64)).astype(np.int32)
frames = {   # fid: (conversion, stored PNG codes, original DN or None, manifest status, left out?)
    "N1000000001_1": ("12BIT", ds.codes_from_original(dn12, "12BIT"), dn12, "ok", True),
    "W1000000002_1": ("12BIT", ds.codes_from_original(dn12_b, "12BIT"), dn12_b, "ok", True),
    "N1000000003_1": ("8LSB", ds.codes_from_original(dn8, "8LSB"), dn8, "ok", True),
    # an 8LSB frame the archive copied from an old PNG (not what its original gives): kept
    "N1000000004_1": ("8LSB", rng.integers(0, 255, (64, 64)).astype(np.uint8), dn8, "ok", False),
    # a TABLE frame (no original): kept
    "N1000000005_1": ("TABLE", rng.integers(0, 255, (64, 64)).astype(np.uint8), None, None, False),
    # an original its manifest does not mark ok: not read, kept
    "N1000000006_1": ("12BIT", ds.codes_from_original(dn12, "12BIT"), dn12, "check", False),
    # an original that does not squeeze to the stored codes (another frame's): kept
    "N1000000007_1": ("12BIT", ds.codes_from_original(dn12, "12BIT"), np.full((64, 64), 2000, np.int32), "ok", False),
}
checks = 0
with tempfile.TemporaryDirectory() as tmp:
    full, lean, originals = (os.path.join(tmp, n) for n in ("cassini_lut8.zip", "cassini_lut8_lean.zip", "orig12"))
    with zipfile.ZipFile(full, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.csv", "id\n")
        for folder in ("nac_data", "wac_data"):
            z.writestr(f"{folder}/FORMAT.txt", "lut8 v1\n")
        for fid, (conv, codes, _, _, _) in frames.items():
            folder = "nac_data" if fid[0] == "N" else "wac_data"
            z.writestr(f"{folder}/{fid}.png", png(codes))
            z.writestr(f"{folder}/{fid}.LBL", LABEL.format(conv=conv))
            z.writestr(f"{folder}/{fid}.prefix.gz", b"\x1f\x8b prefix")
    os.makedirs(os.path.join(originals, "volumes"))
    os.makedirs(os.path.join(originals, "manifest"))
    with zipfile.ZipFile(os.path.join(originals, "volumes", "COISS_2001.zip"), "w") as z, \
            open(os.path.join(originals, "manifest", "COISS_2001.csv"), "w") as fh:
        fh.write("fid,status\n")
        for fid, (conv, _, dn, status, _) in frames.items():
            if dn is not None:
                z.writestr(f"COISS_2001/data/{fid}.IMG.xz", lzma.compress(img_bytes(dn, half=conv == "12BIT")))
                fh.write(f"{fid},{status}\n")

    env = dict(os.environ, CASSINI_ORIGINALS_PARTIAL="1", CASSINI_INDEX_CACHE=os.path.join(tmp, "zip_index"))
    run = lambda *a: subprocess.run([sys.executable, TOOL, *a, "--data", full, "--originals", originals, "--workers", "2"],
                                    env=env, capture_output=True, text=True)
    p = run("build", "--out", lean)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "3 PNGs left out" in p.stdout, p.stdout
    assert run("build", "--out", lean).returncode != 0   # never over an existing file
    p = run("verify", "--lean", lean)
    assert p.returncode == 0 and "OK" in p.stdout, p.stdout + p.stderr
    checks += 3

    # the members: left out exactly the frames it can make again, everything else byte for byte
    with zipfile.ZipFile(full) as zf, zipfile.ZipFile(lean) as zl:
        assert set(zl.namelist()) == set(zf.namelist()) | {"LEAN_ARCHIVE.txt"}
        for name in zf.namelist():
            fid = os.path.basename(name).split(".")[0]
            if name.endswith(".png") and frames[fid][4]:
                assert ds.lean_stub(zl.read(name)) == frames[fid][0], name
            else:
                assert zl.read(name) == zf.read(name), name
    assert os.path.getsize(lean) < os.path.getsize(full)
    checks += 1

    # data_source reads every frame of the lean archive as of the full one
    ds.INDEX_CACHE = os.path.join(tmp, "zip_index")
    ds.ORIGINALS, ds._originals, ds._lut8 = originals, None, None

    def read_all(source):
        ds._source, ds._lut8 = source, None
        ds._decoded.clear()
        ds._original_kept.clear()
        out = {}
        for fid in frames:
            rel = f"{'nac_data' if fid[0] == 'N' else 'wac_data'}/{fid}.png"
            gray = ds.imread(rel, cv2.IMREAD_GRAYSCALE)
            again = ds.imread(rel, cv2.IMREAD_GRAYSCALE)   # (from the decoded ones kept)
            assert np.array_equal(gray, again)
            out[fid] = (gray, ds.imread(rel), ds.imread(rel, cv2.IMREAD_UNCHANGED),
                        cv2.imdecode(np.frombuffer(ds.read_bytes(rel), np.uint8), cv2.IMREAD_GRAYSCALE),
                        ds.exists(rel), ds.read_text(rel[:-4] + ".lbl"))
        return out, ds.listdir("nac_data"), ds.listdir("wac_data"), ds.lut8()

    want, got = read_all(full), read_all(lean)
    assert want[1:] == got[1:]
    ds._source = full
    assert not ds.lean()
    ds._source = lean
    assert ds.lean()
    for fid in frames:
        for a, b in zip(want[0][fid], got[0][fid]):
            assert (np.array_equal(a, b) if isinstance(a, np.ndarray) else a == b), fid
        assert np.array_equal(got[0][fid][0], frames[fid][1])
        # a frame read from its stub is writable and calibrates as before: full_values takes the original either way
        info = {"DATA_CONVERSION_TYPE": frames[fid][0], "path": f"nac_data/{fid}.png"}
        if frames[fid][0] == "12BIT":
            assert np.array_equal(cal.full_values(got[0][fid][0], info), cal.full_values(want[0][fid][0], info))
    print(f"{sum(f[4] for f in frames.values())} of {len(frames)} frames read from their originals, all the same")
    checks += 2

    # no originals (or off): a left-out frame stops, it never reads as something else; the kept ones still read
    ds._source = lean
    for setting in (None, "off"):
        ds.ORIGINALS, ds.ORIGINALS_OFF = setting, setting == "off"
        ds._decoded.clear()
        try:
            ds.imread("nac_data/N1000000001_1.png", cv2.IMREAD_GRAYSCALE)
            raise AssertionError("a left-out frame read without its original")
        except ds.LeanFrameMissing as e:
            assert "CASSINI_ORIGINALS" in str(e)
        assert np.array_equal(ds.imread("nac_data/N1000000005_1.png", cv2.IMREAD_GRAYSCALE), frames["N1000000005_1"][1])
        if setting == "off":   # (a build's guard says so before it starts)
            try:
                ds.check_originals(); raise AssertionError("a build on a lean archive with the originals off")
            except ds.OriginalsMissing as e:
                assert "lean archive" in str(e)
    ds.ORIGINALS, ds.ORIGINALS_OFF, ds._originals = originals, False, None
    os.rename(os.path.join(originals, "volumes", "COISS_2001.zip"), os.path.join(tmp, "moved.zip"))
    ds._original_kept.clear(); ds._decoded.clear(); ds._original_zips.clear()
    try:
        ds.read_bytes("nac_data/N1000000001_1.png")
        raise AssertionError("a left-out frame read without its original")
    except ds.LeanFrameMissing:
        pass
    checks += 2
    ds._source, ds.ORIGINALS, ds._originals, ds._lut8 = None, None, None, None

print(f"OK ({checks} checks)")
