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
import cv2
import datetime
import multiprocessing
import os
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
Adds a frame to the mosaic window: the last 5 frames
"""
def add_to_window(window, img):
    if len(window) > 4:
        window.pop(0)
    window.append(img)


"""
Layers the frames in the window on top of each other
"""
def composite_window(window):
    if len(window) == 1:
        return window[0]
    composite = window[0]
    for image in window:
        composite = Image.alpha_composite(composite, image)
    return composite


# BUG: Image order is incorrect sometimes
def build_mosaic(img):
    add_to_window(buffer, img)
    return composite_window(buffer)


"""
How many processes build frames at once: the CASSINI_WORKERS environment variable,
otherwise one per CPU core. 1 runs everything in this process like before.
"""
def worker_count(workers=None):
    if workers is None:
        workers = os.environ.get("CASSINI_WORKERS") or os.cpu_count() or 1
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
returns a PIL image
"""
def make_frame(row, filters):
    num_channels = len(filters)
    imgs = []
    lbls = []

    if num_channels == 1:
        image = lh.label(row[filters[0]], as_png = True).auto_center(border)
        return Image.fromarray(image)

    for filter in filters:
        lbl, img = stacking.load_stacked(row[filter], max_frames = 5 if stack_repeats else 1)
        lbls.append(lbl)
        imgs.append(img)
    if calibrate:
        # puts every filter on the same brightness scale (see calibration.py)
        imgs = cal.load_channels(lbls, imgs)

    # align to the middle frame in time so the largest offset is as small as possible
    order = sorted(range(len(lbls)), key=lambda j: lbls[j].info["IMAGE_TIME"])
    ref = order[len(order)//2]
    lbl = lbls[ref]

    try:
        imgs = ic.align_images(imgs, ref)
    except:
        print("Image alignment failure")

    for j in range(0, len(imgs)):
        imgs[j] = Image.fromarray(imgs[j]).convert('L')

    if num_channels == 3:
        image = Image.merge("RGBA",(imgs[2],imgs[1],imgs[0], get_mask()))
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

    return image


def frame_path(row, target, folder):
    id = row["seconds_1970"]
    title = f"{id}_{target}"
    return f"output/{folder}/{title}.png"


"""
Sharpens and saves a finished frame
"""
def save_frame(image, path):
    try:
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.5)
        image.save(path)
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
def save_mosaic(window, path):
    save_frame(composite_window([uncrop(c) for c in window]), path)


"""
Does all the work for one frame that doesn't depend on other frames. Runs in a worker
process when running in parallel.
Saves the frame itself, except for mosaics: their frames are returned so they can be
added to the mosaic in order.
Returns None when there's nothing left to do, including when the frame failed.
"""
def frame_task(row, filters, target, folder, mosaic):
    try:
        image = make_frame(row, filters)
        if mosaic and len(filters) == 3:
            return image
        save_frame(image, frame_path(row, target, folder))
    except Exception:
        print(f"Failed to make {row['seconds_1970']}_{target}:")
        traceback.print_exc()
    return None


"""
frame_task for the worker processes: mosaic frames are sent back cropped
"""
def worker_frame_task(row, filters, target, folder, mosaic):
    image = frame_task(row, filters, target, folder, mosaic)
    if image is not None:
        return crop(np.asarray(image))
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
            image = frame_task(row, filters, target, folder, mosaic)
            if image is not None:
                save_frame(build_mosaic(image), frame_path(row, target, folder))
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
            saves.append(pool.submit(save_mosaic, list(window), frame_path(row, target, folder)))
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
