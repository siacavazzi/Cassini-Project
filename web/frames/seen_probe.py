#!/usr/bin/env python3
"""Small-moon movie passes where SPICE's place of the moon jumps (obs_mosaic.seen_places; Sam 2026-11-04: "see
variance between frames that are close together and then if it's a certain amount then we like just use visual frame
alignment"). Lists every movie pass whose target is one of Saturn's small moons (obs_mosaic.SMALL_RADIUS) with its
disk big enough for color_image.find_small_body (FIND_MIN_RADIUS to FIND_MAX_RADIUS px), one JSON line each: the
pass, its frames, the moon's radius in px. With --measure, also works out each pass's stabilization chain in --cache
(a scratch cache: tiles are drawn) and prints what seen_places measured: on how many tiles the moon was found, the
share of neighbouring pairs whose SPICE error jumps past STEADY_JUMPY, SPICE's median error, and whether the
pictures' places were taken ("held").

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/seen_probe.py --out seen.jsonl \\
      [--measure --cache /scratch/cache] [--most 40] [--targets PAN,ATLAS] [--years 2017]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402  (puts the repo on the path)


def pd_years(rows):
    """Each row's calendar year (UTC)."""
    import datetime
    return rows["seconds_1970"].map(lambda v: datetime.datetime.fromtimestamp(v, datetime.timezone.utc).year)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", help="a scratch cache, for --measure")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--most", type=int, default=40, help="passes measured at most (the longest first)")
    ap.add_argument("--targets", default="", help="comma-separated, default every small moon")
    ap.add_argument("--years", default="", help="comma-separated years, default all")
    args = ap.parse_args()
    import calibration
    import color_image
    import obs_mosaic as om
    idx, _ = reel.load_index()
    targets = [t for t in (args.targets.split(",") if args.targets else om.SMALL_RADIUS) if t]
    rows = idx[idx["TARGET_NAME"].astype(str).isin(targets)]
    if args.years:
        years = {int(y) for y in args.years.split(",")}
        rows = rows[pd_years(rows).isin(years)]
    found = []
    for (target, obs, inst) in dict.fromkeys(zip(rows["TARGET_NAME"], rows["OBSERVATION_ID"], rows["INSTRUMENT_ID"])):
        cam = "N" if inst == "ISSNA" else "W"
        for u in om.units(target, obs, cam):
            if not u.get("movie") or u.get("track") or not u.get("z"):
                continue
            radius = om.RADIUS.get(target, 0) / (u["z"] * om.IFOV[cam])
            if not color_image.FIND_MIN_RADIUS <= radius <= color_image.FIND_MAX_RADIUS:
                continue
            found.append((u, radius))
    found.sort(key=lambda ur: -len(ur[0]["frames"]))
    with open(args.out, "w") as out:
        for k, (u, radius) in enumerate(found):
            line = {"pass": [str(v) for v in u["key"]], "first": u["frames"][0][1], "frames": len(u["frames"]),
                    "radius": round(radius, 1)}
            if args.measure and k < args.most:
                with calibration.looking("balanced"):
                    om.steady_chain(u, args.cache)
                with open(os.path.join(om.folder(u, args.cache), om.STEADY_FILE)) as fh:
                    kept = json.load(fh)
                line["seen"], line["held"] = kept.get("seen"), bool(kept.get("held"))
            out.write(json.dumps(line) + "\n")
            print(json.dumps(line), flush=True)


if __name__ == "__main__":
    main()
