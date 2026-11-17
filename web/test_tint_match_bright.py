"""A tinted frame's brightness follows its exposure gain on a bright body. tinted_frame matches the frame to its colour
set over the lit pixels both show, leaving the frame's clipped pixels out. It left out everything from TINT_CLIP (200)
up, which is only where the frame starts easing over to the set's picture: clipping is CLIP_FROM (240). A body whose
disk sits at 185 to 225 (Jupiter in its approach movie) lost a third of its disk from the match at its own exposure
and more with every step of gain, until the match was its limb and haze against the set's: frame 59 of C23RI RMOV001
came out at median 187 at gain 1.055, 208 at 1.06, 240 at 1.08 and 242 at 1.4 (2026-11-16). Here a made-up disk that
bright with a set a little brighter, both at a run of gains: the tinted frame brightens with each step, by a steady
share, and the frame's match to its set stays the same.
Run: python web/test_tint_match_bright.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

G = 2.2
om._onto_frame = lambda colour, grey: colour     # (the set already sits on the frame here)
S, R = 512, 90
yy, xx = np.mgrid[:S, :S]
r = np.hypot(xx - S / 2, yy - S / 2) / R
mu = np.sqrt(np.clip(1 - r ** 2, 0, 1))
disk = r < 1
# linear brightness: a limb-darkened disk with bands, its middle about display level 215, on a black sky
lin = np.where(disk, (0.36 + 0.42 * mu) * (1 + 0.06 * np.sin(yy / 9.0)), 0.0).astype(np.float32)
enc = lambda v: (om.calibration.encode(np.clip(v, 0, 1), G) * 255 + 0.5).astype(np.uint8)
dec = lambda v: om.calibration.decode(v.astype(np.float32) / 255, G)
assert 205 < np.median(enc(lin)[disk]) < 235 and (enc(lin)[disk] >= om.TINT_CLIP).mean() > 0.5


def tinted(gain):
    grey = np.dstack([enc(lin * gain)] * 3 + [np.full((S, S), 255, np.uint8)])
    hue = np.asarray([1.10, 1.00, 0.85], np.float32)
    colour = np.dstack([enc(lin * gain * 1.08 * h) for h in hue] + [np.full((S, S), 255, np.uint8)])
    out = om.tinted_frame(colour, grey, G, True)
    y = dec(out[..., :3]) @ np.asarray([0.2126, 0.7152, 0.0722], np.float32)
    ok = disk & (grey[..., 0] < om.TINT_CLIP - 5) & (lin > 0.05)      # where the frame is its own and far from clipping
    return float(np.median(out[..., :3].mean(axis=2)[disk])), float(np.median(y[ok] / dec(grey[..., 0])[ok]))


gains = [0.8, 0.9, 1.0, 1.03, 1.06, 1.1, 1.2]
got = [tinted(g) for g in gains]
med, match = [m for m, _ in got], [k for _, k in got]
print("median", [round(m, 1) for m in med], "match", [round(k, 3) for k in match])
assert all(b >= a - 0.5 for a, b in zip(med, med[1:])), med                 # brighter with each step of gain
assert all(b - a < 14 for a, b in zip(med, med[1:])), med                    # and by a step, not a leap
assert max(match) / min(match) < 1.06, match                                # the frame's match to its set is one match
print("ok")
