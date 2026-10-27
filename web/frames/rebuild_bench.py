#!/usr/bin/env python3
"""
How fast a machine makes the pre-build's pictures, and whether it makes them byte for byte as the Mac Mini does: the
pre-build's own items (prebuild.items, made by the frame server's makers) for the 34 frames of the opt-audit sample,
one at a time on one core, in a fresh cache. The same frames, code and script on two machines give their per-core
speed ratio on this exact work, and the digests of what they made say whether a cache built on one could stand in for
one built on the other (a rented cloud machine for a whole rebuild, 2026-10-27).

  python rebuild_bench.py sample ARCHIVE OUT.zip     the sample's 104 members, copied out of the lean archive
                                                     (cassini_lut8.zip), checked against their CRCs
  REPO=<checkout> PHASE=<phase> OUT=<json> python rebuild_bench.py
                                                     one phase on the sample (CASSINI_DATA=OUT.zip), its own process

Phases: frames (1024, 512 and 128 of each frame), processed (1024, 512 and 256, centred as Auto center asks),
composites (the page's filter sets of the sample and the golden rig's, 1024 and 512, centred), movies (make_pass on
every pass whose frames are all in the sample, as its own kind) and mosaics (the same passes drawn as mosaics).
rebuild_bench.sh runs every phase twice and then several copies at once (every core).
"""
import contextlib
import copy
import hashlib
import io
import json
import os
import platform
import shutil
import sys
import tempfile
import time
import zlib

# the opt-audit sample (Enceladus, 2005-07-14): 34 NAC frames, 3 passes, 5 filter sets
SAMPLE = ["N1500041260_2", "N1500041293_2", "N1500041326_2", "N1500041374_2", "N1500041422_2", "N1500041470_2",
          "N1500041518_2", "N1500041566_2", "N1500041614_2", "N1500041648_2", "N1500045760_2", "N1500045793_2",
          "N1500045826_2", "N1500045859_2", "N1500046660_2", "N1500046693_2", "N1500046726_2", "N1500046774_2",
          "N1500046822_2", "N1500046892_2", "N1500046962_2", "N1500047010_2", "N1500047058_2", "N1500047092_2",
          "N1500050560_2", "N1500050593_2", "N1500050659_2", "N1500050692_2", "N1500051163_2", "N1500051211_2",
          "N1500051259_2", "N1500051292_2", "N1500051325_3", "N1500051358_2"]
MEMBERS = sorted([f"data/nac_data/{i}.{ext}" for i in SAMPLE for ext in ("lbl", "png", "prefix.gz")] +
                 ["data/nac_data/FORMAT.txt", "data/wac_data/FORMAT.txt"])
# sha256 of the members' "name CRC" lines, as the sample.zip the cloud rigs use has them
SAMPLE_DIGEST = "996fc91ef907478c3b9775ab60eed7777a3fe3fe7e9ee491fdb4e13c18011670"
GOLDEN_SETS = [["N1500045826_2", "N1500045793_2", "N1500045760_2"], ["N1500050659_2", "N1500050593_2", "N1500050560_2"],
               ["N1500041518_2", "N1500041260_2", "N1500041374_2"], ["N1500046962_2", "N1500046660_2", "N1500046774_2"],
               ["N1500051292_2", "N1500051163_2", "N1500051211_2"]]


def make_sample(archive, out):
    """The sample's members copied out of archive into a stored zip at out. Read through the repo's own zip index
    when one is already made for archive (CASSINI_INDEX_CACHE; it is never made or replaced here, since making one
    clears the other indexes of that zip), else through zipfile (about 1 GB of memory for the whole archive)."""
    datas = {}
    os.environ["CASSINI_DATA"] = archive
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    import data_source
    if os.path.isdir(data_source._index_folder(archive)):
        for name in MEMBERS:
            datas[name] = data_source.read_bytes(name)
    else:
        import zipfile
        with zipfile.ZipFile(archive) as z:
            names = {n.lower(): n for n in z.namelist()}
            for name in MEMBERS:
                datas[name] = z.read(names[name.lower()])
    import zipfile
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for name in MEMBERS:
            z.writestr(name, datas[name])
    lines = "\n".join(f"{name} {zlib.crc32(datas[name]) & 0xffffffff}" for name in MEMBERS)
    digest = hashlib.sha256(lines.encode()).hexdigest()
    print(json.dumps({"members": len(MEMBERS), "bytes": sum(map(len, datas.values())), "digest": digest,
                      "same_as_cloud_sample": digest == SAMPLE_DIGEST}))
    return digest == SAMPLE_DIGEST


def bench():
    repo = os.environ["REPO"]
    os.chdir(repo)
    sys.path.insert(0, os.path.join(repo, "web", "frames"))
    t_import = time.perf_counter()
    import cv2
    cv2.setNumThreads(int(os.environ.get("CV_THREADS", "1")))   # one core, on any machine
    import frame_server as fs
    import obs_mosaic
    import prebuild
    import reel
    import calibration
    obs_mosaic.tiles_ahead = lambda *a, **k: None      # as the pre-build runs: everything made in order
    obs_mosaic.rolling_ahead = lambda *a, **k: None
    fs.data_source.KEEP_SPICE_CACHE = True
    phase = os.environ["PHASE"]
    ids = SAMPLE
    fs.color_image.stacking.load_index()
    idx, _ = reel.load_index()
    t_ready = time.perf_counter() - t_import

    if phase == "frames":
        work = [(i, 3, lambda c, i=i: [fs.webp(i, s, c) for s in (1024, 512, 128)]) for i in ids]
    elif phase == "processed":
        work = [(i, 3, lambda c, i=i: [fs.processed_webp(i, z, c, centre=prebuild.centred(i)) for z in (1024, 512, 256)])
                for i in ids]
    elif phase == "composites":
        sets = [s for s in prebuild.page_sets() if all(i in ids for i in s)]
        sets += [s for s in GOLDEN_SETS if s not in sets]
        work = [("_".join(s), 2, lambda c, s=s: [fs.color_webp(s, z, c, centre=prebuild.centred(s[-1])) for z in (1024, 512)])
                for s in sets]
    else:
        rows = idx[idx["id"].isin(ids)]
        keys = sorted(set(zip(rows["TARGET_NAME"], rows["OBSERVATION_ID"], rows["INSTRUMENT_ID"])))
        passes = [u for t, o, inst in keys for u in obs_mosaic.units(t, o, "N" if inst == "ISSNA" else "W")
                  if u["frames"] and all(f[1] in ids for f in u["frames"])]
        if phase == "mosaics":
            passes = [dict(copy.deepcopy(u), mosaic=True, kind="mosaic") for u in passes]
        work = [("_".join(map(str, u["key"])), 2 * len(u["frames"]), lambda c, u=u: prebuild.make_pass(u, c))
                for u in passes]

    cache = tempfile.mkdtemp(prefix=f"bench-{phase}-", dir=os.environ.get("SCRATCH") or None)
    each, errors = [], []
    t_all, cpu_all = time.perf_counter(), time.process_time()
    with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
        for name, pictures, fn in work:
            t0, c0 = time.perf_counter(), time.process_time()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    fn(cache)
                err = None
            except Exception as e:   # noqa: BLE001  (counted; the phase goes on)
                err = f"{type(e).__name__}: {e}"[:200]
                errors.append([name, err])
            each.append([name, pictures, round(time.perf_counter() - t0, 4), round(time.process_time() - c0, 4), err])
    wall, cpu = time.perf_counter() - t_all, time.process_time() - cpu_all
    hashes, size = {}, 0
    for root, _, files in os.walk(cache):
        for f in files:
            with open(os.path.join(root, f), "rb") as fh:
                data = fh.read()
            size += len(data)
            hashes[os.path.relpath(os.path.join(root, f), cache)] = hashlib.sha256(data).hexdigest()[:20]
    shutil.rmtree(cache, ignore_errors=True)
    ok = [e for e in each if not e[4]]

    def digest(keep):
        return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(hashes.items()) if keep(k)).encode()).hexdigest()[:16]
    out = {"phase": phase, "machine": platform.node(), "cpu": platform.processor() or platform.machine(),
           "python": platform.python_version(), "items": len(each), "ok": len(ok), "errors": errors,
           "pictures": sum(e[1] for e in ok), "wall_s": round(wall, 3), "cpu_s": round(cpu, 3),
           "s_per_item": round(sum(e[2] for e in ok) / max(1, len(ok)), 4),
           "s_per_picture": round(sum(e[2] for e in ok) / max(1, sum(e[1] for e in ok)), 4),
           "bytes": size, "files": len(hashes), "startup_s": round(t_ready, 2), "load": os.getloadavg(),
           # the same digest on two machines: every file (pictures and their reports) came out byte for byte the same
           "digest": digest(lambda k: True), "digest_pictures": digest(lambda k: k.endswith((".webp", ".png"))),
           "each": each, "hashes": hashes}
    with open(os.environ["OUT"], "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("each", "hashes")}), flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["sample"]:
        sys.exit(0 if make_sample(sys.argv[2], sys.argv[3]) else 1)
    bench()
