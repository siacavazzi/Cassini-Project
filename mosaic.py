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
(defaults to reproject_surface).
"""
def compose(window, reproject=None):
    if reproject is None:
        reproject = reproject_surface
    frames = [np.asarray(entry[0]) for entry in window]
    newest = window[-1]
    if reproject and newest[2] is not None:
        for i, entry in enumerate(window[:-1]):
            if (entry[2] is not None and entry[1]["target"] == newest[1]["target"]
                    and newest[1]["et"] - entry[1]["et"] <= max_reproject_age):
                frames[i] = rp.warp_to_newest((frames[i],) + tuple(entry[1:]), newest)

    gains = match_gains(frames)
    return composite(frames, gains)


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
Works out a brightness gain per frame and color channel so the frames agree where they
overlap. The newest frame keeps its brightness and the others are matched to it, directly
or through other frames they overlap. Frames that overlap nothing keep a gain of 1.

Least squares over every overlapping pair, as in Brown & Lowe's panorama gain compensation:
    sum over pairs of N_ij * (g_i * mean_i - g_j * mean_j)^2 + small pull of every gain toward 1
returns array of shape (frames, 3)
"""
def match_gains(frames):
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
                if N < min_overlap:
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
        A[-1, :] = 0
        A[-1, -1] = 1
        b[-1] = 1
        gains[:, c] = np.linalg.solve(A, b)

    return np.clip(gains, 1 / max_gain, max_gain)


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
"""
def composite(frames, gains):
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
    for info, gain in zip(infos, gains):
        if info is None:
            continue
        box, color, own, feathered = info
        sl = (slice(box[0] - y0, box[1] - y0), slice(box[2] - x0, box[3] - x0))
        below = acc_alpha[sl]
        a = feathered * below + own * (1 - below)
        color = color * gain.astype(np.float32)
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
