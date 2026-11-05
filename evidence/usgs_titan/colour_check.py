# For each pass of the Titan observations that hold USGS frames: grey or colour (obs_mosaic.colour_of on its tiles
# per filter), and its tile count, with the geometry cache this run is given. argv: repo years out.json
import sys, os, json, collections
sys.path.insert(0, sys.argv[1] + "/web/frames"); sys.path.insert(0, sys.argv[1])
import pandas as pd
import obs_mosaic as om
years = sys.argv[2].split(",")
usgs = {l.strip() for l in open(sys.argv[1] + "/spice_extra/usgs_titan/images.lis")}
ix = pd.read_csv(sys.argv[1] + "/Image_index.csv", usecols=["path", "OBSERVATION_ID", "IMAGE_MID_TIME"], low_memory=False)
ix = ix[ix.path.notna() & ix.IMAGE_MID_TIME.str[:4].isin(years)]
ix["frame"] = ix.path.str.split("/").str[-1].str.split(".").str[0]
obs = sorted(set(ix[ix.frame.isin(usgs)].OBSERVATION_ID))
out = {}
for o in obs:
    for cam in "NW":
        try:
            us = om.units("TITAN", o, cam)
        except Exception as e:
            continue
        for u in us:
            count = collections.Counter(fr[2] for fr in u["frames"])
            nms = {fr[2]: fr[4] for fr in u["frames"]}
            c = om.colour_of(count, nms) if count else None
            out["/".join(map(str, u["key"]))] = [u["kind"], len(u["frames"]), c]
json.dump(out, open(sys.argv[3], "w"), indent=0)
print(len(out), "passes")
