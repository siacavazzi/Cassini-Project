"""A film and a Pre-process are made only at sizes the cache keeps pictures at. Export Movie's Picture size offered 768,
and "up to 1536", and a film at 768 asked every maker for a 768 px picture (export.Pictures.make), which no phase of the build keeps: every
picture of it was drawn on the request (2026-11-16). Both are gone from the picker (export.html SIZES), from the film's
sizes (export.SIZES) and from a Pre-process's (prebuild.SEGMENT_SIZES); a request that still names it takes the nearest
kept size (the larger of two as near: a 768 kept on a device is 1024, on the label, the slider and the request).
Run: python web/test_export_sizes.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import re  # noqa: E402
import export  # noqa: E402
import prebuild  # noqa: E402

KEPT = {512, 1024}   # prebuild's phases: frames, composites, processed, mosaics and movies at 1024 and 512
assert set(export.SIZES) == KEPT, export.SIZES
assert set(prebuild.SEGMENT_SIZES) == KEPT, prebuild.SEGMENT_SIZES

q = lambda **k: {key: [str(v)] for key, v in {"from": "2006-09-15T14:32:00", "until": "2006-09-15T17:12:00", **k}.items()}
for asked, got in ((512, 512), (700, 512), (768, 1024), (800, 1024), (1024, 1024), (1280, 1024), (1536, 2048), (1600, 2048), (2048, 2048)):
    assert export.options(q(size=asked))["size"] == got, (asked, export.options(q(size=asked))["size"])
assert export.options(q(size="full"))["size"] == export.FULL
for asked, got in (("512,1024", [512, 1024]), ("768", [1024]), ("512,768,1024", [512, 1024]), ("900", [1024])):
    assert prebuild.segment_options(q(sizes=asked))["sizes"] == got, (asked, prebuild.segment_options(q(sizes=asked))["sizes"])

# the picker offers the film's sizes, the "up to" mosaic sizes and Full, and its slider has a stop for each
here = os.path.dirname(os.path.abspath(__file__))
for page in ("cassini-os/src/export.html", "cassini-os/index.html"):
    src = open(os.path.join(here, page)).read()
    sizes = re.search(r"const SIZES = \[([^\]]+)\];", src).group(1)
    assert [s.strip() for s in sizes.split(",")] == ["512", "1024", "2048", '"full"'], (page, sizes)
    assert re.search(r'id="exsize" min="0" max="3" step="1"', src), page
    # a size kept before 768 went: the larger of the two as near, one rule for the label, the slider and the request
    assert "Math.abs(v - sz) <= Math.abs(m - sz) ? v : m" in src and "String(sizeOf())" in src and "SIZES.indexOf(sizeOf())" in src, page
print("ok")
