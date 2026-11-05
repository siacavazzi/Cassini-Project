"""The WAC mosaic of one pass from the branch's preview server, with the geom step off (before) and on (after),
re-asking until it is complete (behind = 0). python3 mos.py LASTFRAME OUTDIR"""
import json, os, sys, time, urllib.request, urllib.error
H = "http://127.0.0.1:8894"
last, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
def get(u):
    try:
        with urllib.request.urlopen(H + u, timeout=1800) as r: return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)
    except Exception as e: return "ERR", repr(e).encode(), {}
def behind(h):
    for k, v in h.items():
        if k.lower().startswith("x-") and "behind" in v:
            try: return json.loads(v).get("behind", 0) or 0
            except ValueError: pass
    return 0
for tag, q in (("before", "&off=geom"), ("after", "")):
    for size in (1024, "full"):
        u = f"/frames/mosaic/{last}.webp?size={size}{q}"
        t0 = time.time(); tries = 0
        while True:
            st, b, h = get(u); tries += 1
            if (st == 200 and behind(h) == 0) or (st != 200 and b"yet" not in b) or tries > 120: break
            time.sleep(15)
        print(tag, size, st, round(time.time() - t0), "s", tries, {k: v for k, v in h.items() if k.lower().startswith("x-")}, flush=True)
        if st == 200: open(os.path.join(out, f"{tag}_{size}.webp"), "wb").write(b)
        else: print(b[:500])
