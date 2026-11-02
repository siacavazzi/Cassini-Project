# -*- coding: utf-8 -*-
"""
Created on Sun Apr  3 01:57:31 2022

@author: Sam Iacavazzi
"""

from PIL import Image, ImageEnhance
import label_handler as lh
import image_correction as ic
import index_maker as im
import stacking
import calibration as cal
import bootleg_autonav as ba
import data_source as ds
import numpy as np
import mosaic as mo
import cv2
import datetime
import multiprocessing
import os
import threading
import traceback
from collections import deque
from concurrent.futures import ProcessPoolExecutor


output = "output"
format = "jpg"
border = True
last = None

folder = "test"
"""
ORDER OF COLORS ***

1 ch: B&W
2 ch: red, blue *** fake green may be inserted into the middle
3 ch: red, green, blue

"""

triband_from_dualband = True
stack_repeats = True # combine repeat exposures of each filter to cut noise
calibrate = True # put every filter on one brightness scale so colors are true (False = old per frame stretch)
buffer = []

"""
Adds a frame to the mosaic window: the last mo.buffer_size frames
"""
def add_to_window(window, entry):
    if len(window) >= mo.buffer_size:
        window.pop(0)
    window.append(entry)


"""
Draws the frames in the window on top of each other (see mosaic.py). Each entry is
(RGBA numpy array, geometry, view, placement), as frame_task returns them.
"""
def composite_window(window, reproject=None):
    return Image.fromarray(mo.compose(window, reproject))


def build_mosaic(entry):
    add_to_window(buffer, entry)
    return composite_window(buffer)


"""
How many processes build frames at once: the CASSINI_WORKERS environment variable,
otherwise one per 6 GB of memory, at most 4 (so 2 on a 16 GB machine). Every worker
needs up to ~1 GB, and running short of memory makes everything far slower than
building frames one at a time. 1 runs everything in this process like before.
"""
max_default_workers = 4
gb_per_worker = 6

def total_memory_gb():
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (ValueError, OSError, AttributeError):
        return None  # not available on Windows

def worker_count(workers=None):
    if workers is None:
        workers = os.environ.get("CASSINI_WORKERS")
    if workers is None:
        memory = total_memory_gb()
        by_memory = int(memory // gb_per_worker) if memory else 2
        workers = min(max_default_workers, os.cpu_count() or 1, by_memory)
    return max(1, int(workers))


_mask = None

def get_mask():
    global _mask
    if _mask is None:
        _mask = Image.open("mask.png").convert("L")
    return _mask


"""
The camera's outermost lines and columns are not picture. Across the archive the first and last column of nearly every
frame read brighter than the columns beside them (in sky and on bright ground alike: N1503242138_1 has 201 where its
neighbours have 112, W1295204353_1 29 against 24) and the first line often does (N1503242138_1: 173 against 151); a WAC
frame's second line can too (W1507745867_2). Drawn at the soft edge's first value (mask.png's 46 of 255) on a
stretched dark sky, turned north up and resized, they became dotted bright lines along two edges of every frame
(Titan 2006 020TI, Jupiter 2000, Phoebe, Titan 2007 054TI) and white specks along every ring film's edge (113RI).
A frame's mask (pixels it has) leaves out EDGE_PX full-resolution pixels at each edge of a full frame, and
SUMMED_EDGE_PX of a summed one (4 of a 512 line frame's own pixels, 2 of a 256 line one's): a summed frame's bright
edge runs further in. N1349081639_2 (Jupiter 2000, 512 lines), on the full-resolution grid from the edge: 127 127
(the valid mask's left-out first pixel), 39 41, 14 14, 19 19, 2 2, then 0 in the sky; the Mini's second and third
renders, which left out 2 of its own pixels, still showed a faint line from the third and fourth.
Leaving a pixel out of the mask is not enough on its own: turning the frame north up (label.translate, linear on
colour and alpha apart) mixes a left-out pixel's colour into the new edge, and the calibrated path leaves 127 (half
scale) under a summed frame's left-out edge column. That was most of the dotted lines (the Mini's edge profile of
W1576834985_1, N1515805292_1, N1349081639_2: 127 in the left-out columns, 0 to 13 in the sky beside them; the first
render of this fix, which trimmed the mask only, kept the lines). So the colour under every left-out pixel next to
the picture is the picture's own nearest colour (rim_coloured), as load_aligned hands its pictures on. The soft edge
(mask.png) is unchanged; it starts edge_px in.
"""
EDGE_PX = 2
SUMMED_EDGE_PX = 8


def edge_px(lbl, side=1024):
    """How many full-resolution pixels at each edge of frame lbl (on a side px grid) are not picture: EDGE_PX of
    a full frame, SUMMED_EDGE_PX (or EDGE_PX of its own pixels, if more) of a summed one."""
    try:
        lines = int(lbl.info.get("LINES", side))
    except (TypeError, ValueError, AttributeError):
        lines = side
    summing = max(1, side // max(1, min(lines, side)))
    return EDGE_PX if summing == 1 else max(SUMMED_EDGE_PX, EDGE_PX * summing)


def edge_trimmed(mask, lbl):
    """mask (pixels a frame has, the 1024 px grid) with the frame's outermost edge_px lines and columns left out."""
    if mask is None:
        return mask
    n = edge_px(lbl, mask.shape[0])
    out = mask.copy()
    out[:n] = False
    out[-n:] = False
    out[:, :n] = False
    out[:, -n:] = False
    return out


RIM_PX = 8   # how far past the picture (pixels) rim_coloured paints: past what a linear turn and LANCZOS resize reach


def rim_coloured(img, valid):
    """img (uint8, one band or three) with the left-out pixels within RIM_PX of the picture (valid) the colour of
    the picture's nearest pixel, so no colour that is not the picture's reaches its edge when it is turned or
    resized. The picture itself is unchanged."""
    if img is None or valid is None or valid.all() or not valid.any() or img.dtype != np.uint8:
        return img
    dist, labels = cv2.distanceTransformWithLabels((~valid).astype(np.uint8), cv2.DIST_L2, 3,
                                                   labelType=cv2.DIST_LABEL_PIXEL)
    band = (dist > 0) & (dist <= RIM_PX)
    if not band.any():
        return img
    # each label is one picture pixel (a zero of the transform's input), numbered from 1 in row-major order
    flat = np.flatnonzero(valid.ravel())[labels[band] - 1]
    near = np.stack([flat // valid.shape[1], flat % valid.shape[1]], 1)
    out = img.copy()
    out[band] = img[near[:, 0], near[:, 1]]
    return out


"""
Builds one frame up to (not including) the mosaic step
row = one row of the image index: the label path for each filter plus seconds_1970
returns a PIL image and the label it was centered with
"""
def make_frame(row, filters):
    num_channels = len(filters)
    imgs = []
    lbls = []

    if num_channels == 1:
        # same 1024 px RGBA frame with soft edges as the color path, so B&W frames can mosaic
        lbl = lh.label(row[filters[0]], as_png = True)
        gray = Image.fromarray(lbl.resize_image()).convert('L')
        image = np.asarray(Image.merge("RGBA",(gray,gray,gray, get_mask())))
        return Image.fromarray(lbl.set_color(image).auto_center(border)), lbl

    imgs, valid, lbl, _ = load_aligned([row[filter] for filter in filters])

    for j in range(0, len(imgs)):
        imgs[j] = Image.fromarray(imgs[j]).convert('L')

    if len(imgs) == 3:
        # transparent where any channel has no data, instead of a colored streak
        alpha = Image.fromarray(np.where(valid, np.asarray(get_mask()), 0).astype(np.uint8))
        image = Image.merge("RGBA",(imgs[2],imgs[1],imgs[0], alpha))
        image = np.asarray(image)
        image = lbl.set_color(image).auto_center()
        image = Image.fromarray(image)

    else:
        if triband_from_dualband:
            blank = Image.new('L', imgs[0].size, 0)
            green = Image.merge("RGB",(imgs[0],blank,imgs[1])).convert('L')
            image = Image.merge("RGB",(imgs[0],green,imgs[1]))

        else:
            image = Image.merge("P",imgs[0],imgs[1])

    return image, lbl


"""
The color path of make_frame up to the merge, also used by the frame server's composites
(web/frames/frame_server.py): each frame stacked with its repeat exposures, lost pixels
filled, every filter put on one brightness scale, then aligned to the middle frame in time.
paths = the frames' paths, one per channel
hdr = merge every repeat exposure, whatever its exposure time, in I/F (stacking.load_hdr)
instead of averaging only identical ones: the faint parts come from the long exposures, the
bright ones from the short
scale = a fixed display scale shared by all the pictures of a mosaic (calibration.load_channels)
repeat_window = how close (seconds) a frame of the same filter must be to be stacked in as a repeat exposure;
a movie taking frames faster than that passes less, so its frames are not stacked into one another
around = a movie's frame (one path): the paths of the same filter's frames just before and after it in the movie,
whose one-frame spikes (cosmic rays, image_correction.spikes) are then replaced by what is round them (report["spikes_px"])
returns (images, mask of pixels valid in every channel, the reference frame's label, report)
where report says how each frame was calibrated and aligned, and report["dropped"] which frames were
left out because they can't be calibrated (then there is one image fewer than paths: a two-filter picture).
A two-filter set balanced like false color (calibration.color_mix) comes back as three images, green the mean of the two.
Channels whose own match fails are aligned near where SPICE puts them (spice_offsets, image_correction.guided_shift).
A channel that nothing places (unaligned) makes the whole set grey from the reference (grey_from, report["grey"]).
"""
def load_aligned(paths, hdr=False, scale=None, repeat_window=120, around=None):
    # Settings > Processing turns steps off per request (calibration.step); stacking checks its own
    calibrating, fill, align = calibrate and cal.step("calibrate"), cal.step("fill"), cal.step("align")
    lbls, imgs, stacked, iofs, masks, clips = [], [], [], [], [], []
    spiked = 0
    for path in paths:
        iof = clip = None
        if hdr and calibrating:
            lbl, iof, n, mask, clip = stacking.load_hdr(path, repeat_window, valid=True, clipped=True)
        if iof is None:
            lbl, img, n, mask = stacking.load_stacked(path, repeat_window, max_frames = 5 if stack_repeats else 1,
                                                      count=True, valid=True)
        else:
            img = lbl.resize_image()
        lbls.append(lbl)
        imgs.append(img)
        iofs.append(iof)
        # what the camera saturated in every exposure merged (drawn white)
        clips.append(clip)
        stacked.append(n)
        # pixels each frame lost in downlink (truncated lines) that no repeat exposure stacked with it had
        masks.append(mask)
    if around and fill and len(paths) == 1:
        # a movie's frame: its one-frame spikes (cosmic rays, there in neither neighbour) replaced by what is round them
        def neighbour(p):
            try:
                return _linear(lh.label(p, as_png=True))
            except Exception as e:
                print(f"Can't read {p} for spikes: {e}")
        found = ic.spikes(_linear(lbls[0]), [neighbour(p) for p in around if p])
        if found.any():
            imgs[0] = ic.unspike(imgs[0], found)
            if iofs[0] is not None:
                iofs[0] = ic.unspike(iofs[0], found)
            spiked = int(found.sum())
    lost = sum(int((~m).sum()) for m in masks)
    if fill and lost:
        # short runs of lost lines from the rows above and below (now valid); the rest from round them, only so
        # they don't skew the brightness scale or bleed when shifted: those stay invalid
        # (which runs are filled, and along which slant, is worked out on the display image, for its I/F too)
        fills = [ic.line_fills(img, mask, line=max(1024 // int(lbl.info.get("LINES", 1024)), 1))
                 for img, mask, lbl in zip(imgs, masks, lbls)]
        lined = [ic.fill_lines(img, mask, fills=f) for img, mask, f in zip(imgs, masks, fills)]
        iofs = [None if iof is None else ic.fill_lines(iof, mask, fills=f)[0] for iof, mask, f in zip(iofs, masks, fills)]
        imgs, masks = [l[0] for l in lined], [l[1] for l in lined]
    left = sum(int((~m).sum()) for m in masks)
    if fill:
        imgs = [ic.fill_invalid(img, mask) for img, mask in zip(imgs, masks)]
        iofs = [None if iof is None else ic.fill_invalid(iof, mask) for iof, mask in zip(iofs, masks)]
    # each frame's outermost lines and columns are not picture (edge_trimmed), so they move with the frame as it is
    # aligned and drop out of every picture made of it
    masks = [edge_trimmed(mask, lbl) for mask, lbl in zip(masks, lbls)]
    dropped = []
    if calibrating and len(lbls) > 1:
        # each frame calibrated once, here, for the display models below to share
        iofs = cal.calibrated_each(lbls, imgs, iofs)
        keep = [j for j, iof in enumerate(iofs) if iof is not None]
        # a channel that can't be calibrated (an 8LSB frame: only its low 8 bits were sent) is left out
        # when two others calibrate, so the set is a calibrated two-filter picture instead of every
        # channel falling back to its own stretch (Phoebe day, 2004-06-11: every NAC BL1 frame is 8LSB)
        if 2 <= len(keep) < len(lbls):
            dropped = [os.path.basename(paths[j]).split(".")[0] for j in range(len(lbls)) if j not in keep]
            print(f"Can't calibrate {dropped}, making a two-filter picture of the others")
            lbls, imgs, iofs, masks, stacked, clips = ([v[j] for j in keep] for v in (lbls, imgs, iofs, masks, stacked, clips))
            if scale is not None:
                scale = dict(scale, blacks=[scale["blacks"][j] for j in keep])
    calibrated = False
    guide = linear = saturated = full = None
    if calibrating:
        if scale is None and cal.look() != "classic":
            # balanced: the channels stay linear until they are aligned, then are drawn together (calibration.tone);
            # one frame: what the camera saturated is white (a frame saturated all over is white, not its flat field),
            # and a frame saturated over much of it keeps the rest soft instead of taking its floor black
            # (merged in I/F: what every exposure saturated, stacking.load_hdr's clipped)
            share = 0.0
            if len(lbls) == 1:
                full = [cal.saturated_of(lbls[0], imgs[0].shape[:2]) if iofs[0] is None else clips[0]]
                full = None if full[0] is None else full
                share = float(full[0].mean()) if full else 0.0
            linear = cal.load_linear(lbls, imgs, iofs, floor=cal.saturated_floor(share), glow=cal.saturated_glow(share))
        if linear is not None:
            calibrated = True
            if full is not None:
                share = cal.draw_saturated(linear[0], linear[1], full)
                if share >= 0.5:
                    saturated = round(share, 3)
        if linear is not None and len(lbls) > 1:
            # the channels are aligned on their classic display whatever the look, so a look changes only how
            # the picture is drawn, never where its channels land
            with cal.looking("classic"):
                guide = cal.load_channels(lbls, imgs, iofs=iofs)
            # what the camera saturated in each channel (merged in I/F: what every exposure saturated), moved with
            # its channel below: filled from the channels that did not saturate there (calibration.tone, fill_saturated)
            each = [_saturated_of(l, img.shape[:2]) if clip is None else clip for l, img, clip in zip(lbls, imgs, clips)]
            if any(m is not None and m.any() for m in each):
                full = [np.zeros(imgs[0].shape[:2], np.float32) if m is None else m.astype(np.float32) for m in each]
        elif linear is None:
            # puts every filter on the same brightness scale (see calibration.py)
            before = imgs
            if scale is not None:
                # a mosaic's or movie's shared scale: what the camera saturated is white, as in a one frame picture
                clips = [cal.saturated_of(l, img.shape[:2]) if clip is None else clip
                         for l, img, clip in zip(lbls, imgs, clips)]
            imgs = cal.load_channels(lbls, imgs, iofs=iofs, scale=scale, saturated=clips if scale is not None else None)
            calibrated = imgs is not before

    # align to the middle frame in time so the largest offset is as small as possible
    order = sorted(range(len(lbls)), key=lambda j: lbls[j].info["IMAGE_TIME"])
    ref = order[len(order)//2]
    # where SPICE says each channel's target sits relative to the reference's, for when the frames' own match fails
    guess = spice_offsets(lbls, ref) if align and len(lbls) > 1 else None
    # the body grows or turns between the filters of a close flyby (the range or the camera's twist changes): each
    # channel is first scaled and turned onto the reference's about its target's centre, so the translation found
    # below lines up the whole limb, not only its middle
    warps = spice_warps(lbls, ref) if align and len(lbls) > 1 else None
    if warps and any(w is not None for w in warps):
        masks = [m if w is None else warp_frame(m.astype(np.float32), w) > 0.99 for m, w in zip(masks, warps)]
        if guide is not None:
            guide = [g if w is None else warp_frame(g, w) for g, w in zip(guide, warps)]
            if full is not None and len(lbls) > 1:
                full = [m if w is None else warp_frame(m, w) for m, w in zip(full, warps)]
            linear = ([c if w is None else warp_frame(c, w) for c, w in zip(linear[0], warps)],) + tuple(linear[1:])
        else:
            imgs = [i if w is None else warp_frame(i, w) for i, w in zip(imgs, warps)]

    # masks move with the frames, so pixels alignment leaves uncovered become invalid too
    aligned = []
    try:
        if not align:
            # Settings > Processing: the channels as the camera took them, one over the other
            aligned = ["off"] * len(imgs)
            if linear is not None:
                guide = None
        elif guide is not None:
            shifts = []
            ic.align_with_masks(guide, [m.copy() for m in masks], ref, aligned, found=shifts, guess=guess)
            channels, masks = ic.align_with_masks(linear[0], masks, ref, use=shifts)
            if full is not None:
                full = [m if d is None else ic.shift_image(m, *d) for m, d in zip(full, shifts)]
            # a set drawn grey (a channel not aligned) is every channel the reference's, so no channel fill
            imgs = cal.tone(*_greyed(channels, linear, ref, aligned),
                            saturated=None if unaligned(aligned) else _saturated_masks(full))
        else:
            imgs, masks = ic.align_with_masks(imgs, masks, ref, aligned, guess=guess)
    except Exception:
        print("Image alignment failure")
        aligned = ["failed"] * len(imgs)
        if linear is not None:
            guide = None
    if linear is not None and guide is None:
        imgs = cal.tone(*_greyed(linear[0], linear, ref, aligned),
                        saturated=_saturated_masks(full) if len(lbls) > 1 and not unaligned(aligned) else None)
    grey = unaligned(aligned)
    if grey:
        # a channel neither its own match nor SPICE could place: drawn grey from the reference alone, never in colours
        # that sit apart (its valid pixels are the reference's own)
        if linear is None:
            imgs = grey_from(imgs, ref)
        masks = [masks[ref]]
    report = {"calibrated": calibrated, "stacked": stacked, "aligned": aligned}
    if grey:
        # drawn grey from one filter (grey_from): the channels could not be lined up
        report["grey"] = "not aligned"
    if warps and any(w is not None for w in warps):
        # each channel's scale and turn onto the reference (SPICE's range and twist), None where it needed none
        report["warped"] = [None if w is None else [round(w[2], 4), round(w[3], 3)] for w in warps]
    if not fill:
        report["filled"] = False
    if lost:
        # lost pixels (1024 px grid) after stacking, and how many of them are still missing after the fill
        report["lost_px"] = [lost, left]
    if dropped:
        report["dropped"] = dropped
    if spiked:
        report["spikes_px"] = spiked
    if saturated:
        # most of the frame saturated in the raw data (the camera's top), drawn white
        report["saturated"] = saturated
    shares = [float(c.mean()) for c in clips if c is not None]
    if shares and max(shares) > 0:
        # the share of the frame the camera saturated in every exposure merged (the most of any channel): drawn white
        report["saturated_share"] = round(max(shares), 4)
    valid = np.logical_and.reduce(masks)
    # no colour that is not the picture's under the pixels round it (rim_coloured)
    imgs = [rim_coloured(img, valid) for img in imgs]
    return imgs, valid, lbls[ref], report


"""
Whether a set's alignment (load_aligned's report["aligned"]) left a channel unplaced: "not aligned" (no match, and
SPICE's offset neither lined the frames up nor was within image_correction.SPICE_SURE) or "failed". Such a set is drawn
grey (grey_from), not in colours that sit apart. Alignment turned off ("off") is the viewer's own choice and stays.
"""
UNALIGNED = ("not aligned", "failed")


def unaligned(aligned):
    return len(aligned) > 1 and any(a in UNALIGNED for a in aligned)


"""
A set's channels drawn grey from one of them: every channel takes channels[src] where region is True (everywhere when
region is None), so those pixels come out neutral, as the reference filter saw them. Works on the linear channels
(before calibration.tone: the same values give the same grey in every channel) and on drawn 8-bit images. A region
(a body that moved between the filters) greys only that part of the picture; None, the whole set (a channel not
aligned, load_aligned).
"""
def grey_from(channels, src, region=None):
    if region is None:
        return [channels[src].copy() for _ in channels]
    out = []
    for c in channels:
        r = region if c.ndim == region.ndim else region[..., None]
        out.append(np.where(r, channels[src], c).astype(c.dtype))
    return out


"""
calibration.tone's arguments for the linear channels (linear = load_linear's (channels, margin, mix)): as they are, or,
when a channel was not aligned (unaligned), every channel the reference's and no colour mix, so the picture is grey
"""
def _greyed(channels, linear, ref, aligned):
    if unaligned(aligned):
        return grey_from(channels, ref), linear[1], None
    return channels, linear[1], linear[2]


"""
calibration.saturated_of, or None for a frame whose codes can't be read
"""
def _saturated_of(lbl, shape):
    try:
        return cal.saturated_of(lbl, shape)
    except Exception as e:
        print(f"Can't read {lbl.get_info().get('path')} for its saturated pixels: {e}")
        return None


"""
Each channel's saturated pixels as masks (from float32 masks moved with their channels), or None when none saturated
"""
def _saturated_masks(masks):
    if not masks:
        return None
    out = [m > 0.5 for m in masks]
    return out if any(m.any() for m in out) else None


"""
SPICE's offset of each frame's target from the reference frame's (lbls[ref]), (dx, dy) in full resolution pixels,
as image_correction.align_with_masks takes it (guess): the geometry cache places the target on every frame
(label.target_loc), and between the filters of a set it moves only as far as the camera's pointing drifted and the
body moved. None for a frame SPICE can't place; None for the whole set when the geometry cache is off (the batch
pipeline, which loads no kernels for this) or the frames are of different targets.
"""
def spice_offsets(lbls, ref):
    locs = _spice_locs(lbls)
    if locs is None or locs[ref] is None:
        return None
    return [None if loc is None else (locs[ref][0] - loc[0], locs[ref][1] - loc[1]) for loc in locs]


def _spice_locs(lbls):
    """label.target_loc of each frame ([x, y, range km, north angle], None where SPICE can't place it), or None when
    the geometry cache is off or the frames are of different targets."""
    if not ba.GEOMETRY_CACHE or len({lbl.info.get("TARGET_NAME") for lbl in lbls}) != 1:
        return None
    locs = []
    with spice_lock:
        for lbl in lbls:
            try:
                locs.append(lbl.target_loc())
            except Exception:
                locs.append(None)
    return locs


"""
How each channel of a set is scaled and turned onto the reference frame (lbls[ref]) about its target's centre, from
SPICE: (centre x, centre y, scale, degrees counter clockwise as cv2.getRotationMatrix2D takes them) per frame, or None
where it needs none (under WARP_LEAST px anywhere in the frame) or SPICE can't place it; None for the whole set
without the geometry cache. The range changes between filters on a close flyby (an Enceladus set, N1489051187_2,
17% closer by its last filter: the limb 120 px off where the middle lines up) and the camera turns in a slew.
"""
WARP_LEAST = 0.5     # px at the frame's corner (HALF_DIAGONAL from its middle)
WARP_MOST = 0.5      # a scale change past this share, or a turn past WARP_TURN degrees, is no use (not the same view)
WARP_TURN = 30.0
HALF_DIAGONAL = 724


def spice_warps(lbls, ref):
    locs = _spice_locs(lbls)
    if locs is None or locs[ref] is None or len(locs[ref]) < 4 or not locs[ref][2]:
        return None
    out = []
    for loc in locs:
        if loc is None or len(loc) < 4 or not loc[2] or loc[3] is None or locs[ref][3] is None:
            out.append(None)
            continue
        scale = float(loc[2]) / float(locs[ref][2])
        turn = ((float(loc[3]) - float(locs[ref][3]) + 180) % 360) - 180
        moves = HALF_DIAGONAL * (abs(scale - 1) + abs(np.radians(turn)))
        if moves < WARP_LEAST or abs(scale - 1) > WARP_MOST or abs(turn) > WARP_TURN:
            out.append(None)
            continue
        # about the target's centre; a close-up wholly on its target's disk about the frame's middle: its centre
        # is thousands of px off (Titan at 6,000 km), and a scale about it moves the whole frame by hundreds
        if _on_disk(lbls[ref], locs[ref]) or _on_disk(lbls[len(out)], loc):
            out.append((ba.CCD_CENTER, ba.CCD_CENTER, scale, turn))
        else:
            out.append((ba.CCD_CENTER - float(loc[0]), ba.CCD_CENTER - float(loc[1]), scale, turn))
    return out


def _on_disk(lbl, loc):
    """True when SPICE puts the frame wholly on its target's disk (sets_passes.pointing, the colour sets' rule)"""
    if lbl is None or loc is None:
        return False
    try:
        import obs_mosaic
        import sets_passes
    except ImportError:
        return False
    info = getattr(lbl, "info", None) or {}
    cam = "W" if info.get("INSTRUMENT_ID") == "ISSWA" else "N"
    return sets_passes.pointing(tuple(loc[:3]), obs_mosaic.RADIUS.get(info.get("TARGET_NAME")), obs_mosaic.IFOV[cam]) is None


"""
A frame (or its mask as float32) scaled and turned about a point, warp = (x, y, scale, degrees) as spice_warps gives
"""
def warp_frame(im, warp):
    x, y, scale, turn = warp
    M = cv2.getRotationMatrix2D((x, y), turn, scale)
    h, w = im.shape[:2]
    return cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_CUBIC if im.dtype != np.float32 or im.ndim == 3 else cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT)


"""
A frame in the camera's own values (calibration.stored_values: DN, or the codes of a TABLE frame), float32, sized like
label.resize_image: what image_correction.spikes looks for a movie frame's cosmic rays in
"""
def _linear(lbl):
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    values = (cal.stored_values(codes, lbl.info) if ds.lut8() else codes).astype(np.float32)
    if values.shape != (1024, 1024):
        values = cv2.resize(values, (1024, 1024), interpolation=cv2.INTER_AREA)
    return values


"""
One picture for the frame server's body reel (web/frames/reel.py): the frames at paths through
the color path above (load_aligned: stacked with their repeat exposures, lost pixels filled,
calibrated, aligned), merged like make_frame, then placed by auto_center (SPICE): north up, and
where the frame sits relative to the target's centre. One path makes a black and white
picture, two a two-filter one (green from both).
paths = the frames' paths, longest wavelength first
max_offset = how far (full resolution pixels) the target's centre may sit from the frame's
middle for the picture to count as centred on it; 600 is just past the frame's corners' reach
returns (RGBA numpy image, its label, report). With SPICE, the image is translate's canvas with
the frame's middle at the canvas middle, rotated north up, and report["frame_offset"] is where
that middle sits relative to the target's centre (canvas pixels, x right, y down): a close-up's
panels keep their places on the body, so they can mosaic. report["centred"] is True when the
target's centre is on the frame. Without SPICE, the 1024 px frame as it is.
hdr, scale, repeat_window, around = as load_aligned (for whole-observation mosaics and movies)
"""
def processed_frame(paths, max_offset=600, hdr=False, scale=None, repeat_window=120, around=None):
    imgs, valid, lbl, report = load_aligned(list(paths), hdr, scale, repeat_window, around=around)
    chans = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img for img in imgs]
    if len(chans) == 1:
        chans = chans * 3
    elif len(chans) == 2:
        chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
    alpha = np.where(valid, np.asarray(get_mask()), 0).astype(np.uint8)
    # blue, green, red like make_frame's merge: translate turns it into RGBA
    image = np.dstack([chans[2], chans[1], chans[0], alpha])
    try:
        with spice_lock:
            # where SPICE puts the frame (lbl.placement) and the canvas it goes on, not drawn: the
            # picture is the one drawn north up below
            shape = lbl.set_color(image).auto_center(border, draw=False)
        # the frame's middle goes to placement @ (511.5, 511.5), the target's centre to the
        # middle of the canvas
        middle = np.array([(shape[1] - 1) / 2, (shape[0] - 1) / 2])
        moved = (lbl.placement @ np.array([ba.CCD_CENTER, ba.CCD_CENTER, 1.0]))[:2]
        offset = moved - middle
        report["frame_offset"] = [round(float(v), 1) for v in offset]
        report["offset_px"] = round(float(np.hypot(*offset)), 1)
        report["centred"] = bool(report["offset_px"] <= max_offset)
        if not report["centred"]:
            report["why"] = f"the target's centre is off the frame (close-up), {report['offset_px']:.0f} px from its middle"
        # the same rotation without the shift: the frame north up at the middle of the canvas
        # (a close-up's shift would push it off the canvas)
        angle = np.degrees(np.arctan2(lbl.placement[0, 1], lbl.placement[0, 0]))
        return lbl.translate("png", 0, 0, angle, border), lbl, report
    except Exception as e:
        print(f"Can't centre {lbl.info.get('PRODUCT_ID')}: {e}")
        report["centred"] = False
        report["why"] = str(e)[:200]
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGBA), lbl, report


"""
One frame as science data: its I/F (reflectance relative to sunlight, calibration.calibrate) at the camera's own
resolution, float32, with no stacking, alignment, stretch or placement; pixels lost in downlink (label.valid_mask)
are NaN. path = the frame's path in the archive (nac_data/<ID>.png)
returns (I/F image, the frame's PDS label as text, a note on how it was made), or None when the frame can't be
calibrated (an 8LSB frame, an unknown filter or gain)
"""
def science_frame(path):
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    iof = cal.calibrate(codes, info, smooth=False)
    if iof is None:
        return None
    iof = np.asarray(iof, np.float32)
    valid = lbl.valid_mask()
    if valid.shape != iof.shape:
        valid = cv2.resize(valid.astype(np.uint8), iof.shape[::-1], interpolation=cv2.INTER_NEAREST).astype(bool)
    iof[~valid] = np.nan
    saturated = cal.saturated(codes, info)
    note = (f"I/F of {info.get('PRODUCT_ID', path)} (Cassini ISS), float32, {iof.shape[1]} x {iof.shape[0]} px, made by the "
            f"Cassini Project's calibration.calibrate: bias, shutter offset, exposure, gain, filter and sensitivity "
            f"corrections, bias from the overclocked pixels, dark current and hot pixels, nonlinearity, flat field (dust "
            f"rings and mottle) and the Sun's distance, with CISSCAL's own calibration maps. "
            f"Lost pixels (downlink): NaN, {int((~valid).sum())}. Saturated pixels: {int(saturated.sum())}.")
    return iof, ds.read_text(lbl.path), note


# auto_center loads a year of SPICE kernels into the one SPICE pool when the year changes;
# a server centring frames on several threads takes turns
spice_lock = threading.Lock()


def frame_path(row, target, folder):
    id = row["seconds_1970"]
    title = f"{id}_{target}"
    return f"output/{folder}/{title}.png"


def sharpen(image):
    return ImageEnhance.Sharpness(image).enhance(1.5)


"""
Sharpens and saves a finished frame
"""
def save_frame(image, path):
    try:
        sharpen(image).save(path)
    except Exception:
        print(f"Failed to save {path}:")
        traceback.print_exc()


"""
Mosaic frames are mostly empty space around the target. Workers send just the part
that isn't blank, which is much quicker to pass between processes.
"""
def crop(image):
    if image.shape[2] == 4:
        # reading each RGBA pixel as one 32 bit number is much faster than any(axis=2)
        used = np.ascontiguousarray(image).view(np.uint32)[..., 0] != 0
    else:
        used = image.any(axis=2)
    rows = np.flatnonzero(used.any(axis=1))
    cols = np.flatnonzero(used.any(axis=0))
    if len(rows) == 0:
        return (image.shape, 0, 0, image[:0, :0].copy())
    y, x = rows[0], cols[0]
    return (image.shape, y, x, image[y:rows[-1] + 1, x:cols[-1] + 1].copy())


def uncrop(cropped):
    shape, y, x, part = cropped
    image = np.zeros(shape, dtype=part.dtype)
    image[y:y + part.shape[0], x:x + part.shape[1]] = part
    return Image.fromarray(image)


"""
Builds and saves one mosaic frame from the cropped frames in its window
"""
def save_mosaic(window, path, reproject):
    entries = [(np.asarray(uncrop(c)),) + tuple(info) for c, info in window]
    save_frame(composite_window(entries, reproject), path)


"""
Does all the work for one frame that doesn't depend on other frames. Runs in a worker
process when running in parallel.
Saves the frame itself, except for mosaics: their frames are returned, with what
surface reprojection needs (mosaic.frame_info), so they can be added to the mosaic in order.
Returns None when there's nothing left to do, including when the frame failed.
"""
def frame_task(row, filters, target, folder, mosaic):
    try:
        image, lbl = make_frame(row, filters)
        if mosaic and len(filters) in (1, 3):
            return (np.asarray(image),) + mo.frame_info(lbl)
        save_frame(image, frame_path(row, target, folder))
    except Exception:
        print(f"Failed to make {row['seconds_1970']}_{target}:")
        traceback.print_exc()
    return None


"""
frame_task for the worker processes: mosaic frames are sent back cropped
"""
def worker_frame_task(row, filters, target, folder, mosaic):
    entry = frame_task(row, filters, target, folder, mosaic)
    if entry is not None:
        return crop(entry[0]), entry[1:]
    return None


"""
Runs once in every worker process
"""
def init_worker():
    # the main process extracts and deletes kernels; a worker deleting them would pull
    # them out from under the other workers
    ds.KEEP_SPICE_CACHE = True
    # the workers already keep every core busy, OpenCV's own threads would just compete
    cv2.setNumThreads(1)


def frame_year(row):
    return datetime.datetime.fromtimestamp(row["seconds_1970"], datetime.timezone.utc).year


def export_sequence(camera, filters, target, delta, folder, mosaic, start_loc, workers=None):
    index = im.get_images(camera, target, delta, filters, start_loc,make_csv=False)
    rows = [index.iloc[i].to_dict() for i in range(0, len(index))]
    # frames from an earlier run are kept. Mosaics are always redrawn since
    # each frame is drawn on top of the frames before it
    if not mosaic:
        todo = [row for row in rows if not os.path.exists(frame_path(row, target, folder))]
        if len(todo) < len(rows):
            print(f"Kept {len(rows) - len(todo)} frames already in output/{folder}")
        rows = todo
    workers = worker_count(workers)
    # start every sequence with an empty mosaic, so one target doesn't blend into the next
    buffer.clear()

    if workers == 1 or len(rows) <= 1:
        for row in rows:
            entry = frame_task(row, filters, target, folder, mosaic)
            if entry is not None:
                save_frame(build_mosaic(entry), frame_path(row, target, folder))
        return

    print(f"Building {len(rows)} frames with {workers} worker processes")
    # spawn (the macOS default) everywhere, so every worker opens the zip itself instead of
    # sharing the main process's file handle
    pool = ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn"), initializer=init_worker)
    pending = deque()
    saves = deque()
    window = []

    # frames come back in order, so the main process knows which frames make up each
    # mosaic; building and saving the mosaic goes back out to the workers
    def collect_oldest():
        future, row = pending.popleft()
        result = future.result()
        if result is not None:
            add_to_window(window, result)
            saves.append(pool.submit(save_mosaic, list(window), frame_path(row, target, folder), mo.reproject_surface))
            while len(saves) > workers * 2:
                saves.popleft().result()

    try:
        year = None
        for row in rows:
            # one year of kernels at a time, like the single process version: finish the
            # year, delete its kernels, then extract the next year's once for every worker
            if frame_year(row) != year:
                while pending:
                    collect_oldest()
                if year is not None:
                    ds.clear_spice_cache()
                year = frame_year(row)
                ba.extract_kernels(year)

            pending.append((pool.submit(worker_frame_task, row, filters, target, folder, mosaic), row))
            # keep a few frames queued per worker so none sit idle, without piling up
            # finished mosaic frames in memory while waiting on a slow one
            while len(pending) > workers * 2:
                collect_oldest()

        while pending:
            collect_oldest()
        while saves:
            saves.popleft().result()
    finally:
        pool.shutdown(cancel_futures=True)
