import json, os
C = "/Volumes/SAM_IAC_PHOTO/cassini-work/cache-full-f9ab1b4"
p = os.path.join(C, "color-v58-q95-ctr10-s1024", "1024")
out = []
for name in os.listdir(p):
    if not name.endswith(".json"): continue
    try: r = json.load(open(os.path.join(p, name)))
    except Exception: continue
    out.append([name[:-5], r.get("grey"), r.get("grey_moved"), r.get("aligned"), r.get("calibrated"), r.get("dropped"), r.get("centred"), r.get("stacked")])
print(json.dumps(out))
