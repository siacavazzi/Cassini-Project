#!/usr/bin/env python3
"""
Additional stabilization of a film (the Movie Editor's Framing, under Auto center): each picture of the film matched
to the picture before it by what the two show, for when SPICE's centering wobbles. Auto center puts each picture's body
where SPICE says it is, and SPICE's pointing is a few pixels off, differently from picture to picture; on a small
moon in the NAC (Atlas, 2005-08-18) that is a large part of the body, and the film wobbles. Here the pictures as the
film shows them are matched one to the next by the pipeline's own alignment (image_correction.find_shift: phase
correlation round the target, then image_correction.centroid_shift, the lit area's centroid), the matches add up to
where the body drifts in the film, and each picture is moved by how far that drift is from a Gaussian average of it
over smooth pictures (obs_mosaic.held_to_spice, with SPICE's places at 0: the pictures are centred already). The
wobble from one picture to the next comes out, the slow motion stays.

It works on the finished pictures the film shows (centred, cropped by nothing yet, in the film's order, with every
frame the editor left out gone), which depend on the viewer's edit, so it runs on the viewer's computer
(docs/compute-on-viewer.md): the page's port is web/cassini-os/src/film-steady.html (window.cassiniFilmSteady), line
for line, and web/test_film_steady.py runs both on the same pictures. The page sends the moves with the film
(export.py steadied=, added to the editor's nudge), so the frame server only moves pictures; it never measures them.

  g, v = grey(rgba), valid(rgba)         # a picture as the alignment sees it: grey, 0 where it has nothing; where it has
  (dx, dy), how = shift(g0, g1, v0, v1)   # how far g1's content is from g0's (pixels), or (None, how)
  m = measure(greys, keys, valids)        # each run of the film and where its content drifts (the slow part)
  xy = moves(greys, m, smooth)            # each picture's move, parts of the picture [x, y], for a smoothing
"""
import cv2
import numpy as np

import image_correction
from obs_mosaic import FRAME, held_to_spice

SIDE = 512        # px: the film's pictures are measured this big on their longer side
MOST = 0.08       # of the picture: the largest move between two pictures believed (SPICE's centering is a few px off)
SMOOTH = 12       # pictures: the editor's smoothing by default
SMOOTH_MOST = 60  # pictures: the most smoothing offered
PLACES = 5        # decimals a move is sent with (parts of the picture: 1/100 px at 1024)
LEAST = 32        # px: the smallest window two pictures are matched in; under it, the whole pictures
AUTO = 0.05       # of a frame: a film whose body's radius is under this (the median over its pictures, full
                  # resolution pixels) is steadied without being asked, at SMOOTH: SPICE's 3 to 5 px is a good part of
                  # a body that small (Atlas, 2 px; obs_mosaic.SMALL_BODY's specks are under 0.02)


def grey(rgba):
    """The picture as the alignment sees it (obs_mosaic._shift_onto): its grey (cv2's RGB to grey), 0 where its alpha is."""
    a = np.asarray(rgba)
    g = cv2.cvtColor(np.ascontiguousarray(a[..., :3]), cv2.COLOR_RGB2GRAY)
    return np.where(a[..., 3] > 0, g, 0).astype(np.uint8) if a.shape[2] == 4 else g


def valid(rgba):
    """Where the picture has picture (its alpha whole); everywhere when it has no alpha."""
    a = np.asarray(rgba)
    return a[..., 3] == 255 if a.ndim == 3 and a.shape[2] == 4 else np.ones(a.shape[:2], bool)


def window(v0, v1):
    """Where two pictures are matched, (x0, y0, x1, y1): the largest box of the pictures' shape round their middle (where
    Auto center puts the body) that both have picture all over, as obs_mosaic._shift_onto matches two tiles only over
    the part of the view both cover. A centred picture is turned north up and moved by SPICE, so its own edge, the
    line between it and the empty fill, stays where SPICE put it while what it shows wobbles; matched with that edge
    in, the edge pulls the match back toward no move (a frame of Atlas's, between the A ring's bright edge and the
    fill, matched half its wobble). The whole pictures when both have picture everywhere, or the box would be under
    LEAST."""
    h, w = v0.shape
    both = (v0 & v1).astype(np.int64)
    if both.all():
        return 0, 0, w, h
    ii = np.pad(both.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    m, cx, cy, best = min(w, h), w // 2, h // 2, None
    for k in range(1, m // 2 + 1):
        hw, hh = k * w // m, k * h // m
        x0, y0, x1, y1 = max(cx - hw, 0), max(cy - hh, 0), min(cx + hw, w), min(cy + hh, h)
        if ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0] != (x1 - x0) * (y1 - y0):
            break
        best = (x0, y0, x1, y1)
    if best is None or min(best[2] - best[0], best[3] - best[1]) < LEAST:
        return 0, 0, w, h
    return best


def auto(radii):
    """Whether a film is steadied without being asked: the radius of its body on each picture (full resolution pixels,
    the body's mean radius over the frame's km per pixel; None where it has none), its median under AUTO of a frame."""
    r = sorted(v for v in radii if v is not None and v > 0)
    return bool(r) and r[len(r) // 2] < AUTO * FRAME


def most(shape):
    """The largest move believed between two pictures of this shape, whole pixels."""
    return max(1, int(round(MOST * max(shape))))


def shift(g0, g1, v0=None, v1=None):
    """How far picture g1's content is from picture g0's ((dx, dy) pixels: g1 moved back by it lands on g0), and how it
    was found: the alignment of a set's channels (image_correction.align_with_masks) without its edge match, which is
    for filters that see a body differently, not for one picture after the next: phase correlation round the target,
    then the lit area's centroid, within window(v0, v1) (v: where each has picture, valid; None: everywhere);
    (None, "not aligned") when neither finds it within most()."""
    m = most(g0.shape)
    if v0 is not None and v1 is not None:
        x0, y0, x1, y1 = window(v0, v1)
        g0, g1 = np.ascontiguousarray(g0[y0:y1, x0:x1]), np.ascontiguousarray(g1[y0:y1, x0:x1])
    a, b = cv2.cvtColor(g0, cv2.COLOR_GRAY2BGR), cv2.cvtColor(g1, cv2.COLOR_GRAY2BGR)
    found = image_correction.find_shift(a, b, m)
    if found is not None:
        return (float(found[0]), float(found[1])), "phase"
    found = image_correction.centroid_shift(a, b, m)
    if found is not None:
        return (float(found[0]), float(found[1])), "centroid"
    return None, "not aligned"


def runs(greys, keys):
    """The film's pictures in runs measured on their own: a run ends where the camera, the target or the kind of picture
    changes (keys), or the picture's shape does (another framing)."""
    out = []
    for i, g in enumerate(greys):
        if out and keys[i] == keys[out[-1][-1]] and g.shape == greys[out[-1][-1]].shape:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def chain(greys, run, valids=None):
    """Where the content of each picture of a run is (pixels), the first at 0: each picture's place is the picture
    before's moved by the match between them. One that matches nothing (a lost frame, a jump too far) keeps the place
    before, and the picture after it is matched to the newest picture that did match, failing the one before."""
    places, hows, good = [[0.0, 0.0]], ["first"], 0
    for k in range(1, len(run)):
        for j in dict.fromkeys((k - 1, good)):
            v = (valids[run[j]], valids[run[k]]) if valids is not None else (None, None)
            s, how = shift(greys[run[j]], greys[run[k]], *v)
            if s is not None:
                break
        if s is not None:
            places.append([places[j][0] + s[0], places[j][1] + s[1]])
            good = k
        else:
            places.append(list(places[-1]))
        hows.append(how if j == k - 1 or s is None else f"{how} to {k - j} before")
    return places, hows


def measure(greys, keys, valids=None):
    """The film's runs and each run's chain: [(run, places, hows)], what the moves for every smoothing are made from."""
    return [(run, *chain(greys, run, valids)) for run in runs(greys, keys)]


def moves(greys, measured, smooth):
    """Each picture's move ([x, y], parts of the picture, as the editor's nudge: export.framed), so its content lands
    where a Gaussian average of its run's drift over smooth pictures has it: minus held_to_spice(0, chain, smooth).
    smooth 0: no moves (None)."""
    if smooth <= 0:
        return None
    out = [None] * len(greys)
    for run, places, _ in measured:
        held = held_to_spice([[0.0, 0.0]] * len(run), places, smooth)
        for i, (x, y) in zip(run, held):
            h, w = greys[i].shape
            out[i] = [round(-x / w, PLACES) + 0.0, round(-y / h, PLACES) + 0.0]
    return out


def offsets(greys, keys, smooth=SMOOTH, report=None, valids=None):
    """measure, then moves (None with smooth 0). report: a list given each picture's how."""
    if smooth <= 0:
        return None
    measured = measure(greys, keys, valids)
    if report is not None:
        report.extend(h for _, _, hows in measured for h in hows)
    return moves(greys, measured, smooth)
