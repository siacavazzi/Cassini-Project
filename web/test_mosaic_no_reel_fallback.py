#!/usr/bin/env python3
"""The mosaic route draws no body-reel shot for a frame obs_mosaic puts in no mosaic.

The camera windows ask /frames/mosaic/<ID>.webp for every frame. For a frame of a pass obs_mosaic calls no mosaic,
the route fell back to the body reel's panel shot (reel.mosaic_of, reel.shot_webp) and drew it on request: no build
stores reel shots and the public site refuses them, so the zero-render check on 2017 (11-18) found 635 frames whose
picture the private site drew on request (435 shots). The route now answers 404 at once and the window keeps its
frame, as on the public site; a real mosaic pass still answers its mosaic.

  python web/test_mosaic_no_reel_fallback.py
"""
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import frame_server as fs  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reel  # noqa: E402


def forbidden(name):
    def f(*a, **k):
        raise AssertionError(f"{name} was called")
    return f


def check(what, ok):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        sys.exit(1)


LONE = {"key": ("SATURN", "ISS_000SA_LONE001_PRIME", "N", 2), "mosaic": False, "movie": False, "kind": None,
        "frames": [(0, "N1400000001_1", "CL1/CL2")]}
reel._index = object()                               # the index is loaded (the route's obs_mosaic branch runs)
om.mosaic_webp = lambda *a, **k: None                # obs_mosaic has no mosaic for the frame
om.unit_of = lambda fid: (LONE, 0)
om.parse_tune = lambda *a: ((), ())
reel.mosaic_of = forbidden("reel.mosaic_of")
reel.shot_webp = forbidden("reel.shot_webp")

cache = tempfile.mkdtemp(prefix="cassini-test-")
server = fs.Server(("127.0.0.1", 0), fs.make_handler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cassini-os"), cache))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_address[1]}/frames/mosaic/N1400000001_1.webp?size=512"
try:
    urllib.request.urlopen(url, timeout=30)
    code = 200
except urllib.error.HTTPError as e:
    code = e.code
server.shutdown()
check("a frame in no mosaic answers 404 (the window keeps its frame)", code == 404)
check("nothing was written to the cache", not any(fs_ for _, _, fs_ in os.walk(cache)))
print("ok")
