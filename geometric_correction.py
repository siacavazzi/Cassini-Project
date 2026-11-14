"""
CISSCAL's geometric distortion correction for the Wide Angle Camera (CISSCAL 4.1 step 11, cassimg__geomcorr.pro, Ben
Knowles and Bob West 2002), ported line for line, with its per-filter focal lengths (calib/distortion/
wac_focallengths.tab, PDS COISS_0011 calib volume, 2004-12-07).

The WAC's optics bend the picture a little towards its corners (a barrel distortion, k = -6.2e-5 per mm^2 round the
optical centre, sample 548, line 508), and each filter pair focuses at its own focal length (200.71 mm for CL1/GRN to
201.22 mm for CB3/CL2), so a frame taken through one filter is a slightly different size on the CCD from one taken
through another. CISSCAL resamples the frame onto a straight (pinhole) grid at one focal length for every filter,
f_default = 200.956 mm: a straight line on the sky is straight in the frame, and every filter's frame is the same size.
Up to 3.4 px at the corners for the distortion, and up to 1.2 px at the edges between filters.

The NAC is left as it is: CISSCAL uses k = 0 and one focal length for it ("not much sense in doing separate filters
for NAC - max. offset error is 0.22 pixels at corners"), so its resampling would only re-interpolate every pixel onto
itself.

After the correction a WAC frame is a pinhole camera of focal length F_LINEAR (LINEAR_SCALE pixels per unit of tan
angle) at full resolution, which is the scale bootleg_autonav places the bodies with (linear_scale) and the IFOV
the mosaics measure with.

One deliberate difference from the IDL: CISSCAL finds the pixels the resampling reached past the frame's edge by
filling the margin with -1e38 and calling every output pixel below 0 bad, so a calibrated pixel that is a little
negative of its own (noise on a dark sky, after the bias and dark are taken off) is set to 0 as well. Here a pixel is
bad when the -1e38 margin would have made it negative (the margin's share of its cubic stencil is positive), the same
pixels CISSCAL finds at the edge, and a dark sky keeps its noise.

The pipeline step is "geom" (calibration.STEPS; Settings > Processing), on with "calibrate": the frames calibrated
(calibration.calibrate) are resampled, and the masks of their pixels (label_handler.valid_mask, calibration.saturated)
are moved the same way, so they still fall on the same pixels.
"""
import collections
import functools
import threading

import numpy as np


# cassimg__geomcorr.pro, the WAC branch
K = -0.000062                 # mm^-2, "use for all filters"
F_DEFAULT = 200.956           # mm
CENTRE = (548.0, 508.0)       # sample, line of the optical centre (full resolution)
PIXEL_MM = 0.012              # mm a full resolution pixel is across
CUBIC = -0.5                  # IDL interpolate(..., cubic=-0.5)
# the focal length every corrected frame has, and its pixels per unit of tan(angle) off the boresight
F_LINEAR = F_DEFAULT
LINEAR_SCALE = F_LINEAR / PIXEL_MM

# calib/distortion/wac_focallengths.tab: filter 1, filter 2 -> focal length (mm); the error column is left out
FOCAL_LENGTHS = {
    ("CL1", "GRN"): 200.710, ("CL1", "HAL"): 200.740, ("CL1", "RED"): 200.740, ("CL1", "CL2"): 200.770,
    ("CL1", "IR1"): 200.800, ("MT2", "IRP0"): 200.810, ("CB2", "IRP0"): 200.820, ("MT2", "IRP90"): 200.820,
    ("MT2", "CL2"): 200.820, ("CB2", "IRP90"): 200.830, ("CB2", "CL2"): 200.850, ("CL1", "BL1"): 200.860,
    ("IR2", "IR"): 200.950, ("IR2", "IRP90"): 200.950, ("IR2", "CL2"): 200.970, ("IR3", "IRP90"): 201.030,
    ("IR3", "IRP0"): 201.040, ("MT3", "CL2"): 201.040, ("IR3", "CL2"): 201.040, ("MT3", "IRP0"): 201.060,
    ("MT3", "IRP90"): 201.070, ("CL1", "VIO"): 201.090, ("CB3", "IRP0"): 201.110, ("CB3", "IRP90"): 201.120,
    ("IR4", "IRP0"): 201.120, ("IR4", "IRP90"): 201.160, ("CB3", "CL2"): 201.220, ("IR4", "CL2"): 201.220,
}


def _value(info, key, default=""):
    v = info.get(key, default)
    return str(v).strip().strip('"') if v is not None else default


def filters(info):
    """The frame's two filter names (FILTER_NAME), upper case, as CISSCAL's Filter1 and Filter2."""
    raw = info.get("FILTER_NAME", "")
    if isinstance(raw, (list, tuple)):
        names = [str(n) for n in raw]
    else:
        names = str(raw).strip("()").replace('"', "").split(",")
    names = [n.strip().upper() for n in names]
    return (names + ["", ""])[:2]


def focal_length(info):
    """The focal length (mm) CISSCAL takes for the WAC frame's filter pair, f_default when the table has no row for it."""
    return FOCAL_LENGTHS.get(tuple(filters(info)), F_DEFAULT)


def wants(info):
    """True for a frame CISSCAL corrects: a WAC frame with its shutter enabled (the NAC's correction is the identity)."""
    return _value(info, "INSTRUMENT_ID") == "ISSWA" and _value(info, "SHUTTER_STATE_ID", "ENABLED") != "DISABLED"


def active(info):
    """True when the request corrects this frame: it is one CISSCAL corrects, and "calibrate" and "geom" are on."""
    if not wants(info):
        return False
    import calibration as cal   # (calibration imports this module)
    return cal.step("calibrate") and cal.step("geom")


# Kept per frame size and focal length. A process meets up to 21 focal lengths (FOCAL_LENGTHS and F_DEFAULT) and a WAC
# sequence cycles through more filters than the plans kept: with 6, the plan was worked out again for 30% of the
# mission's 124,723 WAC frames, each time a frame was calibrated (168 ms at 1024 px on the M5, as much again as the
# 80 ms correction; 6% of the pre-build's processed phase on days of many-filter WAC sequences, 2026-11-14). A plan
# is 43 MB at 1024 px, so not every one can stay; what can:
#   _edges   the mask of the pixels past the edge alone (a byte a pixel, every size and focal length met): all a
#            mask's correction (correct_mask) asks of a plan, and 69 ms of working a plan out
#   _plan    8 plans instead of 6 (17% of the WAC frames then work one out, without their edge mask)
#   _map     2 maps instead of 8 (17 MB each, 4 ms to work out, used once a plan and once a mask), which pays for the
#            two more plans: 399 MB at most at 1024 px with every focal length's edge mask, 392 MB before
# Every value is worked out exactly as before; only how long it is kept changed.
PLANS_KEEP = 8
MAPS_KEEP = 2
EDGES_KEEP = 96
_edges = collections.OrderedDict()   # (npix, f) -> the mask of the pixels the resampling reaches past the edge
_edges_lock = threading.Lock()


@functools.lru_cache(maxsize=MAPS_KEEP)
def _map(npix, f):
    """Where each output pixel of an npix x npix frame comes from, in the buffered array (cassimg__geomcorr.pro):
    (b, arrsize, Xobspx, Yobspx) for the output pixels only (the IDL's array truncated to the frame), b the margin's
    width in whole pixels. For the camera's own sizes (1024, 512, 256) the margin is a whole 12, 6 or 3 px and this is
    the IDL as written; another size (a picture resized) keeps the IDL's optical centre and scale in its own pixels."""
    buffsize = 12.0 * npix / 1024.0                    # thickness of buffer zone around image
    b = int(np.ceil(buffsize))
    arrsize = npix + 2 * b
    xcen = CENTRE[0] * (npix + 2.0 * buffsize) / 1024.0    # sample of optical center WAC (in the IDL's array)
    ycen = CENTRE[1] * (npix + 2.0 * buffsize) / 1024.0    # line of optical center WAC
    temp = np.arange(npix, dtype=np.float64) + buffsize
    Xcorrpx, Ycorrpx = np.meshgrid(temp, temp)         # [line, sample]: X runs along a line, Y down the columns
    mm = PIXEL_MM * (1024.0 / npix)
    Xcorrmm = (Xcorrpx - xcen) * mm                    # optical x in mm
    Ycorrmm = (Ycorrpx - ycen) * mm                    # optical y in mm
    Rsq = Xcorrmm ** 2 + Ycorrmm ** 2                  # distance from oc in mm
    Xobsmm = (f / F_DEFAULT) * Xcorrmm / (1.0 + K * Rsq)
    Yobsmm = (f / F_DEFAULT) * Ycorrmm / (1.0 + K * Rsq)
    Xobspx = Xobsmm / mm + xcen - buffsize + b         # convert back to pixel # (in this margin's array)
    Yobspx = Yobsmm / mm + ycen - buffsize + b
    return b, arrsize, Xobspx, Yobspx


def _keys(t):
    """IDL's cubic convolution weights (Keys, a = CUBIC) for the four neighbours floor(t)-1 .. floor(t)+2."""
    a = CUBIC
    base = np.floor(t)
    d = t - base
    out = []
    for off in (-1, 0, 1, 2):
        s = np.abs(d - off)
        w = np.where(s <= 1, (a + 2) * s ** 3 - (a + 3) * s ** 2 + 1,
                     np.where(s < 2, a * s ** 3 - 5 * a * s ** 2 + 8 * a * s - 4 * a, 0.0))
        out.append(w)
    return base.astype(np.int64), out


def _interpolate(array, X, Y, weights=None):
    """IDL interpolate(array, X, Y, cubic=-0.5): array[line, sample] at the (sample X, line Y) points, neighbours past
    the array's edge clamped to it. weights = (bx, wx, by, wy) from _keys, worked out once for several arrays."""
    bx, wx, by, wy = weights if weights is not None else (*_keys(X), *_keys(Y))
    rows, cols = array.shape
    dtype = np.float32 if array.dtype == np.float32 else np.float64
    out = np.zeros(bx.shape, dtype)
    for j, oy in enumerate((-1, 0, 1, 2)):
        iy = np.clip(by + oy, 0, rows - 1)
        line = np.zeros(bx.shape, dtype)
        for i, ox in enumerate((-1, 0, 1, 2)):
            ix = np.clip(bx + ox, 0, cols - 1)
            line += wx[i] * array[iy, ix]
        out += wy[j] * line
    return out


def _smooth_nan(image, width):
    """IDL smooth(image, width, /nan, /edge_truncate): the boxcar mean of the finite pixels round each one (edges
    repeated), NaN where there are none."""
    import cv2
    finite = np.isfinite(image)
    values = np.where(finite, image, 0.0)
    total = cv2.boxFilter(values, -1, (width, width), normalize=False, borderType=cv2.BORDER_REPLICATE)
    count = cv2.boxFilter(finite.astype(np.float64), -1, (width, width), normalize=False,
                          borderType=cv2.BORDER_REPLICATE)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0.5, total / np.maximum(count, 1e-12), np.nan)


@functools.lru_cache(maxsize=PLANS_KEEP)
def _plan(npix, f):
    """What geomcorr needs for every frame of size npix at focal length f, worked out once: the map, its cubic
    weights (float32) and the mask of the pixels the resampling reaches past the edge."""
    b, arrsize, Xobspx, Yobspx = _map(npix, f)
    bx, wx = _keys(Xobspx)
    by, wy = _keys(Yobspx)
    weights = (bx.astype(np.int32), [w.astype(np.float32) for w in wx], by.astype(np.int32),
               [w.astype(np.float32) for w in wy])
    with _edges_lock:
        bad = _edges.get((npix, f))
    if bad is None:
        # bad outer pixels: CISSCAL fills the margin with -1e38 and calls what comes out negative bad; here the margin's
        # share of each stencil (its weights sum) is what would have made it negative (see the module's notes)
        margin = np.ones((arrsize, arrsize), np.float32)
        margin[b:arrsize - b, b:arrsize - b] = 0.0
        bad = _interpolate(margin, Xobspx, Yobspx, weights) > 1e-6
        bad.setflags(write=False)   # (kept, and handed to every plan and mask of this size and focal length)
        with _edges_lock:
            _edges[(npix, f)] = bad
            while len(_edges) > EDGES_KEEP:
                _edges.popitem(last=False)
    return b, arrsize, weights, bad


def _edge(npix, f):
    """The mask of the pixels the resampling of an npix frame at focal length f reaches past the edge (_plan's):
    the one kept (_edges), or from the plan, worked out when this size and focal length are met for the first time."""
    with _edges_lock:
        bad = _edges.get((npix, f))
    return _plan(npix, f)[3] if bad is None else bad


def geomcorr(image, f):
    """cassimg__geomcorr.pro on an npix x npix image (float, [line, sample]) taken at focal length f (mm): the image
    resampled onto the straight grid at F_DEFAULT, and the mask of its pixels the resampling reached past the edge
    (set to 0, as CISSCAL sets them)."""
    in_image = np.asarray(image, np.float32)
    npix = in_image.shape[1]
    b, arrsize, weights, bad = _plan(npix, float(f))

    # blur buffered image so that cubic spline doesn't blow up at edges
    blur_image = np.full((arrsize, arrsize), np.nan, np.float32)
    blur_image[b:arrsize - b, b:arrsize - b] = in_image
    blur_image = _smooth_nan(blur_image, int(12.0 * npix / 1024.0) * 2 + 1)
    # replace middle of blurred buffer image with original image
    blur_image[b:arrsize - b, b:arrsize - b] = in_image
    blur_image = np.where(np.isfinite(blur_image), blur_image, 0.0)

    # apply distortion correction (the output pixels only: the IDL truncates to the original size afterwards)
    out_image = _interpolate(blur_image, None, None, weights)
    out_image[bad] = 0.0
    return out_image, bad


def correct(image, info):
    """The frame's calibrated image (calibration.calibrate) with CISSCAL's geometric correction when the request
    corrects it (active), else as it is. Keeps the image's dtype."""
    image = np.asarray(image)
    if not active(info) or image.ndim != 2 or image.shape[0] != image.shape[1]:
        return image
    out, _ = geomcorr(image, focal_length(info))
    return out.astype(image.dtype, copy=False)


def correct_mask(mask, info, outside=False):
    """A mask on the frame's pixels (lost in downlink, saturated) moved as correct moves the pixels: each corrected pixel
    takes the mask of the pixel nearest the place it comes from. outside = the value for the pixels the correction
    reached past the frame's edge (False: not valid; for saturated masks also False)."""
    mask = np.asarray(mask)
    if not active(info) or mask.ndim != 2 or mask.shape[0] != mask.shape[1]:
        return mask
    npix = mask.shape[1]
    b, arrsize, Xobspx, Yobspx = _map(npix, float(focal_length(info)))
    ix = np.rint(Xobspx).astype(np.int64) - b
    iy = np.rint(Yobspx).astype(np.int64) - b
    inside = (ix >= 0) & (ix < npix) & (iy >= 0) & (iy < npix)
    out = mask[np.clip(iy, 0, npix - 1), np.clip(ix, 0, npix - 1)]
    out = np.where(inside, out, outside)
    if not outside:
        out = out & ~_edge(npix, float(focal_length(info)))
    return out.astype(mask.dtype, copy=False)
