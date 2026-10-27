# -*- coding: utf-8 -*-
"""
Rolling mosaic for video output.

Every new frame is drawn on top of the last few frames so a mosaic builds up over the
video. Before drawing, the older frames are brightness matched to the newest frame
(using the pixels where they overlap) and each frame's edge is feathered into whatever
is already underneath, so panel seams don't show.
"""
import math
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
anchor_pull = 0.05  # anchored gains: how hard every log gain is pulled toward 0, against a tile's overlaps
                    # (weights scaled so the best measured overlap counts 1)
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
out beforehand (seams), used instead of solving them here; offsets are always on the levels.
level = seam leveling where the level step is on (composite); False draws the frames as the gains leave them.
under = the frame that is a picture drawn so far (composite).
kept, decided = what the blend step decided for each frame (its leveling and its seam) kept, or given (composite).
"""
def compose(window, reproject=None, calibrated=False, pin=-1, gamma=None, corrections=None, level=True, under=None,
            kept=None, decided=None):
    if reproject is None:
        reproject = reproject_surface
    frames = [np.asarray(entry[0]) for entry in window]
    newest = window[-1]
    if reproject and newest[2] is not None:
        for i, entry in enumerate(window[:-1]):
            if (entry[2] is not None and entry[1]["target"] == newest[1]["target"]
                    and newest[1]["et"] - entry[1]["et"] <= max_reproject_age):
                frames[i] = rp.warp_to_newest((frames[i],) + tuple(entry[1:]), newest)

    more = {"level": level, "pin": pin, "under": under, "kept": kept, "decided": decided}
    if corrections is not None:
        return composite(frames, *corrections, gamma=gamma, **more)
    if not calibrated:
        return composite(frames, match_gains(frames, pin=pin), **more)
    return composite(frames, *seams(frames, pin, gamma), gamma=gamma, **more)


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
    # the offsets stay on the levels, each filter its own, as without gamma: on linear values a sky offset of a
    # fraction of a percent of white is tens of levels at the black end of a steep curve, and tints the sky
    return gains, match_offsets(frames, gains, pin, calibrated_overlap)


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
        A = np.eye(n) * anchor_pull
        b = anchor_pull * np.log(gains[:, c])
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
than overlap pixels, as match_gains) keep 0. toward = offsets (frames, 3) to pull toward instead of 0 (pin None).
returns array of shape (frames, 3)
"""
def match_offsets(frames, gains, pin=-1, overlap=None, toward=None):
    n = len(frames)
    offsets = np.zeros((n, 3))
    if n < 2:
        return offsets
    small, pairs = overlaps(frames, overlap)
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
The soft edge every frame is made with (mask.png, color_image.get_mask): its alpha from a straight edge inward,
one value a pixel of a 1024 px frame, and where it reaches 250 of 255 (EDGE_AT), which _edge_width looks for.
"""
_edge = None
EDGE_AT = 250


def edge_profile():
    global _edge
    if _edge is None:
        import os
        from PIL import Image
        mask = np.asarray(Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mask.png")).convert("L"))
        row = mask[mask.shape[0] // 2].astype(np.float32) / 255
        _edge = (row[:np.argmax(row >= 1) + 1], int(np.argmax(row >= EDGE_AT / 255)))
    return _edge


"""
How wide a frame's own soft edge is on this canvas, in pixels from its edge to where its alpha reaches EDGE_AT:
the farthest distance from the edge at which still at least a quarter as many pixels are under EDGE_AT as right at the
edge (along a straight edge every distance up to the width has about the same number; the corners, where two soft edges
cross, add a few farther in). A frame drawn at another size than 1024 px has its soft edge at that size. 0 for a
frame with a hard edge.
"""
def _edge_width(alpha, dist):
    soft = (alpha > 0) & (alpha < EDGE_AT)
    if not soft.any():
        return 0.0
    counts = np.bincount(np.rint(dist[soft]).astype(np.int64))
    if len(counts) < 2 or counts[1] == 0:
        return 0.0
    return float(np.flatnonzero(counts >= counts[1] / 4).max())


"""
The blend step's per frame parts (prepare): (its colours, where the frame has picture, its weight in the blend, the
width of its own soft edge, where it has picture with its outline's slant (_support)); drawn = a picture drawn so far
(composite's under), not a tile. Where its alpha is under PICTURE_AT, a little below its soft edge's first value
(mask.png's 46 of 255), a pixel's colour is not the frame's: turning it north up (linear, on its colour and alpha
apart) mixes its edge with the black round it, and resizing it on alpha this low rounds its colour far off (a tile
turned 20 degrees and drawn at twice its size had colours at 0 up to 5 px in from its first nonzero alpha, and
specks in its faint corners; none where its alpha reaches 40). Those pixels take the colour of the nearest one that
is the frame's, so a weight there draws the frame's colour. The
weight ramps from 0 at the edge of the frame's picture to 1 at feather_px inside, on where it has picture only: the
soft edge it was made with (mask.png) is the mosaic's outer edge, not a weight, so where two frames meet their
colours blend and nothing between them is left part transparent.
"""
RIM = 0
PICTURE_AT = 40


def _colors(frame):
    """A frame's colours as floats for the blend step: (h, w, 1) when its three bands are the same (every tile of a
    filter's mosaic, and the picture so far it is grown on, is grey), so the blend works on one band, not three."""
    rgb = frame[..., :3]
    if (rgb[..., 0] == rgb[..., 1]).all() and (rgb[..., 1] == rgb[..., 2]).all():
        return rgb[..., :1].astype(np.float32)
    return rgb.astype(np.float32)


def _blend_parts(frame, drawn=False):
    alpha = frame[..., 3]
    color = _colors(frame)
    if drawn:
        # a picture drawn so far (composite's under): all of it is picture, its colours as drawn
        if alpha.min() >= EDGE_AT:
            # (opaque all over, inside the mosaic: picture everywhere at its full weight, no edge of its own here)
            whole = np.ones(alpha.shape, np.float32)
            return color, whole, whole, 0.0, whole
        dist = _inside((alpha > 0).astype(np.uint8), alpha >= EDGE_AT)
        # its weight from TRUST_DEPTH in: along its outer edge it holds its tiles' rims (_rim) where they were alone
        ramp = (dist - max(2.0, feather_px * TRUST_DEPTH)) * (1.0 / feather_px)
        return (color, (alpha > 0).astype(np.float32), np.clip(ramp, 0, 1).astype(np.float32), _edge_width(alpha, dist),
                _support(alpha, dist))
    off = (alpha > 0) & (alpha < PICTURE_AT)
    if off.any() and (alpha >= PICTURE_AT).any():
        # each such pixel's nearest that is the frame's (the labels number those in raster order)
        _, nearest = cv2.distanceTransformWithLabels((alpha < PICTURE_AT).astype(np.uint8), cv2.DIST_L2, 5,
                                                     labelType=cv2.DIST_LABEL_PIXEL)
        good = np.flatnonzero(alpha.ravel() >= PICTURE_AT)
        flat = color.reshape(-1, color.shape[2])
        flat[np.flatnonzero(off.ravel())] = flat[good[nearest[off] - 1]]
    on = alpha >= EDGE_AT
    dist = _inside((alpha > 0).astype(np.uint8), on)
    has = dist > RIM
    # the weight ramps in from the edge of what is the frame's own picture (not its rim, _rim), so a frame's dark rim
    # never goes into what is below it
    rim = _rim(color, has, dist)
    inside = dist - (RIM + 1) if rim is None else _inside((has & ~rim).astype(np.uint8), on)
    return (color, has.astype(np.float32), np.clip((inside - TRUST_INSET) * (1.0 / feather_px), 0, 1).astype(np.float32),
            _edge_width(alpha, dist), _support(alpha, dist))


def _support(alpha, dist):
    """Where a frame has picture (alpha > 0), its outermost pixels each as much as their alpha is of what it would be
    were they whole: of the most alpha next to them, as much less as the soft edge's first value is than its second
    (edge_profile; mask.png's corners are fainter all along, so it is next to them that says): how much of the pixel
    the frame covers where its edge is slanted, turned north up (linear: an edge pixel half covered has half its
    alpha). The mosaic's outer edge is worked out from it (_outer_edge), so a slanted edge is as smooth as the frames'
    own, not a stair (a slanted limb was dotted)."""
    profile = edge_profile()[0]
    out = (alpha > 0).astype(np.float32)
    rim = dist <= 1.5
    if rim.any():
        whole = cv2.dilate(alpha, np.ones((3, 3), np.uint8))[rim].astype(np.float32) * np.float32(profile[0] / profile[1])
        out[rim] = np.minimum(alpha[rim] / np.maximum(whole, 1), 1)
    return out


"""
Where a frame's picture is not its own (_blend_parts): its rim. A real tile's outermost pixels are often not its
picture though its alpha says they are: a stack of repeat exposures (color_image.load_aligned) moved into line leaves
a strip only some of the frames cover, darker by their share (a WAC movie's tiles of Saturn's hexagon, 2013, had a
pixel of black and four at half their brightness all along an edge), and turning and resizing a tile mixes its edge
with the black round it. Drawn over another tile each such pixel weighs little, but where the same place is drawn
again and again (a mosaic movie's laps, a pass's repeated pointings) the little adds up to a dark band, and the
pyramids carry it farther in. So a pixel within TRUST_DEPTH of feather_px of the frame's edge that is under TRUST_DARK as
bright as the frame just inside it (where that is brighter than TRUST_LIT, not the sky), and that reaches the edge
through such pixels (a rim, not a dark crater just inside the edge), is not the frame's: the frame is drawn there
only where nothing is below it, as it is, and its weight starts TRUST_INSET pixels inside the rest. The frame just
inside: its mean round each pixel past TRUST_DEPTH, worked out at a quarter of the size. The frame's outermost
pixel is its rim anyway. None for a frame without one.
"""
TRUST_DEPTH = 1 / 4
TRUST_DARK = 0.9
TRUST_LIT = 24
TRUST_INSET = 1


def _rim(color, has, dist):
    depth = max(2.0, feather_px * TRUST_DEPTH)
    band = has & (dist <= depth)
    deep = has & (dist > depth)
    if not band.any() or not deep.any():
        return None
    lum = color.min(axis=2)   # the darkest band, so a rim missing one colour is found too
    h, w = lum.shape
    q = 4
    # (in whole quarters: a frame's box starts on a multiple of 8 of its pixels, prepare)
    fit = lambda v: np.pad(v, ((0, -h % q), (0, -w % q)))
    small = (-(-w // q), -(-h // q))
    sigma = max(1.0, depth / q / 2)
    wd = cv2.GaussianBlur(cv2.resize(fit(deep.astype(np.float32)), small, interpolation=cv2.INTER_AREA), (0, 0), sigma)
    wl = cv2.GaussianBlur(cv2.resize(fit(lum * deep), small, interpolation=cv2.INTER_AREA), (0, 0), sigma)
    ref = cv2.resize(wl / np.maximum(wd, 1e-3), (small[0] * q, small[1] * q), interpolation=cv2.INTER_LINEAR)[:h, :w]
    bad = band & (lum < ref * TRUST_DARK) & (ref > TRUST_LIT)
    if not bad.any():
        return None
    # what reaches the frame's edge through such pixels
    edge = has & (dist <= RIM + 1)
    _, lab = cv2.connectedComponents((bad | edge).astype(np.uint8), connectivity=8)
    rim = np.zeros(lab.max() + 1, bool)
    rim[lab[edge]] = True
    rim[0] = False
    return rim[lab]


"""
Multi-band blending (Burt and Adelson, "A multiresolution spline", 1983; Brown and Lowe's panoramas, OpenCV's
stitcher, Hugin's enblend): each frame's picture is split into a Laplacian pyramid, bands of detail a level each, sizes
doubling up to feather_px * BAND_TOP, and what is coarser than all of them; and every band is blended across the
seam over a width in proportion to its own size. The coarse part over feather_px (the weight, as before), so the
brightness changes slowly from one frame to the next; each band of detail over a few of its own sizes (the seam
taken down the pyramid with it), so detail that is not in quite the same place in both (a pixel of pointing, a cloud
that moved, the terminator seen minutes apart) changes over at the seam in a few pixels instead of showing doubled
over the whole feather. Every band changes over at the same place, the seam, where the coarse weight is a half or,
when the frames' detail differs, where they agree best (_seam_cut). The pyramids are over each picture only (each
level the picture's mean round it, the empty canvas past its edge left out), so no edge darkens a band.
"""
BAND_TOP = 1 / 8


def _levels_of():
    return max(1, round(math.log2(max(feather_px * BAND_TOP, 1))))


"""
The pixels the blend step lays its pyramids and blurs on: the frames' pixel (0, 0) and every GRID-th one from it
(each pyramid starts on one, a blur worked out smaller has its pixels on them). Frames that are parts of one bigger
picture starting on the same grid (mosaic_native's blocks) so get the same pixels where they hold the same, whatever
part each is (for pyramids up to 6 levels: feather_px up to 512 or so).
"""
GRID = 64


def _pyramid(x, n):
    out = [x]
    for _ in range(n):
        out.append(cv2.pyrDown(out[-1]))
    return out


def _per_pixel(color):
    """How a weight (h, w) multiplies colours like color: as it is for one band (h, w), with an axis added for three."""
    return (lambda w: w) if color.ndim == 2 else (lambda w: w[..., None])


def _normed(color, has, n):
    """color's Gaussian pyramid over where has (1 inside the picture, 0 past it), n levels down: each level the
    weighted mean of the picture round each pixel, so the empty canvas past its edge does not darken it (the first
    level is color itself, as good as it inside the picture, the only place it is used)."""
    px = _per_pixel(color)
    cs, ws = _pyramid(color * px(has), n), _pyramid(has, n)
    return [color] + [c / px(np.maximum(w, 1e-3)) for c, w in zip(cs[1:], ws[1:])]


def _bands_blended(color, has, under, cover, seam, a, n):
    """color (has its picture) drawn over under (cover) in n bands: each band of detail with the seam (1 where color
    comes in) taken down to its level, the coarse part with the weight a. The arrays are the area worked on, colours
    (h, w) for one band or (h, w, 3). Only the difference of the two goes through the bands: under + each band of it
    times its weight."""
    px = _per_pixel(color)
    up = lambda x, like: cv2.pyrUp(x, dstsize=(like.shape[1], like.shape[0]))
    nf, nb = _normed(color, has, n), _normed(under, cover, n)
    diff = [f - b for f, b in zip(nf, nb)]
    either = np.maximum(has, cover)
    ms, es = _pyramid(seam * either, n), _pyramid(either, n)
    # the bands of detail, each blended at its level, put back together
    out, coarse = np.zeros_like(diff[n]), diff[n]
    for k in range(n - 1, -1, -1):
        m = np.clip(ms[k] / np.maximum(es[k], 1e-3), 0, 1)
        band = diff[k] - up(diff[k + 1], diff[k])
        band *= px(m)
        band += up(out, diff[k])
        out = band
        coarse = up(coarse, diff[k])
    # and the coarse part, brought up to the full size, with the weight there: exactly 0 at the frame's edge and 1 at
    # the edge of what is below, however narrow the overlap
    coarse *= px(a)
    out += coarse
    out += under
    return out


def _inside(valid, on):
    """How far each pixel of valid (uint8, 1 inside) lies from its edge. The array's border is an edge only where the
    picture does not go on past it (on, bool: where it does): a frame the canvas cuts, or the mosaic a tile is grown
    over (obs_mosaic._over draws on the part of it round the tile only), goes on, at its full alpha; a frame whose own
    soft edge lies on the canvas's border ends there."""
    return cv2.distanceTransform(_past(valid, on, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]


def _past(a, on, m):
    """a with m pixels added round it: a again where it goes on past the border (on), else 0."""
    out = np.pad(a * on.astype(a.dtype), m, mode="edge")
    out[m:-m, m:-m] = a
    return out


"""
Per frame work that doesn't change while the frame sits in the buffer: the box around its
pixels, its colors as floats, its alpha and its feathered alpha. Kept for the frames in
the buffer so each frame is only prepared once.
"""
_prepared = {}

def prepare(frame, drawn=False):
    cached = _prepared.get(id(frame))
    if cached is not None and cached[0] is frame and cached[2] == drawn:
        return cached[1]
    h, w = frame.shape[:2]
    ys, xs = np.nonzero(frame[::8, ::8, 3])
    if len(ys) == 0:
        info = None
    else:
        box = (max(ys.min() * 8 - 8, 0), min(ys.max() * 8 + 9, h),
               max(xs.min() * 8 - 8, 0), min(xs.max() * 8 + 9, w))
        f = frame[box[0]:box[1], box[2]:box[3]]
        if calibration.step("blend"):
            color, has, ramp, width, support = _blend_parts(f, drawn)
            info = (box, color, f[..., 3] * np.float32(1 / 255), has, ramp, width, support)
        else:
            info = (box, f[..., :3].astype(np.float32), f[..., 3] * np.float32(1 / 255), feather_alpha(f[..., 3]))
    _prepared[id(frame)] = (frame, info, drawn)
    return info


"""
Draws the frames oldest first, each over the ones before it. Where there is already
something underneath, a frame's edge fades in over feather_px; over empty background
the frame keeps its own alpha, so a lone frame looks the same as before.
Only the area the frames cover is worked on, then pasted into an empty canvas.
offsets = optional levels added to each frame after its gain (match_offsets)
gamma = the frames' levels encode linear brightness so (compose): gains are applied to linear values,
then encoded again; offsets stay on the levels
level = seam leveling (_levels) where the level step is on; False draws the frames as their gains leave them;
pin = the frame whose leveling gain stays 1 (as compose's pin), None for none
under = the frame that is a picture drawn so far, not a tile (obs_mosaic's growing mosaics draw a tile over the part
of the picture round it): with the blend step its picture is its alpha as it is, its own soft edge kept, none of it
taken for a tile's edge (that took a few pixels off the picture's outer edge with every tile drawn near it)
kept = a list the blend step adds what it decided for each frame to (_blended: its leveling and its seam, None
for a frame it decided nothing for), so the same mosaic can be drawn again at another scale or in parts with them
(mosaic_native); decided = those decisions given, one per frame (_blended), used instead of working any out
"""
def composite(frames, gains, offsets=None, gamma=None, level=True, pin=None, under=None, kept=None, decided=None):
    if offsets is None:
        offsets = np.zeros((len(frames), 3))
    h, w = frames[0].shape[:2]
    under = None if under is None else range(len(frames))[under]
    infos = [prepare(frame, i == under) for i, frame in enumerate(frames)]
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

    if len(next(info for info in infos if info is not None)) == 7:
        _blended(out, infos, gains, offsets, gamma, (y0, y1, x0, x1), level and leveling(), pin, kept, decided)
        return out

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
            color = _corrected(color, gain, gamma)
        else:
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


_normal = None


def _outer_edge(support, cover, width, on):
    """The soft edge of the mosaic of frames covering cover (1 where a frame has picture; support: the same with their
    slanted edges, _support), frames whose own soft edge is width canvas pixels wide (_edge_width), past the array's
    border where on (_inside): along a straight stretch of its edge, the frames' own profile (edge_profile) at that
    width, from the edge of what all the frames cover, so it runs on unbroken where two frames meet; at a corner a
    little softer, as a frame's own corners are. How far inside the edge a pixel lies is read off support blurred (a
    Gaussian of half the width, worked out at a quarter of that size or less, which changes it by under 1%): along a
    straight edge the blur is the normal curve of that distance, and at a corner, where the blur sees less picture
    round it, it reads as nearer the edge. 1 everywhere (cover as it is) when no edge is near."""
    global _normal
    border = np.concatenate([on[0], on[-1], on[:, 0], on[:, -1]])
    if cover.min() > 0 and border.all():
        return cover.copy()
    if _normal is None:
        z = np.linspace(-6, 6, 4801)
        _normal = (z, (0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))).astype(np.float32))
    profile, at = edge_profile()
    sigma = width / 2
    # (worked out at a power of two smaller, on GRID: the array's pixel (0, 0) is one of its pixels)
    q = 1 << max(0, int(sigma // 4).bit_length() - 1)
    m = -(-int(math.ceil(3 * sigma)) // q) * q
    padded = _past(support, on, m)
    if q > 1:
        h, w = support.shape
        H, W = padded.shape
        padded = np.pad(padded, ((0, -H % q), (0, -W % q)), mode="edge")
        small = cv2.resize(padded, (padded.shape[1] // q, padded.shape[0] // q), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma / q, borderType=cv2.BORDER_CONSTANT)
        blur = cv2.resize(small, padded.shape[::-1], interpolation=cv2.INTER_LINEAR)[m:m + h, m:m + w]
    else:
        blur = cv2.GaussianBlur(padded, (0, 0), sigma, borderType=cv2.BORDER_CONSTANT)[m:-m, m:-m]
    # the profile at x canvas pixels from the edge (a frame's first pixel, its middle half a pixel in, has the
    # profile's first value; 0 at the edge itself), looked up in tables: by the blur (at a pixel whose middle lies x
    # inside a straight edge the blur is the normal curve at x / sigma), and by the distance to the nearest pixel
    # past the edge
    xp = np.concatenate([[-0.5], np.arange(len(profile))])
    fp = np.concatenate([[0.0], profile])
    at_x = lambda x: np.interp(x * (at / width) - 0.5, xp, fp, left=0, right=1)
    steps = 1 << 14
    by_blur = at_x(np.interp(np.linspace(0, 1, steps + 1), _normal[1], _normal[0]) * sigma).astype(np.float32)
    soft = by_blur[(np.clip(blur, 0, 1) * steps + 0.5).astype(np.int32)]
    # nor farther in than the pixel lies from the nearest edge: round a small gap inside the mosaic (where tiles do not
    # quite meet) the blur sees picture nearly everywhere, and the gap would get a hard edge
    far = len(profile) * width / at + 1
    by_dist = at_x(np.arange(int(far * 8) + 2) / 8 - 0.5).astype(np.float32)
    d = _inside((cover > 0).astype(np.uint8), on)
    soft = np.minimum(soft, by_dist[np.minimum(d * 8 + 0.5, len(by_dist) - 1).astype(np.int32)])
    return soft * cover


"""
Seam leveling, the level step (calibration.step("level"), Settings > Processing > Level mosaic seams; needs blend).
One gain per frame (match_gains) cannot make two frames agree all along their seam: the brightness of the same ground
changes across a frame with the light (the terminator, a hazy limb) and with the angle it was seen from, and frames
taken minutes apart see it differently, so a gain right at one end of a seam is wrong at the other. Each frame gets a
smooth gain over all of it instead, every frame's worked out together, the way ISIS's equalizer works out a mosaic's
gains from all its overlaps at once and its noseam and the gradient-domain blending of Perez et al. ("Poisson image
editing", 2003) and Microsoft's Image Composite Editor carry what is left smoothly across each picture. The gains are
the log of the gain in cells (LEVEL_CELL of feather_px) of the canvas: along a seam, the two frames' gains there are
to bring them to the same brightness, measured in the cell where the later frame fades in over the earlier (its
weight under 1: where one frame wholly covers another there is no seam to hide, and what they show there may differ
in earnest: a mosaic movie's place taken again an hour on) from the pixels where both are lit, agree within
LEVEL_MAX and change slowly (under LEVEL_EDGE over an eighth of feather_px: at the terminator, a limb or a crater's
rim a pixel of pointing is a big ratio that says nothing about the light); within a frame, every cell's gain is to
be its neighbours' (so the gain changes smoothly, never in a step); and every gain is held to 1 so that a seam's
correction fades over LEVEL_REACH into the frame (a screened membrane), which keeps each frame at its own level away
from its seams and the mosaic at its overall level. Least squares over all of it, each colour band on its own. pin =
a frame whose gain stays 1 (the mosaic a tile is grown over: what is drawn stays as drawn, and the new tile is
leveled to it along its edge, at its own level inside).
"""
LEVEL_CELL = 1 / 4    # of feather_px: the cells the gain is worked out in
LEVEL_MAX = 1.5       # the most a frame is brightened or darkened anywhere (and 1 / LEVEL_MAX)
LEVEL_LIT = 12        # levels: both pictures above this where their ratio is measured
LEVEL_FILL = 0.2      # of a cell: the share of its pixels measured for it to count
LEVEL_EDGE = 0.25     # the most a pixel's brightness (log) changes over an eighth of feather_px for it to be measured
LEVEL_STIFF = 1.0     # how much a cell's gain is held to its neighbours' against what it measures
LEVEL_REACH = 4       # of feather_px (half a frame): how far into a frame a seam's correction reaches before
                      # it has faded to a third, the frame back at its own (matched) gain past that


def leveling():
    return calibration.step("blend") and calibration.step("level")


DRAWING = 5   # bumped when the blend or level steps change how a mosaic is drawn


def drawing():
    """What a mosaic's cache name gets for how its tiles are drawn together: "" with the blend step off (drawn as
    before it, so the pictures made then keep their names), else "seams<DRAWING>-blend" or "...-blend-level"."""
    if not calibration.step("blend"):
        return ""
    return f"seams{DRAWING}-blend" + ("-level" if calibration.step("level") else "")


def _cells(a, c, oy, ox):
    """a (h, w[, channels]), whose first pixel lies at (oy, ox) of the area, summed over the area's c x c cells:
    (the sums, the cell of its first row and column)."""
    h, w = a.shape[:2]
    ty, tx = oy % c, ox % c
    H, W = -(-(h + ty) // c) * c, -(-(w + tx) // c) * c
    a = np.pad(a, ((ty, H - h - ty), (tx, W - w - tx)) + ((0, 0),) * (a.ndim - 2))
    return a.reshape(H // c, c, W // c, c, *a.shape[2:]).sum(axis=(1, 3)), (oy // c, ox // c)


def _levels(boxes, colors, hases, ramps, pin=None):
    """Seam leveling (above) of the frames (boxes in the area, colours as toned, where each has picture, their
    weights): a list of each frame's (log gains of its cells (rows, columns, 1 or 3), the cells' size, the area pixel
    the first cell's corner lies at (y, x)), or None for a frame that needs none; _field makes its gains."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    n = len(boxes)
    c = max(2, int(round(feather_px * LEVEL_CELL)))
    grey = all(col.shape[2] == 1 or (np.array_equal(col[::7, ::7, 0], col[::7, ::7, 1])
                                     and np.array_equal(col[::7, ::7, 0], col[::7, ::7, 2]))
               for col in colors if col is not None)
    ch = 1 if grey else 3
    # every frame's cells (its box's), numbered
    grids, first = [], 0
    for i, b in enumerate(boxes):
        if b is None or i == pin:
            grids.append(None)
            continue
        gy0, gx0 = b[0] // c, b[2] // c
        gh, gw = (b[1] - 1) // c - gy0 + 1, (b[3] - 1) // c - gx0 + 1
        grids.append((gy0, gx0, gh, gw, first))
        first += gh * gw
    if first == 0:
        return [None] * n
    rows, cols, vals = [], [], []
    rhs = np.zeros((first, ch))

    def add(r, k, v):
        rows.append(r); cols.append(k); vals.append(v)

    calm = {}

    def calm_of(i):
        # where frame i's brightness changes slowly (LEVEL_EDGE)
        if i not in calm:
            lum = np.log(np.maximum(cv2.GaussianBlur(colors[i].mean(axis=2), (0, 0), 1.0), 1))
            gx, gy = cv2.Sobel(lum, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(lum, cv2.CV_32F, 0, 1, ksize=3)
            calm[i] = np.hypot(gx, gy) * (feather_px / 64) < LEVEL_EDGE
        return calm[i]

    measured = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if a is None or b is None:
                continue
            y0, y1, x0, x1 = max(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3])
            if y1 <= y0 or x1 <= x0:
                continue
            si = (slice(y0 - a[0], y1 - a[0]), slice(x0 - a[2], x1 - a[2]))
            sj = (slice(y0 - b[0], y1 - b[0]), slice(x0 - b[2], x1 - b[2]))
            # the seam: where j, drawn over i, fades in over it
            seam = (hases[i][si] > 0) & (hases[j][sj] > 0) & (ramps[j][sj] < 1)
            if not seam.any():
                continue
            fi, fj = colors[i][si][..., :ch], colors[j][sj][..., :ch]
            lit = seam & (fi.min(axis=2) > LEVEL_LIT) & (fj.min(axis=2) > LEVEL_LIT) & calm_of(i)[si] & calm_of(j)[sj]
            if not lit.any():
                continue
            ratio = np.log(np.maximum(fj, 1)) - np.log(np.maximum(fi, 1))
            # a pixel the two do not agree on within LEVEL_MAX is not the light: the limb a pixel off, a moved cloud, a star
            ok = lit & (np.abs(ratio).max(axis=2) < math.log(LEVEL_MAX))
            cnt, (cy, cx) = _cells(ok.astype(np.float32), c, y0, x0)
            tot, _ = _cells(ratio * ok[..., None], c, y0, x0)
            for gy, gx in zip(*np.nonzero(cnt >= LEVEL_FILL * c * c)):
                w = float(cnt[gy, gx]) / (c * c)
                d = tot[gy, gx] / cnt[gy, gx]   # f_i - f_j should be this: frame i times e^f_i meets j times e^f_j
                Y, X = cy + gy, cx + gx
                ki = None if grids[i] is None else grids[i][4] + (Y - grids[i][0]) * grids[i][3] + (X - grids[i][1])
                kj = None if grids[j] is None else grids[j][4] + (Y - grids[j][0]) * grids[j][3] + (X - grids[j][1])
                if ki is not None:
                    add(ki, ki, w); rhs[ki] += w * d
                if kj is not None:
                    add(kj, kj, w); rhs[kj] -= w * d
                if ki is not None and kj is not None:
                    add(ki, kj, -w); add(kj, ki, -w)
                measured += w
    if measured == 0:
        return [None] * n
    # within each frame its neighbouring cells alike, and every cell held to 0 just so much that a correction fades
    # over LEVEL_REACH (a screened membrane): each frame keeps its own level away from its seams, so corrections do not
    # add up from frame to frame across a mosaic grown a tile at a time (and the whole mosaic keeps its level)
    pull = LEVEL_STIFF * (LEVEL_CELL / LEVEL_REACH) ** 2
    for g in grids:
        if g is None:
            continue
        gy0, gx0, gh, gw, k0 = g
        idx = k0 + np.arange(gh * gw).reshape(gh, gw)
        for p, q in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
            p, q = p.ravel(), q.ravel()
            rows.extend(p); cols.extend(p); vals.extend([LEVEL_STIFF] * len(p))
            rows.extend(q); cols.extend(q); vals.extend([LEVEL_STIFF] * len(p))
            rows.extend(p); cols.extend(q); vals.extend([-LEVEL_STIFF] * len(p))
            rows.extend(q); cols.extend(p); vals.extend([-LEVEL_STIFF] * len(p))
    rows.extend(range(first)); cols.extend(range(first)); vals.extend([pull] * first)
    A = coo_matrix((vals, (rows, cols)), shape=(first, first)).tocsc()
    f = np.asarray(spsolve(A, rhs)).reshape(first, ch)
    out = []
    for g in grids:
        if g is None:
            out.append(None)
            continue
        gy0, gx0, gh, gw, k0 = g
        grid = np.clip(f[k0:k0 + gh * gw].reshape(gh, gw, ch), -math.log(LEVEL_MAX), math.log(LEVEL_MAX))
        out.append((grid.astype(np.float32), c, gy0 * c, gx0 * c) if np.abs(grid).max() > 1e-4 else None)
    return out


def _field(level, box):
    """A frame's gains from its leveling (_levels) over box (y0, y1, x0, x1, in the pixels its first cell's corner
    is given in): each cell's gain at its middle, linear in between."""
    grid, c, oy, ox = level
    gh, gw, ch = grid.shape
    up = cv2.resize(grid, (gw * c, gh * c), interpolation=cv2.INTER_LINEAR).reshape(gh * c, gw * c, ch)
    ty, tx = box[0] - oy, box[2] - ox
    return np.exp(up[ty:ty + box[1] - box[0], tx:tx + box[3] - box[2]])


def _toned(color, gain, offset, gamma):
    """A frame's colours with its gain and offset applied, as composite does (color itself when they change nothing;
    one band when color is one band, its gain and offset the same in every band)."""
    if np.all(gain == 1) and not offset.any():
        return color
    if color.shape[2] == 1:
        gain, offset = gain[:1], offset[:1]
    if gamma is not None:
        color = _corrected(color, gain, gamma)
    else:
        color = color * gain.astype(np.float32)
    if offset.any():
        color += offset.astype(np.float32) * np.minimum(color * np.float32(1 / offset_ramp), 1)
    return color


def _blended(out, infos, gains, offsets, gamma, area, level, pin=None, kept=None, decided=None):
    """composite with the blend step on (calibration.step("blend"), Settings > Processing > Blend mosaic seams).
    The frames' soft edges (mask.png) no longer go into one another: drawn over each other they left the join part
    transparent wherever two frames overlap by less than their two soft edges, a darker line along every seam and a
    notch where a seam meets the mosaic's edge. Instead each frame is drawn over the frames below with a weight that
    ramps in from its own edge (_blend_parts), and the weight of what is below ramps in from its edges the same way,
    so a frame fades in past the edge of what is below and what is below fades out before its own edge: the colours
    meet smoothly from both sides whatever the overlap, and a newer frame still covers an older one where both are
    whole. In bands (multi-band blending, _bands_blended): the coarse part with that weight, each band of detail
    across the seam (_seam_cut) over a few of its own sizes. level: the frames leveled first (_levels; pin as there). Where
    any frame has picture the mosaic is opaque; the soft edge is kept along the mosaic's outer edge only, the same
    profile as each frame's (edge_profile) at the frames' width (_edge_width), from the edge of what all of them
    cover. Without overlaps (a lone frame) the picture is the frame as it is, its alpha included.
    What is decided for the whole of the frames (its leveling, solved over all of them, and each seam, cut through all
    of its overlap) changes with what of them is drawn. So a mosaic drawn in parts (mosaic_native's blocks) is
    drawn with what was decided for it whole: kept, a list, gets each frame's {"field": its leveling (_levels, at the
    frame's pixels), "cut": (where it comes in over its seam's area (_seam_cut), the frame's pixel that area starts
    at (y, x))}, or None; decided, one per frame, gives them back as (gains (h, w, 1 or 3) over a box of the frame's
    pixels (y0, y1, x0, x1), where it comes in over a box: 0 to 1, -1 for nothing said), functions of the box, either
    or the pair None, and nothing else is worked out. The pyramids and blurs are laid on GRID."""
    y0, y1, x0, x1 = area
    y0, x0 = y0 - y0 % GRID, x0 - x0 % GRID
    # one band when every frame is grey (each band the same, and so its gain and offset), else three
    same = lambda v: v is None or np.all(np.asarray(v) == np.asarray(v).flat[0])
    one = all(info is None or (info[1].shape[2] == 1 and same(gain) and same(offset))
              for info, gain, offset in zip(infos, gains, offsets))
    rgb = np.zeros((y1 - y0, x1 - x0) if one else (y1 - y0, x1 - x0, 3), np.float32)
    px = _per_pixel(rgb)
    cover = np.zeros((y1 - y0, x1 - x0), np.float32)   # 1 where a frame drawn so far has picture
    outline = np.zeros((y1 - y0, x1 - x0), np.float32) # the same with the frames' slanted edges (_support)
    weight = np.zeros((y1 - y0, x1 - x0), np.float32)  # what is drawn so far's own ramp, drawn over each other
    alpha = np.zeros((y1 - y0, x1 - x0), np.float32)   # the most of the frames' own alphas
    width = 0.0
    levels = _levels_of()
    margin = 4 << levels
    toned = [None if info is None else _toned(info[1] if one or info[1].shape[2] == 3 else np.repeat(info[1], 3, axis=2),
                                              gain, offset, gamma) for info, gain, offset in zip(infos, gains, offsets)]
    decisions = [None if info is None else {"field": None, "cut": None} for info in infos]
    if level and decided is not None:
        fields = [None if info is None or d is None or d[0] is None else d[0](info[0]) for info, d in zip(infos, decided)]
        toned = [t if fl is None else t * fl for t, fl in zip(toned, fields)]
    elif level and sum(info is not None for info in infos) > 1:
        boxes = [None if info is None else (info[0][0] - y0, info[0][1] - y0, info[0][2] - x0, info[0][3] - x0) for info in infos]
        found = _levels(boxes, toned, [None if info is None else (info[4] > 0).astype(np.float32) for info in infos],
                        [None if info is None else info[4] for info in infos],
                        None if pin is None else range(len(infos))[pin])
        toned = [t if lv is None else t * _field(lv, b) for t, lv, b in zip(toned, found, boxes)]
        for d, lv in zip(decisions, found):
            if lv is not None:
                d["field"] = (lv[0], lv[1], lv[2] + y0, lv[3] + x0)
    if one:
        toned = [None if t is None else t[..., 0] for t in toned]
    for i, (info, color) in enumerate(zip(infos, toned)):
        if info is None:
            continue
        box, _, own, has, ramp, w, support = info
        width = max(width, w)
        sl = (slice(box[0] - y0, box[1] - y0), slice(box[2] - x0, box[3] - x0))
        below, wb = cover[sl], weight[sl]
        a = np.where(below > 0, ramp / np.maximum(ramp + (1 - ramp) * wb, 1e-6), has)
        if (below * has).any():
            # the frame and what is below it in bands, worked out over a margin round the frame, so the pyramids near
            # its box's edge see what lies past it
            # (starting on a pixel the pyramid's coarsest level has, of the frames' own: GRID)
            ya, yb = max((sl[0].start - margin) >> levels << levels, 0), min(sl[0].stop + margin, y1 - y0)
            xa, xb = max((sl[1].start - margin) >> levels << levels, 0), min(sl[1].stop + margin, x1 - x0)
            inner = (slice(sl[0].start - ya, sl[0].stop - ya), slice(sl[1].start - xa, sl[1].stop - xa))
            under = rgb[sl]
            if decided is None:
                seam, cut = _seam_cut(a, has, below, color, under)
                if cut is not None:
                    decisions[i]["cut"] = (cut[0], cut[1] + box[0], cut[2] + box[2])
            else:
                given = decided[i] is not None and decided[i][1]
                seam = _seam_given(a, has, below, given(box) if given else None)
            pad = lambda v: np.pad(v, ((inner[0].start, yb - ya - inner[0].stop), (inner[1].start, xb - xa - inner[1].stop))
                                   + ((0, 0),) * (v.ndim - 2))
            mixed = _bands_blended(pad(color), pad((ramp > 0).astype(np.float32)), rgb[ya:yb, xa:xb], cover[ya:yb, xa:xb],
                                   pad(seam), pad(a),
                                   levels)[inner]
            # where only one of them has picture, that one as it is
            rgb[sl] = np.where(px(has > 0), np.where(px(below > 0), mixed, color), under)
        else:
            rgb[sl] += (color - rgb[sl]) * px(a)
        weight[sl] = ramp + wb * (1 - ramp)
        cover[sl] = np.maximum(below, has)
        alpha[sl] = np.maximum(alpha[sl], own * has)
        outline[sl] = np.maximum(outline[sl], support)
    if width > 0:
        # never more transparent than the most opaque frame there, so a frame's own corners and a lost line's gap keep
        # the edge they were made with
        alpha = np.maximum(alpha, _outer_edge(outline, cover, width, alpha >= EDGE_AT / 255))
    if kept is not None:
        kept.extend(decisions)
    rgb = np.clip(rgb, 0, 255).round()
    out[y0:y1, x0:x1, :3] = rgb[..., None] if one else rgb
    out[y0:y1, x0:x1, 3] = (alpha * 255).round()


def moved(decision, y, x):
    """A frame's decisions (_blended's kept) for the frame's pixels moved by (y, x): of a part of a bigger picture,
    for the whole of it."""
    if decision is None:
        return None
    field, cut = decision["field"], decision["cut"]
    return {"field": None if field is None else (field[0], field[1], field[2] + y, field[3] + x),
            "cut": None if cut is None else (cut[0], cut[1] + y, cut[2] + x)}


"""
Where a frame comes in over what is below it, for its bands of detail (_blended): as the graph-cut seams of
panorama stitchers (Kwatra et al., "Graphcut textures", 2003; OpenCV's stitcher, Hugin's enblend): through the
overlap where the two differ least, so detail that is not in quite the same place in both (the terminator seen a
few minutes apart, a limb a pixel off) is cut where it barely shows instead of across it. Looked for only where the
coarse weight is between SEAM_CORE and 1 - SEAM_CORE, so every band has room to change over before either frame's
edge; worked out with the two shrunk so feather_px is SEAM_PX (the cut is for the mid-sized detail; the finest
bands change over within a few pixels wherever it runs). Elsewhere, and without OpenCV's stitching module, the
seam is where the coarse weight is a half: 1 where the frame comes in, 0 where what is below stays.
"""
SEAM_CORE = 0.3
SEAM_PX = 32


def _core(a, has, below):
    return (has > 0) & (below > 0) & (a >= SEAM_CORE) & (a <= 1 - SEAM_CORE)


def _seam_cut(a, has, below, color, under):
    """(the seam, (the cut, the pixel of a it starts at (y, x)) or None where it is a's half)"""
    seam = (a >= 0.5).astype(np.float32)
    core = _core(a, has, below)
    finder = getattr(getattr(cv2, "detail", None), "GraphCutSeamFinder", None)
    if finder is None or core.sum() < 64:
        return seam, None
    ys, xs = np.nonzero(core)
    m = 2
    y0, y1 = max(ys.min() - m, 0), min(ys.max() + 1 + m, a.shape[0])
    x0, x1 = max(xs.min() - m, 0), min(xs.max() + 1 + m, a.shape[1])
    f = min(1.0, SEAM_PX / feather_px)
    h, w = max(2, round((y1 - y0) * f)), max(2, round((x1 - x0) * f))
    shrink = lambda v, how=cv2.INTER_AREA: cv2.resize(np.ascontiguousarray(v[y0:y1, x0:x1]), (w, h), interpolation=how)
    ar, hs, bs = shrink(a), shrink(has) > 0.5, shrink(below) > 0.5
    # the frame where it may come in (all but where it is too faint), what is below where it may stay
    mine = hs & ~(bs & (ar < SEAM_CORE))
    theirs = bs & ~(hs & (ar > 1 - SEAM_CORE))
    if not (mine & theirs).any():
        return seam, None
    # (the finder takes three bands)
    three = lambda v: np.ascontiguousarray(np.broadcast_to(v[..., None], v.shape + (3,)) if v.ndim == 2 else v, np.float32)
    found = finder("COST_COLOR").find([cv2.UMat(three(shrink(color))), cv2.UMat(three(shrink(under)))],
                                      [(0, 0), (0, 0)],
                                      [cv2.UMat(mine.astype(np.uint8) * 255), cv2.UMat(theirs.astype(np.uint8) * 255)])
    cut = found[0].get() if hasattr(found[0], "get") else np.asarray(found[0])
    cut = cv2.resize((cut > 0).astype(np.float32), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR) >= 0.5
    part = seam[y0:y1, x0:x1]
    inside = core[y0:y1, x0:x1]
    part[inside] = cut[inside]
    return seam, (cut, y0, x0)


def _seam_given(a, has, below, cut):
    """The seam as decided (_blended's decided): cut (a's shape: 1 where the frame comes in, 0 where what is below
    stays, -1 where it says nothing, or None) inside the same core _seam_cut looks in, a's half elsewhere."""
    seam = (a >= 0.5).astype(np.float32)
    if cut is not None:
        take = _core(a, has, below) & (cut >= 0)
        seam[take] = cut[take] >= 0.5
    return seam


def _corrected(color, gain, gamma):
    """A frame's levels with its gain applied on linear brightness. Through lookup tables, since the levels
    are whole numbers 0-255 and the result is only kept to 8 bits."""
    if np.all(gain == 1):
        return color.copy()
    to_linear, edges = _tables(gamma)
    lin = to_linear[color.astype(np.uint8)]
    lin *= gain.astype(np.float32)
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
