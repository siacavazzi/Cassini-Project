#!/usr/bin/env python3
"""
A tiny hand-made mirror for deploy.sh's local dry run, in the layout WP3's `publish.py --to-dir` writes (an object
per canonical key, its metadata beside it as <key>.meta.json, manifests under manifest/). Two publishes, A and B,
with different picture versions, so a switch and a rollback change which pictures the Worker answers. The pictures
are flat test cards labelled with their publish, not Cassini pictures: this mirror proves the deploy steps only.

  python web/deploy/make_test_mirror.py OUT_DIR       prints the two manifest keys
"""
import datetime
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "public"))
import keys  # noqa: E402

URLS = ["/frames/N1500060789_2.webp", "/frames/N1500060789_2.webp?size=1024", "/frames/W1500060789_1.webp",
        "/frames/thumb.webp?id=N1500060789_2"]


def card(text, shade):
    try:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (128, 128), (shade, shade, shade))
        ImageDraw.Draw(im).text((8, 56), text, fill=(255 - shade,) * 3)
        b = io.BytesIO(); im.save(b, "WEBP", quality=80)
        return b.getvalue(), "image/webp"
    except ImportError:
        return text.encode(), "text/plain"


def publish(out, label, versions, when, shade):
    tags = keys.family_tags(versions)
    written = 0
    for u in URLS:
        a = keys.canonical("GET", u, tags)
        if a["store"] != "r2":
            continue
        body, ctype = card(f"{label} {a['key'].split('/')[-1][:14]}", shade)
        p = os.path.join(out, a["key"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(body)
        json.dump({"content-type": ctype, "custom": {"x-test-publish": label}}, open(p + ".meta.json", "w"))
        written += 1
    pid = when.strftime("%Y%m%dT%H%M%SZ") + "-" + "0000000"
    m = {"publish_id": pid, "published": when.isoformat().replace("+00:00", "Z"), "commit": "0000000",
         "versions": versions, "families": tags, "slices": {"spans": None, "phases": {}},
         "version": {"test_publish": label, "pictures": versions}, "counts": {"objects": written}}
    key = f"manifest/{pid}.json"
    os.makedirs(os.path.join(out, "manifest"), exist_ok=True)
    json.dump(m, open(os.path.join(out, key), "w"), indent=1)
    json.dump({"content-type": "application/json"}, open(os.path.join(out, key) + ".meta.json", "w"))
    return key


def main(out):
    t = datetime.datetime(2026, 11, 11, 21, 0, 0, tzinfo=datetime.timezone.utc)
    a = publish(out, "A", {"frame_server.FRAME_VERSION": "test-a", "obs": "test-a"}, t, 40)
    b = publish(out, "B", {"frame_server.FRAME_VERSION": "test-b", "obs": "test-b"}, t + datetime.timedelta(hours=1), 200)
    print(a); print(b)


if __name__ == "__main__":
    main(sys.argv[1])
