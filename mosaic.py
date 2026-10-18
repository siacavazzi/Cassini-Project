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


buffer_size = 5     # number of frames kept in the rolling mosaic (including the newest)
feather_px = 64     # width in pixels of the soft edge where a frame blends into the frames below
min_overlap = 2000  # overlapping pixels (at 1/4 scale) needed before two frames are brightness matched
max_gain = 2.0      # older frames are never brightened or darkened by more than this factor

buffer = []


"""
Empties the rolling mosaic (call at the start of every new sequence)
"""
def reset():
    buffer.clear()


"""
Adds a frame and returns the mosaic of the frames in the buffer
frame = RGBA numpy array (uint8), all frames the same size
"""
def add_frame(frame):
    buffer.append(np.asarray(frame))
    if len(buffer) > buffer_size:
        buffer.pop(0)
    gains = match_gains(buffer)
    return composite(buffer, gains)


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
Draws the frames oldest first, each over the ones before it. Where there is already
something underneath, a frame's edge fades in over feather_px; over empty background
the frame keeps its own alpha, so a lone frame looks the same as before.
Only the area the frames cover is worked on, then pasted into an empty canvas.
"""
def composite(frames, gains):
    h, w = frames[0].shape[:2]
    boxes = []
    for frame in frames:
        ys, xs = np.nonzero(frame[::8, ::8, 3])
        if len(ys) == 0:
            boxes.append(None)
            continue
        boxes.append((max(ys.min() * 8 - 8, 0), min(ys.max() * 8 + 9, h),
                      max(xs.min() * 8 - 8, 0), min(xs.max() * 8 + 9, w)))
    used = [b for b in boxes if b is not None]
    out = np.zeros((h, w, 4), np.uint8)
    if not used:
        return out
    y0, y1 = min(b[0] for b in used), max(b[1] for b in used)
    x0, x1 = min(b[2] for b in used), max(b[3] for b in used)

    rgb = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
    acc_alpha = np.zeros((y1 - y0, x1 - x0), np.float32)
    for frame, gain, box in zip(frames, gains, boxes):
        if box is None:
            continue
        f = frame[box[0]:box[1], box[2]:box[3]]
        sl = (slice(box[0] - y0, box[1] - y0), slice(box[2] - x0, box[3] - x0))
        own = f[..., 3] * np.float32(1 / 255)
        below = acc_alpha[sl]
        a = feather_alpha(f[..., 3]) * below + own * (1 - below)
        color = f[..., :3] * gain.astype(np.float32)
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
