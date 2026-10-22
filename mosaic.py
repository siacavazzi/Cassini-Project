# -*- coding: utf-8 -*-
"""
Rolling mosaic for video output.

Every new frame is drawn on top of the last few frames so a mosaic builds up over the
video. Before drawing, the older frames are brightness matched to the newest frame
(using the pixels where they overlap) and each frame's edge is feathered into whatever
is already underneath, so panel seams don't show.
"""
import numpy as np
import cv2
import reproject as rp
import calibration


buffer_size = 5     # number of frames kept in the rolling mosaic (including the newest)
feather_px = 64     # width in pixels of the soft edge where a frame blends into the frames below
min_overlap = 2000  # overlapping pixels (at 1/4 scale) needed before two frames are brightness matched
max_gain = 2.0      # older frames are never brightened or darkened by more than this factor
calibrated_gain = 1.1  # the same for frames already on one calibrated scale (only small errors left)
calibrated_overlap = 100  # min_overlap for those: a tight gain and a median offset need few pixels
max_offset = 6.0    # 8 bit levels; a bigger step is light scattered across the frame (a gradient),
                    # which one offset can't take out, and chained over a mosaic shifts its colours
offset_ramp = 16.0  # 8 bit levels over which an offset fades in from black (see composite)
max_linear_offset = 0.01  # the same for offsets solved on linear values (gamma given): a share of white;
                          # the sky's real offset left after the bias is 0.1-1.3% of white
anchor_pull = 0.05  # anchored gains: how hard every log gain is pulled toward 0, against a tile's overlaps
                    # (weights scaled so the best measured overlap counts 1)
toward_pull = 0.3   # ... and toward another filter's seams (seams' toward): a filter departs from them only
                    # where its own overlaps clearly say so
reproject_surface = False  # line up the target's surface between frames (see compose)
max_reproject_age = 20 * 60  # seconds; older frames are only centered (warping across big rotations tears)

buffer = []


"""
Empties the rolling mosaic (call at the start of every new sequence)
"""
def reset():
    buffer.clear()
    _prepared.clear()


"""
What a frame needs to take part in surface reprojection, from the label it was centered
with: (geometry, view, placement), or Nones. Works it out right after auto_center, while
that frame's SPICE kernels are loaded. Picklable, so worker processes can send it back.
"""
def frame_info(lbl):
    geometry = getattr(lbl, "geometry", None)
    placement = getattr(lbl, "placement", None)
    view = None
    if geometry is not None and placement is not None:
        view = rp.spice_view(geometry)
    return geometry, view, placement


"""
The mosaic of a window of frames, oldest first. Each entry is (RGBA numpy array, geometry,
view, placement); the last three may be None. reproject = line up the target's surface
(defaults to reproject_surface). calibrated = the frames are already on one brightness scale
(calibration.load_channels with a fixed scale): gains then only correct small errors, and an
offset per frame takes out what is left of the sky level (bias, stray light). pin = the frame
whose brightness the others are matched to (the newest by default); None pins none, so the
corrections only pull the frames together and keep their overall level (a whole calibrated
mosaic in one window). gamma = how the frames' levels encode linear brightness (calibration.encode):
the corrections are then solved and applied on linear values. corrections = (gains, offsets) worked
out beforehand (seams), used instead of solving them here; offsets are on linear values when gamma
is given.
"""
def compose(window, reproject=None, calibrated=False, pin=-1, gamma=None, corrections=None):
    if reproject is None:
        reproject = reproject_surface
    frames = [np.asarray(entry[0]) for entry in window]
    newest = window[-1]
    if reproject and newest[2] is not None:
        for i, entry in enumerate(window[:-1]):
            if (entry[2] is not None and entry[1]["target"] == newest[1]["target"]
                    and newest[1]["et"] - entry[1]["et"] <= max_reproject_age):
                frames[i] = rp.warp_to_newest((frames[i],) + tuple(entry[1:]), newest)

    if corrections is not None:
        return composite(frames, *corrections, gamma=gamma)
    if not calibrated:
        return composite(frames, match_gains(frames, pin=pin))
    return composite(frames, *seams(frames, pin, gamma), gamma=gamma)


"""
The gains and offsets compose uses for frames already on one calibrated scale: (gains, offsets), each
of shape (frames, 3). gamma as compose; with pin None and gamma given, the gains are anchored (the mean
log gain held at 0, see match_gains), so they keep the mosaic's overall level instead of shrinking.
toward = (gains, offsets) the corrections are pulled toward instead of 1 and 0 (anchored only): another
filter's seams at the same pointings, so this filter keeps their overall level and takes them where its
own overlaps say nothing.
"""
def seams(frames, pin=-1, gamma=None, toward=None):
    anchored = pin is None and gamma is not None
    toward = toward if anchored else None
    gains = match_gains(frames, calibrated_gain, pin, calibrated_overlap, gamma, anchored,
                        None if toward is None else toward[0])
    return gains, match_offsets(frames, gains, pin, calibrated_overlap, gamma, None if toward is None else toward[1])


"""
The frames' 1/4 scale copies as overlaps gives them, as linear brightness 0-255 (gamma as compose), with
the alpha left as it is.
"""
def linear(small, gamma):
    out = []
    for s in small:
        f = s.astype(np.float32)
        f[..., :3] = calibration.decode(f[..., :3] / 255, gamma) * 255
        out.append(f)
    return out


"""
Adds a frame to the rolling buffer and returns the mosaic of the frames in it
frame = RGBA numpy array (uint8), all frames the same size
lbl = the label the frame was centered with (optional, for surface reprojection)
"""
def add_frame(frame, lbl=None):
    geometry, view, placement = frame_info(lbl) if reproject_surface else (None, None, None)
    buffer.append((np.asarray(frame), geometry, view, placement))
    if len(buffer) > buffer_size:
        buffer.pop(0)
    return compose(buffer)


"""
Which earlier pictures a picture is drawn over: the rule for telling a real mosaic (the camera
stepping across a body, a tile at a time) from frames that only follow each other.

pictures = dicts in time order with
    t       seconds
    cam     "N" or "W"
    obs     OBSERVATION_ID
    filter  anything that compares equal for the same filter (or the same kind of colour set)
    x, y    find_target's shift that centres the body, full resolution pixels (None without SPICE)
    z       distance to the body in km (None without SPICE)
Returns, for each picture, the indices of its panels, oldest first (at most buffer_size - 1).

A picture joins earlier ones of the same camera, observation and filter when the pointing moved
by at least min_step of a frame since the panel it would cover (a smaller move replaces that panel:
a stare, a movie, drift or a repeat), it overlaps at least one of them, it is within max_gap of the
last one and the distance to the body is within max_zoom of each. Different filters are never
drawn over each other: a Titan mosaic takes MT3, CB3, MT1 and UV3 at every tile, so the frames
right before a picture are the other filters at the same place.
"""
frame_px = 1024     # full resolution frame, both cameras
min_step = 0.15     # of a frame: a smaller move is the same tile
max_gap = 1800      # seconds between a panel and the next
max_zoom = 0.10     # largest change in distance to the body between panels


def panels(pictures):
    tiles = {}   # (cam, obs, filter) -> [(index, x, y, z, t)], oldest first
    out = []
    for n, p in enumerate(pictures):
        key = (p["cam"], p["obs"], p["filter"])
        if p.get("x") is None or p.get("z") is None:
            tiles.pop(key, None)
            out.append([])
            continue
        x, y, z, t = p["x"], p["y"], p["z"], p["t"]
        kept = tiles.get(key, [])
        if kept and t - kept[-1][4] > max_gap:
            kept = []
        kept = [k for k in kept if abs(k[3] / z - 1) <= max_zoom
                and max(abs(k[1] - x), abs(k[2] - y)) >= min_step * frame_px]
        if kept and not any(abs(k[1] - x) < frame_px and abs(k[2] - y) < frame_px for k in kept):
            kept = []   # no overlap: the camera went somewhere else, start again
        kept = kept[-(buffer_size - 1):] if buffer_size > 1 else []
        out.append([k[0] for k in kept])
        tiles[key] = kept + [(n, x, y, z, t)]
    return out


"""
The pairs of frames that overlap, for match_gains and match_offsets: at 1/4 scale, only pixels fully inside
both frames (not their soft edge), at least overlap pixels (min_overlap by default). Returns the frames at 1/4
scale and [(i, j, slices of the box both frames cover, overlap mask in that box, its pixel count)].
Each pair is looked at only inside the box where both frames have pixels, and pairs whose boxes miss
each other are skipped, so a mosaic of many tiles (most pairs far apart) is quick; the pixels used are
the same as over the whole frame.
"""
def overlaps(frames, overlap=None):
    small = [f[::4, ::4] for f in frames]
    inside = [s[..., 3] == 255 for s in small]
    boxes = []
    for m in inside:
        rows, cols = np.flatnonzero(m.any(1)), np.flatnonzero(m.any(0))
        boxes.append((rows[0], rows[-1] + 1, cols[0], cols[-1] + 1) if len(rows) else None)
    pairs = []
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            a, b = boxes[i], boxes[j]
            if a is None or b is None:
                continue
            y0, y1, x0, x1 = max(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3])
            if y1 <= y0 or x1 <= x0:
                continue
            sl = (slice(y0, y1), slice(x0, x1))
            ov = inside[i][sl] & inside[j][sl]
            N = int(ov.sum())
            if N >= (overlap or min_overlap):
                pairs.append((i, j, sl, ov, N))
    return small, pairs


"""
Works out a brightness gain per frame and color channel so the frames agree where they
overlap. The newest frame (or the frame pin) keeps its brightness and the others are matched
to it, directly or through other frames they overlap (pin None: all are matched to each other,
held near a gain of 1 by the pull below). Frames that overlap nothing keep a gain
of 1, and so do frames whose overlap has fewer than overlap pixels (at 1/4 scale, min_overlap by
default). Gains stay within 1 / limit and limit (max_gain by default).

Least squares over every overlapping pair, as in Brown & Lowe's panorama gain compensation:
    sum over pairs of N_ij * (g_i * mean_i - g_j * mean_j)^2 + small pull of every gain toward 1
gamma = solve on linear values (compose). anchored = solve the log gains instead, with pin None: every
pair asks log g_i - log g_j = log(mean_j / mean_i), weighted by how well the pair's means are measured,
and every log gain is pulled toward 0 (anchor_pull), which holds their mean at 0. Without that the
pull above is too weak for a whole mosaic: the solve shrinks every gain until the limit stops it.
toward = gains (frames, 3) to pull toward instead of 1 (anchored), whose mean log the result keeps.
returns array of shape (frames, 3)
"""
def match_gains(frames, limit=None, pin=-1, overlap=None, gamma=None, anchored=False, toward=None):
    n = len(frames)
    gains = np.ones((n, 3))
    if n < 2:
        return gains

    small, pairs = overlaps(frames, overlap)
    if gamma is not None:
        small = linear(small, gamma)
    limit = limit or max_gain
    if anchored:
        return np.clip(_anchored_gains(small, pairs, n, toward), 1 / limit, limit)

    sig_n = 10.0   # expected noise in a mean brightness (8 bit levels)
    sig_g = 1.0    # how far a gain may wander from 1 without overlaps pinning it down
    for c in range(3):
        A = np.zeros((n, n))
        b = np.zeros(n)
        for i, j, sl, ov, N in pairs:
            mi = small[i][sl][..., c][ov].mean()
            mj = small[j][sl][..., c][ov].mean()
            A[i, i] += N * mi * mi / sig_n ** 2
            A[j, j] += N * mj * mj / sig_n ** 2
            A[i, j] -= N * mi * mj / sig_n ** 2
            A[j, i] -= N * mi * mj / sig_n ** 2
        # scale the prior with the data so it stays a gentle pull
        prior = max(A.diagonal().max(), 1.0) * 1e-4 / sig_g ** 2
        A += np.eye(n) * prior
        b += prior
        # pin the newest frame at a gain of 1
        if pin is not None:
            A[pin, :] = 0
            A[pin, pin] = 1
            b[pin] = 1
        gains[:, c] = np.linalg.solve(A, b)

    return np.clip(gains, 1 / limit, limit)


def _anchored_gains(small, pairs, n, toward=None):
    sig_n = 10.0   # expected noise in a mean brightness (levels)
    gains = np.ones((n, 3)) if toward is None else np.array(toward, dtype=float)
    for c in range(3):
        rows = []
        for i, j, sl, ov, N in pairs:
            mi = small[i][sl][..., c][ov].mean()
            mj = small[j][sl][..., c][ov].mean()
            if min(mi, mj) < 1:
                continue   # black in one of them: the ratio says nothing
            # the variance of log(mj / mi) is about sig_n^2 (1 / mi^2 + 1 / mj^2) / N
            rows.append((i, j, N / (sig_n ** 2 * (1 / mi ** 2 + 1 / mj ** 2)), np.log(mj / mi)))
        if not rows:
            continue
        top = max(w for *_, w, _ in rows)
        pull = anchor_pull if toward is None else toward_pull
        A = np.eye(n) * pull
        b = pull * np.log(gains[:, c])
        for i, j, w, d in rows:
            w /= top
            A[i, i] += w
            A[j, j] += w
            A[i, j] -= w
            A[j, i] -= w
            b[i] += w * d
            b[j] -= w * d
        gains[:, c] = np.exp(np.linalg.solve(A, b))
    return gains


"""
An offset per frame and color channel (8 bit levels, added after its gain, at most max_offset) so
frames that are on one brightness scale also agree on the level of the sky: a calibrated frame
keeps a little of the camera's bias and of the light scattered in the optics, which changes from
frame to frame and shows as a step at every seam of a faint background. The pinned frame keeps an offset of 0
(pin None: the offsets average about 0); the others are matched to it through their overlaps, by least squares on the median difference
over each overlap where both are above black (stars and cosmic rays don't move a median). Frames that overlap nothing (fewer
than overlap pixels, as match_gains) keep 0. gamma = solve on linear values (compose): the offsets are then a share of white,
at most max_linear_offset. toward = offsets (frames, 3) to pull toward instead of 0 (pin None).
returns array of shape (frames, 3)
"""
def match_offsets(frames, gains, pin=-1, overlap=None, gamma=None, toward=None):
    n = len(frames)
    offsets = np.zeros((n, 3))
    if n < 2:
        return offsets
    small, pairs = overlaps(frames, overlap)
    levels = small
    if gamma is not None:
        levels = [f / 255 for f in linear(small, gamma)]
    for c in range(3):
        A = np.eye(n) * 1e-3   # small pull toward 0 (or toward) for frames without overlaps
        b = np.zeros(n) if toward is None else 1e-3 * np.asarray(toward, dtype=float)[:, c]
        for i, j, sl, ov, N in pairs:
            si, sj = small[i][sl][..., c], small[j][sl][..., c]
            # only where both frames are above black: a sky clipped to 0 hides how far it is off
            lit = ov & (si > 2) & (sj > 2)
            N = int(lit.sum())
            if N < (overlap or min_overlap):
                continue
            si, sj = levels[i][sl][..., c], levels[j][sl][..., c]
            # offset_i - offset_j should make up the median difference j - i
            d = np.median(sj[lit] * gains[j, c] - si[lit] * gains[i, c])
            A[i, i] += N
            A[j, j] += N
            A[i, j] -= N
            A[j, i] -= N
            b[i] += N * d
            b[j] -= N * d
        if pin is not None:
            A[pin, :] = 0
            A[pin, pin] = 1
            b[pin] = 0
        offsets[:, c] = np.linalg.solve(A, b)
    limit = max_offset if gamma is None else max_linear_offset
    return np.clip(offsets, -limit, limit)


"""
Soft edge for a frame: ramps from 0 at the edge of the frame's pixels to 1 at feather_px
inside, multiplied by the frame's own alpha
"""
def feather_alpha(alpha):
    valid = (alpha > 0).astype(np.uint8)
    dist = cv2.distanceTransform(valid, cv2.DIST_L2, 5)
    return np.minimum(dist * (1.0 / feather_px), 1.0) * (alpha * np.float32(1 / 255))


"""
Per frame work that doesn't change while the frame sits in the buffer: the box around its
pixels, its colors as floats, its alpha and its feathered alpha. Kept for the frames in
the buffer so each frame is only prepared once.
"""
_prepared = {}

def prepare(frame):
    cached = _prepared.get(id(frame))
    if cached is not None and cached[0] is frame:
        return cached[1]
    h, w = frame.shape[:2]
    ys, xs = np.nonzero(frame[::8, ::8, 3])
    if len(ys) == 0:
        info = None
    else:
        box = (max(ys.min() * 8 - 8, 0), min(ys.max() * 8 + 9, h),
               max(xs.min() * 8 - 8, 0), min(xs.max() * 8 + 9, w))
        f = frame[box[0]:box[1], box[2]:box[3]]
        info = (box, f[..., :3].astype(np.float32), f[..., 3] * np.float32(1 / 255), feather_alpha(f[..., 3]))
    _prepared[id(frame)] = (frame, info)
    return info


"""
Draws the frames oldest first, each over the ones before it. Where there is already
something underneath, a frame's edge fades in over feather_px; over empty background
the frame keeps its own alpha, so a lone frame looks the same as before.
Only the area the frames cover is worked on, then pasted into an empty canvas.
offsets = optional levels added to each frame after its gain (match_offsets)
gamma = the frames' levels encode linear brightness so (compose): gains and offsets (a share of white)
are applied to linear values, then encoded again
"""
def composite(frames, gains, offsets=None, gamma=None):
    if offsets is None:
        offsets = np.zeros((len(frames), 3))
    h, w = frames[0].shape[:2]
    infos = [prepare(frame) for frame in frames]
    keep = {id(frame) for frame in frames}
    for key in list(_prepared):
        if key not in keep:
            del _prepared[key]

    out = np.zeros((h, w, 4), np.uint8)
    used = [info[0] for info in infos if info is not None]
    if not used:
        return out
    y0, y1 = min(b[0] for b in used), max(b[1] for b in used)
    x0, x1 = min(b[2] for b in used), max(b[3] for b in used)

    rgb = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
    acc_alpha = np.zeros((y1 - y0, x1 - x0), np.float32)
    for info, gain, offset in zip(infos, gains, offsets):
        if info is None:
            continue
        box, color, own, feathered = info
        sl = (slice(box[0] - y0, box[1] - y0), slice(box[2] - x0, box[3] - x0))
        below = acc_alpha[sl]
        a = feathered * below + own * (1 - below)
        if gamma is not None:
            color = _corrected(color, gain, offset, gamma)
        else:
            color = color * gain.astype(np.float32)
        if gamma is None and offset.any():
            # in full from offset_ramp levels up, fading to none at black, so what is black stays
            # black (lifting it shows the compression blocks of a dark sky or night side)
            color += offset.astype(np.float32) * np.minimum(color * np.float32(1 / offset_ramp), 1)
        color -= rgb[sl]
        color *= a[..., None]
        rgb[sl] += color
        acc_alpha[sl] = a + below * (1 - a)

    # rgb was built over a black background; divide the alpha back out so the PNG's
    # colors are right wherever it is partly transparent
    rgb /= np.maximum(acc_alpha, 1e-6)[..., None]
    out[y0:y1, x0:x1, :3] = np.clip(rgb, 0, 255).round()
    out[y0:y1, x0:x1, 3] = (acc_alpha * 255).round()
    return out


def _corrected(color, gain, offset, gamma):
    """A frame's levels with its gain and offset applied on linear brightness; the offset fades in over
    offset_ramp levels from black (counted on the levels, as without gamma), so what is black stays black
    while a faint sky just above it gets its whole offset. Through lookup tables, since
    the levels are whole numbers 0-255 and the result is only kept to 8 bits."""
    if np.all(gain == 1) and not np.any(offset):
        return color.copy()
    to_linear, edges = _tables(gamma)
    lin = to_linear[color.astype(np.uint8)]
    lin *= gain.astype(np.float32)
    if np.any(offset):
        lin += offset.astype(np.float32) * np.minimum(color * np.float32(1 / offset_ramp), 1)
    # the level whose span of linear brightness lin falls in: encoding rounded to 8 bits
    return np.searchsorted(edges, lin).astype(np.float32)


_luts = {}


def _tables(gamma):
    """(linear brightness of each level 0-255, the linear brightness halfway between each level and the next)"""
    if gamma not in _luts:
        to_linear = calibration.decode(np.arange(256) / 255, gamma).astype(np.float32)
        edges = calibration.decode((np.arange(255) + 0.5) / 255, gamma).astype(np.float32)
        _luts[gamma] = to_linear, edges
    return _luts[gamma]
