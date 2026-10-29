"""How obs_mosaic lays out the passes the image quality check (2026-10-28, group H) found drawn wrong, on the frames
of those observations as the Mac Mini's index and geometry cache have them (web/test_mosaic_layout.json):
- a time series is a movie, not a mosaic: Saturn's limb every 28 minutes (267SA_LIMBINT002), the WAC beside a NAC
  feature track (191SA_FEATRAK001), a CIRS scan map of Jupiter (C23JU_NSMAP103); a map whose later columns overlap its
  earlier ones (221DI_REGMAP001), a mosaic stepping slowly (242SA_NHEMOSAIC001) and the two ring ansae of an F ring
  monitor (042RI_FMONITOR001) stay mosaics (_revisits);
- a filter set drifting over one view is one picture (STORMW riders, _one_view), and taken lap after lap a movie
  (Saturn's approach, C44SA_APPRMOVB001: its colour set every 104 minutes);
- a map split by ZOOM is joined again (042TI_GLOBMAP001, _zoom_join); a movie that re-points to sky it never comes back
  to plays each view as a pass (287RI_PROPRETRG001, _retargets);
- a lone frame near the middle no longer puts the other filters aside (044RI_PHOTDRK003, _aside);
- a mosaic the camera turns under has a footprint holding every tile the v46 cache placed (033RI_AZDKMRHPH001,
  173RI_DRCLOSE001, 208TI_HIRES002; footprint), where one angle left most of them outside;
- the passes these rules change get RELAID's folder, every other pass keeps its own.
Run: python web/test_mosaic_layout.py; with --refresh (and the index and CASSINI_GEOMETRY_CACHE) it writes the frames
of the observations again."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import pandas as pd
import obs_mosaic as om

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_mosaic_layout.json")
OBS = [("SATURN", "ISS_267SA_LIMBINT002_PRIME", "N"), ("SATURN", "ISS_191SA_FEATRAK001_PRIME", "W"),
       ("JUPITER", "CIRS_C23JU_NSMAP103_PRIME", "N"), ("DIONE", "ISS_221DI_REGMAP001_PIE", "N"),
       ("SATURN", "ISS_242SA_NHEMOSAIC001_PRIME", "W"), ("SATURN", "ISS_042RI_FMONITOR001_PRIME", "W"),
       ("SATURN", "ISS_202SA_STORMW004_RIDER", "W"), ("TITAN", "ISS_042TI_GLOBMAP001_PRIME", "N"),
       ("SATURN", "ISS_287RI_PROPRETRG001_PRIME", "N"), ("SATURN", "ISS_044RI_PHOTDRK003_PRIME", "W"),
       ("DIONE", "ISS_129DI_REGMAP001_PRIME", "N"), ("SATURN", "ISS_033RI_AZDKMRHPH001_PRIME", "N"),
       ("SATURN", "ISS_173RI_DRCLOSE001_PIE", "N"), ("TITAN", "ISS_208TI_HIRES002_VIMS", "W"),
       ("SATURN", "ISS_C44SA_APPRMOVB001_PRIME", "N")]
# the v46 cache's plan (angle, the frame it was measured on) and tile outlines of three passes the camera turns under
# (/mnt/project-files/mosaic-layout/qc-data/v46-json)
V46 = "/mnt/project-files/mosaic-layout/qc-data/v46-json"


def refresh():
    import glob
    import reel
    idx, _ = reel.load_index()
    out = {"frames": [], "v46": {}}
    for target, obs, cam in OBS:
        rows = idx[(idx["TARGET_NAME"] == target) & (idx["OBSERVATION_ID"] == obs)
                   & (idx["INSTRUMENT_ID"] == ("ISSNA" if cam == "N" else "ISSWA"))]
        ids = rows["id"].tolist()
        geo, turned = reel.geometry(ids), reel.turns(ids)
        for r in rows.itertuples(index=False):
            g = geo.get(r.id)
            out["frames"].append([target, obs, cam, r.id, str(r.filter1), str(r.filter2), float(r.seconds_1970),
                                  *([round(v, 2) for v in g] if g else [None] * 3), turned.get(r.id)])
    for d in sorted(glob.glob(V46 + "/*")):
        p = json.load(open(d + "/plan4.json"))
        tiles = sorted((json.load(open(f)) for f in glob.glob(glob.glob(d + "/tiles-*")[0] + "/*.json")),
                       key=lambda t: t["n"])
        out["v46"][os.path.basename(d)] = {"key": p["key"], "angle": p["angle"], "footprint": p["footprint"],
                                           "tiles": [[t["id"], [[round(v, 1) for v in q] for q in t["outline"]]]
                                                     for t in tiles]}
    with open(CASES, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(out['frames'])} frames, {len(out['v46'])} v46 passes in {CASES}")


def load():
    """the observations' frames as units reads them: om._observations, reel.geometry and reel.turns stand in"""
    cases = json.load(open(CASES))
    rows = [{"path": f"x/{fid}.png", "id": fid, "filter1": f1, "filter2": f2, "seconds_1970": t, "TARGET_NAME": target,
             "OBSERVATION_ID": obs, "INSTRUMENT_ID": "ISSNA" if cam == "N" else "ISSWA"}
            for target, obs, cam, fid, f1, f2, t, *_ in cases["frames"]]
    idx = pd.DataFrame(rows).sort_values("seconds_1970", kind="stable").reset_index(drop=True)
    geo = {fr[3]: tuple(fr[7:10]) for fr in cases["frames"] if fr[7] is not None}
    turned = {fr[3]: fr[10] for fr in cases["frames"] if fr[10] is not None}
    groups = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices
    om._observations = lambda: (idx, groups)
    om.reel.geometry = lambda ids: {i: geo[i] for i in ids if i in geo}
    om.reel.turns = lambda ids: {i: turned[i] for i in ids if i in turned}
    om._units.clear()
    om._unit_of.clear()
    rowmap = dict(zip(idx["id"], range(len(idx))))
    om._row_of = lambda: (idx, rowmap)
    return cases


def passes(target, obs, cam):
    return om.units(target, obs, cam)


def kinds(us):
    return [(u["kind"], len(u["frames"])) for u in us]


def relaid(u):
    return om.folder(u, "/c").endswith(om.RELAID)


def main():
    cases = load()

    # time series: movies, in RELAID's folder
    for key in OBS[:3]:
        us = [u for u in passes(*key) if len(u["frames"]) >= 20]
        assert us and all(u["kind"] == "movie" and u["revisit"] and relaid(u) for u in us), (key, kinds(us))
    # maps and mosaics overlapping their earlier ground, and the F ring monitor's two ansae, stay mosaics
    dione = passes(*OBS[3])
    big = max(dione, key=lambda u: len(u["frames"]))
    assert big["kind"] == "mosaic" and len(big["frames"]) == 125 and not big["revisit"], kinds(dione)
    nhem = passes(*OBS[4])
    assert kinds(nhem) == [("mosaic", 96)] and not nhem[0]["revisit"], kinds(nhem)
    fmon = passes(*OBS[5])
    assert fmon[0]["kind"] == "mosaic" and not fmon[0]["revisit"], kinds(fmon)

    # a filter set drifting over one view: one picture (no mosaic)
    storm = passes(*OBS[6])
    assert kinds(storm) == [(None, 5)] and storm[0]["drift"] and relaid(storm[0]), kinds(storm)

    # ... and the same view's filter set lap after lap: a movie
    appr = passes(*OBS[14])
    assert kinds(appr) == [("movie", 70)] and appr[0]["views"] and relaid(appr[0]), kinds(appr)

    # Titan's global map split by ZOOM: one mosaic again (100 pictures: a CB3 repeat 25-36 px off is its own, _pictures)
    titan = passes(*OBS[7])
    assert kinds(titan) == [("mosaic", 100)] and titan[0]["joined"] and relaid(titan[0]), kinds(titan)

    # the Grand Finale's propeller movie re-pointed three times: four movies
    prop = passes(*OBS[8])
    assert [k for k, _ in kinds(prop)] == ["movie"] * 4 and sum(n for _, n in kinds(prop)) == 77, kinds(prop)
    assert all(relaid(u) for u in prop)

    # a lone IR2/IR1 frame near the middle no longer sets the 95 others aside
    dark = passes(*OBS[9])
    assert dark[0]["kind"] == "mosaic" and dark[0]["aside"] and om._aside(dark[0]["frames"], dark[0]) == set(), kinds(dark)

    # a plain map keeps its folder
    reg = passes(*OBS[10])
    assert kinds(reg) == [("mosaic", 41), ("mosaic", 39)] and not any(u["relaid"] for u in reg), kinds(reg)
    assert om.folder(reg[0], "/c").endswith("DIONE_ISS_129DI_REGMAP001_PRIME_N_0")

    # the camera turning under a mosaic: the footprint holds every tile v46 placed (one angle left most outside)
    for name, v in cases["v46"].items():
        target, obs, cam, n = v["key"]
        first = v["tiles"][0][0]
        u = next(u for u in passes(target, obs, cam) if u["frames"] and u["frames"][0][1] == first)
        if not u.get("twist"):   # (173RI_DRCLOSE001 is a movie now: its footprint as a mosaic's)
            u = dict(u, twist={fr[1]: t for fr in u["frames"] for t in [om.reel.turns([fr[1]]).get(fr[1])] if t is not None})
        ref = next(fr[1] for fr in u["frames"] if fr[7] and math.hypot(fr[5], fr[6]) > 200)
        new = om.footprint(u, v["angle"], ref, om._aside(u["frames"], u))

        def outside(fp):
            out = 0
            for _, outline in v["tiles"]:
                xs, ys = [q[0] for q in outline], [q[1] for q in outline]
                share = (max(0, min(max(xs), fp[2]) - max(min(xs), fp[0])) * max(0, min(max(ys), fp[3]) - max(min(ys), fp[1]))
                         / ((max(xs) - min(xs)) * (max(ys) - min(ys))))
                out += share < 0.99
            return out
        assert outside(new) == 0 and outside(v["footprint"]) > len(v["tiles"]) / 2, (name, outside(v["footprint"]), outside(new))
        if obs != "ISS_173RI_DRCLOSE001_PIE":
            assert u["kind"] == "mosaic" and relaid(u), (name, u["kind"])

    print("mosaic layout ok:", {o: kinds(passes(t, o, c)) for t, o, c in OBS})


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        refresh()
    else:
        main()
