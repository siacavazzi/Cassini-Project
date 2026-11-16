"""Noise-aware fine sharpening (sharpen.adaptive_sharpen), the last step of every still and composite: fine detail over
the picture's own noise is raised, sky grain and flat areas are left alone, a cosmic ray is not ringed, a limb gets no
halo past its neighbours' range, saturated patches and the empty canvas do not change, every color takes the same
change, a grainier picture takes less, and frame_server applies it to its stills and composites.
Run: python web/test_adaptive_sharpen.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.dirname(HERE), os.path.join(HERE, "frames")]
import numpy as np  # noqa: E402
import sharpen as S  # noqa: E402

rng = np.random.default_rng(0)
yy, xx = np.mgrid[:512, :512]


def textured(amp, noise=3.0):
    t = 80 + np.where(xx > 256, amp * np.sin(xx / 0.7) * np.sin(yy / 0.8), 0) + rng.normal(0, noise, (512, 512))
    return np.clip(t, 0, 255).astype(np.uint8)


def test_detail_over_noise():
    t = textured(24)
    r = {}
    o = S.adaptive_sharpen(t, report=r)
    assert r["weight"][:, :240].mean() < 0.01, r["weight"][:, :240].mean()        # sky grain: untouched
    assert r["weight"][:, 270:].mean() > 0.3, r["weight"][:, 270:].mean()          # detail: raised
    assert abs(o[:, :240].astype(float).std() - t[:, :240].std()) < 0.1
    assert o[:, 270:].std() > 1.2 * t[:, 270:].std()
    print("detail over the noise raised, sky grain left as it is")


def test_guards():
    z = np.full((64, 64), 40, np.uint8); z[30, 30] = 250
    assert (S.adaptive_sharpen(z, 2.4) == z).all()                                 # a cosmic ray: no ring round it
    e = np.full((64, 64), 20, np.uint8); e[:, 32:] = 200
    o = S.adaptive_sharpen(e, 2.4).astype(int)
    assert o.min() >= 20 - S.OVERSHOOT_MAX and o.max() <= 200 + S.OVERSHOOT_MAX    # a limb: at most a few levels past
    s = textured(24); s[100:200, 300:400] = 255
    o = S.adaptive_sharpen(s)
    assert (o[100:200, 300:400] == 255).all()                                     # saturated: kept
    a = np.dstack([textured(24)] * 3 + [np.where(xx < 200, 0, 255).astype(np.uint8)])
    o = S.adaptive_sharpen(a)
    assert (o[:, :200] == a[:, :200]).all()                                         # the empty canvas: kept
    d = o[..., :3].astype(int) - a[..., :3].astype(int)
    c = a.copy(); c[..., 1] = np.clip(a[..., 1].astype(int) - 10, 0, 255); c[..., 2] = np.clip(a[..., 2].astype(int) + 10, 0, 255)
    dc = S.adaptive_sharpen(c)[..., :3].astype(int) - c[..., :3].astype(int)
    mid = (c[..., :3].min(axis=2) > 30) & (c[..., :3].max(axis=2) < 225)
    assert (np.ptp(dc, axis=2)[mid] <= 1).all()                                    # the same change on every color
    print("no ring on a cosmic ray, no halo past a limb, saturated patches and the empty canvas kept, colors alike")


def test_grain_and_lossy():
    clean, grainy = textured(24, 1.0), textured(24, 6.0)
    rc, rg, rl = {}, {}, {}
    S.adaptive_sharpen(clean, report=rc); S.adaptive_sharpen(grainy, report=rg); S.adaptive_sharpen(clean, report=rl, lossy=True)
    assert rg["amount"] < 0.5 * rc["amount"], (rc, rg)
    assert abs(rl["amount"] - S.LOSSY_AMOUNT * rc["amount"]) < 0.01
    print("a grainier picture takes less (%.2f vs %.2f), a lossy one %.0f%%" % (rg["amount"], rc["amount"], 100 * S.LOSSY_AMOUNT))


def test_server_applies():
    import frame_server as fs
    seen = []
    real = S.adaptive_sharpen
    fs.sharpen.adaptive_sharpen = lambda px, **k: seen.append(px.shape) or real(px, **k)
    try:
        rep = {}
        fs._sharpened(np.dstack([textured(24), np.full((512, 512), 255, np.uint8)]), ["N0000000000_1"], rep)
    finally:
        fs.sharpen.adaptive_sharpen = real
    assert seen == [(512, 512, 2)] and set(rep["sharpen"]) == {"grain", "amount", "changed"}, (seen, rep)
    assert "_sharpened(" in open(fs.__file__).read().split("def composite(")[1].split("def _lossy(")[0]
    assert "_sharpened(" in open(fs.__file__).read().split("def centred(")[1].split("\ndef ")[0]
    print("frame_server: stills and composites end in it")


def test_detail_on_disk():
    """the close-up passes' detail filter on a centred still's SPICE disk: a small moon keeps its shading (not raised
    to flat white against the sky, #304), its craters are raised, the sky and a ring past the limb are not touched"""
    import obs_mosaic as om
    h = w = 400; cx = cy = 199.5; r = 40.0
    r2 = (xx[:h, :w] - cx) ** 2 + (yy[:h, :w] - cy) ** 2
    disk = r2 <= r * r
    lum = np.where(disk, 120 + 60 * (xx[:h, :w] - cx) / r + 8 * np.sin(xx[:h, :w] / 2.0) * np.sin(yy[:h, :w] / 2.3), 4.0)
    px = np.dstack([np.clip(lum, 0, 255).astype(np.uint8)] * 3 + [np.full((h, w), 255, np.uint8)])
    out = om.detail_on_disk(px, cx, cy, r)
    inner = r2 <= (0.8 * r) ** 2
    assert out[..., 0][inner].mean() < 200 and abs(float(out[..., 0][inner].mean()) - float(px[..., 0][inner].mean())) < 15
    assert out[..., 0][inner].std() > 1.05 * px[..., 0][inner].std()
    assert (out[r2 > (1.1 * r) ** 2] == px[r2 > (1.1 * r) ** 2]).all()
    print("detail on a small disk: shading kept (%.0f vs %.0f), craters raised, the sky untouched" % (out[..., 0][inner].mean(), px[..., 0][inner].mean()))


if __name__ == "__main__":
    test_detail_on_disk()
    test_detail_over_noise()
    test_guards()
    test_grain_and_lossy()
    test_server_applies()
    print("ok")
