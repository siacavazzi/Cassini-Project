"""
Noise-aware fine-detail sharpening (Sam, 2026-11-16: "pictures generally don't look very sharp"; he turns Cassini
Studio's Sharpness slider up on almost every picture). The last step of every still and color composite the camera
windows show (frame_server.composite, centred), on the finished 8-bit picture. Passes drawn with obs_mosaic.detail()
(a body that fills its frames) keep that filter at DETAIL 2.0 as it is (Sam preferred it to a gentler one plus this)
and do not take this step.

How it works, on the picture's brightness (the mean of its colors; the same change is added to every color, so
filters slightly off each other do not turn into color fringes):
  d = brightness less its blur (a Gaussian of SIGMA px: the pixel-scale detail the camera's point spread function
      softened; the Cassini Studio Sharpness slider's 4-neighbour kernel is close to SIGMA 0.8)
  E = d^2 averaged over a few pixels: how much fine detail there is here
  N = how much of E noise alone makes, measured on the picture itself at each brightness (NOISE_PCT of E among
      the pixels of that brightness): it includes the stretch's gain, the gamma's slope at that brightness, the
      exposure, summing, 8-bit codes and lossy compression's blocks, as they actually came out
  w = 1 - WIENER x N / E, at least 0: a Wiener filter's signal over signal plus noise (none on sky grain)
  change = AMOUNT x w x d, eased off on big differences (EDGE: a limb or terminator gets only a little more) and
      held within a little of its 3x3 neighbours' range (OVERSHOOT: no halo or ring past an edge)
  no change near saturated pixels (a flat white patch has no detail, its rim would ring), on one-pixel spikes
      (cosmic rays, hot pixels), at the picture's own edge (alpha), or where mask (a body's disk, feathered) is 0
"""
import numpy as np
import cv2

AMOUNT = 2.4        # how much fine detail is raised where it is well over the noise, on a clean picture (about Cassini
                    # Studio's Sharpness slider at 80 there: 2.5 x 80/100 = 2.0 on its 4-neighbour kernel, which raises
                    # the finest detail a little more than SIGMA 0.8 does); a grainy, stretched or lossy picture takes less
SIGMA = 0.8         # px: the blur the detail is measured against
ENERGY_SIGMA = 1.5  # px: E is d^2 averaged over this
NOISE_PCT = 20      # E's percentile among pixels of one brightness taken as that brightness's noise
NOISE_BINS = 24     # brightness bins for the noise
NOISE_MIN_PX = 300  # a bin with fewer pixels takes its neighbours' noise
NOISE_LEVELS = (6, 250)   # levels: the bins the quiet bins are found among
NOISE_CAP_PCT = 25  # the quiet bins: this percentile of the measured bins' noise
NOISE_CAP = 3.0     # no bin's noise is taken as more than this times the quiet bins'
NOISE_P = 0.75      # E's NOISE_PCT percentile over its mean on pure noise (E is d^2 averaged, so it varies little)
WIENER = 1.5        # w = 1 - WIENER x noise / E (none where E is under WIENER x the noise): a Wiener filter's
                    # signal / (signal + noise), with a margin
EDGE = 24.0         # levels: a change of this size or more is eased off (x / (1 + |x| / EDGE))
OVERSHOOT = 0.15    # past the 3x3 neighbours' range by at most this share of it ...
OVERSHOOT_MAX = 6.0  # ... and at most this many levels
SAT_LEVEL = 253     # a pixel with a color at or over this is saturated; none within SAT_PX of it changes
SAT_PX = 2
SPIKE = 5.0         # a pixel this many noise sigmas (and SPIKE_MIN levels) off its 3x3 median is a spike
SPIKE_MIN = 12.0
BLOCK_GAIN = 4.0    # lossy blockiness R (8 px grid steps over the rest) raises N by R^BLOCK_GAIN
IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
NYQ_SIGMA = 3.0     # px: the finest scale's energy averaged over this
NYQ_SHARE = 1.0     # the local noise taken as this share of what the finest scale shows
LOSSY_AMOUNT = 0.75  # a lossy frame takes this share of the amount (its finest detail is partly the codec's)
GRAIN = 2.0         # levels: a picture whose smoothest places show this much grain takes half the amount
GRAIN_SHARE = 0.3   # its smoothest places: this share of its pixels (black and white clipping left out)
QUANT = 1.0 / 12    # 8-bit rounding's variance (levels^2): the least noise any picture has


def _blur(v, sigma, weight=None):
    if weight is None:
        return cv2.GaussianBlur(v, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)
    w = cv2.GaussianBlur(weight, (0, 0), sigma, borderType=cv2.BORDER_CONSTANT)
    return cv2.GaussianBlur(v * weight, (0, 0), sigma, borderType=cv2.BORDER_CONSTANT) / np.maximum(w, 1e-4)


def _kernel_noise(sigma):
    """d's variance per unit white-noise variance: sum of (delta - gaussian)^2"""
    n = int(np.ceil(sigma * 4)) * 2 + 1
    imp = np.zeros((n, n), np.float32)
    imp[n // 2, n // 2] = 1
    g = cv2.GaussianBlur(imp, (0, 0), sigma, borderType=cv2.BORDER_CONSTANT)
    return float(((imp - g) ** 2).sum())


def blockiness(lum, valid, periods=(8, 16)):
    """Lossy compression's block grid: the mean step across every period-th column and row (the phase with the
    biggest) over the biggest step at the phases a quarter, half and three quarters of a period on (the same parity,
    so a 2x summed frame shown at twice its size, whose steps come every other pixel, is not taken for blocks); about
    1 on a picture without blocks."""
    out = 1.0
    for axis in (0, 1):
        step = np.abs(np.diff(lum, axis=axis))
        ok = valid[1:, :] & valid[:-1, :] if axis == 0 else valid[:, 1:] & valid[:, :-1]
        prof = np.where(ok, step, 0).sum(axis=1 - axis) / np.maximum(ok.sum(axis=1 - axis), 1)
        cnt = ok.sum(axis=1 - axis)
        for period in periods:
            if (cnt > 0).sum() < 4 * period:
                continue
            ph = np.array([prof[p::period][cnt[p::period] > 0].mean() if (cnt[p::period] > 0).any() else 0
                           for p in range(period)])
            p = int(np.argmax(ph))
            others = max(ph[(p + k * period // 4) % period] for k in (1, 2, 3))
            if others > 0.05:
                out = max(out, float(ph[p]) / others)
    return out


def picture_grain(lum, d, ok, sigma=SIGMA):
    """The grain (levels, one sigma) of a picture's smoothest places: d's spread among the GRAIN_SHARE of its
    pixels with the least detail round them"""
    ok = ok & (lum > 2) & (lum < 250)
    if ok.sum() < 1000:
        return 0.0
    g = cv2.GaussianBlur(np.abs(d), (0, 0), 4)
    sel = ok & (g <= np.percentile(g[ok], GRAIN_SHARE * 100))
    return float(np.median(np.abs(d[sel])) * 1.4826 / np.sqrt(_kernel_noise(sigma)))


def noise_curve(lum, E, ok, bins=NOISE_BINS):
    """N at each pixel: E's NOISE_PCT percentile among ok pixels of about its brightness (lum blurred), bins with too
    few pixels from their neighbours; returns (N per pixel, the curve)"""
    base = cv2.GaussianBlur(lum, (0, 0), 2.0)
    edges = np.linspace(0, 256, bins + 1)
    idx = np.clip(np.digitize(base, edges) - 1, 0, bins - 1)
    curve = np.full(bins, np.nan)
    for b in range(bins):
        sel = ok & (idx == b)
        if sel.sum() >= NOISE_MIN_PX:
            curve[b] = np.percentile(E[sel], NOISE_PCT)
    have = np.where(~np.isnan(curve))[0]
    if not have.size:
        return None, curve
    measured = curve.copy()
    curve = np.interp(np.arange(bins), have, curve[have])
    # a bin all texture (a bright disk with no smooth patch at its brightness) measures its texture, not noise. On a
    # gamma-encoded picture noise is about as big at every brightness over the toe (shot noise grows as the gamma's slope
    # falls), so no bin's noise is taken as more than NOISE_CAP times the quiet bins' (NOISE_CAP_PCT of the measured
    # bins between NOISE_LEVELS, black and white clipping left out)
    mid = (edges[:-1] >= NOISE_LEVELS[0]) & (edges[1:] <= NOISE_LEVELS[1]) & ~np.isnan(measured)
    if mid.sum() >= 2:
        curve = np.minimum(curve, NOISE_CAP * np.percentile(measured[mid], NOISE_CAP_PCT))
    # a bin's noise is at least its neighbours' (a bin that is all smooth sky must not make its edge look clean)
    curve = np.maximum(curve, 0.5 * np.maximum(np.r_[curve[1:], curve[-1]], np.r_[curve[0], curve[:-1]]))
    return curve[idx].astype(np.float32), curve


def adaptive_sharpen(px, amount=AMOUNT, sigma=SIGMA, mask=None, report=None, grain=None, lossy=False):
    """px (uint8: H x W grey, or H x W x 2|3|4 with alpha last when 2 or 4) with its fine detail raised where it stands
    above the picture's own noise. mask: optional H x W float 0..1 (a body's disk, feathered) the change is scaled by.
    report: optional dict filled with the noise curve, blockiness and the share of pixels changed."""
    px = np.asarray(px)
    if amount <= 0 or px.size == 0:
        return px.copy()
    a3 = px[..., None] if px.ndim == 2 else px
    n = a3.shape[2]
    colors = n - 1 if n in (2, 4) else n
    rgb = a3[..., :colors].astype(np.float32)
    alpha = a3[..., colors].astype(np.float32) / 255 if colors < n else None
    lum = rgb[..., 0] if colors == 1 else rgb.mean(axis=2)
    valid = alpha > 0 if alpha is not None else np.ones(lum.shape, bool)
    inner = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    blur = _blur(lum, sigma, alpha)
    d = lum - blur
    E = _blur(d * d, ENERGY_SIGMA, alpha)
    kd = _kernel_noise(sigma)
    sat = cv2.dilate((rgb.max(axis=2) >= SAT_LEVEL).astype(np.uint8), np.ones((2 * SAT_PX + 1,) * 2, np.uint8)) > 0
    # (noise is measured away from black clipping too: next to clipped sky E is low because half the grain was cut)
    black = cv2.dilate((rgb.max(axis=2) <= 1).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    ok = inner & ~sat & ~black
    N, curve = noise_curve(lum, E, ok)
    if N is None:
        return px.copy()
    # lossy frames (the label's INST_CMPRS_TYPE): their block grid's steps count as noise. Measured blockiness alone
    # is not trusted (a lossless frame's saturated bloom or a centred picture's cut edge reads as blocks: the plume
    # frame N1831473782_1 measured 1.63), so it is used only on a frame the label says is lossy
    block = blockiness(lum, valid) if lossy else 1.0
    # ... and at least the noise the finest scale shows here: white noise is as strong at the highest frequency as
    # anywhere, detail the camera's point spread function softened is not, so a local noise estimate (Immerkaer's
    # kernel, which sees almost only the highest frequency) catches grain whose brightness bin did not (sky under
    # stray light, column stripes, a frame's noisier corner)
    fine = cv2.filter2D(lum, -1, IMMERKAER, borderType=cv2.BORDER_REFLECT)
    local = _blur(fine * fine, NYQ_SIGMA, alpha) * np.float32(kd / 36.0)
    N = np.maximum(N, np.float32(NYQ_SHARE) * local)
    N = np.maximum(N * np.float32(max(1.0, block) ** BLOCK_GAIN), np.float32(QUANT * kd))
    w = np.clip(1 - np.float32(WIENER / NOISE_P) * N / np.maximum(E, 1e-6), 0, 1)
    # spikes: a pixel far off its 3x3 median, more than noise could put it
    med = cv2.medianBlur(np.clip(lum + 0.5, 0, 255).astype(np.uint8), 3).astype(np.float32)
    sig = np.sqrt(N / kd)
    ring = np.ones((3, 3), np.uint8); ring[1, 1] = 0
    around = cv2.dilate(lum, ring) - cv2.erode(lum, ring)
    off = np.abs(lum - med)
    # (and well past the range of its 8 neighbours: a ray hits one pixel, texture moves its neighbours too)
    spike = (off > np.maximum(SPIKE * sig, SPIKE_MIN)) & (off > 2 * around)
    spike = cv2.dilate(spike.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    w = np.where(inner & ~sat & ~spike, w, 0).astype(np.float32)
    if mask is not None:
        w = w * np.asarray(mask, np.float32)
    # how stretched the picture is: the grain left in its smoothest places, in display levels (the stretch's gain
    # times the camera's noise, with every summing, compression and 8-bit step it went through). A picture whose
    # smooth places already show grain of GRAIN levels takes half the amount, a cleaner one nearly all of it.
    # (a movie or a mosaic passes its pass's grain, so every frame and tile takes the same amount: no flicker)
    if grain is None:
        grain = picture_grain(lum, d, valid & ~sat & ~black, sigma)
    amount = amount / (1 + (grain / GRAIN) ** 2) * (LOSSY_AMOUNT if lossy else 1.0)
    x = np.float32(amount) * w * d
    x = x / (1 + np.abs(x) / np.float32(EDGE))
    new = lum + x
    lo = cv2.erode(lum, np.ones((3, 3), np.uint8))
    hi = cv2.dilate(lum, np.ones((3, 3), np.uint8))
    m = np.minimum(OVERSHOOT * (hi - lo), OVERSHOOT_MAX)
    new = np.clip(new, lo - m, hi + m)
    x = new - lum
    # room: the same change on every color, rolled off as it nears 0 or 255 (no clipped colors)
    room = np.where(x > 0, 255 - rgb.max(axis=2), rgb.min(axis=2))
    knee = 0.5 * room
    mag = np.abs(x)
    soft = np.where(mag > knee, knee + (room - knee) * (mag - knee) / np.maximum(mag - knee + room - knee, 1e-6), mag)
    x = np.sign(x) * soft
    out = np.clip(rgb + x[..., None] + 0.5, 0, 255).astype(np.uint8)
    if alpha is not None:
        out = np.where(valid[..., None], out, a3[..., :colors])
    res = np.concatenate([out, a3[..., colors:]], axis=2) if colors < n else out
    if report is not None:
        report.update(grain=round(float(grain), 2), amount=round(float(amount), 3), noise=[round(float(v), 2) for v in curve], block=round(block, 3),
                      changed=round(float((np.abs(x) >= 0.5).mean()), 4), weight=w)
    return res[..., 0] if px.ndim == 2 else res
