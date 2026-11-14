#!/usr/bin/env python3
"""obs_mosaic.tinted_frame's fill where the frame clipped, with the wide reach of its local brightness match worked out
only when the near one leaves part of the fill without anything to go on, against the form it replaced (copied here as
it was at 2bdee523, both reaches every time): the same bytes. Made-up color sets and frames: nothing clipped, clipped
spots with lit picture round them (the wide reach is skipped), a clipped block wider than the near reach (it is
worked out), clipping at the picture's edge, off the set, on a dark frame, and both gammas and both kinds of match.
Run: python web/test_tint_reach.py"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402


def tinted_before(colour, grey, gamma=2.2, same=False):
    lin = lambda v: om.calibration.decode(v.astype(np.float32) / 255, gamma)
    colour = om._onto_frame(colour, grey)
    ca = colour[..., 3].astype(np.float32) / 255
    ga = grey[..., 3].astype(np.float32) / 255
    rgb = lin(colour[..., :3] / np.maximum(ca, 1 / 255)[..., None] / 1.0)
    rgb = np.clip(rgb, 0, None)
    if om.TINT_BLUR > 0:
        # (premultiplied: blurred unweighted, the picture's edge took in the empty canvas past it, a colored seam)
        ca0 = ca
        ca = cv2.GaussianBlur(ca0, (0, 0), om.TINT_BLUR)
        rgb = cv2.GaussianBlur(rgb * ca0[..., None], (0, 0), om.TINT_BLUR) / np.maximum(ca, 1e-3)[..., None]
    y = rgb @ np.asarray([0.2126, 0.7152, 0.0722], np.float32)
    g = lin(grey[..., 0])
    # (a clipped pixel of the frame says nothing of its brightness: left out of the match, and drawn from the set)
    near = np.clip((grey[..., 0].astype(np.float32) - om.TINT_CLIP) / max(1.0, om.CLIP_FROM - om.TINT_CLIP), 0, 1)
    clipped = near > 0
    both = (ca > 0.99) & (ga > 0.99) & ~clipped
    top_y = float(np.percentile(y[both], 99)) if both.any() else 0.0
    top_g = float(np.percentile(g[both], 99)) if both.any() else 0.0
    lit = both & (y > om.TINT_LIT * top_y) & (g > om.TINT_LIT * top_g)
    if lit.sum() >= om.LUM_MATCH_MIN and np.median(g[lit]) > 0:
        match = float(np.median(y[lit]) / np.median(g[lit]))
        hue = np.median(rgb[lit] / np.maximum(y[lit], 1e-6)[:, None], axis=0)
    else:
        match = float(np.median(y[both]) / max(np.median(g[both]), 1e-6)) if both.sum() >= om.LUM_MATCH_MIN else 1.0
        hue = np.ones(3, np.float32)
    # (same: the frame was taken with the set, the same moment, so its brightness is brought to the set's whole; a frame
    # further off only within om.TINT_MATCH)
    match = float(np.clip(match, *((1 / om.LUM_MATCH[1], om.LUM_MATCH[1]) if same else om.TINT_MATCH)))
    own = rgb / np.maximum(y, 1e-6)[..., None]
    # how far a pixel's hue strays from the set's mean, its largest per channel: past om.TINT_TRUST it fades to the mean,
    # gone at om.TINT_HUE (a channel lit where the others are not, the set's channels apart on a limb against the frame's
    # sharp one: a lime rim round Epimetheus, 259EP EPIMETHEU001; a cosmic ray in one channel)
    dev = np.abs(np.log(np.maximum(own, 1e-6) / np.maximum(hue, 1e-6)[None, None, :])).max(axis=2)
    trust = np.clip((math.log(om.TINT_HUE[1]) - dev) / (math.log(om.TINT_HUE[1]) - math.log(om.TINT_TRUST)), 0, 1)
    own = hue[None, None, :] * np.clip(own / np.maximum(hue, 1e-6)[None, None, :], *om.TINT_HUE)
    # the set's own hue where it is lit, held back from the edges of what it saw (its channels part there: magenta and
    # green seams); elsewhere, where the frame is lit (off the set's edge, or where the body has turned or moved since
    # the set: 153HY HYPERION001's cap came out gray), the set's mean hue, and gray only where the frame is dark too
    side = max(colour.shape[:2])
    seen = (ca * np.clip(y / max(om.TINT_DARK * top_y, 1e-6), 0, 1)).astype(np.float32)
    k = max(3, int(round(om.TINT_EDGE * side)) | 1)
    seen = cv2.GaussianBlur(cv2.erode(seen, np.ones((k, k), np.uint8)), (0, 0), k / 2)
    frame_lit = np.clip(g / max(om.TINT_DARK * top_g, 1e-6), 0, 1)[..., None]
    # (and only where the frame itself is lit: its dark sky takes no hue from the set's cosmic rays and hot pixels)
    w = (seen * trust)[..., None] * frame_lit
    rest = hue[None, None, :] * frame_lit + (1 - frame_lit)
    h = own * w + rest * (1 - w)
    out = np.clip(h * (g * match)[..., None], 0, 1)
    # where the frame clipped (a clear frame over-exposed on the planet behind the body it was exposed for) its
    # brightness says nothing: the set's own picture there, fading in from om.CLIP_FROM, so no flat white blotch
    clip = np.clip(cv2.GaussianBlur(near, (0, 0), max(4 * om.TINT_BLUR, om.TINT_FEATHER * side)), 0, 1) * ca
    if clip.any():
        # the set's picture brought to the frame's brightness round it, so the fill meets the frame without a seam
        # (the set was taken at another time and exposure: drawn as it is it made a patch of another brightness and
        # contrast over Saturn, cut along the frame's clipping, behind the 2012 Titan transit)
        valid = lit.astype(np.float32)
        sigma = om.TINT_LOCAL * side
        # (normalized convolution: the ratio of the blurred frame to the blurred set over where both are measured, at
        # two reaches, the wide one where the near one has nothing to go on deep inside the clipped part)
        local = np.ones(g.shape, np.float32)
        for reach in (4 * sigma, sigma):
            num = cv2.GaussianBlur(g * match * valid, (0, 0), reach)
            den = cv2.GaussianBlur(y * valid, (0, 0), reach)
            cover = cv2.GaussianBlur(valid, (0, 0), reach)
            known = np.clip(cover / 0.05, 0, 1)
            local = local * (1 - known) + np.where(den > 1e-9, num / np.maximum(den, 1e-9), 1.0) * known
        local = np.clip(local, *om.TINT_MATCH).astype(np.float32)
        # (the set's brightness there in the trusted hue, h: its own colors as they are carried the set's limb
        # misregistration in, a lime rim round Epimetheus' clipped clear frames, 259EP EPIMETHEU001)
        fill = np.clip(h * (y * local)[..., None], 0, 1)
        out = out * (1 - clip[..., None]) + fill * clip[..., None]
    rgb8 = (om.calibration.encode(out, gamma) * 255 + 0.5).astype(np.uint8)
    return np.dstack([rgb8, grey[..., 3]])
rng = np.random.default_rng(41)


def scene(side, spots, block=None, dark=False, off=0, hole=None):
    """(colour, grey): a color set's RGBA picture of a lit disk and a frame's RGBA of the same disk, off px away, with
    clipped spots [(x, y, radius)] and maybe a clipped block (x0, y0, x1, y1); hole: a box the set has no picture of."""
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
    r = np.hypot(xx - side * 0.5, yy - side * 0.52)
    disk = np.clip((side * 0.38 - r) / 3, 0, 1)
    shade = np.clip(0.35 + 0.5 * (xx / side), 0, 1) * disk * (0.25 if dark else 1.0)
    tex = cv2.GaussianBlur(rng.normal(0, 1, (side, side)).astype(np.float32), (0, 0), 2) * 0.08
    lum = np.clip(shade * (1 + tex), 0, 1)
    colour = np.dstack([np.clip(lum * g * 255, 0, 255).astype(np.uint8) for g in (1.0, 0.82, 0.6)] + [np.full((side, side), 255, np.uint8)])
    grey_l = np.roll(lum, off, axis=1) * 190
    for x, y, rad in spots:
        grey_l = np.where(np.hypot(xx - x, yy - y) < rad, 255, grey_l)
    if block:
        x0, y0, x1, y1 = block
        grey_l[y0:y1, x0:x1] = 255
    g8 = np.clip(grey_l, 0, 255).astype(np.uint8)
    grey = np.dstack([g8, g8, g8, np.full((side, side), 255, np.uint8)])
    grey[:6, :, 3] = 0          # (a frame's edge: no picture there)
    if hole:
        x0, y0, x1, y1 = hole
        colour[y0:y1, x0:x1] = 0
    return colour, grey


def main():
    side = 384
    cases = {
        "nothing clipped": scene(side, []),
        "clipped spots": scene(side, [(150, 170, 5), (230, 220, 9), (200, 120, 3)]),
        "a spot at the limb": scene(side, [(int(side * 0.5 - side * 0.37), int(side * 0.52), 8)]),
        "a wide clipped block": scene(side, [], (110, 110, 290, 300)),
        "a block and spots": scene(side, [(90, 200, 6)], (160, 140, 300, 260)),
        "clipped to the edge": scene(side, [], (0, 150, 140, 260)),
        "clipped off the set": scene(side, [(60, 60, 10)], None, hole=(30, 30, 100, 100)),
        "a dark frame, a bright spot": scene(side, [(190, 200, 7)], dark=True),
        "moved against the set": scene(side, [(170, 190, 6), (240, 150, 4)], off=7),
        "all clipped": scene(side, [], (0, 0, side, side)),
    }
    n = skipped = 0
    for name, (colour, grey) in cases.items():
        for gamma in (2.2, 1.0):
            for same in (False, True):
                c0, g0 = colour.copy(), grey.copy()
                before = tinted_before(colour, grey, gamma, same)
                calls = []
                real = cv2.GaussianBlur
                cv2.GaussianBlur = lambda src, k, s, *a, **kw: (calls.append(s), real(src, k, s, *a, **kw))[1]
                try:
                    after = om.tinted_frame(colour, grey, gamma, same)
                finally:
                    cv2.GaussianBlur = real
                assert np.array_equal(c0, colour) and np.array_equal(g0, grey), name
                assert before.dtype == after.dtype and before.shape == after.shape and before.tobytes() == after.tobytes(), \
                    (name, gamma, same, int((before != after).sum()))
                wide = 4 * om.TINT_LOCAL * side
                worked = sum(1 for s in calls if s == wide)
                assert worked in (0, 3), (name, calls)
                # the wide reach is worked out where the fill has nothing near to go on, and only there
                if name in ("clipped spots", "a spot at the limb", "moved against the set"):
                    assert worked == 0, (name, calls)
                if name in ("a wide clipped block", "all clipped"):
                    assert worked == 3, (name, calls)
                skipped += worked == 0 and om.TINT_LOCAL * side in calls
                n += 1
    print(f"ok: {n} tinted frames the same to the byte as before; the wide reach skipped in {skipped} of them")


if __name__ == "__main__":
    main()
