#!/usr/bin/env python3
"""Spot check round 2, color composites: fetch each sampled set's composite from the on-the-fly preview (8861, main
d4d9ecc) plain and Auto-centred, and from live 8765 (old cache) as "before"; save JPEGs and the X-Composite reports,
and push them to an orphan branch every CHUNK sets so the cloud thread can view them. Read only on the servers.
  python3 qc2_color_fetch.py sample.json OUTDIR PUSHDIR"""
import io, json, os, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

NEW, OLD, CHUNK = "http://127.0.0.1:8861", "http://127.0.0.1:8765", 40
sample, out, push = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
done_path = os.path.join(out, "results.json")
done = json.load(open(done_path)) if os.path.exists(done_path) else {}


def get(url, tries=60, timeout=600):
    t0 = time.time()
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read(), dict(r.headers), round(time.time() - t0, 1), 200
        except urllib.error.HTTPError as e:
            if e.code == 503:
                time.sleep(5)
                continue
            return None, dict(e.headers or {}), round(time.time() - t0, 1), e.code
        except Exception as e:
            return None, {"error": str(e)[:200]}, round(time.time() - t0, 1), -1
    return None, {}, round(time.time() - t0, 1), 503


def jpg(data, path):
    im = Image.open(io.BytesIO(data))
    bg = Image.new("RGB", im.size, (0, 0, 0))
    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
    bg.save(path, quality=85)


def one(r):
    key, rec = r["key"], {"set": r}
    for name, base, extra, tries in (("new", NEW, "", 60), ("ctr", NEW, "&center=1", 60), ("old", OLD, "", 3)):
        data, hdr, secs, code = get(f"{base}/frames/color.webp?ids={r['ids']}&size=1024{extra}", tries, 600 if name != "old" else 120)
        rec[name] = {"code": code, "secs": secs, "report": hdr.get("X-Composite") or hdr.get("X-Center") or hdr.get("error")}
        if data:
            try:
                jpg(data, os.path.join(out, f"{key}__{name}.jpg"))
            except Exception as e:
                rec[name]["code"] = f"bad image {e}"[:100]
    return key, rec


def publish(n):
    subprocess.run(f"rsync -a --include='*.jpg' --include='results.json' --exclude='*' '{out}/' '{push}/' && cd '{push}' && "
                   f"git add -A && git commit -qm 'qc2 color: {n} sets' && git push -q origin HEAD:scratch/qc2-color",
                   shell=True)


todo = [r for r in sample if r["key"] not in done]
print(len(done), "done,", len(todo), "to do", flush=True)
with ThreadPoolExecutor(2) as pool:
    for k, (key, rec) in enumerate(pool.map(one, todo), 1):
        done[key] = rec
        print(len(done), key, rec["new"]["code"], rec["new"]["secs"], rec["old"]["code"], flush=True)
        json.dump(done, open(done_path, "w"), indent=0)
        if k % CHUNK == 0:
            publish(len(done))
publish(len(done))
print("ALL DONE", len(done), flush=True)
