import json, os, glob, csv, collections, datetime, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import catalog as C
D = os.path.dirname(os.path.abspath(__file__))
seqs = C.build(f"{D}/passes2.jsonl", 5)
# after the PR's rule: which pass each picture lands in
after = {}
for l in open(f"{D}/passes_after.jsonl"):
    p = json.loads(l)
    for q in p["pics"]:
        after[q[0]] = (p["pass_id"], p["kind"] or "")
before = {}
pics_of = {}
for l in open(f"{D}/passes2.jsonl"):
    p = json.loads(l)
    pics_of[p["pass_id"]] = [q[0] for q in p["pics"]]
# the live site's data (web/replay/data of the 8765 checkout)
live = {}
for f in sorted(glob.glob(os.path.expanduser("~/dev/Cassini-Project/web/replay/data/months/*.json"))):
    d = json.load(open(f))
    ps = d.get("groups", {}).get("passes", {})
    for i, pa in zip(d["id"], d["pass"]):
        if pa is not None and pa >= 0:
            live[i] = (pa, (ps.get(str(pa)) or [""])[0])
def verdict(ids, table):
    got = [table.get(i) for i in ids]
    mv = {g[0] for g in got if g and g[1] in ("movie", "mosaic_movie")}
    allp = {g[0] for g in got if g}
    if len(mv) == 1 and len(allp) == 1 and None not in got:
        return "yes"
    if mv:
        return "split" if len(allp) > 1 else "part"
    return "no"
spot = set(re.findall(r"ISS_[0-9A-Z]{3}[A-Z]{2}_[A-Z0-9]+_[A-Z]+", open(f"{D}/spotcheck4.html").read())) if os.path.exists(f"{D}/spotcheck4.html") else set()
rows = []
utc = lambda t: datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S")
for s in seqs:
    ids = [i for pid in s["passes"] for i in pics_of[pid]]
    s["main_now"] = s["ours"]
    s["after_pr"] = verdict(ids, after)
    s["live_site"] = verdict(ids, live)
    s["in_spot_check_4"] = any(o in spot for o in s["obs"])
    s["ids"] = ids
    rows.append(s)
json.dump(rows, open(f"{D}/catalog_all.json", "w"))
print(len(rows), "live frames", len(live))
