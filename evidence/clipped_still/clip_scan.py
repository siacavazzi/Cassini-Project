"""Read-only scan: every still mosaic / mosaic movie in colour, where #384's still rule (visit_tiles: long_repeats |
clipped_pointings) differs from before #384 (long_repeats only) and from the fix (long_repeats | clipped_still).
Pass lists and rules are the checkout's own obs_mosaic; saturation is calibration.saturated_of on each colour frame
(the share the camera saturated, as the tile report's "saturated" for a frame with no repeats). Tile places are the
geometry cache's, scaled to the pass's distance as _slot_of does (before panel registration)."""
import os, sys, json, multiprocessing as mp
code = sys.argv[1]; out = sys.argv[2]; workers = int(sys.argv[3]) if len(sys.argv) > 3 else 3
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))

def init():
    global om, cal, lh, np
    import frame_server  # noqa
    import obs_mosaic as om, calibration as cal, label_handler as lh, numpy as np

def share(path):
    try:
        lbl = lh.label(path, as_png=True)
        m = cal.saturated_of(lbl, (om.FRAME, om.FRAME))
        return float(np.asarray(m).mean()) if m is not None else 0.0
    except Exception as e:  # noqa
        return None

def one(key):
    target, obs, inst = key
    cam = "N" if inst == "ISSNA" else "W"
    rows = []
    try:
        us = om.units(target, obs, cam)
    except Exception as e:
        return [{"obs": obs, "target": target, "cam": cam, "error": repr(e)[:200]}]
    for u in us:
        if u.get("kind") not in ("mosaic", "mosaic_movie") or not u["frames"] or not u.get("z"):
            continue
        count, nms = {}, {}
        for fr in u["frames"]:
            count[fr[2]] = count.get(fr[2], 0) + 1; nms[fr[2]] = fr[4]
        try:
            colour = om.colour_of(count, nms)
        except Exception:
            colour = None
        if not colour or len(colour) < 2:
            continue
        tiles = []
        for n, (path, fid, f, t, nm, x, y, z) in enumerate(u["frames"]):
            if f not in colour or not z:
                continue
            s = share(path)
            k = z / u["z"]
            tiles.append({"n": n, "id": fid, "filter": f, "t": t, "saturated": s or 0.0, "lit": 1.0,
                          "offset": [-x * k, -y * k], "box": [-512 * k, -512 * k, 1024 * k, 1024 * k]})
        if not any(t["saturated"] >= om.CLIP_UNDER for t in tiles):
            continue
        lr = om.long_repeats(tiles, colour)
        bad = lr | om.clipped_pointings(u, tiles)
        fix = lr | (om.clipped_still(u, tiles, colour) if hasattr(om, "clipped_still") else set())
        rows.append({"obs": obs, "target": target, "cam": cam, "pass": "_".join(map(str, u["key"])), "kind": u["kind"],
                     "frames": len(u["frames"]), "colour": colour, "last": u["frames"][-1][1],
                     "clipped": sorted(om.clipped_under(tiles)), "long": sorted(lr), "bad": sorted(bad), "fix": sorted(fix), "fix_only": sorted(om.clipped_still(u, tiles, colour)),
                     "max_sat": round(max(t["saturated"] for t in tiles), 3),
                     "ids": {t["n"]: t["id"] for t in tiles if t["n"] in bad | fix}})
    return rows

if __name__ == "__main__":
    init()
    idx, groups = om._observations()
    keys = [k for k in groups if k[2] in ("ISSNA", "ISSWA") and isinstance(k[1], str)]
    print(len(keys), "observations", flush=True)
    done = 0
    with mp.Pool(workers, initializer=init) as pool, open(out, "w") as fh:
        for rows in pool.imap_unordered(one, keys, chunksize=4):
            done += 1
            for r in rows:
                fh.write(json.dumps(r) + "\n"); fh.flush()
            if done % 200 == 0:
                print(done, flush=True)
