#!/usr/bin/env python3
"""
Adds mosaics to the photo score of each encounter (the stars in the Moments list).

The highlight scoring (observations_scored.csv: per observation and target, a score out of 100 from
detail, colour, coverage and clean frames) ranks encounters by their best observation. This adds
up to MOSAIC_POINTS to an observation that built a mosaic, by the same rule the camera windows use
(mosaic.panels: tiles of one filter, the pointing stepping across the body, overlapping), so a pass
that built a big mosaic scores well. The largest mosaic of any one filter counts: a Titan mosaic
taking four filters at each of 31 tiles is a 31 tile mosaic, not 124.

  CASSINI_GEOMETRY_CACHE=/Volumes/LaCie/claude_scratch_spk/geometry.sqlite \\
  python web/replay/score_mosaics.py --scores observations_scored.csv --encounters <export dir>/encounters.json

Writes observations_scored.csv and encounters_ranked.csv next to --out (default: next to --scores)
with mosaic_tiles and the new score, and rewrites encounters.json with each flyby's photo_score
and mosaic_tiles (the same matching as web/export_tracks.py: the best ranked encounter of that body
within a day). Then rebuild the replay data (web/replay/build_data.py) so the page reads it.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "web", "frames"))
import mosaic  # noqa: E402

MOSAIC_POINTS = 15     # added to an observation's score (out of 100) for a FULL_MOSAIC tile mosaic
FULL_MOSAIC = 30       # tiles for full marks; a 2 tile mosaic gets a fifth of them (log scale)


def mosaic_tiles(index, where):
    """{(observation, target): tiles of the largest mosaic of one filter} for observations with one."""
    pictures, keys = [], []
    for r in index.itertuples(index=False):
        g = where.get(r.id)
        pictures.append({"t": r.seconds_1970, "cam": r.INSTRUMENT_ID, "obs": (r.OBSERVATION_ID, r.TARGET_NAME),
                         "filter": r.FILTER_NAME, "x": g and g[0], "y": g and g[1], "z": g and g[2]})
        keys.append((r.OBSERVATION_ID, r.TARGET_NAME, r.INSTRUMENT_ID, r.FILTER_NAME))
    # a mosaic is a run of pictures each drawn over earlier ones (a picture that is not starts a new run);
    # its tiles are the distinct places in the run, so repeats and drift at one tile count once
    step = mosaic.min_step * mosaic.frame_px
    run, best = {}, {}
    for key, p, panels in zip(keys, pictures, mosaic.panels(pictures)):
        if not panels:
            run[key] = [(p["x"], p["y"])] if p["x"] is not None else []
            continue
        tiles = run.setdefault(key, [])
        if all(max(abs(p["x"] - x), abs(p["y"] - y)) >= step for x, y in tiles):
            tiles.append((p["x"], p["y"]))
        if len(tiles) > 1:
            best[key[:2]] = max(best.get(key[:2], 0), len(tiles))
    return best


def mosaic_score(tiles):
    return np.clip(np.log10(np.maximum(tiles, 1)) / np.log10(FULL_MOSAIC), 0, 1)


def rank_encounters(o):
    """score.py's encounter windows: one body's observations with gaps under 36 h, scored by the best one."""
    o = o.sort_values(["target", "start"])
    ev = []
    for tg, x in o.groupby("target"):
        gid = (x.start - x.end.shift().fillna(x.start.iloc[0])).gt(pd.Timedelta("36h")).cumsum()
        for _, w in x.groupby(gid):
            top = w.sort_values("score", ascending=False).iloc[0]
            ev.append(dict(target=tg, start=w.start.min(), end=w.end.max(), n_obs=len(w), frames=int(w.n.sum()),
                           rgb_sets=int(w.rgb_sets.sum()), best_res_km=w.best_res_km.min(), max_diam_px=w.max_diam_px.max(),
                           best_obs=top.OBSERVATION_ID, best_score=top.score, phase=top.med_phase,
                           mosaic_tiles=int(w.mosaic_tiles.max()), mosaic_obs=w.sort_values("mosaic_tiles").iloc[-1].OBSERVATION_ID,
                           score=top.score + 5 * np.log10(len(w))))
    return pd.DataFrame(ev).sort_values("score", ascending=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores", required=True, help="observations_scored.csv from the highlight scoring")
    ap.add_argument("--encounters", required=True, help="encounters.json to rewrite (the replay export's)")
    ap.add_argument("--out", help="folder for the new CSVs (default: next to --scores)")
    ap.add_argument("--index", default=os.path.join(REPO, "Image_index.csv"))
    args = ap.parse_args()
    import reel
    o = pd.read_csv(args.scores, parse_dates=["start", "end"])
    if "score_before_mosaics" in o:   # run again: start from the scores without mosaics
        o["score"] = o["score_before_mosaics"]
    idx = pd.read_csv(args.index, usecols=["path", "INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME", "seconds_1970"],
                      low_memory=False)
    idx = idx[idx["path"].notna()].sort_values("seconds_1970", kind="stable")
    idx["id"] = idx["path"].str.rsplit("/", n=1).str[-1].str.replace(".png", "", regex=False)
    where = reel.geometry(idx["id"].tolist())
    if not where:
        sys.exit("no geometry: set CASSINI_GEOMETRY_CACHE to the filled geometry cache")
    print(f"{len(where)} of {len(idx)} frames placed by SPICE", flush=True)
    best = mosaic_tiles(idx, where)
    o["mosaic_tiles"] = [best.get((a, b), 0) for a, b in zip(o.OBSERVATION_ID, o.target)]
    o["s_mosaic"] = mosaic_score(o.mosaic_tiles)
    o["score_before_mosaics"] = o["score"]
    o["score"] = o["score"] + MOSAIC_POINTS * o["s_mosaic"]
    out = args.out or os.path.dirname(os.path.abspath(args.scores))
    o.to_csv(os.path.join(out, "observations_scored.csv"), index=False)
    e = rank_encounters(o)
    e.to_csv(os.path.join(out, "encounters_ranked.csv"), index=False)

    found = json.load(open(args.encounters))
    changed = []
    for f in found:
        if f["kind"] != "flyby":
            continue
        t = pd.Timestamp(f["utc"])
        m = e[(e.target == f["body"]) & (e.start <= t + pd.Timedelta("1D")) & (e.end >= t - pd.Timedelta("1D"))]
        if not len(m):
            continue
        top = m.sort_values("score", ascending=False).iloc[0]
        before = f.get("photo_score")
        f["photo_score"] = round(float(top.score), 1)
        f["frames"] = int(top.frames)
        f["rgb_sets"] = int(top.rgb_sets)
        f["mosaic_tiles"] = int(top.mosaic_tiles)
        changed.append((f["utc"][:10], f["body"], before, f["photo_score"], f["mosaic_tiles"]))
    with open(args.encounters, "w") as fh:
        json.dump(found, fh, indent=0)
    stars = lambda s: max(1, round((s or 0) / 20))
    print(f"{len(o)} observations, {int((o.mosaic_tiles > 1).sum())} with a mosaic; {len(changed)} flybys scored")
    print("date        body         before  after  tiles  stars")
    for d, b, s0, s1, n in sorted(changed, key=lambda c: -c[4])[:40]:
        print(f"{d}  {b:11s} {s0 or 0:6.1f} {s1:6.1f} {n:6d}  {stars(s0)} -> {stars(s1)}")


if __name__ == "__main__":
    main()
