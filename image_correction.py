# -*- coding: utf-8 -*-
"""
Created on Sat Apr  9 13:09:54 2022

@author: Sam I
"""

import numpy as np
import warnings

#from color_transfer import color_transfer

import cv2

last = None



def align_images(imgs, ref=0):
    # ref = index of the frame the others are aligned to; the middle frame in time keeps offsets smallest
    for i in range(0, len(imgs)):
        if i != ref:
            imgs[i] = shift_align(imgs[ref],imgs[i])

    return imgs


"""
Fills a frame's invalid pixels (mask False) from the valid ones around them, so the zeros of
truncated lines don't bleed into neighbouring rows when the frame is shifted or skew its
brightness scale. The pixels stay invalid; this only keeps them from affecting the rest.
"""
def fill_invalid(img, mask):
    if mask.all():
        return img
    return cv2.inpaint(img, (~mask).astype(np.uint8), 3, cv2.INPAINT_TELEA)


# the tallest gap (rows, at the 1024 line size) fill_lines bridges: four lines of a summed 512 line frame. Lost
# segments that short are a line or a few here and there, which the rows above and below show well; a taller
# block is a stretch of the picture that never arrived and stays marked lost rather than painted over
LINE_GAP = 8


"""
For each pixel, the nearest row at or above it where on (a 2D bool mask) is True, -1 where there is none: what
np.maximum.accumulate(np.where(on, rows, -1), axis=0) gives, worked out a row at a time (numpy's accumulate down a
frame's columns steps across memory, ~16 ms a 1024 px frame; a row at a time ~1.5 ms). rows_below: the nearest row
at or below, h where there is none.
"""
def rows_above(on):
    out = np.empty(on.shape, int)
    last = np.full(on.shape[1], -1, int)
    for r in range(on.shape[0]):
        np.copyto(last, r, where=on[r])
        out[r] = last
    return out


def rows_below(on):
    h = on.shape[0]
    out = np.empty(on.shape, int)
    last = np.full(on.shape[1], h, int)
    for r in range(h - 1, -1, -1):
        np.copyto(last, r, where=on[r])
        out[r] = last
    return out


"""
Fills the short runs of lost pixels (mask False) down each column from the valid rows above and
below, and returns (image, mask with those pixels now valid). Lost pixels are the ends of lines
that never arrived, so a lost run down a column is a stack of those lines; where it is at most
max_gap rows tall its two valid neighbours bound it closely. Taller runs, and runs at the top or
bottom edge, are left as they are (still invalid). Which pixels are filled, and how, is
line_fills' (worked out on img); fills = that, worked out on another picture of the same frame
(its display image for its I/F), so both are filled alike.
"""
def fill_lines(img, mask, max_gap=LINE_GAP, fills=None):
    if mask.all():
        return img, mask
    fillable, slope = line_fills(img, mask, max_gap) if fills is None else fills
    if not fillable.any():
        return img, mask
    above, below = rows_above(mask), rows_below(mask)
    ys, xs = np.nonzero(fillable)
    a, b = above[ys, xs], below[ys, xs]
    t = ((ys - a) / (b - a)).astype(np.float32)
    k = slope[ys, xs]
    va = _along(img, a, xs - k * (ys - a))
    vb = _along(img, b, xs + k * (b - ys))
    if img.ndim == 3:
        t = t[:, None]
    v = va + (vb - va) * t
    out = img.copy()
    out[ys, xs] = np.clip(v + 0.5, 0, 255).astype(img.dtype) if img.dtype == np.uint8 else v.astype(img.dtype)
    return out, mask | fillable


"""
img's values in rows ys at the (fractional) columns xs, read between the two nearest pixels, as float32.
"""
def _along(img, ys, xs):
    w = img.shape[1]
    xs = np.clip(xs, 0, w - 1)
    x0 = np.floor(xs).astype(int)
    x1 = np.minimum(x0 + 1, w - 1)
    f = (xs - x0).astype(np.float32)
    if img.ndim == 3:
        f = f[:, None]
    lo, hi = img[ys, x0].astype(np.float32), img[ys, x1].astype(np.float32)
    return lo + (hi - lo) * f


# how far (pixels sideways per row) a fill may follow the picture's slant (line_fills): a ring's edge or a limb
# crossing the gap at down to about 18 degrees from the lines
FILL_SLANT = 3
# a run is filled only when the same fill, tried on the valid rows just above and below it, is out by at most
# FILL_MISS times the frame's row-to-row noise (and FILL_FLOOR display levels): a fill out by more is a flat grey
# dash across the picture, and the run is better left lost (transparent)
FILL_MISS = 3.0
FILL_FLOOR = 3.0
# ... or by at most this share of how much the picture there varies (a limb across the run: the fill misses where it
# crosses, but draws the rest; a patch no slant reads, which a fill draws no better than its average, stays lost)
FILL_GUESS = 0.5
# ... and only when the trial had valid rows next to at least this share of the run to try on: lines lost every other
# line (a frame's lost packets) leave a few pixels at the run's end, too few to judge it by, and the run is filled
FILL_TRIED = 0.5


"""
Which of mask's lost pixels fill_lines fills, and along which slant: (fillable mask, slope in pixels sideways per
row, as float32 over the frame). A run of lost lines (a connected patch of short lost runs down the columns) is
filled straight between the rows above and below it, along the slant that best matches the row above it to the
row below (rings and limbs cross the gap at an angle; filled straight down, a dark gap between bright ringlets
became a flat grey bar). The fill is first tried on the valid rows next to the run, as if a run as tall were lost
there: a run whose trial fill misses the picture by more than the frame's noise allows (FILL_MISS), and by more than
half of how much the picture varies there (FILL_GUESS), stays lost. A run one of the frame's own lines tall (line:
rows of mask per line, 4 for a 256 line frame on the 1024 grid) is always filled: its two neighbours are the nearest
lines the frame has, no fill does better, and left lost it is a black line through a colour set.
"""
def line_fills(img, mask, max_gap=LINE_GAP, line=1):
    h, w = mask.shape
    slope = np.zeros((h, w), np.float32)
    above, below = rows_above(mask), rows_below(mask)
    fillable = ~mask & (above >= 0) & (below < h) & (below - above - 1 <= max_gap)
    if not fillable.any():
        return fillable, slope
    gray = (img.mean(axis=2) if img.ndim == 3 else img).astype(np.float32)
    # the frame's noise, from the steps between valid neighbouring pixels down the columns and along the rows,
    # whichever are smaller (structure running along one of them, as a ring's, steps only across it)
    steps = [np.abs(np.diff(gray, axis=0))[mask[1:] & mask[:-1]], np.abs(np.diff(gray, axis=1))[mask[:, 1:] & mask[:, :-1]]]
    noise = min(1.4826 * float(np.median(d)) / np.sqrt(2) if d.size else np.inf for d in steps)
    noise = 0.0 if np.isinf(noise) else noise
    # the nearest lost row below each pixel, so a trial knows its rows are all valid
    lost_below = rows_below(~mask)
    count, runs = cv2.connectedComponents(fillable.astype(np.uint8), connectivity=8)
    keep = np.zeros(count, bool)
    every_y, every_x = np.nonzero(fillable)
    of = runs[every_y, every_x]
    order = np.argsort(of, kind="stable")
    starts = np.searchsorted(of[order], np.arange(1, count + 1))
    for r in range(1, count):
        at = order[starts[r - 1]:starts[r]]
        ys, xs = every_y[at], every_x[at]
        a, b = above[ys, xs], below[ys, xs]
        span = int((b - a).max())
        if span - 1 <= line:
            keep[r] = True
            slope[ys, xs] = _slant(gray, mask, a.min(), b.max(), xs.min(), xs.max() + 1, span)
            continue
        x0, x1 = xs.min(), xs.max() + 1
        k = _slant(gray, mask, a.min(), b.max(), x0, x1, span)
        # the trial: the same fill on the rows above the run (a run as tall, ending at its top row) and below it
        misses, spreads = [], []
        for top, bottom in ((a - (b - a), a), (b, b + (b - a))):
            ok = (top >= 0) & (bottom < h)
            ok[ok] &= (lost_below[top[ok], xs[ok]] > bottom[ok])
            if not ok.any():
                continue
            yy = ys[ok] - a[ok] + top[ok]
            t, tt, bb = (yy - top[ok]) / (bottom[ok] - top[ok]), top[ok], bottom[ok]
            va = _along(gray, tt, xs[ok] - k * (yy - tt))
            vb = _along(gray, bb, xs[ok] + k * (bb - yy))
            truth = gray[yy, xs[ok]]
            misses.append(np.abs(va + (vb - va) * t - truth))
            spreads.append(np.abs(truth - truth.mean()))
        tried = sum(len(m) for m in misses)
        miss = float(np.mean(np.concatenate(misses))) if misses else 0.0
        spread = float(np.mean(np.concatenate(spreads))) if spreads else 0.0
        if tried < FILL_TRIED * len(ys) or miss <= max(FILL_MISS * noise, FILL_FLOOR, FILL_GUESS * spread):
            keep[r] = True
            slope[ys, xs] = k
    fillable = keep[runs] & fillable
    return fillable, slope


"""
The slant (pixels sideways per row) along which rows y0 and y1 of gray best match over columns x0..x1 (FILL_SLANT
per row at most, in quarter pixel steps of the whole gap): 0 unless a slant matches clearly better than straight.
"""
def _slant(gray, mask, y0, y1, x0, x1, span):
    w = gray.shape[1]
    reach = int(np.ceil(FILL_SLANT * span))
    xs = np.arange(max(x0 - reach // 2, 0), min(x1 + reach // 2, w))
    dx = np.arange(-4 * reach, 4 * reach + 1)[:, None] / 4.0
    # row y0 at x - dx / 2 against row y1 at x + dx / 2: the slant crossing the gap through x
    left, right = xs - dx / 2, xs + dx / 2
    ok = mask[y0, xs] & mask[y1, xs] & (left >= 0) & (right <= w - 1)
    n = ok.sum(axis=1)
    d = np.abs(_along(gray, np.full(left.shape, y0), left) - _along(gray, np.full(right.shape, y1), right))
    d = np.where(n >= 4, (d * ok).sum(axis=1) / np.maximum(n, 1), np.inf)
    straight, best = d[4 * reach], int(np.argmin(d))
    if not np.isfinite(straight) or d[best] > 0.8 * straight:
        return 0.0
    return float(dx[best, 0]) / span


# a one-frame spike (spikes): a peak this many times the frame's noise above its own surroundings
SPIKE_SIGMA = 5.0
# px: a peak in a neighbouring frame this close (after registration) is the same thing seen again (a star drifting,
# a small moon), not a spike
SPIKE_REACH = 5
# px: the widest a spike is (a cosmic ray's dot or short track); a wider peak is structure (a crater, lightning)
SPIKE_SIZE = 9


"""
The pixels of img (a movie's frame: as label.resize_image, or better in the camera's own values, color_image._linear,
where a faint sky has more than the few levels a frame's 8-bit stretch leaves it) that are one-frame spikes: a cosmic ray's dot or short
track, there in this frame only. A pixel is one when it stands SPIKE_SIGMA times the frame's noise above the
frame's own surroundings (its 5 px median), on a peak no wider than SPIKE_SIZE, and neither neighbour (the same
filter's frames just before and after it in the movie, registered to it by find_shift as stack_frames does) has a
peak within SPIKE_REACH of it. In a long dark stare a new set of them every frame twinkled across the sky. The
frame's spikes are replaced by what is round them (unspike, color_image.load_aligned).
returns a bool mask the size of img, True on the spikes and the pixel round each
"""
def spikes(img, neighbours):
    neighbours = [n for n in neighbours if n is not None and n.shape == img.shape]
    if not neighbours:
        return np.zeros(img.shape[:2], bool)

    def peaks(im):
        g = (cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im).astype(np.float32)
        p = g - cv2.medianBlur(g, 5)
        # the noise: the spread of the peaks under the top 1%, as the median of them is 0 in a frame stored in
        # coarse steps (a faint sky in the lean archive's codes is a level or two, 10 DN apart)
        a = np.abs(p)
        return p, max(1.4826 * float(np.median(a)), float(np.std(p[a <= np.percentile(a, 99)]))) + 0.5

    own, noise = peaks(img)
    found = own > SPIKE_SIGMA * noise
    if not found.any():
        return found
    count, runs, stats, _ = cv2.connectedComponentsWithStats(found.astype(np.uint8), connectivity=8)
    small = np.r_[False, (stats[1:, cv2.CC_STAT_WIDTH] <= SPIKE_SIZE) & (stats[1:, cv2.CC_STAT_HEIGHT] <= SPIKE_SIZE)]
    found = small[runs]
    near = np.ones((2 * SPIKE_REACH + 1, 2 * SPIKE_REACH + 1), np.uint8)
    for other in neighbours:
        if not found.any():
            break
        shift = find_shift(_bgr(img), _bgr(other))
        if shift is not None:
            other = shift_image(other, *shift)
        theirs, their_noise = peaks(other)
        # the highest peak near each pixel in the neighbour, against this frame's peak there (each in its own
        # frame's noise): one half as high counts, as a star a little fainter in the next frame is still that star
        seen = cv2.dilate(theirs / their_noise, near) >= 0.5 * own / noise
        found &= ~seen
    return cv2.dilate(found.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0


def _bgr(im):
    """im as find_shift takes it: 8-bit BGR, a single channel float image stretched from 0 to its 99.9th percentile"""
    if im.ndim == 3:
        return im
    if im.dtype != np.uint8:
        top = max(float(np.percentile(im, 99.9)), 1e-9)
        im = np.clip(im * (255.0 / top), 0, 255).astype(np.uint8)
    return cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)


"""
img with the pixels of found (spikes) replaced by the median of the 5 x 5 pixels round each: a spike a pixel or two
wide (found takes in the pixel round it) is a few of those 25, so the median is what is round it.
"""
def unspike(img, found):
    work = img if img.dtype in (np.uint8, np.float32) else img.astype(np.float32)
    out = img.copy()
    out[found] = cv2.medianBlur(work, 5)[found]
    return out


"""
Like align_images, but also moves each frame's valid-pixel mask (label.valid_mask) with it,
so pixels a shift leaves uncovered count as invalid too.
Phase correlation needs the frames to look alike; through filters far apart (UV against
IR) it can fail to find a match. A whole target in every frame then still lines up by
its centroid (centroid_shift).
report = optional list that gets one entry per frame: how it was aligned
guess = optional list, one per frame: where SPICE says the frame's target sits relative to the reference's,
(dx, dy) in the frames' pixels, or None (see guided_shift). A colour set's channels pass it
(color_image.load_aligned)
within = px: each frame searched only this near its guess (or no shift), nothing else tried (_match): a mosaic's
tiles, already at SPICE's places (obs_mosaic._register)
Three frames (a colour set) are also matched with one another and solved together (_loop).
returns (imgs, masks)
"""
def align_with_masks(imgs, masks, ref=0, report=None, found=None, use=None, guess=None, within=None):
    # the frames as they came, for matching the channels with one another (the loop check below)
    orig, omasks = list(imgs), [m.copy() for m in masks]
    shifts, hows = [None] * len(imgs), [None] * len(imgs)
    for i in range(0, len(imgs)):
        if i == ref:
            continue
        if use is not None:
            # shifts found on other versions of these frames (see color_image.load_aligned)
            if use[i] is not None:
                imgs[i] = shift_image(imgs[i], *use[i])
                masks[i] = shift_image(masks[i].astype(np.float32), *use[i]) > 0.99
            continue
        g = guess[i] if guess is not None else None
        shifts[i], hows[i] = _match(orig[ref], orig[i], g, omasks[ref], omasks[i], within)
    if use is None and within is None and len(imgs) == 3:
        _loop(orig, omasks, ref, shifts, hows, guess)
    for i in range(0, len(imgs)):
        if i == ref:
            if report is not None:
                report.append("reference")
            if found is not None:
                found.append(None)
            continue
        if use is not None:
            continue
        shift, how = shifts[i], hows[i]
        if shift is not None:
            imgs[i] = shift_image(imgs[i], *shift)
            masks[i] = shift_image(masks[i].astype(np.float32), *shift) > 0.99
        if report is not None:
            report.append(f"{how} {shift[0]:+.1f},{shift[1]:+.1f}" if shift is not None else "not aligned")
        if found is not None:
            found.append(shift)
    return imgs, masks


"""
How far im2 is from im1, (dx, dy) as shift_image moves im2 back by, and how it was found: phase correlation; then,
with SPICE's offset g, again near it (guided_shift); then on stars (star_shift: a star field, a black sky); then on
edges, then by the lit area's centroid; then SPICE's offset alone where it lines the edges up better than none.
within = only near g (or no shift) within that many px (guided_shift's search alone): a mosaic tile already at
SPICE's place, where a larger move is a false match (obs_mosaic._register). ((dx, dy) or None, how)
"""
def _match(im1, im2, g, mask1, mask2, within=None):
    if within is not None:
        found, how = guided_shift(im1, im2, g if g is not None else (0.0, 0.0), window=within)
        return found, how
    shift, how = find_shift(im1, im2), "phase"
    if shift is None and g is not None:
        # SPICE knows about where the frame is: the frames are matched again near there first
        shift, how = guided_shift(im1, im2, g, weak=True)
    rejected = []
    if shift is None:
        shift, how = _plausible(star_shift(im1, im2), "stars", g, rejected)
    if shift is None:
        shift, how = find_shift(edges(im1), edges(im2)), "edges"
        # an edge match at exactly no shift is the camera's own fixed pattern (dust rings, bad
        # columns) matching itself, not the target: it says nothing
        if shift is not None and abs(shift[0]) < 0.25 and abs(shift[1]) < 0.25:
            shift = None
        shift, how = _plausible(shift, how, g, rejected)
        if shift is None:
            shift, how = centroid_shift(im1, im2), "centroid"
    if shift is None and g is not None:
        # nothing matched anywhere (or only wild fits): SPICE's offset, where it lines the frames up better than none
        shift, how = spice_shift(im1, im2, mask1, mask2, g)
    if rejected:
        how = f"{how} ({', '.join(rejected)} rejected)"
    return shift, how


"""
A star or edge fit (the fallbacks after phase correlation) found far from SPICE's offset g is taken for a false one:
stars on a ring frame or an all-planet frame, edges of rings, the noise of an empty sky (W1874655257_1: stars 106 px
from SPICE, W1537024388_1: +32,-92, N1716316428_1: -17,-65). Within FIT_REACH px of g it stands; without g it stands as
before. The centroid is not checked: it is taken only when the whole target is in both frames, and SPICE's offset
between two filters is itself up to 30 px off (N1830230441_1: SPICE 27 px, the centroid and phase both under 3 px).
(shift or None, how); a rejected fit is noted in rejected.
"""
FIT_REACH = 32.0    # px: past the 27 to 30 px SPICE is seen off between a set's filters (W1714632762_1, N1830230441_1)


def _plausible(shift, how, g, rejected):
    if shift is None or g is None or np.hypot(shift[0] - g[0], shift[1] - g[1]) <= FIT_REACH:
        return shift, how
    rejected.append(f"{how} {shift[0]:+.1f},{shift[1]:+.1f}")
    return None, how


"""
The loop check of a three-channel set: each channel was matched to the reference on its own, so a wrong match went
unnoticed (W1643279524_1 took a -50.7 px phase match, N1807503852_1 a +12.9,-33.9 centroid). The two other channels
are matched with each other too; that third match must equal the difference of the first two. Within LOOP_CLOSE px
the three are solved together (least squares, the error shared); further, the pair of the three matches that lines
the edges up best (_agreement) stands and the third follows from it; and a channel that matched nothing takes its
place from the other one through their own match. shifts and hows (per channel, None for the reference) are changed.
"""
LOOP_CLOSE = 1.0   # px
AS_TAKEN = 0.6     # edge agreement (_agreement) a channel as the camera took it needs to stand unshifted


def _loop(orig, masks, ref, shifts, hows, guess):
    a, b = [i for i in range(3) if i != ref]
    sa, sb = shifts[a], shifts[b]
    g = None
    if guess is not None and guess[a] is not None and guess[b] is not None:
        g = (guess[b][0] - guess[a][0], guess[b][1] - guess[a][1])
    if sa is None and sb is None:
        return
    sab, how = _match(orig[a], orig[b], g, masks[a], masks[b])
    if sab is None:
        return
    if sa is None or sb is None:
        # the channel that matched nothing lands through the other one
        c = a if sa is None else b
        landing = (sb[0] - sab[0], sb[1] - sab[1]) if sa is None else (sa[0] + sab[0], sa[1] + sab[1])
        shifts[c], hows[c] = landing, f"{how} via the other channel"
        # a landing is no better than the match it came through (SPICE's offset alone, where the two other channels
        # matched nothing either): one that lines the edges up worse than the channel as the camera took it does not
        # stand. The channel stays as taken where that lines up well (AS_TAKEN), else it is not aligned (175TI
        # N1733045482_1: SPICE 24 px off between the filters, the landing put a magenta rim round Titan; as taken the
        # edges agree 0.84, the landing 0.63)
        here = _agreement(orig[ref], orig[c], masks[ref], masks[c], landing)
        still = _agreement(orig[ref], orig[c], masks[ref], masks[c], (0.0, 0.0))
        if still > here:
            shifts[c], hows[c] = ((0.0, 0.0), "as taken (the landing via the other channel worse)") if still >= AS_TAKEN \
                else (None, "not aligned")
        return
    rx, ry = sab[0] - (sb[0] - sa[0]), sab[1] - (sb[1] - sa[1])
    if np.hypot(rx, ry) <= LOOP_CLOSE:
        shifts[a] = ((2 * sa[0] + sb[0] - sab[0]) / 3, (2 * sa[1] + sb[1] - sab[1]) / 3)
        shifts[b] = ((sa[0] + 2 * sb[0] + sab[0]) / 3, (sa[1] + 2 * sb[1] + sab[1]) / 3)
        return
    # the loop does not close: one of the three matches is wrong
    candidates = [(sa, sb, None), (sa, (sa[0] + sab[0], sa[1] + sab[1]), b), ((sb[0] - sab[0], sb[1] - sab[1]), sb, a)]

    def score(c):
        return _agreement(orig[ref], orig[a], masks[ref], masks[a], c[0]) + \
            _agreement(orig[ref], orig[b], masks[ref], masks[b], c[1])
    best = max(candidates, key=score)
    shifts[a], shifts[b] = best[0], best[1]
    if best[2] is not None:
        hows[best[2]] = f"{how} via the other channel (loop {np.hypot(rx, ry):.1f} px)"


"""
Gradient magnitude of a frame, as a 3 channel 8-bit image for find_shift. Limbs, terminators
and crater rims sit in the same place through every filter even when their brightness does
not (bright haze in blue, dark surface in infrared), so edges can match where the frames don't.
"""
def edges(im):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    gray = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.5)
    mag = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    mag = np.clip(mag * 255.0 / max(np.percentile(mag, 99.5), 1e-6), 0, 255).astype(np.uint8)
    return cv2.cvtColor(mag, cv2.COLOR_GRAY2BGR)


"""
Offset of im2 from im1 by the centroid of the target's lit area, for when phase
correlation fails. Only used when the target sits wholly inside both frames (its lit
area touches no edge), since a cut-off target moves its centroid.
returns (dx, dy) or None
"""
def centroid_shift(im1, im2, max_shift=100):
    centres = []
    for im in (im1, im2):
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32) if im.ndim == 3 else im.astype(np.float32)
        blurred = cv2.GaussianBlur(gray, (0, 0), 3)
        if blurred.max() <= 0:
            return None
        lit = blurred > 0.2 * blurred.max()
        if lit.sum() < 50 or lit[0].any() or lit[-1].any() or lit[:, 0].any() or lit[:, -1].any():
            return None
        ys, xs = np.nonzero(lit)
        weight = blurred[ys, xs]
        centres.append(((xs * weight).sum() / weight.sum(), (ys * weight).sum() / weight.sum()))
    dx, dy = centres[1][0] - centres[0][0], centres[1][1] - centres[0][1]
    if abs(dx) > max_shift or abs(dy) > max_shift:
        return None
    return dx, dy


"""
Offset of im2 from im1 when phase correlation alone found none, with SPICE's offset guess = (dx, dy) to go by:
where the geometry cache places the target in each frame, which follows the camera's pointing from frame to frame.
A frame-filling limb or ring seen through two filters far apart correlates too weakly to pass find_shift's bar, and
its lit area touches the frame's edge so the centroid refuses it; the pointing drift between the frames then stayed
in the picture as colour fringes, a quarter of Rhea wide when the camera moved 105 px between filters (N1711682068_1).
Here the frame is first moved by SPICE's offset, then matched again within GUESS_WINDOW of it, where a weaker peak
(GUESS_RESPONSE) is believed: by phase correlation, then on edges, then the centroid (on the frames as they are,
believed within the same window). SPICE's pointing can itself be tens of pixels off (a WAC set of 2012-05-02,
W1714632762_1, moved 30 px that SPICE doesn't show), so when nothing matches near it the frames' own fallbacks still
run (align_with_masks), and only then SPICE's offset (spice_shift). A guess past GUESS_MAX is no help: the frames
show different parts of the scene. weak = a colour set's channels (not a mosaic's tiles): phase correlation and edges
that agree within WEAK_AGREE px are believed down to GUESS_WEAK.
returns ((dx, dy), how) or (None, "not aligned")
"""
GUESS_WINDOW = 12     # px: SPICE's pointing is 3 to 5 px off from panel to panel, 11 at most (obs_mosaic.PANEL_MAX)
GUESS_RESPONSE = 0.1  # the least phase correlation peak believed within that window
GUESS_MAX = 256       # px: a quarter of the frame
AGREE_MARGIN = 0.02   # how much better SPICE's offset must line the edges up than no shift does


GUESS_WEAK = 0.05     # the least peak believed when phase correlation and edges agree (weak=True)
WEAK_AGREE = 3.0      # px: how near the two must agree


def guided_shift(im1, im2, guess, window=GUESS_WINDOW, weak=False):
    gx, gy = float(guess[0]), float(guess[1])
    if np.hypot(gx, gy) > GUESS_MAX:
        return None, "not aligned"
    moved = shift_image(im2, gx, gy)
    for how, a, b in (("phase", im1, moved), ("edges", edges(im1), edges(moved))):
        found = find_shift(a, b, window, GUESS_RESPONSE)
        if found is not None:
            dx, dy = gx + found[0], gy + found[1]
            # as align_with_masks: an edge match at exactly no shift is the camera's fixed pattern
            if how == "edges" and abs(dx) < 0.25 and abs(dy) < 0.25:
                continue
            return (dx, dy), how + " near SPICE"
    found = centroid_shift(im1, im2)
    if found is not None and np.hypot(found[0] - gx, found[1] - gy) <= window:
        return found, "centroid near SPICE"
    if weak:
        # a weaker peak both on the frames and on their edges, at the same place: two matches agreeing are believed
        # where neither alone is (WAC Grand Finale rings, W1874655257_1: phase and edges both 18,175 px at 0.07 and
        # 0.08 where SPICE says 28,169, which leaves a fringe on every ringlet)
        pa = find_shift(im1, moved, window, GUESS_WEAK)
        pe = find_shift(edges(im1), edges(moved), window, GUESS_WEAK) if pa is not None else None
        if pe is not None and np.hypot(pa[0] - pe[0], pa[1] - pe[1]) <= WEAK_AGREE:
            return (gx + (pa[0] + pe[0]) / 2, gy + (pa[1] + pe[1]) / 2), "phase and edges near SPICE"
    return None, "not aligned"


"""
SPICE's offset guess for im2 when no match was found anywhere, if it lines the frames' edges up better than no shift
(by AGREE_MARGIN) or is under SPICE_SURE px, else none (the set is then drawn grey, color_image.grey_from). masks = the two frames' valid pixels (label.valid_mask)
returns ((dx, dy), "SPICE") or (None, "not aligned")
"""
SPICE_SURE = 2.0   # px: an offset this small is taken as it is (no shift or SPICE's differ by less than a fringe)


def spice_shift(im1, im2, mask1, mask2, guess):
    gx, gy = float(guess[0]), float(guess[1])
    if np.hypot(gx, gy) <= SPICE_SURE:
        return (gx, gy), "SPICE"
    if np.hypot(gx, gy) <= GUESS_MAX and \
            _agreement(im1, im2, mask1, mask2, (gx, gy)) > _agreement(im1, im2, mask1, mask2, (0.0, 0.0)) + AGREE_MARGIN:
        return (gx, gy), "SPICE"
    return None, "not aligned"


"""
How well im2 moved by shift lines up with im1: the correlation of their edges (edges) over the pixels valid in both
"""
def _agreement(im1, im2, mask1, mask2, shift):
    a = edges(im1)[..., 0].astype(np.float32)
    b = edges(shift_image(im2, *shift))[..., 0].astype(np.float32)
    both = mask1 & (shift_image(mask2.astype(np.float32), *shift) > 0.99)
    # not the edge the shift's own border makes (edges blurs it a few pixels into the frame)
    both = cv2.erode(both.astype(np.uint8), np.ones((9, 9), np.uint8), borderValue=0) > 0
    if both.sum() < 100:
        return -1.0
    a, b = a[both] - a[both].mean(), b[both] - b[both].mean()
    return float((a * b).sum() / max(np.sqrt((a * a).sum() * (b * b).sum()), 1e-9))


"""
Finds the sub-pixel translation of im2 relative to im1 by phase correlation.
Filter frames in a color sequence are taken seconds apart, so the target only
moves across the sensor; a translation is the right motion model.
max_shift = largest offset in pixels that is accepted as real
min_response = phase correlation peak below which the match is rejected

returns (dx, dy) or None if no trustworthy match was found
"""
def find_shift(im1, im2, max_shift=100, min_response=0.3):
    im1_gray = cv2.cvtColor(im1,cv2.COLOR_BGR2GRAY).astype(np.float32)
    im2_gray = cv2.cvtColor(im2,cv2.COLOR_BGR2GRAY).astype(np.float32)

    # correlate only the area around the target so empty sky does not dilute the match
    blurred = cv2.GaussianBlur(im1_gray, (0,0), 3)
    ys, xs = np.nonzero(blurred > 0.2 * blurred.max())
    if len(ys) == 0:
        print("Image alignment skipped: blank reference frame")
        return None
    if len(ys) < DARK_SHARE * blurred.size:
        # a black scene (stars, a backlit ring, a speck of a moon): its brightest pixels may be hot pixels and its
        # texture the camera's fixed pattern, which sit still while the scene moves and pull the match to no shift.
        # A 3 x 3 median takes the one-pixel ones out of both frames before they are matched
        im1_gray = cv2.medianBlur(im1_gray, 3)
        im2_gray = cv2.medianBlur(im2_gray, 3)
        blurred = cv2.GaussianBlur(im1_gray, (0,0), 3)
        ys, xs = np.nonzero(blurred > 0.2 * blurred.max())
        if len(ys) == 0:
            return None
    h, w = im1_gray.shape
    # (at least FIND_MARGIN round the target, so a small search keeps the limb clear of the window's taper)
    reach = max(int(np.ceil(max_shift)), FIND_MARGIN)
    y0, y1 = max(ys.min() - reach, 0), min(ys.max() + reach, h)
    x0, x1 = max(xs.min() - reach, 0), min(xs.max() + reach, w)
    a = im1_gray[y0:y1, x0:x1]
    b = im2_gray[y0:y1, x0:x1]

    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, window)

    if response < min_response or abs(dx) > max_shift or abs(dy) > max_shift:
        print(f"Image alignment failure: shift ({dx:.1f}, {dy:.1f}) response {response:.2f}")
        return None
    return dx, dy


def find_shift_whole(im1, im2, max_shift, min_response):
    """find_shift over the whole of both frames (BGR, the same size) rather than round im1's brightest part, with the
    peak: (dx, dy, response), or None when the response is under min_response or the shift past max_shift. For a
    frame whose brightest part is a sliver (a bright ringlet or a limb's glow on a ring tile), where find_shift's crop
    matched noise (195RI HIPHASEC001 W1752967654_1: a 0.74 peak over the whole overlap, 0.02 round its brightest part)."""
    a = cv2.cvtColor(im1, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(im2, cv2.COLOR_BGR2GRAY).astype(np.float32)
    (dx, dy), response = cv2.phaseCorrelate(a, b, cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F))
    if response < min_response or abs(dx) > max_shift or abs(dy) > max_shift:
        return None
    return dx, dy, response


FIND_MARGIN = 100   # px: the least margin round the target that find_shift correlates over (a 12 px margin put the limb
                    # under the window's taper and biased a small search by half a pixel)
DARK_SHARE = 0.02   # of the frame: a reference lit over less than this is a black scene (find_shift)


"""
Offset of im2 from im1 matched on point sources (stars, specks of moons), for a star field or a black sky where
phase correlation and the lit area's centroid fail (N1807503852_1: SKY, no SPICE target, a centroid 35 px off).
The points of each frame (star_points) vote for every offset between a point of one and a point of the other
within max_shift; the offset most pairs agree on (STAR_BIN px), by at least STAR_LEAST pairs and STAR_SHARE of
the fewer points, wins, refined to the mean of those pairs. Only on frames lit over at most STAR_DARK. Hot pixels are taken out first (a 3 x 3 median), as
they sit still and would vote for no shift. returns (dx, dy) or None
"""
STAR_MOST = 150     # brightest points kept per frame
STAR_SIGMA = 6.0    # a point stands this many noise sigmas over what is round it
STAR_LEAST = 5      # pairs agreeing on the offset, at least
STAR_SHARE = 0.3    # ... and this share of the fewer points
STAR_BIN = 2.0      # px
STAR_DARK = 0.1     # of the frame: the most a star field may be lit (lit_share)


def lit_share(im):
    """The share of the frame lit over a fifth of its brightest above its sky (its 5th percentile), 3 px blurred as
    find_shift sees a target, after a 3 x 3 median so hot pixels don't set the brightest"""
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    blurred = cv2.GaussianBlur(cv2.medianBlur(np.ascontiguousarray(gray).astype(np.float32), 3), (0, 0), 3)
    blurred -= np.percentile(blurred, 5)
    top = float(blurred.max())
    return float((blurred > 0.2 * top).mean()) if top > 0 else 0.0


def star_points(im):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    gray = cv2.medianBlur(gray.astype(np.float32), 3)
    detail = gray - cv2.medianBlur(np.clip(gray, 0, 255).astype(np.uint8), 15).astype(np.float32)
    sigma = 1.4826 * np.median(np.abs(detail - np.median(detail))) + 1e-3
    peak = (detail == cv2.dilate(detail, np.ones((5, 5), np.uint8))) & (detail > STAR_SIGMA * sigma)
    peak[:4] = peak[-4:] = False
    peak[:, :4] = peak[:, -4:] = False
    ys, xs = np.nonzero(peak)
    if len(ys) > STAR_MOST:
        keep = np.argsort(detail[ys, xs])[-STAR_MOST:]
        ys, xs = ys[keep], xs[keep]
    pts = []
    for y, x in zip(ys, xs):
        w = np.clip(detail[y - 2:y + 3, x - 2:x + 3], 0, None)
        if w.sum() <= 0:
            continue
        gy, gx = np.mgrid[-2:3, -2:3]
        pts.append((x + (w * gx).sum() / w.sum(), y + (w * gy).sum() / w.sum()))
    return np.array(pts, np.float32).reshape(-1, 2)


def star_shift(im1, im2, max_shift=100):
    # stars are seen only on a black sky: a frame lit over more than STAR_DARK (a planet, rings, a moon filling it,
    # an empty sky stretched into grey noise) has no stars to match, only texture that votes for a false offset
    if lit_share(im1) > STAR_DARK or lit_share(im2) > STAR_DARK:
        return None
    p1, p2 = star_points(im1), star_points(im2)
    if len(p1) < STAR_LEAST or len(p2) < STAR_LEAST:
        return None
    d = (p2[None, :, :] - p1[:, None, :]).reshape(-1, 2)
    d = d[(np.abs(d[:, 0]) <= max_shift) & (np.abs(d[:, 1]) <= max_shift)]
    if len(d) == 0:
        return None
    cells = np.floor(d / STAR_BIN).astype(np.int64)
    keys, counts = np.unique(cells[:, 0] * 100003 + cells[:, 1], return_counts=True)
    best = keys[np.argmax(counts)]
    cx, cy = (best + 50001) // 100003, best - ((best + 50001) // 100003) * 100003
    centre = (np.array([cx, cy]) + 0.5) * STAR_BIN
    near = d[np.abs(d - centre).max(axis=1) <= STAR_BIN]
    if len(near) < max(STAR_LEAST, STAR_SHARE * min(len(p1), len(p2))):
        return None
    dx, dy = np.median(near, axis=0)
    near = d[np.hypot(d[:, 0] - dx, d[:, 1] - dy) <= 1.0]
    dx, dy = near.mean(axis=0)
    return float(dx), float(dy)


def shift_image(im, dx, dy):
    h, w = im.shape[:2]
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    return cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)


"""
Aligns im2 to im1; returns im2 unchanged if no trustworthy match was found
"""
def shift_align(im1, im2, max_shift=100, min_response=0.3):
    shift = find_shift(im1, im2, max_shift, min_response)
    if shift is None:
        return im2
    return shift_image(im2, *shift)


"""
Combines repeat exposures of the same filter into one lower-noise frame.
frames = list of images of the same target, filter and exposure time; frames[0] is the reference
sigma = pixels further than this many noise sigmas from the others are rejected
        (cosmic rays, hot pixels)
max_shift = largest offset in pixels between repeats; repeats seconds apart barely move,
        so a bigger offset means a different view or a false match

Each frame is aligned to the reference and brightness-matched to it. Where the scene
itself changed between exposures (a moon moved), a frame is only used where it agrees
with the reference, so moving objects come from the reference alone instead of
leaving ghosts. Frames that cannot be aligned are left out.
masks = optional valid-pixel mask per frame (label.valid_mask): pixels a frame lost in downlink
        (truncated lines, zeros in the file) don't go into the stack, so a repeat that has them
        fills the reference's gap and a damaged repeat leaves no streak in a clean reference
returns the stacked frame in the same format as the input (8-bit, 3 channel gray), and with
masks also the mask of pixels valid in any frame that went in
"""
"""
Per pixel median of the frames in stack where agrees is True (count = how many per pixel, at
least one), the same as np.nanmedian with the others set to NaN. A sort of the few frames is
several times quicker than nanmedian, which goes through masked arrays.
"""
def agreeing_median(stack, agrees, count):
    ordered = _sorted(np.where(agrees, stack, np.inf))
    low = np.take_along_axis(ordered, ((count - 1) // 2)[None], 0)[0]
    high = np.take_along_axis(ordered, (count // 2)[None], 0)[0]
    return (low + high) / 2


# up to this many frames _sorted sorts them with minimum and maximum passes over whole frames: numpy's sort down
# axis 0 sorts each pixel's few values on its own (~70 ms a 1024 px stack of 2 to 6 frames, the passes 4 to 24 ms)
SORT_PASSES = 8


"""
np.sort(values, axis=0) of a stack of a few frames: each frame sunk in turn into the sorted ones before it, which puts
the same values in the same order (NaN, which numpy sorts last, goes to numpy's sort)
"""
def _sorted(values):
    if len(values) > SORT_PASSES or np.isnan(values).any():
        return np.sort(values, axis=0)
    out = list(values)
    for i in range(1, len(out)):
        for j in range(i, 0, -1):
            out[j - 1], out[j] = np.minimum(out[j - 1], out[j]), np.maximum(out[j - 1], out[j])
    return np.stack(out)


# a display level at or above this is clipped (a saturated star, a blown limb): it doesn't show how bright the scene is
CLIPPED = 250
# how far round a clipped pixel the change test also looks away: a star's wing beyond its clipped top, shifted a
# pixel, and up and down its column, where the charge of a full pixel bleeds (by a different amount in each exposure)
CLIP_MARGIN = np.ones((41, 7), np.uint8)
# ... where a pixel differs from the reference's by more than this many times the frames' pixel noise, it is a change
CLIP_SIGMA = 4.0
# a clipped patch is a star when less than this share of the margin round it is lit (above a quarter of CLIPPED): a
# blown spot on a moon has the moon round it, whose edge moving between repeats is a change like any other (a margin
# under Enceladus showed as a grey box, N1710205762_3)
CLIP_STAR = 0.5


"""
Where the change test looks at each pixel on its own (stack_frames): CLIP_MARGIN round each clipped patch of clipped
(uint8) that is a star (CLIP_STAR: mostly dark round it in gray).
"""
def _stars(clipped, gray):
    count, parts, stats, _ = cv2.connectedComponentsWithStats(clipped, connectivity=8)
    out = np.zeros(clipped.shape, bool)
    my, mx = CLIP_MARGIN.shape[0] // 2, CLIP_MARGIN.shape[1] // 2
    h, w = clipped.shape
    for i in range(1, count):
        x, y, bw, bh = stats[i, :4]
        y0, y1, x0, x1 = max(y - my, 0), min(y + bh + my, h), max(x - mx, 0), min(x + bw + mx, w)
        near = cv2.dilate((parts[y0:y1, x0:x1] == i).astype(np.uint8), CLIP_MARGIN) > 0
        if (gray[y0:y1, x0:x1][near] > CLIPPED / 4).mean() < CLIP_STAR:
            out[y0:y1, x0:x1] |= near
    return out


def stack_frames(frames, sigma=3.0, max_shift=20, masks=None):
    if masks is not None and all(np.array_equal(m, masks[0]) for m in masks[1:]):
        # nothing lost, or every frame lost the same pixels (a summed frame's edge column): no frame can fill another,
        # so the plain stack below, byte for byte
        return stack_frames(frames, sigma, max_shift), masks[0]
    lost = masks is not None
    if len(frames) == 1:
        # nothing to stack it with (most frames have no repeat): the frame as it is, as below
        return (frames[0], masks[0]) if lost else frames[0]
    ref = frames[0]
    ref_valid = masks[0] if lost else None
    # shifts are found on the frames with their lost pixels filled, so a gap's edge doesn't pull the match
    ref_match = fill_invalid(ref, ref_valid) if lost else ref
    ref_gray = cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY).astype(np.float32)
    blurred = cv2.GaussianBlur(ref_gray, (0,0), 3)
    target = blurred > 0.1 * blurred.max()
    unclipped = target & (ref_gray < CLIPPED)

    stack = [ref_gray]
    agrees = [ref_valid if lost else np.ones(ref_gray.shape, bool)]
    for i, frame in enumerate(frames[1:], 1):
        if frame.shape != ref.shape:
            continue
        if lost:
            # shifted with its lost pixels filled, so their zeros don't bleed into the valid ones beside them
            frame = fill_invalid(frame, masks[i])
        shift = find_shift(ref_match, frame, max_shift)
        if shift is None:
            continue
        gray = cv2.cvtColor(shift_image(frame, *shift),cv2.COLOR_BGR2GRAY).astype(np.float32)
        if lost:
            valid = shift_image(masks[i].astype(np.float32), *shift) > 0.99
            both = ref_valid & valid
            matched = unclipped & both
        else:
            matched = unclipped
        if matched.sum() > 100:
            # match brightness to the reference; a gain alone keeps black sky black
            gain = (gray[matched] * ref_gray[matched]).sum() / max((gray[matched] ** 2).sum(), 1)
            gray = gain * gray
        # mark where the scene changed: differences that survive smoothing are structure, not noise
        # (noise is measured over the whole frame, since a moving moon can fill much of the target)
        diff = gray - ref_gray
        if lost:
            # where either frame lost the pixel there is nothing to compare: not a change
            diff[~both] = 0
        # nor where either frame is clipped, and just round it: a saturated star's flat top sits a fraction of a pixel
        # elsewhere in each repeat, which reads as a change the size of the star and left a box of the reference
        # alone round every bright star (W1601346192_1); a real change (a moving moon) is far larger than the margin
        clipped = _stars(((gray >= CLIPPED) | (ref_gray >= CLIPPED)).astype(np.uint8), ref_gray)
        # (most repeats have no clipped star: then nothing below is judged pixel by pixel)
        stars = clipped.any()
        if stars:
            pixel_diff = diff.copy()
            diff[clipped] = 0
        smooth_diff = cv2.GaussianBlur(diff, (0,0), 2)
        level = np.median(smooth_diff)
        smooth_diff = np.abs(smooth_diff - level)
        noise = 1.4826 * np.median(smooth_diff)
        changed = (smooth_diff > max(5 * noise, 3)).astype(np.uint8)
        # drop specks (cosmic rays, hot pixels are handled per pixel below), then pad what is left
        changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((7,7), np.uint8))
        changed = cv2.dilate(changed, np.ones((15,15), np.uint8)) > 0
        # round a clipped star each pixel is judged on its own, by the same test with no specks dropped and no
        # padding, or by its own difference: a repeat's bleed down the columns (a vertical spike averaged in,
        # W1601346192_1), the star's edge a fraction of a pixel off and a limb's glow that differs (a grey box
        # under Enceladus, N1710205762_3) are the reference's alone, the sky between them every frame's (no box)
        if stars:
            near = cv2.GaussianBlur(pixel_diff, (0, 0), 2)
            spread = np.abs(pixel_diff - np.median(pixel_diff))
            pixel_noise = 1.4826 * float(np.median(spread[both] if lost else spread))
            changed |= clipped & ((np.abs(near - level) > max(5 * noise, 3))
                                  | (np.abs(pixel_diff) > max(CLIP_SIGMA * pixel_noise, 3)))
        stack.append(gray)
        # where the reference lost the pixel nothing was compared (diff 0 there): a change padded in from beside it
        # says nothing about this frame's pixel, which is then the only picture there is; left out, it left a
        # hole along the edge of every block the reference lost, filled as a flat grey dash (N1800422096_8)
        agrees.append((~changed | ~ref_valid) & valid if lost else ~changed)

    if len(stack) == 1:
        return (ref, ref_valid) if lost else ref
    stack = np.array(stack)
    agrees = np.array(agrees)

    # reject single-pixel outliers among the frames that agree with the reference
    count = agrees.sum(axis=0)
    if lost:
        # a pixel no frame has: any value, so the sort below has one; it stays the reference's and invalid
        count = np.maximum(count, 1)
    median = agreeing_median(stack, agrees, count)
    resid = np.abs(stack - median)
    noise = 1.4826 * np.median(resid[:, target][agrees[:, target]] if target.any() else resid) + 1
    keep = agrees & (resid <= sigma * noise)
    # with two frames an outlier can't be voted out; keep the darker value,
    # since cosmic rays and hot pixels only ever add light
    pair = (count == 2) & (keep.sum(axis=0) < 2)
    out = (stack * keep).sum(axis=0) / np.maximum(keep.sum(axis=0), 1)
    out = np.where(pair, np.where(agrees, stack, np.inf).min(axis=0), out)
    out = np.where(keep.any(axis=0) | pair, out, ref_gray)

    out = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    return (out, agrees.any(axis=0)) if lost else out
        
        
def seqAlign(im):
    global last
    if last is None:
        last = im
        return im
    try:
        
        out = imgAlign(last,im)
        last = out
        return out
    except:
        return
    
    
def match_hist(im1, im2):
    # scikit-image is only needed here and in scale_brightness, which the frame server never calls, so it is loaded
    # when they are (45 MB and half a second less for every server, with matplotlib in bootleg_autonav)
    from skimage.exposure import match_histograms
    return match_histograms(im2, im1)


def find_edges(gray_img):
    height, width = gray_img.shape
    gray_img = 255 - gray_img
    gray_img[gray_img > 100] = 255
    gray_img[gray_img <= 100] = 0
    black_padding = np.zeros((50, width))
    gray_img = np.vstack((black_padding, gray_img))
    kernel = np.ones((30, 30), np.uint8)
    closing = cv2.morphologyEx(gray_img, cv2.MORPH_CLOSE, kernel)
    edges = cv2.Canny(closing, 100, 200)
    
    return edges
    
    
def imgAlign(im1, im2, mosaic):
    mosaic = True
    try:
        # Convert images to grayscale
        im1_gray = cv2.cvtColor(im1,cv2.COLOR_BGR2GRAY)
        im2_gray = cv2.cvtColor(im2,cv2.COLOR_BGR2GRAY)
        #warp_mode = cv2.MOTION_HOMOGRAPHY
    
        if mosaic:
            warp_mode = cv2.MOTION_HOMOGRAPHY
            im1_gray = find_edges(im1_gray)
            im2_gray = find_edges(im2_gray)
            
            """
            im1_gray = cv2.GaussianBlur(im1_gray, (3,3), 0)
            im2_gray = cv2.GaussianBlur(im2_gray, (3,3), 0)
    
            im1_gray = cv2.Canny(image=im1_gray, threshold1=200, threshold2=200)
            im2_gray = cv2.Canny(image=im2_gray, threshold1=200, threshold2=200)
            
            """      
        # Find size of image1
        sz = im1.shape

    # Define the motion model
  

    # Define 2x3 or 3x3 matrices and initialize the matrix to identity
        if warp_mode == cv2.MOTION_HOMOGRAPHY :
            warp_matrix = np.eye(3, 3, dtype=np.float32)
        else :
            warp_matrix = np.eye(2, 3, dtype=np.float32)

    # Specify the number of iterations.
        number_of_iterations = 2000;

    # Specify the threshold of the increment
    # in the correlation coefficient between two iterations
        termination_eps = 0.1;

    # Define termination criteria
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, number_of_iterations,  termination_eps)

    # Run the ECC algorithm. The results are stored in warp_matrix.
        (cc, warp_matrix) = cv2.findTransformECC (im1_gray,im2_gray,warp_matrix, warp_mode, criteria)

        if warp_mode == cv2.MOTION_HOMOGRAPHY :
            # Use warpPerspective for Homography
            im2_aligned = cv2.warpPerspective (im2, warp_matrix, (sz[1],sz[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
        else :
            # Use warpAffine for Translation, Euclidean and Affine
            im2_aligned = cv2.warpAffine(im2, warp_matrix, (sz[1],sz[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP);

        return im2_aligned
    
    except:
        return im2
    
def calc_brightness(image, sigma=4):
        mask = np.ones_like(image[:, :], dtype=bool)
    
        if sigma is not None:
            mean = np.mean(image[:, :])
            std = np.std(image[:, :])
            dist = np.abs(image[:, :] - mean) / std
            mask[dist > sigma] = False

        return np.mean(image[mask])
    
def scale_brightness(image, scale):
        from skimage import img_as_ubyte, img_as_uint, img_as_float

        adjusted_image = scale * img_as_float(image)
        adjusted_image[adjusted_image >= 1.0] = 1.0
    
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=UserWarning)
            if image.dtype == np.dtype('uint8'):
                adjusted_image = img_as_ubyte(adjusted_image)
            elif image.dtype == np.dtype('uint16'):
                adjusted_image = img_as_uint(adjusted_image)

        return adjusted_image

class img_deflicker:
    
    def __init__(self):
        self.mean = []


    def compute_avg(self):
        avg = 0
        for i in range(0,len(self.mean)):
            avg = avg + self.mean[i]
           
        avg = avg / len(self.mean)    
        print("AVERAGE:::: ")
        print(avg)
        return avg
            
    
    def rolling_avg_deflicker(self, image, rolling_avg=10):
        
        if len(self.mean) >= rolling_avg:
            self.mean.pop(0)
            brightness = calc_brightness(image)
            self.mean.append(brightness)
            
            scale = self.compute_avg() / brightness
            
            return scale_brightness(image,scale)
        
        if len(self.mean) < rolling_avg:
            self.mean.append(calc_brightness(image))
            return image
    
    



def image_stats(image):
    # Compute the mean and standard deviation of each channel
    (l, a, b) = cv2.split(image)
    (l_mean, l_std) = (l.mean(), l.std())
    (a_mean, a_std) = (a.mean(), a.std())
    (b_mean, b_std) = (b.mean(), b.std())

    # return the color statistics
    return (l_mean, l_std, a_mean, a_std, b_mean, b_std)


def transfer_with_alpha(source, target):
    alpha = cv2.split(source)[3]
    output = match_hist(source, target)
    
    output = cv2.cvtColor(output, cv2.COLOR_RGB2RGBA)
    output[:, :, 3] = alpha
    return output
























# This function will perform color transfer from one input image (source)
# onto another input image (destination)
def color_transfer(source, target, clip=True, preserve_paper=False):
	"""
	Transfers the color distribution from the source to the target
	image using the mean and standard deviations of the L*a*b*
	color space.
	This implementation is (loosely) based on to the "Color Transfer
	between Images" paper by Reinhard et al., 2001.
	Parameters:
	-------
	source: NumPy array
		OpenCV image in BGR color space (the source image)
	target: NumPy array
		OpenCV image in BGR color space (the target image)
	clip: Should components of L*a*b* image be scaled by np.clip before 
		converting back to BGR color space?
		If False then components will be min-max scaled appropriately.
		Clipping will keep target image brightness truer to the input.
		Scaling will adjust image brightness to avoid washed out portions
		in the resulting color transfer that can be caused by clipping.
	preserve_paper: Should color transfer strictly follow methodology
		layed out in original paper? The method does not always produce
		aesthetically pleasing results.
		If False then L*a*b* components will scaled using the reciprocal of
		the scaling factor proposed in the paper.  This method seems to produce
		more consistently aesthetically pleasing results 
	Returns:
	-------
	transfer: NumPy array
		OpenCV image (w, h, 3) NumPy array (uint8)
	"""
	# convert the images from the RGB to L*ab* color space, being
	# sure to utilizing the floating point data type (note: OpenCV
	# expects floats to be 32-bit, so use that instead of 64-bit)
 
	source = cv2.cvtColor(source, cv2.COLOR_BGR2LAB).astype("float32")
	target = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype("float32")

	# compute color statistics for the source and target images
	(lMeanSrc, lStdSrc, aMeanSrc, aStdSrc, bMeanSrc, bStdSrc) = image_stats(source)
	(lMeanTar, lStdTar, aMeanTar, aStdTar, bMeanTar, bStdTar) = image_stats(target)

	# subtract the means from the target image
	(l, a, b) = cv2.split(target)
	l -= lMeanTar
	a -= aMeanTar
	b -= bMeanTar

	if preserve_paper:
		# scale by the standard deviations using paper proposed factor
		l = (lStdTar / lStdSrc) * l
		a = (aStdTar / aStdSrc) * a
		b = (bStdTar / bStdSrc) * b
	else:
		# scale by the standard deviations using reciprocal of paper proposed factor
		l = (lStdSrc / lStdTar) * l
		a = (aStdSrc / aStdTar) * a
		b = (bStdSrc / bStdTar) * b

	# add in the source mean
	l += lMeanSrc
	a += aMeanSrc
	b += bMeanSrc

	# clip/scale the pixel intensities to [0, 255] if they fall
	# outside this range
	l = _scale_array(l, clip=clip)
	a = _scale_array(a, clip=clip)
	b = _scale_array(b, clip=clip)

	# merge the channels together and convert back to the RGB color
	# space, being sure to utilize the 8-bit unsigned integer data
	# type
	transfer = cv2.merge([l, a, b])
	transfer = cv2.cvtColor(transfer.astype("uint8"), cv2.COLOR_LAB2BGR)
	
	# return the color transferred image
	return transfer

def image_stats(image):
	"""
	Parameters:
	-------
	image: NumPy array
		OpenCV image in L*a*b* color space
	Returns:
	-------
	Tuple of mean and standard deviations for the L*, a*, and b*
	channels, respectively
	"""
	# compute the mean and standard deviation of each channel
	(l, a, b) = cv2.split(image)
	(lMean, lStd) = (l.mean(), l.std())
	(aMean, aStd) = (a.mean(), a.std())
	(bMean, bStd) = (b.mean(), b.std())

	# return the color statistics
	return (lMean, lStd, aMean, aStd, bMean, bStd)

def _min_max_scale(arr, new_range=(0, 255)):
	"""
	Perform min-max scaling to a NumPy array
	Parameters:
	-------
	arr: NumPy array to be scaled to [new_min, new_max] range
	new_range: tuple of form (min, max) specifying range of
		transformed array
	Returns:
	-------
	NumPy array that has been scaled to be in
	[new_range[0], new_range[1]] range
	"""
	# get array's current min and max
	mn = arr.min()
	mx = arr.max()

	# check if scaling needs to be done to be in new_range
	if mn < new_range[0] or mx > new_range[1]:
		# perform min-max scaling
		scaled = (new_range[1] - new_range[0]) * (arr - mn) / (mx - mn) + new_range[0]
	else:
		# return array if already in range
		scaled = arr

	return scaled

def _scale_array(arr, clip=True):
	"""
	Trim NumPy array values to be in [0, 255] range with option of
	clipping or scaling.
	Parameters:
	-------
	arr: array to be trimmed to [0, 255] range
	clip: should array be scaled by np.clip? if False then input
		array will be min-max scaled to range
		[max([arr.min(), 0]), min([arr.max(), 255])]
	Returns:
	-------
	NumPy array that has been scaled to be in [0, 255] range
	"""
	if clip:
		scaled = np.clip(arr, 0, 255)
	else:
		scale_range = (max([arr.min(), 0]), min([arr.max(), 255]))
		scaled = _min_max_scale(arr, new_range=scale_range)

	return scaled






























