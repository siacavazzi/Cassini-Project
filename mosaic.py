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


buffer_size = 5     # number of frames kept in the rolling mosaic (including the newest)
feather_px = 64     # width in pixels of the soft edge where a frame blends into the frames below
min_overlap = 2000  # overlapping pixels (at 1/4 scale) needed before two frames are brightness matched
max_gain = 2.0      # older frames are never brightened or darkened by more than this factor
calibrated_gain = 1.1  # the same for frames already on one calibrated scale (only small errors left)
calibrated_overlap = 100  # min_overlap for those: a tight gain and a median offset need few pixels
max_offset = 6.0    # 8 bit levels; a bigger step is light scattered across the frame (a gradient),
                    # which one offset can't take out, and chained over a mosaic shifts its colours
offset_ramp = 16.0  # 8 bit levels over which an offset fades in from black (see composite)
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
mosaic in one window).
"""
def compose(window, reproject=None, calibrated=False, pin=-1):
    if reproject is None:
        reproject = reproject_surface
    frames = [np.asarray(entry[0]) for entry in window]
    newest = window[-1]
    if reproject and newest[2] is not None:
        for i, entry in enumerate(window[:-1]):
            if (entry[2] is not None and entry[1]["target"] == newest[1]["target"]
                    and newest[1]["et"] - entry[1]["et"] <= max_reproject_age):
                frames[i] = rp.warp_to_newest((frames[i],) + tuple(entry[1:]), newest)

    if not calibrated:
        return composite(frames, match_gains(frames, pin=pin))
    gains = match_gains(frames, calibrated_gain, pin, calibrated_overlap)
    return composite(frames, gains, match_offsets(frames, gains, pin, calibrated_overlap))


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
Works out a brightness gain per frame and color channel so the frames agree where they
overlap. The newest frame (or the frame pin) keeps its brightness and the others are matched
to it, directly or through other frames they overlap (pin None: all are matched to each other,
held near a gain of 1 by the pull below). Frames that overlap nothing keep a gain
of 1, and so do frames whose overlap has fewer than overlap pixels (at 1/4 scale, min_overlap by
default). Gains stay within 1 / limit and limit (max_gain by default).

Least squares over every overlapping pair, as in Brown & Lowe's panorama gain compensation:
    sum over pairs of N_ij * (g_i * mean_i - g_j * mean_j)^2 + small pull of every gain toward 1
returns array of shape (frames, 3)
"""
def match_gains(frames, limit=None, pin=-1, overlap=None):
    n = len(frames)
    gains = np.ones((n, 3))
    if n < 2:
        return gains

    # work at 1/4 scale, only on pixels that are fully inside a frame (not its soft edge)
    small = [f[::4, ::4] for f in frames]
    inside = [s[..., 3] == 255 for s in small]

    sig_n = 10.0   # expected noise in a mean brightness (8 bit levels)
    sig_g = 1.0    # how far a gain may wander from 1 without overlaps pinning it down
    for c in range(3):
        A = np.zeros((n, n))
        b = np.zeros(n)
        for i in range(n):
            for j in range(i + 1, n):
                ov = inside[i] & inside[j]
                N = int(ov.sum())
                if N < (overlap or min_overlap):
                    continue
                mi = small[i][..., c][ov].mean()
                mj = small[j][..., c][ov].mean()
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

    limit = limit or max_gain
    return np.clip(gains, 1 / limit, limit)


"""
An offset per frame and color channel (8 bit levels, added after its gain, at most max_offset) so
frames that are on one brightness scale also agree on the level of the sky: a calibrated frame
keeps a little of the camera's bias and of the light scattered in the optics, which changes from
frame to frame and shows as a step at every seam of a faint background. The pinned frame keeps an offset of 0
(pin None: the offsets average about 0); the others are matched to it through their overlaps, by least squares on the median difference
over each overlap where both are above black (stars and cosmic rays don't move a median). Frames that overlap nothing (fewer
than overlap pixels, as match_gains) keep 0.
returns array of shape (frames, 3)
"""
def match_offsets(frames, gains, pin=-1, overlap=None):
    n = len(frames)
    offsets = np.zeros((n, 3))
    if n < 2:
        return offsets
    small = [f[::4, ::4] for f in frames]
    inside = [s[..., 3] == 255 for s in small]
    for c in range(3):
        A = np.eye(n) * 1e-3   # small pull toward 0 for frames without overlaps
        b = np.zeros(n)
        for i in range(n):
            for j in range(i + 1, n):
                ov = inside[i] & inside[j]
                N = int(ov.sum())
                if N < (overlap or min_overlap):
                    continue
                # only where both frames are above black: a sky clipped to 0 hides how far it is off
                lit = ov & (small[i][..., c] > 2) & (small[j][..., c] > 2)
                N = int(lit.sum())
                if N < (overlap or min_overlap):
                    continue
                # offset_i - offset_j should make up the median difference j - i
                d = np.median(small[j][..., c][lit] * gains[j, c] - small[i][..., c][lit] * gains[i, c])
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
    return np.clip(offsets, -max_offset, max_offset)


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
"""
def composite(frames, gains, offsets=None):
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
        color = color * gain.astype(np.float32)
        if offset.any():
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
