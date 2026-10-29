#!/usr/bin/env python3
"""Before/after sheets for Auto center's rule (obs_mosaic.centre_half), from two running frame servers: for each
pass, a few of its movie frames with Auto center on (center=1) as the server on the old rule draws them (--before)
beside the same frames from a server on the new rule (--after). Writes <out>/<pass>.png and an index.html.
Run: python web/frames/centre_evidence.py --before http://127.0.0.1:8765 --after http://127.0.0.1:8861 --out DIR IDS..."""
import argparse
import io
import json
import os
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw

SIZE = 512
PICKS = 6


def get(url, tries=60):
    """The answer to url, waiting while the server works out the pass (503)."""
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code != 503:
                raise
            time.sleep(5)
    raise TimeoutError(url)


def sheet(servers, frame_id, out):
    info = json.loads(get(f"{servers[0]}/frames/movie/{frame_id}.json")[0])
    ids = [f[0] for f in info["frames"]] or [frame_id]
    picks = sorted({ids[round(i * (len(ids) - 1) / max(1, PICKS - 1))] for i in range(PICKS)}, key=ids.index)
    W = 2 * SIZE + 30
    im = Image.new("RGB", (W, 40 + len(picks) * (SIZE + 30)), (20, 20, 20))
    d = ImageDraw.Draw(im)
    name = f"{info['target']}_{info['observation']}_{info['camera']}_{info['pass']}"
    d.text((10, 8), f"{name}   before: Auto center, old rule            after: Auto center, new rule",
           fill=(230, 230, 230))
    rows = []
    for k, fid in enumerate(picks):
        y = 40 + k * (SIZE + 30)
        row = {"id": fid}
        for j, server in enumerate(servers):
            data, head = get(f"{server}/frames/movie/{fid}.webp?size={SIZE}&center=1&trail=0")
            pic = Image.open(io.BytesIO(data)).convert("RGB")
            pic.thumbnail((SIZE, SIZE))
            im.paste(pic, (10 + j * (SIZE + 10), y + 20))
            rep = json.loads(head.get("X-Movie", "{}"))
            row["before" if j == 0 else "after"] = {"centred": rep.get("centred"), "n": rep.get("n")}
        d.text((10, y + 4), f"{fid}  (frame {ids.index(fid) + 1} of {len(ids)})", fill=(200, 200, 200))
        rows.append(row)
    path = os.path.join(out, f"{frame_id}.png")
    im.save(path)
    return {"frame": frame_id, "pass": name, "sheet": os.path.basename(path), "frames": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", default="http://127.0.0.1:8765", help="a frame server on the old rule")
    ap.add_argument("--after", required=True, help="a frame server on the new rule")
    ap.add_argument("--out", required=True)
    ap.add_argument("ids", nargs="+", help="a frame of each pass")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    made = [sheet((a.before.rstrip("/"), a.after.rstrip("/")), i, a.out) for i in a.ids]
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(made, f, indent=1)
    with open(os.path.join(a.out, "index.html"), "w") as f:
        f.write("<!doctype html><meta charset=utf-8><title>Auto center rule</title><body style='background:#111;color:#ddd;"
                "font:14px system-ui'><h1>Auto center: before / after</h1>")
        for m in made:
            f.write(f"<h2>{m['pass']}</h2><img src='{m['sheet']}' style='max-width:100%'>")
    print(json.dumps(made, indent=1))
