"""One channel of a colour picture cut in the page (D5, docs/public-site; steady-local.html cassiniChannelCutMath, which
the camera windows' drill-down and save menu use with the public switch on) is the frame server's channel (frame_server
color_webp(..., channel=c): composite()'s band c of the composite, black and white with its alpha) within WebP q95 noise.

The server cuts its channel from the composite before encoding it; the page cuts it from the composite as served, a
WebP at q95. Both go through the server's own code here: color_webp makes the composite and each channel into a scratch
cache from the same composite picture (frame_server._recent_composite answers it), the composite's WebP is decoded and
cut by the page's function in node, and the two are compared, as luminance and alpha. The noise each is held to is the
server's own encoding of that channel: how far the served channel is from the band it was made from.

Composite pictures: real ones from a cache when CASSINI_CHANNEL_SAMPLES names a folder of colour WebPs (read only, the
picture is only the input), else synthetic ones (smooth fields, edges and a transparent margin, as a centred composite
has).
Run: python web/test_channel_cut.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import glob, io, json, re, subprocess, tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import frame_server as fs  # noqa: E402

page = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = page[page.index("<script>") + 8:page.index("</script>")]


def samples():
    folder = os.environ.get("CASSINI_CHANNEL_SAMPLES")
    if folder:
        for p in sorted(glob.glob(os.path.join(os.path.expanduser(folder), "*.webp")))[:12]:
            im = Image.open(p).convert("RGBA")
            yield os.path.basename(p)[:-5], os.path.basename(p)[:-5], im
        return
    rng = np.random.default_rng(11)
    for n in range(4):
        H, W = 1024, 1024 if n % 2 == 0 else 768
        y, x = np.mgrid[0:H, 0:W] / 1024
        # a body's brightness with a muted tint that changes across it (Cassini's colour pictures are mostly that)
        lum = 0.15 + 0.7 * (np.sin(6 * x + n) * 0.25 + np.cos(5 * y - n) * 0.25 + 0.5)
        rgb = lum[..., None] * np.stack([1 + 0.15 * np.sin(3 * y + n), 1 + 0.1 * np.cos(4 * x), 1 - 0.15 * np.sin(2 * x * y + n)], -1)
        # grain shared by the filters (a composite's noise is mostly in its brightness: its colour is smooth, the
        # colour sets aligned and mixed, and WebP keeps colour at half resolution, 4:2:0, so colour finer than that is
        # not in the served picture for either side to cut)
        rgb += rng.normal(0, 0.03, rgb.shape[:2])[..., None]
        rgb[(x - 0.5) ** 2 + (y - 0.45) ** 2 < 0.04] *= 0.3   # a hard edge
        a = np.where((x > 0.04) & (x < 0.96) & (y > 0.03) & (y < 0.97), 255, 0).astype(np.uint8)   # a transparent margin
        im = Image.fromarray(np.dstack([(np.clip(rgb, 0, 1) * 255).astype(np.uint8), a]), "RGBA")
        yield f"synthetic{n}", f"N16000{n:05d}_1_N16000{n:05d}_2_N16000{n:05d}_3", im


def page_cut(rgba, ch):
    """The page's cut of rgba (H x W x 4, uint8), in node."""
    with tempfile.TemporaryDirectory() as tmp:
        rgba.tofile(f"{tmp}/in.raw")
        js = ("const window = {};\n" + script + f"\nconst fs = require('fs'), buf = fs.readFileSync('{tmp}/in.raw');\n"
              f"const out = window.cassiniChannelCutMath(new Uint8ClampedArray(buf.buffer, buf.byteOffset, buf.length), {ch});\n"
              f"fs.writeFileSync('{tmp}/out.raw', Buffer.from(out.buffer));")
        subprocess.run(["node", "-e", js], check=True)
        return np.fromfile(f"{tmp}/out.raw", np.uint8).reshape(rgba.shape)


def decode(data, mode):
    return np.asarray(Image.open(io.BytesIO(data)).convert(mode))


cache = tempfile.mkdtemp()
worst, rows = [], []
for name, stem, im in samples():
    ids = re.findall(r"[NW]\d{10}_\d+", stem)
    fs._recent_composite = lambda ids_, centre=None, im=im: (im, {"ids": list(ids_)})
    composite, _ = fs.color_webp(ids, 1024, cache)
    served = decode(composite, "RGBA")
    for ch in range(3 if len(ids) == 3 else 2):
        c = (0, 1, 2)[ch] if len(ids) == 3 else (0, 2)[ch]
        server = decode(fs.color_webp(ids, 1024, cache, channel=c)[0], "LA")
        cut = page_cut(np.ascontiguousarray(served), c)
        band = np.asarray(im)[..., c]
        if server.shape[:2] != cut.shape[:2]:
            raise SystemExit(f"FAIL {name} channel {c}: server {server.shape} page {cut.shape}")
        lit = server[..., 1] > 0
        d = np.abs(cut[..., 0].astype(int) - server[..., 0].astype(int))[lit]
        noise = np.abs(server[..., 0].astype(int) - band.astype(int))[lit]   # the server's own WebP q95 noise
        alpha = np.abs(cut[..., 3].astype(int) - server[..., 1].astype(int))
        grey = bool((cut[..., 0] == cut[..., 1]).all() and (cut[..., 1] == cut[..., 2]).all())
        r = {"picture": name, "channel": c, "mean": round(float(d.mean()), 3), "p99": int(np.percentile(d, 99)), "max": int(d.max()),
             "noise_mean": round(float(noise.mean()), 3), "noise_p99": int(np.percentile(noise, 99)), "alpha_max": int(alpha.max()), "grey": grey}
        rows.append(r)
        print(json.dumps(r))
        # within WebP q95 noise: on average no further from the server's channel than twice the server's own encoding
        # noise (the page's picture went through one more encoding, the composite's), and no pixel further than the
        # composite's encoding moves one; alpha the same everywhere but the margin's encoded edge; black and white
        ok = (r["mean"] <= 2 * r["noise_mean"] + 0.5 and r["p99"] <= 2 * r["noise_p99"] + 2 and r["max"] <= 40
              and r["alpha_max"] <= 64 and grey)
        if not ok:
            worst.append(r)
print(f"{len(rows) - len(worst)} of {len(rows)} channels within WebP q95 noise of the server's")
sys.exit(1 if worst or not rows else 0)
