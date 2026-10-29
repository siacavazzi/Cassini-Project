#!/usr/bin/env python3
"""
Evidence for the colour registration and two-filter colour fixes (image_correction.guided_shift, calibration.color_mix):
the same colour sets made by two checkouts of the pipeline, side by side.

  extract   a lean archive of the frames of the sets named in a log (every frame id in it, the frames of the same
            camera and observation within WINDOW s of each, so a set's other filters and its repeat exposures come
            too), copied member for member from CASSINI_DATA's zip, for a machine without the archive:
              CASSINI_DATA=/Volumes/LaCie/cassini_lut8.zip python web/frames/color_register_evidence.py extract \\
                  log.tsv [more ids or files] --out sets.zip
  compare   each set's composite (color_image.load_aligned, as the frame server's composite draws it) by the
            checkout OLD and by NEW, as one JPEG per set (old left, new right) and a TSV of how each channel was
            aligned in both:
              CASSINI_DATA=sets.zip CASSINI_GEOMETRY_CACHE=geometry.sqlite CASSINI_CISSCAL=... \\
                  python web/frames/color_register_evidence.py compare log.tsv --old OLD --new NEW --out DIR
  movie     the movie frame and mosaic of the pass each frame named is in (obs_mosaic.movie_frame and so_far at that
            frame, as the camera window plays it), by OLD and by NEW, each in a fresh cache of its own:
              CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/color_register_evidence.py movie \
                  W1486331264_1 --old OLD --new NEW --out DIR
            (and the frame drawn grey; MOVIE_ONLY=1 leaves the mosaics out)
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WINDOW = 700   # s: two set gaps (sets_passes.SET_GAP) and more, round each frame named; at most 120 (the repeat
               # exposures' window, stacking): round each frame of the named frames' sets only
ID = re.compile(r"\b[NW]1\d{9}_\d+\b")


def ids_in(items):
    out = []
    for item in items:
        text = open(item).read() if os.path.exists(item) else item
        out += [i for i in ID.findall(text) if i not in out]
    return out


def extract(args):
    named = ids_in(args.items)
    rows = list(csv.DictReader(open(os.path.join(REPO, "Image_index.csv"))))
    by_id = {r["path"].rsplit("/", 1)[-1][:-4]: r for r in rows if r.get("path")}
    by_obs = {}
    for r in rows:
        if r.get("path"):
            by_obs.setdefault((r["INSTRUMENT_ID"], r["OBSERVATION_ID"]), []).append(r)
    want = set()
    members = sorted({m for ids in sets_of(named).values() for m in ids}) if args.window <= 120 else named
    for i in members:
        r = by_id.get(i)
        if r is None:
            print("not in the index:", i)
            continue
        t = float(r["seconds_1970"])
        for q in by_obs[r["INSTRUMENT_ID"], r["OBSERVATION_ID"]]:
            if abs(float(q["seconds_1970"]) - t) <= args.window:
                want.add(q["path"].rsplit("/", 1)[-1][:-4])
    if args.count:
        print(f"{len(named)} ids named, {len(want)} frames")
        return
    src = zipfile.ZipFile(os.environ["CASSINI_DATA"])
    n = 0
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_STORED) as out:
        for info in src.infolist():
            stem = info.filename.rsplit("/", 1)[-1].split(".")[0]
            # and the folders' FORMAT.txt, which says the PNGs hold the lean archive's codes (data_source.lut8)
            if stem in want or info.filename.endswith("FORMAT.txt"):
                out.writestr(info, src.read(info))
                n += 1
    print(f"{len(named)} ids named, {len(want)} frames, {n} members into {args.out} ({os.path.getsize(args.out) >> 20} MB)")


def sets_of(named):
    """{named id: the ids of its set's channels in channel order} by the one rule (sets_passes, reel.load_index)."""
    sys.path.insert(0, HERE)
    import reel
    idx, sets = reel.load_index()
    ids = idx["id"].tolist()
    at = {i: q for q, i in enumerate(ids)}
    out = {}
    for i in named:
        q = at.get(i)
        if q is not None and idx["set"][q] >= 0:
            out[i] = [ids[r] for r in sets[idx["set"][q]]["use"]]
    return out


# one checkout's composites, in a process of its own (the two checkouts' modules can't share one)
MAKE = r"""
import io, json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(sys.argv[1], "web", "frames")); sys.path.insert(0, sys.argv[1])
import frame_server
sets = json.load(open(sys.argv[2]))
out = {}
for key, ids in sets.items():
    try:
        im, report = frame_server.composite(ids)
        im.convert("RGBA").save(os.path.join(sys.argv[3], key + ".png"))
        out[key] = {"aligned": report.get("aligned"), "calibrated": report.get("calibrated")}
    except Exception as e:
        out[key] = {"error": f"{type(e).__name__}: {e}"[:300]}
json.dump(out, open(os.path.join(sys.argv[3], "reports.json"), "w"))
"""


# one checkout's movie frames and mosaics of the frames' passes
MOVIE = r"""
import json, os, sys, tempfile
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(sys.argv[1], "web", "frames")); sys.path.insert(0, sys.argv[1])
import frame_server, obs_mosaic
out, cache = {}, tempfile.mkdtemp(dir=sys.argv[3])
for fid in json.load(open(sys.argv[2])):
    found = obs_mosaic.unit_of(fid)
    if found is None:
        out[fid] = {"error": "in no pass"}
        continue
    u, n = found
    rec = out[fid] = {"pass": list(u["key"]), "kind": u.get("kind"), "n": n, "plan colour": obs_mosaic.plan(u, cache)["colour"]}
    kinds = [("movie", lambda: obs_mosaic.movie_frame(u, n, cache)), ("grey", lambda: obs_mosaic.movie_frame(u, n, cache, colour=False)),
             ("mosaic", lambda: obs_mosaic.so_far(u, n, cache))]
    # MOVIE_ONLY=1: the movie frame (and the same frame drawn grey) only, not the pass's mosaic
    for name, draw in kinds[:2] if os.environ.get("MOVIE_ONLY") else kinds:
        try:
            im, rep = draw()
            if im is not None:
                im = im if isinstance(im, Image.Image) else Image.fromarray(np.asarray(im))
                im.convert("RGBA").save(os.path.join(sys.argv[3], f"{fid}-{name}.png"))
            rec[name] = {k: rep.get(k) for k in ("color", "ids", "filter_names", "filters", "why", "set_places", "held")} if rep else None
        except Exception as e:
            rec[name] = {"error": f"{type(e).__name__}: {e}"[:300]}
json.dump(out, open(os.path.join(sys.argv[3], "reports.json"), "w"), indent=1, default=str)
"""


def movie(args):
    from PIL import Image, ImageDraw
    named = ids_in(args.items)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "ids.json"), "w") as f:
        json.dump(named, f)
    reports = {}
    for name, tree in (("old", args.old), ("new", args.new)):
        folder = os.path.join(args.out, name)
        os.makedirs(folder, exist_ok=True)
        subprocess.run([sys.executable, "-c", MOVIE, os.path.abspath(tree), os.path.join(args.out, "ids.json"), folder],
                       check=True, cwd=os.path.abspath(tree), stdout=subprocess.DEVNULL)
        reports[name] = json.load(open(os.path.join(folder, "reports.json")))
    for fid in named:
        for kind in ("movie", "grey", "mosaic"):
            pics = [os.path.join(args.out, n, f"{fid}-{kind}.png") for n in ("old", "new")]
            if not all(os.path.exists(q) for q in pics):
                continue
            side = Image.new("RGB", (2 * 600 + 8, 640), (24, 24, 24))
            for k, (q, name) in enumerate(zip(pics, ("before", "after"))):
                im = Image.open(q).convert("RGBA")
                im.thumbnail((600, 600))
                side.paste(im, (k * 608 + (600 - im.width) // 2, 40 + (600 - im.height) // 2), im)
                r = reports["old" if k == 0 else "new"][fid].get(kind) or {}
                ImageDraw.Draw(side).text((k * 608 + 8, 8), f"{name}  {fid} {kind}  " + " ".join(
                    r.get("color") or r.get("filter_names") or ["grey"]), fill=(230, 230, 160))
            side.save(os.path.join(args.out, f"{fid}-{kind}.jpg"), quality=90)
    with open(os.path.join(args.out, "reports.json"), "w") as f:
        json.dump(reports, f, indent=1)
    print(json.dumps(reports, indent=1))


def compare(args):
    import numpy as np
    from PIL import Image, ImageDraw
    named = ids_in(args.items)
    sets = sets_of(named)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "sets.json"), "w") as f:
        json.dump(sets, f)
    reports = {}
    for name, tree in (("old", args.old), ("new", args.new)):
        folder = os.path.join(args.out, name)
        os.makedirs(folder, exist_ok=True)
        subprocess.run([sys.executable, "-c", MAKE, os.path.abspath(tree), os.path.join(args.out, "sets.json"), folder],
                       check=True, cwd=os.path.abspath(tree), stdout=subprocess.DEVNULL)
        reports[name] = json.load(open(os.path.join(folder, "reports.json")))
    with open(os.path.join(args.out, "aligned.tsv"), "w") as f:
        f.write("set\tchannels\told\tnew\tchanged px\n")
        for key, ids in sets.items():
            pics = []
            for name in ("old", "new"):
                path = os.path.join(args.out, name, key + ".png")
                pics.append(np.asarray(Image.open(path).convert("RGB")) if os.path.exists(path) else None)
            changed = "" if any(p is None for p in pics) else int((np.abs(pics[0].astype(int) - pics[1]) > 2).any(2).sum())
            old, new = (reports[n].get(key, {}) for n in ("old", "new"))
            f.write(f"{key}\t{','.join(ids)}\t{old.get('aligned', old.get('error'))}\t{new.get('aligned', new.get('error'))}\t{changed}\n")
            if all(p is not None for p in pics):
                side = Image.new("RGB", (2 * 600 + 8, 640), (24, 24, 24))
                for k, (p, name) in enumerate(zip(pics, ("before", "after"))):
                    side.paste(Image.fromarray(p).resize((600, 600)), (k * 608, 40))
                    ImageDraw.Draw(side).text((k * 608 + 8, 8), f"{name}  {key}  " + " ".join(
                        str(a) for a in (old if k == 0 else new).get("aligned") or []), fill=(230, 230, 160))
                side.save(os.path.join(args.out, key + ".jpg"), quality=88)
    print(f"{len(sets)} sets into {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("extract", "compare", "movie"))
    ap.add_argument("items", nargs="+", help="logs or frame ids: every frame id in them names a set")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=float, default=WINDOW, help="extract: seconds round each frame named")
    ap.add_argument("--count", action="store_true", help="extract: only count the frames")
    ap.add_argument("--old", help="compare, movie: the checkout before")
    ap.add_argument("--new", default=REPO, help="compare, movie: the checkout after (this one)")
    args = ap.parse_args()
    {"extract": extract, "compare": compare, "movie": movie}[args.mode](args)


if __name__ == "__main__":
    main()
