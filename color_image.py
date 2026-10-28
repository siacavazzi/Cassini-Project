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
returns (images, mask of pixels valid in every channel, the reference frame's label, report)
where report says how each frame was calibrated and aligned, and report["dropped"] which frames were
left out because they can't be calibrated (then there is one image fewer than paths: a two-filter picture)
"""
def load_aligned(paths, hdr=False, scale=None, repeat_window=120):
    # Settings > Processing turns steps off per request (calibration.step); stacking checks its own
    calibrating, fill, align = calibrate and cal.step("calibrate"), cal.step("fill"), cal.step("align")
    lbls, imgs, stacked, iofs, masks = [], [], [], [], []
    for path in paths:
        iof = None
        if hdr and calibrating:
            lbl, iof, n, mask = stacking.load_hdr(path, repeat_window, valid=True)
        if iof is None:
            lbl, img, n, mask = stacking.load_stacked(path, repeat_window, max_frames = 5 if stack_repeats else 1,
                                                      count=True, valid=True)
        else:
            img = lbl.resize_image()
        lbls.append(lbl)
        imgs.append(img)
        iofs.append(iof)
        stacked.append(n)
        # pixels each frame lost in downlink (truncated lines) that no repeat exposure stacked with it had
        masks.append(mask)
    lost = sum(int((~m).sum()) for m in masks)
    if fill and lost:
        # short runs of lost lines from the rows above and below (now valid); the rest from round them, only so
        # they don't skew the brightness scale or bleed when shifted: those stay invalid
        lined = [ic.fill_lines(img, mask) for img, mask in zip(imgs, masks)]
        iofs = [None if iof is None else ic.fill_lines(iof, mask)[0] for iof, mask in zip(iofs, masks)]
        imgs, masks = [l[0] for l in lined], [l[1] for l in lined]
    left = sum(int((~m).sum()) for m in masks)
    if fill:
        imgs = [ic.fill_invalid(img, mask) for img, mask in zip(imgs, masks)]
        iofs = [None if iof is None else ic.fill_invalid(iof, mask) for iof, mask in zip(iofs, masks)]
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
            lbls, imgs, iofs, masks, stacked = ([v[j] for j in keep] for v in (lbls, imgs, iofs, masks, stacked))
            if scale is not None:
                scale = dict(scale, blacks=[scale["blacks"][j] for j in keep])
    calibrated = False
    guide = linear = None
    if calibrating:
        if scale is None and cal.look() != "classic":
            # balanced: the channels stay linear until they are aligned, then are drawn together (calibration.tone)
            linear = cal.load_linear(lbls, imgs, iofs)
        if linear is not None:
            calibrated = True
        if linear is not None and len(lbls) > 1:
            # the channels are aligned on their classic display whatever the look, so a look changes only how
            # the picture is drawn, never where its channels land
            with cal.looking("classic"):
                guide = cal.load_channels(lbls, imgs, iofs=iofs)
        elif linear is None:
            # puts every filter on the same brightness scale (see calibration.py)
            before = imgs
            imgs = cal.load_channels(lbls, imgs, iofs=iofs, scale=scale)
            calibrated = imgs is not before

    # align to the middle frame in time so the largest offset is as small as possible
    order = sorted(range(len(lbls)), key=lambda j: lbls[j].info["IMAGE_TIME"])
    ref = order[len(order)//2]

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
            ic.align_with_masks(guide, [m.copy() for m in masks], ref, aligned, found=shifts)
            channels, masks = ic.align_with_masks(linear[0], masks, ref, use=shifts)
            imgs = cal.tone(channels, linear[1], linear[2])
        else:
            imgs, masks = ic.align_with_masks(imgs, masks, ref, aligned)
    except Exception:
        print("Image alignment failure")
        aligned = ["failed"] * len(imgs)
        if linear is not None:
            guide = None
    if linear is not None and guide is None:
        imgs = cal.tone(linear[0], linear[1], linear[2])
    report = {"calibrated": calibrated, "stacked": stacked, "aligned": aligned}
    if not fill:
        report["filled"] = False
    if lost:
        # lost pixels (1024 px grid) after stacking, and how many of them are still missing after the fill
        report["lost_px"] = [lost, left]
    if dropped:
        report["dropped"] = dropped
    return imgs, np.logical_and.reduce(masks), lbls[ref], report


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
hdr, scale, repeat_window = as load_aligned (for whole-observation mosaics and movies)
"""
def processed_frame(paths, max_offset=600, hdr=False, scale=None, repeat_window=120):
    imgs, valid, lbl, report = load_aligned(list(paths), hdr, scale, repeat_window)
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
    iof = cal.calibrate(codes, info)
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
