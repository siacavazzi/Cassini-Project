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
What moved between the filters once the set is aligned on its target (a second moon, the rings or Saturn's limb behind
it) is drawn grey from the reference too (grey_plan, moved_region): that part (report["grey_moved"], its share of the
picture), or the whole set when it is most of the picture (report["grey"] = "moved").
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
        # ... and when fewer than two calibrate, the set is drawn grey from one filter (the one that calibrates, or the
        # first, the longest wavelength, when none does) instead of each channel stretched on its own: the Moon's
        # IR1/UV3/UV1 set of 1999-08-18 (two 8LSB members) came out with a blue sky and its disks side by side
        if len(keep) < 2:
            keep = keep or [0]
        if len(keep) < len(lbls):
            dropped = [os.path.basename(paths[j]).split(".")[0] for j in range(len(lbls)) if j not in keep]
            print(f"Can't calibrate {dropped}, making a {'two-filter' if len(keep) > 1 else 'grey'} picture of the others")
            lbls, imgs, iofs, masks, stacked, clips = ([v[j] for j in keep] for v in (lbls, imgs, iofs, masks, stacked, clips))
            if scale is not None:
                scale = dict(scale, blacks=[scale["blacks"][j] for j in keep])
    calibrated = False
    alone = False   # a color set drawn on its own in the classic look (its sky made neutral after alignment)
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
            linear = cal.load_linear(lbls, imgs, iofs, floor=cal.saturated_floor(share), glow=cal.saturated_glow(share),
                                     off_disk=lambda linear: dim_off_disk(lbls, linear))
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
            # (on the channels' grid: a summed frame's own mask is 512 px, and one with nothing saturated comes back
            # at its own size, N1356864915_2 in a Jupiter set of 1024 px frames)
            shape = linear[0][0].shape[:2]
            each = [_saturated_of(l, shape) if clip is None else clip for l, clip in zip(lbls, clips)]
            if any(m is not None and m.any() for m in each):
                full = [np.zeros(shape, np.float32) if m is None else _on_grid(m, shape) for m in each]
        elif linear is None:
            # puts every filter on the same brightness scale (see calibration.py)
            before = imgs
            if scale is not None:
                # a mosaic's or movie's shared scale: what the camera saturated is white, as in a one frame picture
                clips = [cal.saturated_of(l, img.shape[:2]) if clip is None else clip
                         for l, img, clip in zip(lbls, imgs, clips)]
            # (a set drawn on its own: its sky black in every channel, as the balanced look's, fix plan D)
            alone = scale is None and len(lbls) > 1 and cal.look() == "classic"
            imgs = cal.load_channels(lbls, imgs, iofs=iofs, scale=scale, saturated=clips if scale is not None else None,
                                     off_disk=(lambda linear: dim_off_disk(lbls, linear)) if alone else None)
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
    why = region = bodies = None
    bands = [cal.band_of(lbl.info) for lbl in lbls]
    try:
        if not align:
            # Settings > Processing: the channels as the camera took them, one over the other
            aligned = ["off"] * len(imgs)
            if linear is not None:
                guide = None
        elif guide is not None:
            shifts = []
            # the channels before alignment, for per_body
            before = (list(guide), list(linear[0]), list(masks), None if full is None else list(full))
            ic.align_with_masks(guide, [m.copy() for m in masks], ref, aligned, found=shifts, guess=guess)
            channels, masks = ic.align_with_masks(linear[0], masks, ref, use=shifts)
            if full is not None:
                full = [m if d is None else ic.shift_image(m, *d) for m, d in zip(full, shifts)]
            # a body that moved between the filters (grey_plan): drawn grey from the reference there, or everywhere
            why, region = grey_plan(aligned, channels, ref, np.logical_and.reduce(masks), bands)
            if why == "moved":
                # ... unless each body can be aligned on its own (per_body)
                got = per_body(lbls, ref, before[0], before[1], before[2], bands, before[3], shifts, warps)
                if isinstance(got, dict):
                    bodies = got
                elif got is not None:
                    channels, masks, region, bodies = got
                    why = "moved" if region is not None else None
                    full = bodies.pop("_full")
            # a set drawn grey (a channel not aligned) is every channel the reference's, so no channel fill; a part
            # drawn grey keeps no channel's fill there either (the fill would put a colour back)
            imgs = cal.tone(*_greyed(channels, linear, ref, aligned, why, region),
                            saturated=None if why and region is None else _saturated_masks(full, region))
            if why and region is not None:
                imgs = neutral(imgs, region)
        else:
            before, shifts = (list(imgs), list(imgs), list(masks)), []
            imgs, masks = ic.align_with_masks(imgs, masks, ref, aligned, found=shifts, guess=guess)
            why, region = grey_plan(aligned, imgs, ref, np.logical_and.reduce(masks), bands)
            if why == "moved":
                got = per_body(lbls, ref, *before, bands, None, shifts, warps)
                if isinstance(got, dict):
                    bodies = got
                elif got is not None:
                    imgs, masks, region, bodies = got
                    bodies.pop("_full")
                    why = "moved" if region is not None else None
            if why == "moved":
                imgs = grey_from(imgs, ref, region)
    except Exception:
        print("Image alignment failure")
        aligned = ["failed"] * len(imgs)
        if linear is not None:
            guide = None
    if linear is not None and guide is None:
        imgs = cal.tone(*_greyed(linear[0], linear, ref, aligned),
                        saturated=_saturated_masks(full) if len(lbls) > 1 and not unaligned(aligned) else None)
    grey = unaligned(aligned) or (why == "moved" and region is None)
    if alone and calibrated and not grey and len(imgs) > 1:
        # the classic look's color set: its darkest part neutral (calibration.neutral_display), drawn after it was aligned
        imgs = cal.neutral_display(imgs)
    if grey:
        # a channel neither its own match nor SPICE could place, or a body that moved over most of the picture: drawn
        # grey from the reference alone, never in colours that sit apart (its valid pixels are the reference's own)
        if linear is None:
            imgs = grey_from(imgs, ref)
        masks = [masks[ref]]
    report = {"calibrated": calibrated, "stacked": stacked, "aligned": aligned}
    if grey:
        # drawn grey from one filter (grey_from): the channels could not be lined up ("not aligned"), or a body
        # moved between the filters over most of the picture ("moved")
        report["grey"] = "not aligned" if unaligned(aligned) else "moved"
    elif region is not None:
        # the share of the picture drawn grey from the reference where a body moved between the filters (grey_plan)
        report["grey_moved"] = round(float(np.mean(region)), 4)
    if bodies is not None:
        # each body aligned on its own (per_body), or why that failed and the set was drawn grey as before
        report["per_body_failed" if "failed" in bodies else "per_body"] = bodies.get("failed", bodies)
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
Where the sky of a color set is when its own sky test finds too little of it (calibration.load_linear's off_disk):
every pixel off its target's disk in every frame of the set, as SPICE places it (the geometry cache), DISK_MARGIN
wider for SPICE's error, as a mask of the given shape (a frame's, its channels not yet aligned). The sky round a moon
can be lit all over, so its own test (calibration._sky, under a twentieth of the brightest) finds none: the faint offset
round Phoebe a few dozen pixels across (2004, violet). (Mimas's 2010 color set, 126MI, is not one: its "sky" is Saturn
behind it, too bright for dim_off_disk, and its magenta is Saturn's limb moving between the filters.) None when SPICE can't place the target on every frame, or for a
target whose own light reaches past its disk (DISK_LIT: Saturn's rings, Titan's haze), whose sky is not all sky.
"""
DISK_LIT = ("SATURN", "TITAN")
DISK_MARGIN = (0.2, 16)   # the disk this much wider (of its radius, and full resolution pixels), as obs_mosaic's


def off_disk(lbls, shape):
    target = lbls[0].info.get("TARGET_NAME")
    if target in DISK_LIT:
        return None
    try:
        import obs_mosaic
    except ImportError:
        return None
    if target not in obs_mosaic.RADIUS:
        return None
    locs = _spice_locs(lbls)
    if locs is None or any(loc is None or len(loc) < 3 or not loc[2] for loc in locs):
        return None
    k = 1024 / shape[0]   # (a summed frame's pixels are full resolution ones scaled to 1024)
    rows = np.arange(shape[0], dtype=np.float32)[:, None] * k
    cols = np.arange(shape[1], dtype=np.float32)[None, :] * k
    sky = np.ones(shape, dtype=bool)
    for lbl, loc in zip(lbls, locs):
        cam = "W" if lbl.info.get("INSTRUMENT_ID") == "ISSWA" else "N"
        radius = obs_mosaic.RADIUS[target] / (float(loc[2]) * obs_mosaic.IFOV[cam])
        reach = radius * (1 + DISK_MARGIN[0]) + DISK_MARGIN[1]
        cy, cx = ba.CCD_CENTER - float(loc[1]), ba.CCD_CENTER - float(loc[0])
        sky &= (rows - cy) ** 2 + (cols - cx) ** 2 >= reach * reach
    return sky


"""
calibration.load_linear's off_disk for a color set (off_disk), only where the sky it gives is dim in every channel:
its OFF_DISK_PCT percentile (the noise floor's, calibration.sky_levels) under OFF_DISK_DIM of the 99th percentile on
the disk. Light off the disk brighter than that is something lit (Saturn behind Mimas in 126MI, whose limb moved
between the filters; an Enceladus plume), not sky: taken for sky, it set a noise margin that dimmed the plume
"""
OFF_DISK_DIM = 0.05
OFF_DISK_PCT = 98


def dim_off_disk(lbls, iofs):
    sky = off_disk(lbls, iofs[0].shape)
    if sky is None or sky.all() or not sky.any():
        return None
    disk = ~sky
    for iof in iofs:
        top = float(np.percentile(iof[disk], 99))
        if not top > 0 or not float(np.percentile(iof[sky], OFF_DISK_PCT)) < OFF_DISK_DIM * top:
            return None
    return sky


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
        if r.dtype == bool:
            out.append(np.where(r, channels[src], c).astype(c.dtype))
        else:
            # a soft region (grey_plan's, 0 to 1): the reference's share of each pixel, so its edge is no seam
            mixed = c.astype(np.float32) * (1 - r) + channels[src].astype(np.float32) * r
            if np.issubdtype(c.dtype, np.integer):
                mixed = np.clip(mixed + 0.5, np.iinfo(c.dtype).min, np.iinfo(c.dtype).max)
            out.append(mixed.astype(c.dtype))
    return out


"""
Where a set's channels can't be lined up because something in the picture moved between the filters, after the set
was aligned on its target: a second moon whose copies sit apart (Enceladus 2015, three coloured dots), a moon over
the rings (Janus 2006, three coloured blobs), the rings behind a distant Earth (N1870757502_1), or Saturn's limb
behind a moon (Mimas 126MI, N1644787450_1: the limb sits in the green frame where the red and blue frames see only
Saturn, a magenta square). Fix plan PR 5: such parts are drawn grey from the reference frame (grey_from), not in
colours that sit apart. A general rule on the aligned channels, nothing per moment:

1. Each channel is set against the reference at MOVED_SIZE px, both on their own brightness (MOVED_TOP percentile, or half a small body's peak)
   and the channel scaled by the set's typical ratio of the two over what both see lit (so a colour of the whole
   picture is no difference).
2. A pixel differs when one of the two is lit (over MOVED_LIT) and the other at least MOVED_RATIO times fainter:
   something is there in one filter and not in the other. No colour of a surface in the visible and near infrared is
   that strong; a band that sees another layer of an atmosphere is (a methane band: Saturn dark where its rings are
   bright; the ultraviolet: Titan's detached haze), so a channel through one (other_layer) is not compared.
3. Patches of at least MOVED_AREA px once thinned by a px are kept (a star, a cosmic ray or a lit line is no body),
   widened over what touches them and still differs by MOVED_RATIO_LOW (the moved body's soft edge, no further than
   the patch is across), then by MOVED_GROW, softened over MOVED_SOFT (full resolution px), and drawn grey.
4. Over MOVED_WHOLE of what is lit in the picture, the whole set is drawn grey.

Returns the region as float32 (0 to 1) at the channels' size, "whole", or None when nothing moved. channels = the
aligned channels, linear (calibration.load_linear) or drawn (8-bit, grey or BGR); valid = pixels valid in every
channel; bands = each channel's filters (calibration.band_of), None when not known.
"""
MOVED_SIZE = 512       # px on the longer side, where the channels are compared
MOVED_TOP = 99.5       # a channel's percentile taken as its full brightness,
MOVED_PEAK = 0.5       # or at least this share of its MOVED_PEAK_AT percentile (a small body's)
MOVED_PEAK_AT = 99.95
MOVED_LIT = 0.08       # of full brightness: lit
MOVED_RATIO = 6.0      # the other frame at least this much fainter: something there in one frame only
MOVED_RATIO_LOW = 1.5  # what is widened over: still this much fainter, next to a patch kept
MOVED_AREA = 4         # px at MOVED_SIZE, once thinned by a px: smaller or thinner patches are left
MOVED_GROW = 8         # full resolution px the region is widened by (the soft edges of what moved)
MOVED_SOFT = 16        # full resolution px over which the region fades
MOVED_WHOLE = 0.4      # of the lit picture: the whole set drawn grey


def other_layer(band):
    """True for a band that sees another layer of an atmosphere than the visible and near infrared continuum: a
    methane band (calibration.is_methane) or the ultraviolet (UV1 to UV3), alone or stacked ("CL1/UV3")"""
    return cal.is_methane(band) or any(p.startswith("UV") for p in str(band or "").split("/"))


def moved_region(channels, ref, valid=None, bands=None):
    if len(channels) < 2 or (bands and other_layer(bands[ref])):
        return None
    shape = channels[ref].shape[:2]
    f = min(1.0, MOVED_SIZE / max(shape))
    small = (max(1, round(shape[1] * f)), max(1, round(shape[0] * f)))

    def level(c):
        c = np.asarray(c, np.float32)
        if c.ndim == 3:
            c = c.mean(axis=2)
        c = cv2.resize(c, small, interpolation=cv2.INTER_AREA) if f < 1 else c
        # a small body (a crescent over a sky that fills the frame) is the frame's full brightness, not its sky
        top = max(float(np.percentile(c, MOVED_TOP)), MOVED_PEAK * float(np.percentile(c, MOVED_PEAK_AT)))
        return np.clip(c, 0, None) / top if top > 0 else None

    ok = np.ones(small[::-1], bool)
    if valid is not None:
        ok = cv2.resize(np.asarray(valid, np.uint8), small, interpolation=cv2.INTER_NEAREST) > 0 if f < 1 else valid
        ok = cv2.erode(ok.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    r = level(channels[ref])
    if r is None:
        return None
    k = np.ones((3, 3), np.uint8)
    found = np.zeros(r.shape, bool)
    within = np.zeros(r.shape, bool)
    for j, c in enumerate(channels):
        if j == ref or (bands and other_layer(bands[j])):
            continue
        c = level(c)
        if c is None:
            continue
        both = ok & (c > MOVED_LIT) & (r > MOVED_LIT)
        if both.sum() >= 200:
            c = c / float(np.clip(np.median(c[both] / r[both]), 0.25, 4.0))
        hi, lo = np.maximum(c, r), np.minimum(c, r)
        differs = ok & (hi > MOVED_LIT) & (lo * MOVED_RATIO < hi)
        if not differs.any():
            continue
        differs = cv2.morphologyEx(differs.astype(np.uint8), cv2.MORPH_CLOSE, k) > 0
        n, labels, stats, _ = cv2.connectedComponentsWithStats(differs.astype(np.uint8), connectivity=8)
        kept = np.zeros(r.shape, bool)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < MOVED_AREA:
                continue
            x, y, w, h = stats[i, :4]
            patch = np.pad((labels[y:y + h, x:x + w] == i).astype(np.uint8), 1)
            if int((cv2.erode(patch, k) > 0).sum()) < MOVED_AREA:
                # a line or a speck (a cosmic ray, a star's trail): no body
                continue
            kept[y:y + h, x:x + w] |= patch[1:-1, 1:-1] > 0
            # how far it is widened below: no further than the patch is across (a limb's glow, not the sky's)
            reach = int(max(4, w, h))
            r0, r1, c0, c1 = max(y - reach, 0), y + h + reach, max(x - reach, 0), x + w + reach
            away = cv2.distanceTransform((labels[r0:r1, c0:c1] != i).astype(np.uint8), cv2.DIST_L2, 3)
            within[r0:r1, c0:c1] |= away <= reach
        if kept.any():
            # widened over the moved body's soft edge (a limb's glow, its own blur): what still differs by
            # MOVED_RATIO_LOW, touches a patch kept and is within its reach
            near = (ok & within & (hi > MOVED_LIT / 2) & (lo * MOVED_RATIO_LOW < hi)) | kept
            n, labels = cv2.connectedComponents(near.astype(np.uint8), connectivity=8)
            hit = np.unique(labels[kept])
            found |= np.isin(labels, hit[hit > 0])
    if not found.any():
        return None
    lit = ok & ((r > MOVED_LIT) | found)
    if found.sum() > MOVED_WHOLE * max(int(lit.sum()), 1):
        return "whole"
    region = found.astype(np.uint8)
    if f < 1:
        region = cv2.resize(region, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * MOVED_GROW + 1,) * 2)
    region = cv2.dilate(region, grow).astype(np.float32)
    region = cv2.GaussianBlur(region, (0, 0), MOVED_SOFT / 2)
    return np.clip(region * 2, 0, 1)


"""
Whether, and where, a set is drawn grey from the reference (grey_from), the one rule load_aligned (and the movie,
Day the Earth Smiled and per-body registration fixes, PRs 7, 10 and 15) asks: returns (why, region) where why is
None (colour as aligned), "not aligned" (a channel nothing placed, unaligned: the whole set) or "moved" (moved_region:
region the soft part to grey, or None for the whole set). Alignment turned off is the viewer's own choice: nothing grey.
bands = each channel's filters (calibration.band_of), for moved_region.
"""
def grey_plan(aligned, channels, ref, valid=None, bands=None):
    if unaligned(aligned):
        return "not aligned", None
    if len(channels) < 2 or any(a == "off" for a in aligned):
        return None, None
    region = moved_region(channels, ref, valid, bands)
    if region is None:
        return None, None
    return "moved", (None if isinstance(region, str) else region)


"""
Per-body registration (fix plan PR 15): a set grey_plan draws grey because something "moved", where SPICE puts two or
more known bodies (obs_mosaic.RADIUS) on the frame, each at least PER_BODY_LEAST px across. A moon crossing another,
or Saturn, moves against it between the filters (Tethys over Titan, N1689372813_1: 24 px a filter), so a set aligned on
one body has the other's copies apart and the whole set was drawn grey. Each body is aligned on its own instead:

1. Where the bodies are on the reference: SPICE's disks, all moved by how far the reference's pointing is off
   (_pointing_fix: the disks drawn as a picture, matched to the reference by image_correction.guided_shift, up to
   PER_BODY_POINTING px: N1702247263_1's is 31 px off).
2. From the farthest to the nearest, each channel is matched to the reference by the pipeline's own matcher
   (image_correction.align_with_masks) on that body alone: its disk in both frames, PER_BODY_GROW px wider, with
   every nearer body's disk filled flat, so nothing else is matched. The smallest body first, on its own: how far it is
   from SPICE's move is the camera's drift between the filters, and every other body is looked for only PER_BODY_NEAR
   round SPICE's move of it plus that drift (put there when its own match finds nothing: Titan's featureless haze).
   Where the set's own match over the whole picture lands within PER_BODY_NEAR of a body's, that one is kept.
3. The channels aligned on the farthest body are the picture (the sky keeps its alignment); each nearer body's
   channels go over them within its disk, feathered over PER_BODY_FEATHER px.
4. Where a nearer body hid the one behind it in some filter but not in the reference, that filter has nothing of the
   far body: filled with the far body's color round it (calibration.fill_saturated, the other channels there scaled
   by their local ratio), so the far body keeps its color (Titan round Rhea, N1694916794_1, was a grey crescent).
   A nearer body the camera saturated is drawn grey within its own disk, and anything else still moving (moved_region
   on the composite, off every body's limb: a third moon, ring arcs) grey from the reference (grey_from).

Returns (channels, masks, region or None, report) for load_aligned to go on with, or None where it does not apply,
or a report {"failed": why} when a body's match failed or the composite still moved over most of the picture (the
set is then drawn grey as before, report["per_body_failed"]). guide = the channels to match on (the classic display, or the drawn channels),
chans = the channels to draw (linear or drawn), both before alignment; masks = their valid masks; bands as grey_plan.
"""
PER_BODY_LEAST = 20      # px across: smaller bodies are not aligned on their own
PER_BODY_GROW = 6        # px round a body's disk that its match sees (and PER_BODY_HAZE)
PER_BODY_HAZE = 0.08     # of its radius more (a hazy or soft limb reaches past the disk: Titan's)
PER_BODY_SOFT = 6        # px over which the part a match sees fades out
PER_BODY_HOLE = 3        # px round a nearer body's disk left out of the far one's match
PER_BODY_FEATHER = 3     # px over which a nearer body's limb is blended onto what is behind it
PER_BODY_NEAR = 6        # px round SPICE's move plus the camera's drift that a body is looked for
PER_BODY_POINTING = 64   # px: how far the reference's pointing may be off SPICE's (_pointing_fix's search)
PER_BODY_CRESCENT = 0.2  # a disk whose median is under this share of its mean is drawn at its mean (_pointing_fix)
PER_BODY_MOST = 4        # bodies at most
PER_BODY_CLIPPED = 0.01  # of a nearer body's disk saturated in some filter: drawn grey
PER_BODY_FILL_REACH = 24  # px round the far body's part a filter did not see, whose color it is filled with


def _frame_bodies(lbl):
    """[(name, x, y, r, km)] of every known body SPICE puts on frame lbl (its target from label.target_loc, the others
    from the geometry cache's bodies table, bootleg_autonav.bodies_of), centres in the frame's full resolution pixels,
    radii over PER_BODY_LEAST / 2; None where the target can't be placed or the bodies table has not got the frame."""
    import obs_mosaic
    info = lbl.info
    name = str(info.get("TARGET_NAME", "")).replace('"', "").strip()
    cam = "W" if info.get("INSTRUMENT_ID") == "ISSWA" else "N"
    km = obs_mosaic.RADIUS.get(name)
    try:
        with spice_lock:
            loc = lbl.target_loc()
    except Exception:
        return None
    if not km or not loc or not loc[2]:
        return None
    others = ba.bodies_of([ba.frame_id(lbl)]).get(ba.frame_id(lbl))
    if others is None:
        return None
    out = [(name, ba.CCD_CENTER - float(loc[0]), ba.CCD_CENTER - float(loc[1]), km / (float(loc[2]) * obs_mosaic.IFOV[cam]),
            float(loc[2]))]
    out += [(b, ba.CCD_CENTER + x, ba.CCD_CENTER + y, r, z) for b, x, y, r, z in others if obs_mosaic.RADIUS.get(b)]
    return [b for b in out if 2 * b[3] >= PER_BODY_LEAST]


def _warped_bodies(bodies, warp):
    """_frame_bodies' bodies of a frame as warp_frame moves its picture (full resolution px, about warp's centre)"""
    x, y, scale, turn = warp
    M = cv2.getRotationMatrix2D((x, y), turn, scale)
    return [(n, float(M[0, 0] * bx + M[0, 1] * by + M[0, 2]), float(M[1, 0] * bx + M[1, 1] * by + M[1, 2]), r * scale, z)
            for n, bx, by, r, z in bodies]


def _disk(shape, x, y, r, soft=0.0):
    """A disk at (x, y) of radius r on a picture of shape (rows, columns) at the full resolution grid's scale, as
    float32 0 to 1, feathered over soft px about r (a hard disk when soft is 0)"""
    h, w = shape[:2]
    k = w / ba.FULL_FRAME
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot(xx / k - x, yy / k - y)
    if soft <= 0:
        return (d <= r).astype(np.float32)
    return np.clip((r + soft / 2 - d) / soft, 0, 1).astype(np.float32)


def _grey_level(im):
    """A picture as one float32 brightness plane (the mean of its colors)"""
    im = np.asarray(im, np.float32)
    return im.mean(axis=2) if im.ndim == 3 else im


def _as_like(plane, like):
    """A brightness plane back in the form of picture like (its colors and type), for the matcher"""
    like = np.asarray(like)
    out = plane[..., None].repeat(like.shape[2], axis=2) if like.ndim == 3 else plane
    if np.issubdtype(like.dtype, np.integer):
        out = np.clip(out + 0.5, 0, np.iinfo(like.dtype).max)
    return out.astype(like.dtype)


def _only(im, keep, flat):
    """Picture im with only the part keep (0 to 1) of it seen: the rest made flat, at the level of keep's own edge, and
    the part flat (0 to 1: a nearer body's disk) filled at the level round it, so neither cut is an edge for the
    matcher to line up"""
    g = _grey_level(im)

    def level(band):
        return float(np.median(g[band])) if band.any() else 0.0
    edge = (keep > 0.05) & (keep < 0.95) & (flat < 0.05)
    out = g * keep + level(edge) * (1 - keep)
    if flat.any():
        round_it = (cv2.dilate((flat > 0.05).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & (flat < 0.05) & (keep > 0.95)
        out = out * (1 - flat) + level(round_it) * flat
    return _as_like(out, im)


def _pointing_fix(guide, bodies, ref):
    """How far (dx, dy, full resolution px) the reference's bodies are from SPICE's places: the square round the
    smallest body's disk (the sharpest limb), with every disk drawn at the reference's brightness inside it (each
    nearer one over the ones behind it), matched to the reference there (image_correction.guided_shift,
    PER_BODY_POINTING px round no move); (0, 0) where nothing matches"""
    g = _grey_level(guide[ref])
    k = g.shape[1] / ba.FULL_FRAME
    scene = np.zeros(g.shape, np.float32)
    for name, x, y, r, z in sorted(bodies, key=lambda b: -b[4]):
        d = _disk(g.shape, x, y, r)
        if (d > 0).any():
            # (its median, or its mean for a crescent whose night side is most of the disk: a median of 0 drew no
            # disk at all, and with nothing to match the fix was none, N1702247263_1's 40 px)
            level = float(np.median(g[d > 0]))
            mean = float(np.mean(g[d > 0]))
            scene = np.where(d > 0, level if level >= PER_BODY_CRESCENT * mean else mean, scene)
    scene = cv2.GaussianBlur(scene, (0, 0), 1.0)
    _, x, y, r, _ = min(bodies, key=lambda b: b[3])
    half = (r + PER_BODY_POINTING + 2 * PER_BODY_GROW) * k
    x0, y0 = max(int(x * k - half), 0), max(int(y * k - half), 0)
    x1, y1 = min(int(x * k + half) + 1, g.shape[1]), min(int(y * k + half) + 1, g.shape[0])
    if x1 - x0 < 64 or y1 - y0 < 64:
        return 0.0, 0.0
    a = np.ascontiguousarray(scene[y0:y1, x0:x1])
    b = np.ascontiguousarray(g[y0:y1, x0:x1])
    try:
        found, _ = ic.guided_shift(_as_like(a, guide[ref]), _as_like(b, guide[ref]), (0.0, 0.0), window=PER_BODY_POINTING * k)
    except Exception:
        found = None
    if found is None or np.hypot(*found) > PER_BODY_POINTING * k:
        return 0.0, 0.0
    return float(found[0]) / k, float(found[1]) / k


def per_body(lbls, ref, guide, chans, masks, bands=None, full=None, whole=None, warps=None):
    if len(lbls) < 2:
        return None
    each = [_frame_bodies(l) for l in lbls]
    if any(b is None for b in each):
        return None
    if warps:
        # a channel scaled and turned onto the reference (spice_warps, a close flyby's range changing between the
        # filters): its bodies are where the warp put them (W1714693733_1, Dione over Saturn)
        each = [b if w is None else _warped_bodies(b, w) for b, w in zip(each, warps)]
    names = [b[0] for b in each[ref]]
    if len(names) < 2 or len(names) > PER_BODY_MOST or any({b[0] for b in e} != set(names) for e in each):
        return None
    at = [{b[0]: b for b in e} for e in each]
    # a nearer body filling the frame (over its middle, wider than half of it: a close Titan with Saturn behind, 019TI
    # HDAC001's WAC) shows only a sliver of limb, too little for its own match: its channels came apart into a rainbow
    # round the limb
    nearest_first = sorted(names, key=lambda n: at[ref][n][4])
    if any(at[ref][n][3] >= ba.FULL_FRAME / 2 and
           np.hypot(at[ref][n][1] - ba.CCD_CENTER, at[ref][n][2] - ba.CCD_CENTER) < at[ref][n][3]
           for n in nearest_first[:-1]):
        return None
    shape = np.asarray(guide[ref]).shape[:2]
    k = shape[1] / ba.FULL_FRAME
    fx, fy = _pointing_fix(guide, each[ref], ref)
    # far to near on the reference (the farthest first: its alignment is the sky's)
    order = sorted(names, key=lambda n: -at[ref][n][4])
    report = {"bodies": order, "pointing": [round(fx, 1), round(fy, 1)], "shifts": {}}
    # the smallest body is matched first, on its own (a small disk's whole limb is in view: the sharpest match); how
    # far that match is from SPICE is the camera's own drift between the filters, the same for every body, so each
    # other body is then looked for only PER_BODY_NEAR round SPICE's move of it plus that drift, and is put there
    # when its own match finds nothing (a soft disk with no detail: Titan's haze)
    drift = [None] * len(lbls)
    found_of = {}
    for name in sorted(order, key=lambda n: at[ref][n][3]):
        nearer = order[order.index(name) + 1:]
        shifts = []
        for j in range(len(lbls)):
            if j == ref:
                shifts.append(None)
                continue
            # SPICE's move of this body from the reference to channel j (the pointing fix the same in both)
            b0, bj = at[ref][name], at[j][name]
            g = ((bj[1] - b0[1]) * k, (bj[2] - b0[2]) * k)
            grow = PER_BODY_GROW + PER_BODY_HAZE * b0[3]

            def part(im, b, at_):
                # (each frame seen round its own place of the body, its own nearer bodies filled flat: what is cut
                # moves with the body, so the cut itself pulls the match only towards the body's move)
                flat = np.zeros(shape, np.float32)
                for n in nearer:
                    m = at_[n]
                    flat = np.maximum(flat, _disk(shape, m[1] + fx, m[2] + fy, m[3] + PER_BODY_HOLE, 2.0))
                return _only(im, _disk(shape, b[1] + fx, b[2] + fy, b[3] + grow, PER_BODY_SOFT), flat)
            pair = [part(guide[ref], b0, at[ref]), part(guide[j], bj, at[j])]
            found, how = [], []
            if drift[j] is None:
                ic.align_with_masks(pair, [masks[ref].copy(), masks[j].copy()], 0, how, found=found, guess=[None, g])
                if found[1] is None:
                    return {"failed": f"{name} in channel {j}: {how[1]}"}
                drift[j] = (found[1][0] - g[0], found[1][1] - g[1])
                shifts.append(found[1])
                continue
            g = (g[0] + drift[j][0], g[1] + drift[j][1])
            ic.align_with_masks(pair, [masks[ref].copy(), masks[j].copy()], 0, how, found=found, guess=[None, g],
                                within=PER_BODY_NEAR * k)
            got = found[1] if found[1] is not None else g
            w = whole[j] if whole is not None else None
            if w is not None and np.hypot(w[0] - got[0], w[1] - got[1]) <= PER_BODY_NEAR * k:
                # the set's own match over the whole picture lands on this body too (a frame-filling Saturn, its
                # rings): believed over the match on the body alone, which saw less of it (165TI's ring edges)
                got = w
            shifts.append(got)
        found_of[name] = shifts
        report["shifts"][name] = [None if s is None else [round(s[0], 1), round(s[1], 1)] for s in shifts]
    aligned = {}
    for name in order:
        moved, mmasks = ic.align_with_masks(list(chans), [m.copy() for m in masks], ref, use=found_of[name])
        aligned[name] = (moved, mmasks, found_of[name])
    # the farthest body's alignment, each nearer body over it within its disk
    out, omasks, base = [c.copy() for c in aligned[order[0]][0]], list(aligned[order[0]][1]), aligned[order[0]][2]
    # what the camera saturated in each channel (load_aligned's full), moved with the channels the same way
    moved_full = None if full is None else \
        {name: [m if d is None else ic.shift_image(m, *d) for m, d in zip(full, aligned[name][2])] for name in order}
    ofull = None if full is None else list(moved_full[order[0]])
    # each channel's own ghost: where a nearer body sat in that filter, over the far body the reference saw
    ghosts = [np.zeros(shape, np.float32) for _ in out]
    nearer_disks = np.zeros(shape, bool)
    for name in order[1:]:
        moved, mmasks, shifts = aligned[name]
        b = at[ref][name]
        w = _disk(shape, b[1] + fx, b[2] + fy, b[3], PER_BODY_FEATHER)
        for j, c in enumerate(moved):
            ww = w if c.ndim == 2 else w[..., None]
            mixed = out[j].astype(np.float32) * (1 - ww) + c.astype(np.float32) * ww
            if np.issubdtype(c.dtype, np.integer):
                mixed = np.clip(mixed + 0.5, 0, np.iinfo(c.dtype).max)
            out[j] = mixed.astype(c.dtype)
            omasks[j] = np.where(w > 0.5, mmasks[j], omasks[j])
            if ofull is not None:
                ofull[j] = np.where(w > 0.5, moved_full[name][j], ofull[j])
            if j != ref:
                # where this body sits in the far body's alignment of channel j: that filter saw it, not what is behind
                dx = shifts[j][0] - (base[j] or (0, 0))[0]
                dy = shifts[j][1] - (base[j] or (0, 0))[1]
                ghosts[j] = np.maximum(ghosts[j], _disk(shape, b[1] + fx + dx / k, b[2] + fy + dy / k,
                                                        b[3] + PER_BODY_GROW))
        nearer_disks |= _disk(shape, b[1] + fx, b[2] + fy, b[3] + PER_BODY_GROW) > 0
        for g in ghosts:
            g *= 1 - (w > 0)
    # that filter saw the nearer body there, not the far one: filled with the far body's own color near it (the other
    # channels there scaled by the ratio round it, calibration.fill_saturated over PER_BODY_FILL_REACH px, measured
    # off every nearer body's disk), so the far body keeps its color where it was drawn grey before (Titan round
    # Rhea or Dione). What the camera saturated there was the nearer body's, not the far one's: no longer saturated.
    # ... and where some channel has picture of the far body and another moved onto it has none (the far body cut by
    # the frame's edge, a filter moved 70 px onto it: N1694916618_1's top), whose edge fill drew a band of one color
    # (on the far body: a nearer one cut so is drawn grey there, below, as the fill would give it the far body's color)
    far = at[ref][order[0]]
    far_disk = _disk(shape, far[1] + fx, far[2] + fy, far[3] * (1 + PER_BODY_HAZE) + PER_BODY_GROW) > 0
    on_far = far_disk & ~nearer_disks
    seen_by = np.logical_or.reduce([np.asarray(m, bool) for m in omasks])
    unseen = [seen_by & ~np.asarray(m, bool) for m in omasks]
    edges = [u_ & on_far for u_ in unseen]
    cut_near = np.logical_or.reduce(unseen) & nearer_disks
    # (on the far body only: off it, in the sky, a filter's copy of the nearer body's limb and glare is drawn grey from
    # the reference, below, as before; a fill there from the far body's color drew colored rims round Dione,
    # N1701985106_1)
    sky = np.logical_or.reduce([g > 0 for g in ghosts]) & ~far_disk
    if any((g > 0)[far_disk].any() for g in ghosts) or any(e.any() for e in edges):
        miss = [((g > 0) & far_disk) | e for g, e in zip(ghosts, edges)]
        x = [np.asarray(c, np.float32) for c in out]
        # (the ratio measured inside the far body's limb: its haze ring past the limb is bluer, and a fill near the
        # limb took that blue, N1686941052_1)
        inner = _disk(shape, far[1] + fx, far[2] + fy, far[3] - PER_BODY_GROW - PER_BODY_HAZE * far[3]) > 0
        filled, _ = cal.fill_saturated(x, miss, reach=PER_BODY_FILL_REACH * k, where=inner & ~nearer_disks, floor=False)
        for j, c in enumerate(out):
            if not miss[j].any():
                continue
            f = filled[j]
            if np.issubdtype(c.dtype, np.integer):
                f = np.clip(f + 0.5, 0, np.iinfo(c.dtype).max)
            out[j] = np.where(miss[j] if c.ndim == 2 else miss[j][..., None], f.astype(c.dtype), c)
            if ofull is not None:
                ofull[j] = np.where(miss[j], 0, ofull[j]).astype(ofull[j].dtype)
            omasks[j] = np.asarray(omasks[j], bool) | edges[j]
        report["filled"] = round(float(np.mean(np.logical_or.reduce(miss))), 4)
    ghost = cut_near.astype(np.float32)
    if sky.any():
        grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * MOVED_GROW + 1,) * 2)
        soft = cv2.GaussianBlur(cv2.dilate(sky.astype(np.float32), grow), (0, 0), MOVED_SOFT / 2)
        # (not over the far body, which the fill keeps in color)
        ghost = np.maximum(ghost, np.clip(soft * 2, 0, 1) * (1 - far_disk))
    # a nearer body the camera saturated in some filter (over PER_BODY_CLIPPED of its disk) has no color there to
    # draw: the saturated fill would take the color round it, the far body's (an orange Dione over Titan,
    # N1694954493_1), so it is drawn grey from the reference, as its whole disk
    clipped = []
    if ofull is not None:
        for name in order[1:]:
            b = at[ref][name]
            disk = _disk(shape, b[1] + fx, b[2] + fy, b[3]) > 0
            if disk.any() and max(float((m[disk] > 0.5).mean()) for m in ofull) > PER_BODY_CLIPPED:
                clipped.append(name)
                # (its disk and its own glare round it, feathered: not widened over the far body as a moved part is)
                ghost = np.maximum(ghost, _disk(shape, b[1] + fx, b[2] + fy, b[3] + PER_BODY_GROW, PER_BODY_FEATHER))
    if clipped:
        report["clipped"] = clipped
    region = None
    if ghost.any():
        region = ghost
    # anything else still moving (a third moon, ring arcs): the existing region rule on the composite
    # (not on any body's limb, within PER_BODY_GROW and PER_BODY_HAZE of its radius: each body is aligned there on
    # its own, and what still differs is its own color, a haze's blue ring past the disk in BL1 that RED and GRN
    # don't see, N1694954730_1, not something that moved)
    limbs = np.zeros(shape, bool)
    for name in order:
        b = at[ref][name]
        reach = PER_BODY_GROW + PER_BODY_HAZE * b[3]
        limbs |= (_disk(shape, b[1] + fx, b[2] + fy, b[3] + reach) > 0) & ~(_disk(shape, b[1] + fx, b[2] + fy, b[3] - reach) > 0)
    # (nor where the sky's copies of a nearer body are drawn grey already: they differ, and would make the whole set
    # grey, N1686942882_1)
    rest = moved_region(out, ref, np.logical_and.reduce(omasks) & ~limbs & ~(ghost > 0), bands)
    if isinstance(rest, str):
        return dict(report, failed="still moved over most of the picture")
    if rest is not None:
        region = rest if region is None else np.maximum(region, rest)
    if region is not None:
        # a nearer body's own disk stays in color
        inside = np.zeros(shape, np.float32)
        for name in order[1:]:
            if name in clipped:
                continue
            b = at[ref][name]
            inside = np.maximum(inside, _disk(shape, b[1] + fx, b[2] + fy, b[3] - PER_BODY_FEATHER / 2))
        # (but for what a filter cut off it at the frame's edge)
        region = np.maximum(region * (1 - inside), cut_near.astype(np.float32))
        if not region.any():
            region = None
    report["_full"] = ofull
    return out, omasks, region, report


"""
Drawn channels (8-bit, as calibration.tone returns them) made neutral where region is (0 to 1, grey_plan's): each
pixel there takes the mean of the channels. The channels were already made equal there before the mix (grey_from), so
a natural color mix (its rows add up to one) leaves them grey and this changes nothing; a false color mix's gains and
its body's tint would color them again.
"""
def neutral(drawn, region):
    x = [np.asarray(d, np.float32) for d in drawn]
    mean = sum(x) / len(x)
    r = region if x[0].ndim == region.ndim else region[..., None]
    return [np.clip(c * (1 - r) + mean * r + 0.5, 0, 255).astype(np.uint8) for c in x]


"""
calibration.tone's arguments for the linear channels (linear = load_linear's (channels, margin, mix)): as they are, or,
when a channel was not aligned (unaligned), every channel the reference's and no colour mix, so the picture is grey
"""
def _greyed(channels, linear, ref, aligned, why=None, region=None):
    if unaligned(aligned) or (why and region is None):
        return grey_from(channels, ref), linear[1], None
    if why:
        # a part drawn grey keeps the set's mix elsewhere: a natural mix's rows each add up to one, so equal channels
        # stay neutral, and a false color mix's gains are taken out after drawing (neutral)
        return grey_from(channels, ref, region), linear[1], linear[2]
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
A saturated mask as float32 at shape (rows, columns), resized nearest when it is another size
"""
def _on_grid(mask, shape):
    mask = np.asarray(mask).astype(np.float32)
    if mask.shape[:2] != tuple(shape):
        mask = cv2.resize(mask, tuple(shape)[::-1], interpolation=cv2.INTER_NEAREST)
    return mask


"""
Each channel's saturated pixels as masks (from float32 masks moved with their channels), or None when none saturated
"""
def _saturated_masks(masks, region=None):
    if not masks:
        return None
    out = [m > 0.5 for m in masks]
    if region is not None:
        # none where the set is drawn grey from the reference (grey_plan), which the fill would colour again
        out = [m & ~(region > 0) for m in out]
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


# find_small_body: a small moon's centred view placed on the moon the picture shows, near where SPICE puts it. SPICE's
# place for the 2017 small-moon flybys is tens to hundreds of pixels off (spot check 7: Pan N1867604614_1 36 px, Atlas
# N1870699340_2 about 320 px, so Atlas sat cut at the view's left edge)
FIND_SMOOTH = 2.0      # px: the picture is smoothed this much first, so cosmic rays and stars are not bodies
FIND_AREA = (0.25, 4.0)  # a body's lit area, as a share of the disk SPICE gives it (its mean radius: an irregular moon)
FIND_SPAN = 3.0        # its width and height are under this many times its disk's diameter (a ring arc is not a moon)
FIND_LIT = 0.85        # under this share of its disk lit (half lit, a crescent, or cut by the frame's edge), its centroid
                       # sits off its centre (a half-lit disk's by 0.42 of its radius), so it is used only where SPICE is
                       # off by more than the disk's radius
FIND_MIN_RADIUS = 12.0  # px: smaller bodies look like a cosmic ray's track or a clump of them (Aegaeon N1829224056_1,
                        # 9 px: the blob found was a track 190 px off), so they are left where SPICE puts them
FIND_ROUND = 0.3       # a body's blob is this round or more (short over long side, and its share of its box)
FIND_MAX_RADIUS = 256  # px: bigger bodies fill the frame; SPICE places them, as before
FIND_REACH = 400       # px: the blob is looked for only this near SPICE's place (Atlas N1870699340_2 was 342 px off), and
                       # of the blobs there, the nearest to it is taken, not the biggest: another moon or a bright
                       # ring arc elsewhere in the frame is not the body


"""
Where a small body sits on a picture centred by SPICE (frame_server.centred: RGBA, north up, full resolution pixels):
the centroid of the one compact lit blob the size of its disk, or None where there is no such blob or SPICE is to be
kept. image = RGBA uint8, alpha 0 off the frame; cx, cy = where SPICE puts the body's centre; radius = its disk's radius
(px, obs_mosaic.RADIUS over the range). Returns (x, y) of the body's centre in the picture, or None.
"""
def find_small_body(image, cx, cy, radius, reach=FIND_REACH):
    if not radius or not FIND_MIN_RADIUS <= radius <= FIND_MAX_RADIUS:
        return None
    rgb = image[..., :3].astype(np.float32)
    valid = image[..., 3] > 0
    if valid.sum() < 1000:
        return None
    lum = cv2.GaussianBlur(rgb.mean(axis=2), (0, 0), FIND_SMOOTH)
    inside = cv2.erode(valid.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    values = lum[inside]
    sky = float(np.median(values))
    noise = 1.4826 * float(np.median(np.abs(values - sky))) + 0.5
    top = float(np.percentile(values, 99.9))
    if top - sky < 10 * noise:
        return None
    lit = (lum > sky + max(0.25 * (top - sky), 6 * noise)) & valid
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(lit.astype(np.uint8), connectivity=8)
    disk = np.pi * radius * radius
    best = None
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        if not FIND_AREA[0] * disk <= area <= FIND_AREA[1] * disk or max(w, h) > FIND_SPAN * 2 * radius:
            continue
        if min(w, h) < FIND_ROUND * max(w, h) or area < FIND_ROUND * w * h:
            continue   # a track or a ring arc, not a moon
        d = float(np.hypot(centroids[k][0] - cx, centroids[k][1] - cy))
        if d <= reach and (best is None or d < best[0]):
            best = (d, k)
    if best is None:
        return None
    away, best = best
    x, y, w, h, area = stats[best]
    fx, fy = (float(v) for v in centroids[best])
    # a blob that reaches the frame's edge is a body the frame cuts: its centroid is off its centre too
    cut = bool((labels[y:y + h, x:x + w] == best)[~inside[y:y + h, x:x + w]].any())
    if (area < FIND_LIT * disk or cut) and away <= radius:
        return None
    return fx, fy


# A light unsharp mask, the last step of every picture the site serves (frame_server's stills and composites, and every
# tile obs_mosaic draws into a movie frame or a mosaic, at the size it is drawn): fine detail raised a little, the same
# for everyone (Sam, 2026-11-02: "build it into the pipeline", no setting)
SHARPEN = 0.5                    # how much: each pixel moved away from its neighbourhood by this times the difference
SHARPEN_TAPS = (1, 4, 6, 4, 1)   # the neighbourhood: binomial, a Gaussian of sigma 1 px
SHARPEN_GATE = 3.0               # differences under this many levels (of 255) are raised less, so sky noise stays quiet


def unsharp(px, amount=SHARPEN, taps=SHARPEN_TAPS, gate=SHARPEN_GATE):
    """Picture px (uint8: H x W grey, or H x W x 2|3|4 with alpha last when 2 or 4) with its fine detail raised: each
    pixel's brightness (the mean of its colors) less its neighbourhood's (the binomial blur taps, over the picture's own
    pixels only, weighted by alpha, so the empty canvas round a frame or a tile does not ring at its edge), times
    amount, added to every channel alike (no colour fringes where the filters are slightly off). A difference d under
    gate levels is scaled by |d| / gate, so faint noise is raised far less than edges. Alpha is kept as it is; a pixel
    with none is not touched."""
    px = np.asarray(px)
    if amount <= 0 or px.size == 0:
        return px.copy()
    a3 = px[..., None] if px.ndim == 2 else px
    n = a3.shape[2]
    colors = n - 1 if n in (2, 4) else n
    rgb = a3[..., :colors].astype(np.float32)
    alpha = a3[..., colors].astype(np.float32) / 255 if colors < n else None
    lum = rgb[..., 0] if colors == 1 else rgb.mean(axis=2)
    k = np.asarray(taps, np.float32) / float(sum(taps))
    blur = lambda v: cv2.sepFilter2D(v, cv2.CV_32F, k, k, borderType=cv2.BORDER_CONSTANT)
    if alpha is None:
        # outside the picture counts as nothing: the blur of a picture of ones is the weight
        weight = blur(np.ones_like(lum))
        mean = blur(lum) / weight
    else:
        weight = blur(alpha)
        mean = np.where(weight > 1e-6, blur(lum * alpha) / np.maximum(weight, 1e-6), lum)
    d = lum - mean
    d = np.where(np.abs(d) < gate, d * (np.abs(d) / gate), d) * amount
    out = np.clip(rgb + d[..., None], 0, 255) + 0.5
    out = out.astype(np.uint8)
    if alpha is not None:
        out = np.where((alpha > 0)[..., None], out, a3[..., :colors])
    res = np.concatenate([out, a3[..., colors:]], axis=2) if colors < n else out
    return res[..., 0] if px.ndim == 2 else res


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
