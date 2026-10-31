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

  g = grey(rgba)                          # a picture as the alignment sees it: grey, 0 where it has nothing
  (dx, dy), how = shift(g0, g1)           # how far g1's content is from g0's (pixels), or (None, how)
  m = measure(greys, keys)                # each run of the film and where its content drifts (the slow part)
  xy = moves(greys, m, smooth)            # each picture's move, parts of the picture [x, y], for a smoothing
"""
import cv2
import numpy as np

import image_correction
from obs_mosaic import held_to_spice

SIDE = 512        # px: the film's pictures are measured this big on their longer side
MOST = 0.08       # of the picture: the largest move between two pictures believed (SPICE's centering is a few px off)
SMOOTH = 12       # pictures: the editor's smoothing by default
SMOOTH_MOST = 60  # pictures: the most smoothing offered
PLACES = 5        # decimals a move is sent with (parts of the picture: 1/100 px at 1024)


def grey(rgba):
    """The picture as the alignment sees it (obs_mosaic._shift_onto): its grey (cv2's RGB to grey), 0 where its alpha is."""
    a = np.asarray(rgba)
    g = cv2.cvtColor(np.ascontiguousarray(a[..., :3]), cv2.COLOR_RGB2GRAY)
    return np.where(a[..., 3] > 0, g, 0).astype(np.uint8) if a.shape[2] == 4 else g


def most(shape):
    """The largest move believed between two pictures of this shape, whole pixels."""
    return max(1, int(round(MOST * max(shape))))


def shift(g0, g1):
    """How far picture g1's content is from picture g0's ((dx, dy) pixels: g1 moved back by it lands on g0), and how it
    was found: the alignment of a set's channels (image_correction.align_with_masks) without its edge match, which is
    for filters that see a body differently, not for one picture after the next: phase correlation round the target,
    then the lit area's centroid; (None, "not aligned") when neither finds it within most()."""
    a, b = cv2.cvtColor(g0, cv2.COLOR_GRAY2BGR), cv2.cvtColor(g1, cv2.COLOR_GRAY2BGR)
    m = most(g0.shape)
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


def chain(greys, run):
    """Where the content of each picture of a run is (pixels), the first at 0: each picture's place is the picture
    before's moved by the match between them. One that matches nothing (a lost frame, a jump too far) keeps the place
    before, and the picture after it is matched to the newest picture that did match, failing the one before."""
    places, hows, good = [[0.0, 0.0]], ["first"], 0
    for k in range(1, len(run)):
        for j in dict.fromkeys((k - 1, good)):
            s, how = shift(greys[run[j]], greys[run[k]])
            if s is not None:
                break
        if s is not None:
            places.append([places[j][0] + s[0], places[j][1] + s[1]])
            good = k
        else:
            places.append(list(places[-1]))
        hows.append(how if j == k - 1 or s is None else f"{how} to {k - j} before")
    return places, hows


def measure(greys, keys):
    """The film's runs and each run's chain: [(run, places, hows)], what the moves for every smoothing are made from."""
    return [(run, *chain(greys, run)) for run in runs(greys, keys)]


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


def offsets(greys, keys, smooth=SMOOTH, report=None):
    """measure, then moves (None with smooth 0). report: a list given each picture's how."""
    if smooth <= 0:
        return None
    measured = measure(greys, keys)
    if report is not None:
        report.extend(h for _, _, hows in measured for h in hows)
    return moves(greys, measured, smooth)
