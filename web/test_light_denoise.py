"""The light automatic denoise in the last step of every still and composite (sharpen.light_denoise, taste call 15):
a picture whose grain is at or under DENOISE_FROM is exactly as without it; a grainy one is smoothed by a share that
grows with its grain and never past DENOISE_MAX; edges, stars and saturated patches keep their levels; every color
takes the same change. Run: python web/test_light_denoise.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.dirname(HERE), os.path.join(HERE, "frames")]
import numpy as np  # noqa: E402
import sharpen as S  # noqa: E402

rng = np.random.default_rng(5)
yy, xx = np.mgrid[:400, :400]


def scene(noise):
    """sky glow with a hard-edged disk (level 200) on the right, a few one-pixel stars, a saturated patch"""
    t = 60 + 0.05 * yy + np.where((xx - 300) ** 2 + (yy - 200) ** 2 < 60 ** 2, 140, 0) + rng.normal(0, noise, (400, 400))
    for y, x in [(50, 50), (120, 80), (330, 140)]:
        t[y, x] = 250
    t[20:30, 350:380] = 255
    return np.clip(t, 0, 255).astype(np.uint8)


def test_share():
    assert S.denoise_share(S.DENOISE_FROM) == 0 and S.denoise_share(1.0) == 0
    assert abs(S.denoise_share(S.DENOISE_FULL) - S.DENOISE_MAX) < 1e-9 and S.denoise_share(40) == S.DENOISE_MAX
    mid = (S.DENOISE_FROM + S.DENOISE_FULL) / 2
    assert abs(S.denoise_share(mid) - S.DENOISE_MAX / 2) < 1e-9
    print("share: none up to", S.DENOISE_FROM, "levels, all of", S.DENOISE_MAX, "from", S.DENOISE_FULL)


def test_clean_untouched():
    t = scene(1.0)
    r = {}
    a = S.adaptive_sharpen(t, report=r)
    b = S.adaptive_sharpen(t, denoise=False)
    assert r["grain"] <= S.DENOISE_FROM and r["denoise"] == 0 and np.array_equal(a, b), r["grain"]
    print("a clean picture (grain", r["grain"], ") is exactly as before")


def test_grainy_smoothed_edges_kept():
    t = scene(6.0)
    r = {}
    a = S.adaptive_sharpen(t, amount=0, report=r).astype(float)
    assert r["grain"] > S.DENOISE_FROM and r["denoise"] > 0, r
    sky = (slice(150, 250), slice(60, 180))
    assert a[sky].std() < 0.8 * t[sky].std(), (a[sky].std(), t[sky].std())
    # the disk's edge keeps its step (mean levels each side)
    inside, outside = (slice(190, 210), slice(250, 256)), (slice(190, 210), slice(232, 236))
    step0 = t[inside].mean() - t[outside].mean()
    step1 = a[inside].mean() - a[outside].mean()
    assert abs(step1 - step0) < 3, (step0, step1)
    # stars and the saturated patch keep their levels
    for y, x in [(50, 50), (120, 80), (330, 140)]:
        assert a[y, x] == t[y, x], (y, x, a[y, x])
    assert (a[20:30, 350:380] == 255).all()
    print(f"grainy picture (grain {r['grain']}, share {r['denoise']}): sky spread {t[sky].std():.1f} -> {a[sky].std():.1f}, edge step {step0:.0f} -> {step1:.0f}, stars kept")


def test_never_extreme():
    t = scene(25.0)
    r = {}
    a = S.adaptive_sharpen(t, amount=0, report=r).astype(float)
    assert r["denoise"] == S.DENOISE_MAX
    sky = (slice(150, 250), slice(60, 180))
    assert a[sky].std() > 0.25 * t[sky].std(), (a[sky].std(), t[sky].std())   # a light step: grain is lowered, not wiped
    print("very grainy picture: share capped at", S.DENOISE_MAX, f"sky spread {t[sky].std():.1f} -> {a[sky].std():.1f}")


def test_colors_alike():
    g = scene(6.0)
    rgb = np.dstack([g, np.clip(g.astype(int) - 10, 0, 255), np.clip(g.astype(int) + 5, 0, 255)]).astype(np.uint8)
    a = S.adaptive_sharpen(rgb, amount=0).astype(int) - rgb.astype(int)
    ok = (rgb.max(axis=2) < 250) & (rgb.min(axis=2) > 5)
    assert np.abs(a[..., 0] - a[..., 1])[ok].max() <= 1 and np.abs(a[..., 0] - a[..., 2])[ok].max() <= 1
    print("every color takes the same change")


if __name__ == "__main__":
    test_share()
    test_clean_untouched()
    test_grainy_smoothed_edges_kept()
    test_never_extreme()
    test_colors_alike()
    print("ok")
