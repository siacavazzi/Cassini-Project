#!/usr/bin/env python3
"""Spot check round 2, movie passes: render each pass of passes.tsv on the on-the-fly preview, the way the page asks
for it by default (size 512, color 1, Auto center on, trail 0, laps 1, exposure normalization 8; mosaic movies via
mode=rolling), measure every frame, and make contact sheets. Report only: reads HTTP, writes only under --out.

  python qc2_movies.py --list passes.tsv --host http://127.0.0.1:8861 --out DIR [--push GITDIR] [--max 36] [--jobs 2]
"""
import argparse, csv, io, json, os, subprocess, sys, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image, ImageDraw

STYLE = "size=512&color=1&trail=0&laps=1&exposure=8"
ROLL = "mode=rolling&size=512&trail=0&laps=1&exposure=8"


def get(url, timeout=240, tries_503=90):
    """(status, body bytes, headers); retries 503 (pass being worked out) every 4 s."""
    for i in range(tries_503):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code == 503:
                time.sleep(4)
                continue
            return e.code, e.read(), dict(e.headers or {})
        except Exception as e:  # timeouts, resets
            if i >= 3:
                return 0, str(e).encode(), {}
            time.sleep(5)
    return 503, b"", {}


def pick(n, most):
    """frame indexes: all when few, else the first 2/3 of `most` in a row and the rest spread evenly over the remainder."""
    if n <= most:
        return list(range(n))
    run = most * 2 // 3
    rest = np.linspace(run, n - 1, most - run).round().astype(int).tolist()
    return sorted(set(list(range(run)) + rest))


def stats(im):
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    g = a.mean(axis=2)
    h, w = g.shape
    lit = g > max(24.0, np.percentile(g, 50) + 12)
    ys, xs = np.nonzero(lit)
    edge = (lit[0].mean() + lit[-1].mean() + lit[:, 0].mean() + lit[:, -1].mean()) / 4
    sat = (a.max(axis=2) - a.min(axis=2))
    return {"w": w, "h": h, "mean": round(float(g.mean()), 1), "p1": round(float(np.percentile(g, 1)), 1),
            "p50": round(float(np.percentile(g, 50)), 1), "p995": round(float(np.percentile(g, 99.5)), 1),
            "black": round(float((g < 6).mean()), 3), "white": round(float((g > 250).mean()), 4),
            "lit": round(float(lit.mean()), 3), "edge_lit": round(float(edge), 3),
            "cx": round(float(xs.mean() / w), 3) if len(xs) else -1, "cy": round(float(ys.mean() / h), 3) if len(ys) else -1,
            "chroma": round(float(sat.mean()), 1)}


def label(im, text, size):
    t = im.convert("RGB").copy()
    t.thumbnail((size, size))
    c = Image.new("RGB", (size, size), (40, 40, 48))
    c.paste(t, ((size - t.width) // 2, (size - t.height) // 2))
    d = ImageDraw.Draw(c)
    d.rectangle([0, 0, size, 14], fill=(0, 0, 0))
    d.text((3, 1), text, fill=(255, 255, 0))
    return c


def sheet(tiles, cols, size, path, title):
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new("RGB", (cols * size, rows * size + 18), (20, 20, 20))
    ImageDraw.Draw(out).text((4, 3), title, fill=(255, 255, 255))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % cols) * size, 18 + (i // cols) * size))
    out.save(path, quality=88)


def do_pass(row, a, log):
    group, tag, seed, name = row[:4]
    key = f"{tag}__{seed}"
    d = os.path.join(a.out, key)
    if os.path.exists(os.path.join(d, "done.json")):
        return key, "kept"
    os.makedirs(os.path.join(d, "frames"), exist_ok=True)
    t0 = time.time()
    st, body, _ = get(f"{a.host}/frames/mosaic/{seed}.webp?warm=1", tries_503=3)
    kind = json.loads(body) if st == 200 else {"error": st}
    info = None
    for _ in range(60):
        st, body, _ = get(f"{a.host}/frames/movie/{seed}.json", tries_503=3)
        if st == 200:
            info = json.loads(body)
            break
        if st == 404:
            break
        time.sleep(4)
    rec = {"group": group, "tag": tag, "seed": seed, "name": name, "kind": kind, "status": st}
    if not info:
        json.dump(rec, open(os.path.join(d, "done.json"), "w"))
        return key, f"no pass ({st})"
    rec.update({k: info[k] for k in ("observation", "target", "camera", "pass", "n", "movie", "mosaic", "cadence")})
    frames = info["frames"]
    rolling = kind.get("kind") == "mosaic_movie"
    rec["plays"] = "mosaic_movie" if rolling else ("movie" if info.get("movie") or kind.get("movie") or kind.get("kind") == "movie" else "mosaic")
    if rec["plays"] == "mosaic" and kind.get("kind") == "mosaic":
        json.dump(rec, open(os.path.join(d, "done.json"), "w"))
        return key, "a mosaic, not a movie (skipped)"
    idx = pick(len(frames), a.max)
    rows, tiles = [], []
    for i in idx:
        fid, ts, filt = frames[i]
        url = f"{a.host}/frames/movie/{fid}.webp?{ROLL if rolling else STYLE}"
        f0 = time.time()
        st, body, hd = get(url)
        r = {"i": i, "id": fid, "t": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)), "filter": filt, "http": st,
             "secs": round(time.time() - f0, 1)}
        if st == 200:
            open(os.path.join(d, "frames", f"{i:04d}_{fid}.webp"), "wb").write(body)
            try:
                r["x"] = json.loads(hd.get("X-Movie", "{}"))
            except ValueError:
                r["x"] = hd.get("X-Movie")
            im = Image.open(io.BytesIO(body))
            r.update(stats(im))
            tiles.append(label(im, f"{i} {filt} {fid}", 256))
        else:
            r["why"] = body[:200].decode("utf8", "replace")
            tiles.append(label(Image.new("RGB", (256, 256), (90, 0, 0)), f"{i} {filt} HTTP {st}", 256))
        rows.append(r)
    rec["frames_total"], rec["frames_done"] = len(frames), len(rows)
    rec["secs"] = round(time.time() - t0, 1)
    json.dump(rows, open(os.path.join(d, "frames.json"), "w"))
    for p in range(0, len(tiles), 36):
        sheet(tiles[p:p + 36], 6, 256, os.path.join(d, f"strip{p // 36:02d}.jpg"),
              f"{tag} {name} | {rec['observation']} {rec['camera']} pass {rec['pass']} | plays {rec['plays']} | {len(frames)} frames, shown {len(rows)}")
    json.dump(rec, open(os.path.join(d, "done.json"), "w"))
    return key, f"{rec['plays']} {len(rows)}/{len(frames)} frames {rec['secs']} s"


def full_sheet(d):
    """six frames at full size (512): first, first colour frame, darkest, brightest, biggest jump, last"""
    try:
        rows = [r for r in json.load(open(os.path.join(d, "frames.json"))) if r.get("http") == 200]
    except (OSError, ValueError):
        return
    if not rows or os.path.exists(os.path.join(d, "full.jpg")):
        return
    pick_, why = [], []
    def add(r, w):
        if r["i"] not in [p["i"] for p in pick_]:
            pick_.append(r); why.append(w)
    add(rows[0], "first")
    col = [r for r in rows if r.get("chroma", 0) > 2]
    if col:
        add(col[0], "first colour")
    add(min(rows, key=lambda r: r["mean"]), "darkest")
    add(max(rows, key=lambda r: r["p995"] * 1000 + r["mean"]), "brightest")
    if len(rows) > 1:
        j = max(range(1, len(rows)), key=lambda k: abs(rows[k]["mean"] - rows[k - 1]["mean"]))
        add(rows[j], "biggest jump")
    add(rows[-1], "last")
    for r in rows[1:]:
        if len(pick_) >= 6:
            break
        add(rows[len(rows) // 2], "middle")
        break
    tiles = []
    for r, w in zip(pick_[:6], why):
        try:
            im = Image.open(os.path.join(d, "frames", f"{r['i']:04d}_{r['id']}.webp"))
        except OSError:
            continue
        tiles.append(label(im, f"{r['i']} {r['filter']} {r['id']} [{w}]", 512))
    if tiles:
        sheet(tiles, 3, 512, os.path.join(d, "full.jpg"), os.path.basename(d) + " (full size)")


def push(a, lock):
    if not a.push:
        return
    with lock:
        g = a.push
        subprocess.run(["rsync", "-a", "--include=*/", "--include=*.jpg", "--include=*.json", "--exclude=*", a.out + "/", g + "/qc2/out/"], check=False)
        subprocess.run(["git", "-C", g, "add", "-A"], check=False)
        if subprocess.run(["git", "-C", g, "diff", "--cached", "--quiet"]).returncode:
            subprocess.run(["git", "-C", g, "commit", "-qm", "qc2 movies batch"], check=False)
            for k in range(4):
                if subprocess.run(["git", "-C", g, "push", "-q", "origin", "HEAD:claude/project-thread-7aaoos"]).returncode == 0:
                    break
                time.sleep(2 ** (k + 1))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--list", required=True)
    p.add_argument("--host", default="http://127.0.0.1:8861")
    p.add_argument("--out", required=True)
    p.add_argument("--push")
    p.add_argument("--max", type=int, default=36)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--every", type=int, default=6)
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = [r for r in csv.reader(open(a.list), delimiter="\t") if r and not r[0].startswith("#")]
    lock, done = threading.Lock(), [0]
    log = open(os.path.join(a.out, "run.log"), "a")

    def one(r):
        try:
            k, msg = do_pass(r, a, log)
            full_sheet(os.path.join(a.out, k))
        except Exception as e:
            k, msg = f"{r[1]}__{r[2]}", f"ERROR {e!r}"
        with lock:
            log.write(f"{time.strftime('%H:%M:%S')} {k} {msg}\n")
            log.flush()
            print(k, msg, flush=True)
            done[0] += 1
            n = done[0]
        if n % a.every == 0:
            push(a, plock)
    plock = threading.Lock()
    for k in os.listdir(a.out):
        if os.path.isdir(os.path.join(a.out, k)):
            full_sheet(os.path.join(a.out, k))
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, rows))
    push(a, plock)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
