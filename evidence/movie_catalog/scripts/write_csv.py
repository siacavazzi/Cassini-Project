import json, csv, datetime, collections, re
R = json.load(open("catalog_all.json"))
utc = lambda t: datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S")
def cls(r):
    d = r["disk_px"]
    if r["nontarget"]: return "sky/star"
    return "no size" if d is None else "point (<10 px)" if d < 10 else "small (10-100 px)" if d < 100 else "disk (100+ px)"
VIEW = {"SATURN": "saturn"}
out = [r for r in R if r["steps"] >= 10]
out.sort(key=lambda r: r["start"])
cols = ["sequence", "target", "camera", "filters", "color", "frames", "time_steps", "start_utc", "end_utc", "span_hours",
        "cadence_s", "visit_period_s", "on_cadence", "steady", "flagged_in_metadata", "movie_on_main_now", "movie_after_pr",
        "movie_on_live_site", "in_spot_check_4", "target_px", "target_class", "judged_as", "observations", "passes_on_main", "first_frame", "last_frame", "link"]
with open("/Users/lazarus/agents/outputs/movie-catalog/movie_catalog.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(cols)
    for n, r in enumerate(out, 1):
        view = r["target"].lower() if not r["nontarget"] else "cassini"
        w.writerow([f"M{n:04d}", r["target"], r["camera"], " ".join(r["filters"]), "yes" if r["colour"] else "no", r["frames"], r["steps"],
                    utc(r["start"]), utc(r["end"]), round((r["end"] - r["start"]) / 3600, 2), round(r["cadence"]) if r["cadence"] else "",
                    round(r["visit_period"]) if r["visit_period"] else "", r["on_cadence"], "yes" if r["on_cadence"] >= 0.5 else "no",
                    "yes" if r["flagged"] else "no", r["main_now"], r["after_pr"], r["live_site"], "yes" if r["in_spot_check_4"] else "no",
                    r["disk_px"] if r["disk_px"] is not None else "", cls(r), "+".join({"movie": "pipeline movie", "laps": "mosaic laps", "stare": "same view", "creep": "steady pan", "revisits": "view revisited"}[h] for h in r["how"]), " ".join(r["obs"]), " ".join(map(str, r["passes"])),
                    r["first"].split("/")[-1].replace(".png", ""), r["last"].split("/")[-1].replace(".png", ""),
                    f"http://100.76.189.126:8765/?t={utc(r['start'])}&view={view}&speed=600&play=0&movie=1"])
print(len(out))
# stats for the report
real = [r for r in out if not r["nontarget"]]
print("real", len(real), "flag", sum(r["flagged"] for r in real), "sky", len(out) - len(real))
print(collections.Counter(cls(r) for r in real))
print("colour", sum(r["colour"] for r in real), "NAC", sum(r["camera"] == "NAC" for r in real))
print("new for us (main split/no, unflagged):", sum(r["main_now"] != "yes" for r in real), sum(r["main_now"] != "yes" and not r["flagged"] for r in real))
# flagged observations that never reach 10 steps
allobs = collections.defaultdict(int)
for r in R:
    for o in r["obs"]: allobs[o] = max(allobs[o], r["steps"])
import pandas as pd
ix = pd.read_csv("/Users/lazarus/dev/wt-moviecat/Image_index.csv", usecols=["OBSERVATION_ID"])
FLAG = re.compile(r"MOV|MV(?!E)")
fl = [o for o in ix.OBSERVATION_ID.dropna().unique() if FLAG.search(o)]
covered = {o for r in real for o in r["obs"]}
print("flagged obs", len(fl), "in catalog", sum(o in covered for o in fl), "not", sum(o not in covered for o in fl))
