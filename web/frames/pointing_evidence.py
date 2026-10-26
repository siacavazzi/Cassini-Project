#!/usr/bin/env python3
"""Before/after evidence for opening a mosaic's frames (pictures program phase 4) on real passes, asked of two running
frame servers over HTTP (their own routes, nothing re-implemented): the mosaic as the page shows it at full size, and
for a few of its pointings the spot cut from that mosaic, the frame opened before (/frames/mosaic/<ID>/frame.webp, the
old renderer), the frame opened after (/frames/mosaic/<ID>/p/<n>.webp) and the frames on their own (/frames/color.webp
or /frames/processed/<id>.webp). Each opened picture is brought to its spot's size and compared with the mosaic inside
the pointing's outline (shrunk toward its middle, where its own tile is on top): the mean difference in levels.

  python pointing_evidence.py --before http://127.0.0.1:8790 --after http://127.0.0.1:8829 --out DIR FRAME_ID...
FRAME_ID: a frame of the pass, late in it (the mosaic as it stands at that frame)."""
import argparse
import io
import json
import os
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw


def get(url):
    t = time.time()
    with urllib.request.urlopen(url, timeout=900) as r:
        return r.read(), time.time() - t


def picture(url):
    try:
        data, took = get(url)
    except Exception as e:
        return None, str(e)[:120]
    return Image.open(io.BytesIO(data)).convert("RGBA"), round(took, 2)


def choose(pointings, n):
    """Up to n pointings spread over the pass, color sets first, and a gray one when there is one."""
    sets = [q for q in pointings if q["set"]]
    grey = [q for q in pointings if not q["set"]]
    pick = [sets[round(i * (len(sets) - 1) / max(1, n - 2))] for i in range(min(len(sets), n - 1))] if sets else []
    if grey:
        pick.append(grey[len(grey) // 2])
    while len(pick) < n and len(pick) < len(pointings):
        q = pointings[(len(pick) * 7919) % len(pointings)]
        if q not in pick:
            pick.append(q)
        else:
            break
    return sorted({q["n"]: q for q in pick}.values(), key=lambda q: q["n"])


def spot(mos, q):
    """The mosaic's box round pointing q's outline (px) and a mask of its outline shrunk toward its middle."""
    W, H = mos.size
    poly = [(x * W, y * H) for x, y in q["poly"]]
    x0, y0 = max(0, int(min(p[0] for p in poly))), max(0, int(min(p[1] for p in poly)))
    x1, y1 = min(W, int(max(p[0] for p in poly)) + 1), min(H, int(max(p[1] for p in poly)) + 1)
    cx, cy = q["center"][0] * W, q["center"][1] * H
    inner = [(cx + 0.7 * (x - cx) - x0, cy + 0.7 * (y - cy) - y0) for x, y in poly]
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(m).polygon(inner, fill=255)
    return (x0, y0, x1, y1), np.asarray(m) > 0


def compare(pic, crop, mask):
    """Mean difference (levels, RGB) of pic brought to the crop's size against the crop, where both have picture."""
    if pic is None:
        return None, None
    a = np.asarray(pic.resize(crop.size, Image.LANCZOS)).astype(int)
    b = np.asarray(crop).astype(int)
    keep = mask & (a[..., 3] > 250) & (b[..., 3] > 250)
    if keep.sum() < 200:
        return None, Image.fromarray(a.astype(np.uint8))
    return round(float(np.abs(a[..., :3] - b[..., :3])[keep].mean()), 2), Image.fromarray(a.astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pointings", type=int, default=4)
    ap.add_argument("frames", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    report = []
    for fid in a.frames:
        data, took = get(f"{a.after}/frames/mosaic/{fid}.json")
        m = json.loads(data)
        mos, mt = picture(f"{a.after}/frames/mosaic/{fid}.webp?size=full&force=1&format=png")
        if mos is None:
            report.append({"frame": fid, "error": mt})
            continue
        mos.save(f"{a.out}/{fid}_mosaic.png")
        entry = {"frame": fid, "observation": m["observation"], "target": m["target"], "filters": m["filters"],
                 "pointings": len(m["pointings"]), "mosaic_s": mt, "opened": []}
        for q in choose(m["pointings"], a.pointings):
            fs = [f for f in m["filters"] if f in q["ids"]] or list(q.get("luminance", {}))[-1:]
            ids = [q["ids"].get(f) or q["luminance"][f] for f in fs]
            box, mask = spot(mos, q)
            crop = mos.crop(box)
            after, at = picture(f"{a.after}/frames/mosaic/{fid}/p/{q['n']}.webp?size=full&format=png")
            # (the page before opened a set's three frames, or else the newest drawn one alone)
            old = ids if len(ids) == 3 else ids[-1:]
            before, bt = picture(f"{a.before}/frames/mosaic/{fid}/frame.webp?ids={','.join(old)}&size=full&format=png")
            own_url = f"/frames/color.webp?ids={','.join(ids)}&size=full&format=png" if len(ids) == 3 else \
                f"/frames/processed/{ids[-1]}.webp?size=full&format=png"
            own, ot = picture(a.after + own_url)
            d_after, after_s = compare(after, crop, mask)
            d_before, before_s = compare(before, crop, mask)
            d_own, own_s = compare(own, crop, mask)
            # side by side: the spot in the mosaic | before | after | on its own, each at the spot's size (x2 up to 360 px)
            s = max(1.0, 360 / max(crop.size))
            size = (round(crop.width * s), round(crop.height * s))
            panels = [crop] + [x if x is not None else Image.new("RGBA", crop.size, (40, 0, 0, 255)) for x in (before_s, after_s, own_s)]
            sheet = Image.new("RGB", (4 * size[0] + 30, size[1] + 34), (14, 15, 18))
            d = ImageDraw.Draw(sheet)
            for i, (p, label) in enumerate(zip(panels, ["in the mosaic", f"before: {d_before}", f"after: {d_after}", f"on its own: {d_own}"])):
                bg = Image.new("RGBA", p.size, (0, 0, 0, 255))
                sheet.paste(Image.alpha_composite(bg, p).convert("RGB").resize(size, Image.LANCZOS), (i * (size[0] + 10), 30))
                d.text((i * (size[0] + 10) + 4, 8), label, fill=(230, 232, 236))
            name = f"{fid}_p{q['n']}.png"
            sheet.save(f"{a.out}/{name}")
            entry["opened"].append({"n": q["n"], "set": q["set"], "filters": fs, "ids": ids, "sheet": name,
                                    "diff_before": d_before, "diff_after": d_after, "diff_own": d_own,
                                    "s_before": bt, "s_after": at, "s_own": ot,
                                    "size_before": before.size if before else None, "size_after": after.size if after else None})
            print(json.dumps(entry["opened"][-1]), flush=True)
        report.append(entry)
    with open(f"{a.out}/report.json", "w") as fh:
        json.dump(report, fh, indent=1)
    rows = []
    for e in report:
        if "error" in e:
            rows.append(f"<h2>{e['frame']}</h2><p>{e['error']}</p>")
            continue
        rows.append(f"<h2>{e['target'].title()} · {e['observation']} · {' '.join(e['filters'])} · {e['pointings']} frames</h2>"
                    f"<p><a href='{e['frame']}_mosaic.png'>the mosaic</a></p>")
        for o in e["opened"]:
            rows.append(f"<figure><img src='{o['sheet']}' loading='lazy'><figcaption>Frame {o['n']} ({'color' if o['set'] else 'gray'}, "
                        f"{' '.join(o['filters'])}): mean difference from its spot in the mosaic, before {o['diff_before']}, "
                        f"after {o['diff_after']}, on its own {o['diff_own']} levels. Opened in {o['s_after']} s.</figcaption></figure>")
    with open(f"{a.out}/index.html", "w") as fh:
        fh.write("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Opened frames vs their spot</title>"
                 "<style>body{background:#0e0f12;color:#e6e8ec;font:14px system-ui;margin:16px;max-width:1500px}img{max-width:100%}"
                 "figure{margin:0 0 22px}figcaption{color:#9aa0aa;margin-top:4px}h2{font-size:15px;margin-top:28px}</style>"
                 "<h1>Frames opened from a mosaic, before and after (PR #125)</h1><p>Each row: the spot cut from the mosaic, the frame "
                 "opened before (frame.webp), after (p/&lt;n&gt;), and on its own scale. Numbers: mean difference from the mosaic inside the "
                 "frame's outline, in levels (0-255); lower matches better.</p>" + "".join(rows))


if __name__ == "__main__":
    main()
