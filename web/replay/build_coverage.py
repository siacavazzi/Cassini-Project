"""What Cassini had seen of each moon, and when: the data behind "Seen so far" and "Pictures of this place".

For every picture with recorded pointing, and every mapped moon in its field of view, this works out which places on
the moon the picture shows (sunlit, facing the camera) and how finely (km per pixel there). From that it writes, into
the page's own data folder:

  coverage/<moon>.cov        gzip of TIERS stacked 720 x 360 maps (RGBA, rows north first, longitude 0 in the middle,
                             east to the right: the layout of the surface maps). Each texel holds the first time the
                             place was seen at that tier's resolution or better, as a 24-bit count of DT seconds from
                             T0 in R, G, B (0xFFFFFF: never). Tier k is TIER_KM[moon][k] km per pixel or better; the
                             last tier is the scale of the 2k surface map.
  coverage/<moon>.places.json  for each 2 x 2 degree cell, the K sharpest observations of it (one picture each)
  coverage/index.json        T0, DT, the grid, each moon's tier resolutions, the years covered

It reads only what the page reads (mission.json, catalog/, attitude/, tracks/ under --data), with the page's own
geometry: the camera's axes are the rows of q2m(image_q), a moon turns by the linear IAU terms (replay/index.html
iauMatrix), and a place is on the ellipsoid of the moon's radii. No pictures are opened.

usage: python web/replay/build_coverage.py --data web/replay/data [--years 2004-2017] [--workers N]
"""
import argparse, gzip, json, math, os, struct, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

W, H = 720, 360                      # the coverage grid: half a degree
CELL = 4                             # a "place" is CELL x CELL texels: 2 degrees
TIERS = 6                            # tier k: seen at 2k-map scale x 2^(TIERS-1-k) or better
K = 8                                # observations kept per place
T0_UTC, DT = "2004-01-01T00:00:00", 30.0
FOV_HALF = {"N": math.radians(0.3516 / 2), "W": math.radians(3.4884 / 2)}   # as the page's
IFOV = {"N": 5.99e-6, "W": 59.9e-6}  # radians per pixel (catalog km_per_px / range_km)
MAX_EMISSION, MAX_INCIDENCE = math.radians(80), math.radians(85)
# moons with a surface map on the page and an IAU rotation (Hyperion tumbles: the page spins it by a made-up rule)
MOONS = ["MIMAS", "ENCELADUS", "TETHYS", "DIONE", "RHEA", "IAPETUS", "PHOEBE", "TITAN"]
# Titan's surface only shows through the haze in the 938 nm window, so only those pictures count as seeing it
TITAN_FILTERS = {"CB3"}


def utc_to_et(s):
    """UTC to ephemeris seconds past J2000, as the page's utcToEt (leap seconds since 1999 and 2006)."""
    import datetime
    d = datetime.datetime.fromisoformat(s)
    t = (d - datetime.datetime(2000, 1, 1, 12)).total_seconds()
    leap = 32 if d < datetime.datetime(2006, 1, 1) else 33 if d < datetime.datetime(2009, 1, 1) else 34 if d < datetime.datetime(2012, 7, 1) \
        else 35 if d < datetime.datetime(2015, 7, 1) else 36 if d < datetime.datetime(2017, 1, 1) else 37
    return t + leap + 32.184


def load_track(path):
    b = open(path, "rb").read()
    assert b[:4] == b"CTRK", path
    n = struct.unpack_from("<I", b, 8)[0]
    return (np.frombuffer(b, "<f8", n, 16), np.frombuffer(b, "<f8", 3 * n, 16 + 8 * n).reshape(n, 3),
            np.frombuffer(b, "<f4", 3 * n, 16 + 32 * n).reshape(n, 3).astype(np.float64))


def track_at(tr, et):
    """Cubic Hermite position at each et (the page's positionAt); NaN outside the track."""
    t, p, v = tr
    et = np.atleast_1d(np.asarray(et, np.float64))
    i = np.clip(np.searchsorted(t, et, "right") - 1, 0, len(t) - 2)
    h = (t[i + 1] - t[i])[:, None]
    u = ((et - t[i])[:, None]) / h
    out = (2 * u**3 - 3 * u**2 + 1) * p[i] + (u**3 - 2 * u**2 + u) * h * v[i] + (-2 * u**3 + 3 * u**2) * p[i + 1] + (u**3 - u**2) * h * v[i + 1]
    out[(et < t[0]) | (et > t[-1])] = np.nan
    return out


def load_image_q(path):
    b = open(path, "rb").read()
    magic, _ver, _flags, nimg, _nbg = struct.unpack_from("<4sHHII", b, 0)
    assert magic == b"CATT", path
    return np.frombuffer(b, "<f4", 4 * nimg, 16).reshape(nimg, 4).astype(np.float64)


def q2m(q):
    """Rows: the frame's axes in J2000 (SPICE q2m)."""
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
                     np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
                     np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], -2)


def iau_matrix(b, et):
    """J2000 -> body-fixed, rows; the page's iauMatrix (linear terms only), so places land where the page draws them."""
    d = et / 86400.0
    T = d / 36525.0
    ra, dec = math.radians(b["pole_ra"][0] + b["pole_ra"][1] * T), math.radians(b["pole_dec"][0] + b["pole_dec"][1] * T)
    Wr = math.radians((b["pm"][0] + b["pm"][1] * d) % 360.0)
    z = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])
    node = np.cross([0, 0, 1.0], z)
    node /= np.linalg.norm(node)
    y0 = np.cross(z, node)
    x = math.cos(Wr) * node + math.sin(Wr) * y0
    return np.stack([x, np.cross(z, x), z])


def grid():
    """Unit vectors of the texel centers in the body frame, [H * W, 3]; row 0 is the north edge, column 0 is 180 W."""
    lon = (np.arange(W) + 0.5) / W * 2 * np.pi - np.pi
    lat = np.pi / 2 - (np.arange(H) + 0.5) / H * np.pi
    lo, la = np.meshgrid(lon, lat)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1).reshape(-1, 3)


def tiers_km(radii):
    p2k = 2 * math.pi * (sum(radii) / 3) / 2048
    return [p2k * 2 ** (TIERS - 1 - k) for k in range(TIERS)]


def moon_pass(args):
    """One year of one moon: (first-seen times [TIERS, H*W], the K best (resolution, year * 1e6 + picture) per place, pictures used,
    Cassini's range for each picture kept)."""
    data, year, moon = args
    tdir = os.path.join(data, "tracks", str(year))
    if not os.path.exists(os.path.join(tdir, moon.lower() + ".bin")):
        return year, moon, None
    mission = json.load(open(os.path.join(data, "mission.json")))
    cat = json.load(open(os.path.join(data, "catalog", f"{year}.json")))
    q = load_image_q(os.path.join(data, "attitude", f"{year}.bin"))
    n = len(cat["et"])
    assert len(q) == n, f"{year}: {len(q)} pointings for {n} pictures (the attitude file is from another catalog)"
    et = np.asarray(cat["et"], np.float64)
    cam = np.asarray(cat["cam"])
    f1, f2, obs = cat["f1"], cat["f2"], cat["obs"]
    trk = lambda name: load_track(os.path.join(tdir, name.lower() + ".bin"))
    pc, psun = track_at(trk("CASSINI"), et), track_at(trk("SUN"), et)
    C = q2m(q)                                   # [n, 3, 3]
    ok = np.isfinite(q).all(1) & np.isfinite(pc).all(1)
    half = np.where(cam == "W", FOV_HALF["W"], FOV_HALF["N"])
    ifov = np.where(cam == "W", IFOV["W"], IFOV["N"])
    diag = np.arctan(math.sqrt(2) * np.tan(half))
    b = mission["bodies"][moon]
    radii = np.asarray(b["radii"], np.float64)
    thr = np.asarray(tiers_km(b["radii"]))
    # two grids, both in place order (a place's texels together, so a picture's texels group by place without a sort):
    # every texel, and one point per place for pictures too coarse to tell a place's texels apart
    ncell = (W // CELL) * (H // CELL)
    cell_of = (np.arange(H)[:, None] // CELL * (W // CELL) + np.arange(W)[None, :] // CELL).reshape(-1)
    perm = np.argsort(cell_of, kind="stable")    # place order -> texel index
    G = grid()
    fine = dict(G=np.ascontiguousarray(G[perm]), cell=cell_of[perm])
    coarse = dict(G=np.ascontiguousarray(G[perm].reshape(ncell, CELL * CELL, 3).mean(1)), cell=np.arange(ncell))
    for g in (fine, coarse):
        g["G"] /= np.linalg.norm(g["G"], axis=1)[:, None]
        g["P"] = g["G"] * radii                  # the places, km
        g["N"] = g["G"] / radii
        g["N"] /= np.linalg.norm(g["N"], axis=1)[:, None]   # the ellipsoid's normals
    pb = track_at(trk(moon), et)
    rel = pc - pb                                # the moon -> Cassini, J2000
    rng = np.linalg.norm(rel, axis=1)
    with np.errstate(invalid="ignore"):
        off = np.arccos(np.clip(-(C[:, 2, :] * rel).sum(1) / rng, -1, 1))
        near = ok & np.isfinite(rng) & (off < diag + np.arcsin(np.clip(radii.max() / rng, 0, 1))) & ((rng - radii.max()) * ifov < thr[0])
    if moon == "TITAN":
        near &= np.array([a in TITAN_FILTERS or c in TITAN_FILTERS for a, c in zip(f1, f2)])
    # first[t]: the first time a place was seen with tier t as its finest; tiers are cumulated at the end
    first = np.full((TIERS, ncell, CELL * CELL), np.inf)
    top_res = np.full((ncell, K), np.inf)
    top_ref = np.full((ncell, K), -1, np.int64)
    cand_res, cand_ref, cand_obs = np.full(ncell, np.inf), np.full(ncell, -1, np.int64), None
    cos_e_min, cos_i_min = math.cos(MAX_EMISSION), math.cos(MAX_INCIDENCE)

    def merge():
        cells = np.nonzero(np.isfinite(cand_res))[0]
        if len(cells):
            slot = top_res[cells].argmax(1)
            better = cand_res[cells] < top_res[cells, slot]
            top_res[cells[better], slot[better]] = cand_res[cells[better]]
            top_ref[cells[better], slot[better]] = cand_ref[cells[better]]
        cand_res[:] = np.inf
        cand_ref[:] = -1

    idx = np.nonzero(near)[0]
    # by observation, so each place keeps one picture per observation
    idx = idx[np.argsort(np.array([obs[i] for i in idx]), kind="stable")] if len(idx) else idx
    for k in idx:
        if obs[k] != cand_obs:
            merge()
            cand_obs = obs[k]
        B = iau_matrix(b, et[k])
        o = B @ rel[k]                           # Cassini in the body frame, km
        sun = B @ (psun[k] - pb[k])
        sun /= np.linalg.norm(sun)
        # a picture that cannot reach tier 3 anywhere blurs the map by more than a place: one point per place will do
        g = coarse if (rng[k] - radii.max()) * ifov[k] > thr[3] else fine
        v = np.nonzero((g["G"] @ (o / radii) > 1.0) & (g["N"] @ sun > cos_i_min))[0]   # this side of the horizon, and sunlit
        if not len(v):
            continue
        to_cam = o - g["P"][v]
        dist = np.sqrt((to_cam * to_cam).sum(1))
        cos_e = (g["N"][v] * to_cam).sum(1) / dist
        Pc = to_cam @ (-(C[k] @ B.T).T)          # the places from Cassini, in camera axes
        th = math.tan(half[k])
        inside = (Pc[:, 2] > 0) & (np.abs(Pc[:, 0]) <= th * Pc[:, 2]) & (np.abs(Pc[:, 1]) <= th * Pc[:, 2]) & (cos_e > cos_e_min)
        if not inside.any():
            continue
        v, res = v[inside], dist[inside] * ifov[k] / np.sqrt(cos_e[inside])   # km per pixel, mean of the two directions
        tier = np.searchsorted(-thr, -res, "right") - 1                       # the finest tier this resolution reaches (-1: none)
        c = g["cell"][v]
        if g is fine:
            m = tier >= 0
            f = first.reshape(-1)
            j = tier[m] * (ncell * CELL * CELL) + v[m]
            f[j] = np.minimum(f[j], et[k])
        else:
            m = tier >= 0
            first[tier[m], v[m]] = np.minimum(first[tier[m], v[m]], et[k])
        # this picture's sharpest view of each place it touches (v is in place order)
        starts = np.concatenate([[0], np.nonzero(np.diff(c))[0] + 1])
        cells, best = c[starts], np.minimum.reduceat(res, starts)
        win = best < cand_res[cells]
        cand_res[cells[win]] = best[win]
        cand_ref[cells[win]] = year * 1000000 + k
    merge()
    # seen at a finer tier is seen at every coarser one; then back to texel order
    first = np.minimum.accumulate(first[::-1], 0)[::-1].reshape(TIERS, -1)
    out = np.empty_like(first)
    out[:, perm] = first
    kept = set(int(r) for r in top_ref[top_ref >= 0])
    return year, moon, (out, top_res, top_ref, int(len(idx)), {r: float(rng[r % 1000000]) for r in kept})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="the page's data folder (mission.json, catalog/, attitude/, tracks/)")
    ap.add_argument("--years", default="2004-2017")
    ap.add_argument("--out", help="default: <data>/coverage")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args()
    lo, _, hi = a.years.partition("-")
    years = [y for y in range(int(lo), int(hi or lo) + 1)
             if os.path.exists(os.path.join(a.data, "attitude", f"{y}.bin")) and os.path.exists(os.path.join(a.data, "catalog", f"{y}.json"))]
    if not years:
        sys.exit("no year in that range has both a catalog and pointing under " + a.data)
    out = a.out or os.path.join(a.data, "coverage")
    os.makedirs(out, exist_ok=True)
    mission = json.load(open(os.path.join(a.data, "mission.json")))
    t0 = utc_to_et(T0_UTC)
    tasks = [(a.data, y, m) for y in years for m in MOONS]
    parts = {}
    with ProcessPoolExecutor(min(a.workers, len(tasks))) as ex:
        for y, m, got in ex.map(moon_pass, tasks):
            if got:
                parts[(y, m)] = got
    cats = {}
    index = {"t0": t0, "t0_utc": T0_UTC, "dt": DT, "grid": [W, H], "tiers": TIERS, "cell_deg": 360 / W * CELL, "k": K, "years": years, "moons": {}}
    for moon in MOONS:
        got = [parts[(y, moon)] for y in years if (y, moon) in parts]
        ranges = {r: v for g in got for r, v in g[4].items()}
        if not got:
            continue
        first = np.minimum.reduce([g[0] for g in got])
        res = np.concatenate([g[1] for g in got], 1)
        ref = np.concatenate([g[2] for g in got], 1)
        order = np.argsort(res, 1)[:, :K]
        res, ref = np.take_along_axis(res, order, 1), np.take_along_axis(ref, order, 1)
        # the stacked tiers, 24-bit times
        ticks = np.where(np.isfinite(first), np.clip(np.floor((first - t0) / DT), 0, 0xFFFFFE), 0xFFFFFF).astype(np.uint32).reshape(TIERS * H, W)
        rgba = np.dstack([(ticks >> 16) & 255, (ticks >> 8) & 255, ticks & 255, np.full_like(ticks, 255)]).astype(np.uint8)
        with gzip.GzipFile(os.path.join(out, moon.lower() + ".cov"), "wb", 9, mtime=0) as f:
            f.write(rgba.tobytes())
        # the places: a table of the pictures named, and each cell's [picture, meters per pixel] pairs, sharpest first
        used = sorted(set(int(r) for r in ref[ref >= 0]))
        where = {r: i for i, r in enumerate(used)}
        table = {c: [] for c in ("id", "et", "cam", "f1", "f2", "obs")}
        for r in used:
            y, k = divmod(r, 1000000)
            if y not in cats:
                cats[y] = json.load(open(os.path.join(a.data, "catalog", f"{y}.json")))
            for c in table:
                table[c].append(cats[y][c][k])
        # (Cassini's distance from the moon's center, worked out here: the catalog's range is to the picture's own target)
        table["range_km"] = [round(float(ranges[r])) for r in used]
        cells = {}
        for c in np.nonzero((ref >= 0).any(1))[0]:
            cells[str(int(c))] = [x for r, m in zip(ref[c], res[c]) if r >= 0 for x in (where[int(r)], int(round(m * 1000)))]
        json.dump({"moon": moon, "cell_deg": index["cell_deg"], "cols": W // CELL, "rows": H // CELL, "pictures": table, "cells": cells},
                  open(os.path.join(out, moon.lower() + ".places.json"), "w"), separators=(",", ":"))
        area = np.repeat(np.cos(np.pi / 2 - (np.arange(H) + 0.5) / H * np.pi), W)
        seen = [float((area * np.isfinite(first[t])).sum() / area.sum()) for t in range(TIERS)]
        index["moons"][moon] = {"cov": moon.lower() + ".cov", "places": moon.lower() + ".places.json", "tier_km": [round(x, 4) for x in tiers_km(mission["bodies"][moon]["radii"])],
                                "pictures": sum(g[3] for g in got), "seen": [round(s, 4) for s in seen]}
        print(f"{moon:10s} {index['moons'][moon]['pictures']:6d} pictures  seen by the end, coarse to fine: " + " ".join(f"{s * 100:5.1f}%" for s in seen)
              + f"  {os.path.getsize(os.path.join(out, moon.lower() + '.cov')) // 1024} KB + {os.path.getsize(os.path.join(out, moon.lower() + '.places.json')) // 1024} KB")
    json.dump(index, open(os.path.join(out, "index.json"), "w"), indent=1)
    print("ok", out)


if __name__ == "__main__":
    main()
