#!/usr/bin/env python3
"""
Observation mosaics for the camera windows: when Cassini steps a camera across a body a tile at a
time, the window shows every tile of that pass taken so far, all filters, made like the mosaic
benchmark (web/frames/mosaic_benchmark.py), rather than the reel's rolling window of a few tiles.

A pass (a "unit") is the frames of one camera, one target and one OBSERVATION_ID, split where
the camera pauses more than GAP or the distance to the body changes by more than ZOOM since the
pass began. It is a mosaic when the geometry cache puts its frames at three or more places (at
least mosaic.min_step of a frame apart, once scaled to one distance), its footprint is less than
MAX_FRAMES frames across, and the camera jumps rather than creeps: a movie (a stare, a ring or
storm movie, a moon turning) drifts a little between frames until the drift adds up to "three
places", so a pass whose steps between frames of one filter are at least mosaic.min_step of a
frame less than MOVIE_JUMPS of the time (or that never takes a filter twice), or whose camera stays
MOVIE_DWELL frames of one filter at each place (counting repeat exposures), is a movie, and plays
as frames (no mosaic of any kind) unless the person asks for its mosaic.
Overlap is not required: SPICE places every tile.

Every tile goes through color_image.processed_frame (repeat exposures merged in I/F, calibrated,
centred north up by SPICE) on one display scale for the pass (mosaic_benchmark.display_scale) and
is scaled to the pass's reference distance, so a flyby's tiles keep one km per pixel as Cassini
closes in. Tiles are made when first needed, oldest first, and kept in the cache.

The view: the whole footprint, scaled to fit, worked out once from the geometry cache (so it does
not move or rescale as the mosaic grows, and a tile once drawn never leaves the picture). The mosaic "so far" at a frame is every tile up to it, each
filter drawn by mosaic.compose (calibrated, none pinned) over its own earlier tiles; three or more
filters make false colour (longest wavelength red, middle green, shortest blue, only where all
three have the picture), otherwise the best covered filter in grey. Different filters are never
blended into one another.

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/obs_mosaic.py W1537023863_1 --cache DIR [--all]
  (makes the pass the frame is in ahead of time; the frame server makes it on first request)
"""
import argparse
import collections
import concurrent.futures
import contextlib
import contextvars
import hashlib
import io
import itertools
import json
import math
import os
import re
import sys
import threading
import time

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reel  # noqa: E402  (puts the repo on the path)
import sets_passes  # noqa: E402
import color_image  # noqa: E402
import calibration  # noqa: E402
import mosaic  # noqa: E402
import mosaic_benchmark  # noqa: E402
import image_correction  # noqa: E402
import stacking  # noqa: E402
import label_handler  # noqa: E402

# bumped whenever the way observation mosaics are made changes, so older ones are not served again; one per
# display model (calibration.style), classic being the mosaics made before the balanced display model, raw the
# balanced ones before natural color
# obs-v95/v78/v65: #393 (a color set mixing long and short exposures drawn on one white; a long exposure among short ones gives way to its filter's short frame: 263RI pink rings); numbered past #392's obs-v94/v77/v64; obs-v93/v76/v63: the batch of #383 (fill window, exposure6 chains), #384 (mosaic fixes), #385 (uncached frames), #388 (calibration filter table race), #389 (moon-finder sliver tile and behind-camera pointing) and #390 (reel wavelength race); obs-v92/v75/v62: pictures face the nearest quarter turn to north up (obs_mosaic.pass_turn snaps the pass's axes to 0/90/180/270); obs-v91/v74/v61: #379/#380/#381 (no sharpening on served pictures; Titan two-filter approximate color and tinted frames lined up on the frame; no north-up tilt); obs-v90/v73/v60: no north-up tilt: every picture turned to its pass's own orientation (obs_mosaic.pass_turn); obs-v89/v72/v59: #376/#377 (gentler floor black, FLOOR_SHARE 0.4 capped at FLOOR_GAIN 1.5; moved-body gray leaves dim light in color); obs-v88/v71/v58: #372/#374 (movies: a limb coming into a dark frame plays; an edge strip lost in downlink plays; short exposures not blank against clipped long ones); obs-v87/v70/v57: #369 (tinted movie frames: off-hue colors fade to the set's mean, dark sky takes no color, gray frame up to 10 min away; 259EP lime limb and sky specks); obs-v86/v69/v56: #367 (one look per color movie: set frames drawn from the pass's gray filter too; 259EP Epimetheus, 117TI/147TI/00ATI haze-surface strobe; held frame's own tile); obs-v85/v68/v55: #365 (transit movies: target found at its limb, limb zone on the body's local brightness, exposure gain after the color mix; 154RH halo and lime Rhea, 153DI Dione); obs-v84/v67/v54: #359 (transit movies: target lined up per filter, limb zone mixed from both bodies' colors, ring lines not matched as a body); obs-v83/v66/v53: #357 (movie per-body: another body in a color frame moved, in each filter's plane, to where the shown frame has it; no colored copies); obs-v82/v65/v52: #355 (color-hold cap: tinted frames keep the set's mean hue where the body moved, no seams; a set still coming in shows itself); obs-v81/v64/v51: #353 (limb matches only on frames that are at least 90 % picture: no colored rim round Titan on 153DI); obs-v80/v63/v50: #351 (a hazy far body's limb ring filled in its own color under a transiting moon: no gray wedge across Titan); obs-v79/v62/v49: #348 (storm-watch methane sets filed under a rider moon or UNK mixed as their observation's body); obs-v78/v61/v48: #339 (no hard clipping at white or black in moon mosaics and movies), #345 (color-hold seam) and #346 (transits: per_body off for warped sets, hazy limb ring gray); obs-v77/v60/v47: the gray color sets batch: #340 (featureless sets at SPICE's place, gray sets labeled black and white), #341 (limbs matched on their outline), #342 (movie frames far from their color set play their own picture in its color) and #343 (transits: far body filled in its own color, per_body on warped sets); obs-v76/v59/v46: #336 (each body of a color set aligned on its own where it moved: transit Moments no longer gray); obs-v75/v58/v45: #334 (movie skies: long exposures on their own white, skies stored in whole codes at their median: 155EN jets, 089MI veil, Pan Encke gap, Atlas halo); obs-v74/v57/v44: #328 (a movie taken up again on its view after a pause is one movie) and #329 (frames the body fills keep the pass's black: the guard the #279 merge lost); obs-v73/v56/v43: the batch of #323 (weak color-set matches checked on edges) and #325 (round-7 mosaic leftovers: Saturn 3x3 seams, 00BSA limb notches, Rhea 162RH wedge); obs-v72/v55/v42: the batch of #275 (small-moon centering), #279 (movie glow sky), #286 (small-moon movie stabilization), #300 (white under gain), #301 (sky streaks), #302 (Phoebe dark box), #303 (Auto center for cruise bodies), #305 (color-set cover), #315 (long repeats) and #317 (lossy repeated blocks); obs-v71/v54/v41: #271 (movie stabilization held on the pass's target by SPICE); obs-v70/v53/v40: #304 (no detail sharpening on small centred moons), #306 (registration past SPICE's jumps), #307 (movie colour filters from its sets) and #308 (dark sky under an even offset); obs-v69/v52/v39: #291 (registered tiles redrawn from their own frame: Rhea and Dione colour panels); obs-v68/v51/v38: #288 (each colour filter registered among its pointing's colour frames, then nearest in wavelength); obs-v67/v50/v37: #294 (grey single-filter colour sets); obs-v66/v49/v36: #281 (planet colour mosaics from whole visits, colour frames of one pointing registered to each other, mixes by set_mask on the tiles' boxes); obs-v65/v48/v35: the batch of #274 (080EN plume mosaic), #276 (plume sky smoothing), #277 (mosaic edge notch), #278 (Earth Smiled thin lines), #280 (panel registration limit), #282 (clip floor), #283 (blown filter), #284 (via-check as taken), #285 (lost lines) and #292 (hot pixels next to lost pixels); obs-v64/v47/v34: the WAC's geometric distortion correction and per-filter focal length (CISSCAL step 11, geometric_correction.py); obs-v63/v46/v33: the Day the Earth Smiled mosaic (#267); obs-v62/v45/v32: centred movies drawn as big as what the frames show (#269); obs-v61/v44/v31: movies use complete colour sets (#266); obs-v60/v43/v30: mosaic tile placement: slots inside disks, Titan hole, Iapetus white limb (#251); obs-v59/v42/v29: the batch of #247 (summed and full-size colour sets), #239 (edge trim), #240 (pass layout), #252 (grey where a moving body can't register), #249 (light sharpening), #258 (classic black sky), #261 (dark sky: edge glow and column stripes), #262 (mosaic despike) and #263 (steady mosaic movie colour, 3x3 seams, saturated frames held); obs-v58/v41/v28: even brightness across a pass and dim tiles decided by each pointing's first tile (#253); obs-v57/v40/v27: natural colour emulation keeps today's brightness with methane belt detail at twice a band's share (#254); obs-v56/v39/v26: the colour-set alignment fixes, wild star and edge fits rejected and grey where a channel is not aligned (#236); obs-v55/v38/v25: the tone shoulder, shadow floor and saturated colour fill (#241) and the dark-sky row band fixes (#242); obs-v54/v37/v24: the colour-set registration fixes (#235) and natural filters and palette for colour sets (#237); obs-v53/v36/v23: the CISSCAL 4.1 dark current (#231) and the colour-set repeat and pointing rule (#232); obs-v52/v35/v22: the CISSCAL 2 Hz noise, pixel pair and sky band steps (#230); obs-v51/v34/v21: the batch-4 fixes (thin ringlets kept, gentler compressed frames, movie long exposures held and first whole frame, Titan wind stares in color, natural color); obs-v50/v33/v20: the batch-3 fixes (Titan color, saturated white, movie strobe, small bright bodies keep their surface, line holes, pass kinds and scan rule, ride-along pans and ring strips, scan creep); obs-v49/v32/v19: movie cosmic rays and the small artifact fixes (group I), two-filter passes in color (group F), edge registration of clouded passes (group H2); obs-v48/v31/v18: repeats merged only at the same pointing, Auto center, movie tiles, mosaic movies and the calibration fixes; obs-v47/v30/v17: calibration takes the flat field (dust rings, mottle) and the nonlinearity out
VERSIONS = {"balanced": "obs-v95", "raw": "obs-v78", "eye": "obs-v95-eye", "false": "obs-v95-false", "classic": "obs-v65-classic"}
CANVAS = 2048        # longest side of the canvas the view is drawn on
OUT = 1024           # longest side of the picture sent
FRAME = 1024         # full resolution frame
HALF = 724           # half the side of a north-up frame's canvas (its diagonal)
GAP = 1800           # seconds without a frame that end a pass (mosaic.max_gap)
ZOOM = 1.4           # change in distance that ends a pass (tiles closer than this are rescaled)
MIN_PLACES = 3       # pointings a pass needs to be a mosaic
MAX_FRAMES = 16      # footprints wider than this many frames stay rolling mosaics
MOVIE_JUMPS = 0.3    # a pass whose same-filter steps jump (mosaic.min_step) less often than this is a movie
MOVIE_FIT = 2.0      # a pass played as a movie shows its whole footprint up to this many frames across, else it
                     # follows the frame: each picture the frame as Cassini took it (follow_view)
MOVIE_MARGIN = 0.15  # of a frame, round a movie's footprint when the geometry cache has none of its frames (pass_boxes)
CENTRE_MARGIN = 0.2  # of the body's diameter, round its disk in a movie centred on it
CENTRE_KEEP = 0.95   # of the frames' area a view centred on the body must keep, or the pass is not centred (centre_half)
SEEN_GRID = 16       # points across a frame that centre_half measures that share on (SEEN_GRID x SEEN_GRID per frame)
MOVIE_SAMPLES = 6    # tiles a movie's footprint is measured on
TRAIL = 12           # most earlier frames a movie's rolling trail keeps under the newest
SCALE_FRAMES = 96    # most frames the pass's display scale is measured on (evenly spread over a long movie)
LAP_GAP = 7200       # a mosaic taken again over the same ground within this many seconds is its next lap
LAP_OVERLAP = 0.6    # ... when the two footprints share at least this much (area both cover / either covers)
MOVIE_LAPS = 2       # a mosaic whose places are taken again (median, per filter) this many times is a mosaic movie
LAP_INSIDE = 0.9     # a few frames after a mosaic (a lap stopped short) are part of it when this much of them is inside it
PAIR_STEP = 1.0      # two places at most this many frames apart (their tiles touching) are a 1x2 mosaic
STRAY_LINK = 4       # frames of a pass within this many frames of one another are one patch of sky (_drop_strays) ...
STRAY_SHARE = 0.5    # ... and patches holding less than this share of its frames, away from the rest, are not the pass's
GROUPING = "_g2"     # the folder suffix of a pass these three rules (_drop_strays, _piece, a 1x2) group anew, so the
                     # passes made before them are not served for it; every other pass keeps its folder
MOVIE_DWELL = 8      # ... or whose camera stays this many frames of one filter (median) at each place it goes
TRACK_VISITS = 2     # ... or that follows a moving feature (_judge's track): at least this many visits of 3+ filters,
TRACK_SPAN = 0.12    # ... whose frames spread (median) over more than this much of a frame: more than a colour set's own
                     # pointing jitter (249SA_LIMBINT002's five filters a pointing land 0.09-0.12 apart, 003SA_3X3MOVIE's
                     # and 052SA_STRMOVIA's 0.08-0.11), less than the least a feature track creeps (182SA_FEATRAK012 0.14)
TRACK_SPAN_WAS = 0.08   # (the span before: a pass it judges otherwise gets RETRACKED's folder)
TRACK_CARRY = 0.5    # ... and, on a turning body (SPIN), whose turning carries a feature at least this share of that spread
RELAID = "_g3"       # the folder suffix, after GROUPING's, of a pass the layout rules below lay out anew (a time series, a
                     # drifting filter set, laps over drifted places, a map split by ZOOM joined again, a movie cut at a
                     # retarget, a turning camera, filters a lone frame set aside), or of every pass of an observation
                     # they renumber
RETRACKED = "_g4"    # the folder suffix, after RELAID's, of every pass of an observation where TRACK_SPAN (TRACK_SPAN_WAS
                     # before) judges a pass's track otherwise
REVISIT_PAUSE = 2    # a pause: a gap between frames this many times the pass's usual one (and at least REGISTER_GAP) ...
REVISIT_SHARE = 0.5  # ... and a mosaic whose frames mostly retake, after a pause, one view their filter took is a time series
SCAN_STEP = 0.1      # of a frame: a pass whose pointings between pauses step on by at least this ...
SCAN_EVEN = 0.01     # ... and by one step (to this, in a frame) each way they head (SCAN_TURN apart) is a scan, no time series
SCAN_TURN = 30       # degrees
SET_COLOUR = "_c1"   # the folder suffix, after the others, of a movie that plays in its colour sets' filters where its
                     # tile counts alone made it grey (_set_colour), so its plan and frames are made again
RESCANNED = "_g5"    # the folder suffix, after RETRACKED's, of every pass of an observation where _revisits' scan rule
                     # (a scan that pauses is no time series) judges a pass otherwise than the time-series rule alone
ISLAND_GAP = 0.75    # of a frame: the least empty sky between two islands of a mosaic, separate scans drawn apart
                     # (_retargets): 108RI_TMAPN30LP001's ring ansae 0.92, 113RI_VTMPN60MP001's 1.04; an azimuthal scan
                     # whose stretches of ring do not quite meet (032RI_AZSCNLOPH001, 064RI_AZSCAN001) leaves at most 0.63
ISLANDS = "_g6"      # the folder suffix, after RESCANNED's, of every pass of an observation where a mosaic is cut between
                     # islands (_retargets)
LEAN_JUMPS = 0.08    # a pass within this of MOVIE_JUMPS, LEAN_DWELL of MOVIE_DWELL or LEAN_SPAN of TRACK_SPAN, so that
LEAN_DWELL = 2       # moving them that far each way judges it a movie one way and none the other, is a toss-up: the
LEAN_SPAN = 0.02     # pointing alone cannot tell (a pan along a ring, one view, from a pan across it, a strip mosaic)
RIDE_ALONG = ("TEMP", "SUBM", "TMAP", "VERT", "TDIF", "EQLB", "VTMP")   # the CIRS ring scans (a ring target code,
RIDE_PAN = 0.4       # _name) the WAC rides along on, panning across the rings a quarter to half a frame a step: a WAC
                     # movie of one that travels RIDE_PAN of a frame or more is a strip mosaic (_judge). Its holds
                     # travel at most 0.38 (104RI_TDIFS20HP001's filter sets), its pans at least 0.45 (104RI_TDIFS20HP001
                     # W_5); the NAC's ride-alongs are filter sets on one view (036RI_SUBML27HP002)
DRIFT_SET = 1.5      # frames: a filter set the camera drifts through at a steady rate (within DRIFT_FIT of a frame of
DRIFT_FIT = 0.05     # a straight line in time) less far than this shows one view (_one_view)
PANNED = "_g7"       # the folder suffix, after ISLANDS', of every pass of an observation where a ride-along pan is a mosaic
RINGS = ("RI", "RA", "RB", "RC", "RD", "RE", "RF", "RG")   # the ring target codes of an observation's name (_name):
                     # the rings, a ring, the F and E rings (RH is Rhea)
STRIP_LONG = 6       # frames: a ring mosaic of Saturn whose frames cover a strip at least this long and at most
STRIP_WIDE = 1.5     # this wide (_strip) plays as a movie, its mosaic the window's other choice (Sam, 2026-10-29: the
                     # long thin ring scans were awkward mosaics; 033RI_AZDKMRHPH001 18.0 x 1.2). No least width: a
                     # strip of gappy frames (077RF 0.89, 208RI_SHADSCANU 0.52) falls apart into fragments as a mosaic
STRIP_GRID = 8       # cells a frame, the grid _strip measures a pass's frames on
STRIPPED = "_g8"     # the folder suffix, after PANNED's, of every pass of an observation where a ring strip is a movie
JOIN_ZOOM = ZOOM * ZOOM   # a map units split at ZOOM is joined again while its frames stay within this of its first distance
TWIST = 0.04         # of a frame: a pass the camera turns under (reel.turns) by more than this at its frames' places is drawn
                     # on a footprint turned frame by frame, and judged on its frames' places turned so (_flat)
DRIFT_LAPS = 0.5     # the least share of a frame the places of a time series' laps in a row overlap by (median) as they drift
TOUCH_GAP = 0.2      # frames of a mosaic this share of a frame apart or less touch (_touching): a grid of tiles taken as Cassini
                     # closes in, each tile smaller on the canvas than the step between them (016DI_TARGFLYBY001's ring of
                     # eight round its middle, 5% of a frame apart)
LONE_SHARE = 0.5     # a mosaic's lone frames (_lone: no frame at another of its places touches theirs) fewer than this share
                     # of its frames show as single pictures (u["off"]); a mosaic of more is no mosaic but pieces (_scatter)
LAID = "_g9"         # the folder suffix, after STRIPPED's, of every pass of an observation where the pass layout rules of
                     # 2026-11-02 judge a pass otherwise: a toss-up's footprint turned frame by frame, a time series of
                     # one view drifting (_drifting), a map split by ZOOM joined on its frames' ground
                     # (_zoom_join), lone frames shown as themselves or a scattered mosaic cut (_lone, _scatter)
RADIUS = {"SATURN": 60268, "JUPITER": 69911, "TITAN": 2575, "RHEA": 764, "IAPETUS": 735, "DIONE": 561,
          "TETHYS": 531, "ENCELADUS": 252, "MIMAS": 198, "HYPERION": 135, "PHOEBE": 107}
# Saturn's small moons (mean radius, Thomas 2010, Denk et al. 2018; web/replay/build_data.SMALL_MOONS), so Auto center
# has a disk to centre their passes on; under the catalog's own names (bootleg_autonav.CATALOG_NAMES). pass_scale's
# filled scale (a body filling the frames) stays with the bodies above: frames centred on a small moon are mostly
# sky round a disk a few per cent of the frame, which that scale (gamma 1.5) blew out to white
SMALL_RADIUS = {"JANUS": 89.5, "EPIMETHEUS": 58.1, "PROMETHEUS": 43.1, "PANDORA": 40.6, "HELENE": 18, "ATLAS": 15.1,
                "PAN": 14, "TELESTO": 12.4, "CALYPSO": 9.5, "DAPHNIS": 3.8, "PALLENE": 2.2, "METHONE": 1.45,
                "POLYDEUCES": 1.3, "ANTHE": 0.5, "K07S4": 0.5, "AEGAEON": 0.33,
                "SIARNAQ": 20, "ALBIORIX": 16, "PAALIAQ": 11, "YMIR": 9, "KIVIUQ": 8, "TARVOS": 7.5, "IJIRAQ": 6,
                "ERRIAPUS": 5, "ERRIAPO": 5, "SKATHI": 4, "SKADI": 4, "THRYMR": 4, "THRYM": 4, "HYROKKIN": 4,
                "SUTTUNGR": 3.5, "SUTTUNG": 3.5, "MUNDILFARI": 3.5, "NARVI": 3.5, "BESTLA": 3.5, "KARI": 3.5,
                "TARQEQ": 3.5, "BEBHIONN": 3, "BERGELMIR": 3, "FORNJOT": 3, "HATI": 3, "LOGE": 3, "SKOLL": 3, "SURTUR": 3,
                "JARNSAXA": 3, "GREIP": 3, "S13_2004": 3, "S12_2004": 2.5}
# bodies only ever seen as specks, under a pixel (Earth from Saturn, equatorial radius: Day the Earth Smiled, 195RI
# HIPHASEC001, 2013-07-19, 0.7 NAC px at 1.45e9 km; 269RI HIPHASEFB001, 2017): a disk for the pass's display scale
# only (small_body, pass_scale's white), so the movie's white is set on the body and each frame's black over its
# stray-light veil. Without one the 99.9th percentile of the pass was the veil, stretched black to white, which showed
# its leftover 2 Hz line bands (0.3% of the sky, columns once turned north up) and each filter's sky level as gray,
# yellow and cyan frames. Not in RADIUS: centred on SPICE's place its movie's filters landed 10-20 px apart, and its
# colour sets' sky off the disk drew Earth gray ("moved")
SPECKS = {"EARTH": 6378}
# the bodies of the cruise (mean radius): Jupiter's moons in 2000-2001 and the Moon at the Earth flyby in 1999, so Auto
# center has a disk to center their pictures on (Io and Europa in eclipse, Himalia, the Moon: "no disk of a known
# body", the picture left where the camera had it). Like the small moons, not in FILL_RADIUS: far off they are disks
# of a few dozen pixels in the sky, which the filled scale would blow out
CRUISE_RADIUS = {"IO": 1822, "EUROPA": 1561, "GANYMEDE": 2634, "CALLISTO": 2410, "HIMALIA": 70, "MOON": 1737}
FILL_RADIUS = dict(RADIUS)
RADIUS.update(SMALL_RADIUS)
RADIUS.update(CRUISE_RADIUS)
IFOV = {"N": 6.0e-6, "W": 0.012 / 200.956}   # radians per full resolution pixel; the WAC's at the focal length its frames
                                             # are resampled to (geometric_correction.F_LINEAR), 59.7 microradians
# radius (km) and rotation period (hours) of the bodies a camera can follow a feature on (_judge's track): a feature
# the body's turning carries along. The moons turn with their orbits (Phoebe and Hyperion on their own)
SPIN = {"SATURN": (60268, 10.66), "JUPITER": (71492, 9.925), "EARTH": (6378, 23.93), "VENUS": (6052, 5832.5),
        "MOON": (1737, 655.7), "IO": (1822, 42.46), "EUROPA": (1561, 85.23), "GANYMEDE": (2634, 171.7),
        "CALLISTO": (2410, 400.5), "TITAN": (2575, 382.7), "RHEA": (764, 108.4), "IAPETUS": (735, 1903.9),
        "DIONE": (561, 65.69), "TETHYS": (531, 45.31), "ENCELADUS": (252, 32.89), "MIMAS": (198, 22.62),
        "HYPERION": (135, 312.0), "PHOEBE": (107, 9.27)}
QUALITY = 95         # WebP quality of every picture sent; its folders carry it (frame_server.QUALITY)

_units = {}           # (target, obs, cam) -> [unit dicts]
_lock = threading.Lock()
_unit_locks = {}
_warming = set()
_background = threading.Semaphore(1)   # background work (passes made ahead) runs one at a time, so it never
                                       # crowds out what a window is waiting for
_upto, _from = {}, {}   # a pass being made ahead: the last tile to make, the first mosaic to make
_tile_locks = {}      # (pass key, mode, tile) -> its lock (calibration.mode: another look or step set is another tile)
_making = {}          # path of a mosaic being made -> its lock, so two requests for it make it once


def _row_of():
    idx, _ = reel.load_index()
    with _lock:
        if not hasattr(_row_of, "row"):
            _row_of.row = dict(zip(idx["id"], range(len(idx))))
    return idx, _row_of.row


_observations_lock = threading.Lock()


def _observations():
    """{(target, observation, instrument): the index's row numbers of its frames, in index order}, made once (a third of
    a second, as the server starts), so units finds an observation's frames in a lookup instead of comparing three
    fields of every frame in the index (70 ms the first time a server met each observation, on the request threads)"""
    idx, _ = reel.load_index()
    with _observations_lock:
        if not hasattr(_observations, "rows"):
            _observations.rows = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices
    return idx, _observations.rows


def units(target, obs, cam):
    """The passes of one camera's frames of one observation: [{key, frames: [(path, id, filter, t, nm, x, y, z)],
    mosaic, whole, z, last, repeat_gap}] in time order, from the index and the geometry cache. Repeat exposures
    (the same filter within the pass's repeat_gap, at the same pointing: _pictures) are left out, as
    stacking.load_hdr merges them in. repeat_gap
    is REPEAT_GAP, except in a movie that takes a filter more often than that (a spoke movie every 11 s): there it
    is half the movie's own pace, so every frame of the movie is its own picture rather than stacked with the
    next ones (repeat_window)."""
    with _lock:
        if (target, obs, cam) in _units:
            return _units[(target, obs, cam)]
    idx, observations = _observations()
    inst = "ISSNA" if cam == "N" else "ISSWA"
    at = observations.get((target, obs, inst))
    # the rows of idx[(idx["OBSERVATION_ID"] == obs) & (idx["TARGET_NAME"] == target) & (idx["INSTRUMENT_ID"] == inst)]
    rows = idx.iloc[at] if at is not None else idx.iloc[:0]
    where = reel.geometry(rows["id"].tolist())
    turned = reel.turns(rows["id"].tolist())
    out, cur = [], None
    for r in rows.itertuples(index=False):
        f1, f2 = str(r.filter1), str(r.filter2)
        f = "/".join(x for x in (f1, f2) if not x.startswith("CL")) or "CL1/CL2"
        g = where.get(r.id)
        t = float(r.seconds_1970)
        if cur is None or t - cur["last"] > GAP or (g and cur["z"] and not 1 / ZOOM < g[2] / cur["z"] < ZOOM):
            zoomed = cur is not None and t - cur["last"] <= GAP
            cur = {"frames": [], "all": [], "taken": [], "z": g and g[2], "last": t, "turns": turned, "zoomed": zoomed}
            out.append(cur)
        cur["last"] = t
        cur["taken"].append((f, *(g or (None, None, None))))   # every frame, repeats too, for _judge
        if not cur["z"] and g:
            cur["z"] = g[2]
        cur["all"].append((r.path, r.id, f, t, reel.wavelength(inst, f1 + f2), *(g or (None, None, None))))
    for u in out:
        u["frames"] = _pictures(u["all"], mosaic_benchmark.REPEAT_GAP)
    # laps: a mosaic taken again over the same places after a pause longer than GAP (the Jupiter approach's 2x2
    # color mosaics, six laps 74 minutes apart in one observation) is one pass, a mosaic movie, rather than a
    # mosaic that starts again from nothing every lap
    for u in out:
        _drop_strays(u)
    laps, shifted, relaid, retracked, rescanned, panned = [], False, False, False, False, False
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, len(laps))
        _judge(u)
        retracked = retracked or u["retracked"]
        rescanned = rescanned or u.get("rescanned", False)
        panned = panned or u["panned"]
        prev = laps[-1] if laps else None
        # (and one view taken lap after lap, a filter set each time, is one pass: a time series, _judge's views)
        views = bool(prev and (prev.get("drift") or prev.get("views")) and u.get("drift"))
        # (and a movie taken again on the same view after a pause longer than GAP, within LAP_GAP, is one movie: a
        # stare or a ride-along WAC whose observation pauses between its legs, 048SA_STRMOVIEC001's WAC every 100
        # minutes for 19 hours, 052SA_APOMOVIC001's twelve legs. Sam 2026-11-06, the movie catalog)
        views = views or _restare(prev, u)
        if (prev and (prev["mosaic"] or views) and u["frames"] and u["frames"][0][3] - prev["last"] <= LAP_GAP and u["z"]
                and 1 / ZOOM < u["z"] / prev["z"] < ZOOM
                and (views and _overlap(prev, u) >= LAP_OVERLAP
                     or not views and (u["mosaic"] and _overlap(prev, u) >= LAP_OVERLAP or _piece(prev, u)))):
            prev["views"] = views
            relaid = relaid or views   # (the passes after it are renumbered)
            # (a piece, or a lap that is a mosaic only by the newer rules, joining it renumbers the passes after it)
            shifted = shifted or not u["mosaic"] or any(v.get("pair") or v.get("off") for v in (prev, u))
            for k in ("frames", "all", "taken"):
                prev[k] += u[k]
            prev["last"] = u["last"]
            prev["off"] = prev.get("off", set()) | u.get("off", set())
            _judge(prev)
            rescanned = rescanned or prev["rescanned"]
            panned = panned or prev["panned"]
        elif prev and _zoom_join(prev, u, _ahead(out, n, (target, obs, cam, len(laps) + 1))):
            relaid = True   # (the passes after it are renumbered)
            rescanned = rescanned or prev["rescanned"]
            panned = panned or prev["panned"]
        else:
            laps.append(u)
    # a raster's lap that ZOOM cut short takes the tiles that finish it back from the pass after it
    if _lap_tails(laps):
        relaid = True   # (the passes after it change, or are renumbered)
    # a movie that re-points to sky it never comes back to plays each view as a pass of its own, and a mosaic that
    # holds separate scans (islands) draws each as a mosaic of its own
    # (a map joined or kept apart on its frames' ground, or a time series judged on places turned frame by frame,
    # otherwise than before: LAID's folder for every pass, as the pieces below are new dicts)
    laid = any(u.get("zoom_ground") or u.get("drifting") for u in laps)
    out, islands = [], False
    for u in laps:
        pieces = _retargets(u)
        relaid = relaid or len(pieces) > 1
        islands = islands or any(v.get("island") for v in pieces)
        out += pieces
    # a mosaic's lone frames show as themselves, and a mosaic of scattered frames is cut into its pieces (_scatter),
    # each pass judged as the loop below judges it first (a time series is no mosaic)
    # (a ring strip plays as a movie, below, its frames however far apart)
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, n)
        _judge(u)
    out = [v for u in out for v in ([u] if _ring(u) and _strip(u) else _scatter(u))]
    stripped = False
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, n)
        _judge(u)
        retracked = retracked or u["retracked"]
        rescanned = rescanned or u.get("rescanned", False)
        panned = panned or u["panned"]
        # a long thin scan across the rings plays as a movie, its mosaic pre-built besides it (a toss-up's, make_pass)
        u["strip"] = u["kind"] in ("mosaic", "mosaic_movie") and _ring(u) and _strip(u)
        if u["strip"]:
            u["kind"], u["movie"], u["mosaic"], u["tossup"] = "movie", True, False, True
            u["pair"] = u["slot_laps"] = u["whole"] = False
        stripped = stripped or u["strip"]
        # GROUPING's folder: a pass grouped anew (strays out, or a mosaic only as a 1x2), or every pass of an
        # observation whose passes these rules renumbered; RELAID's: a pass the layout rules after them changed, or
        # every pass of an observation they renumbered
        u["regrouped"] = bool(shifted or u.get("off") or u.get("pair"))
        u["repeat_gap"] = repeat_window(u)
        if u["repeat_gap"] < mosaic_benchmark.REPEAT_GAP:
            # (a movie's frames split anew, repeats closer than its own window kept apart: each frame placed again,
            # so u["place"] and what follows it (slots, lap_of) have one entry per frame, as 209TI_CLOUD002's did not)
            u["frames"] = _pictures(u["all"], u["repeat_gap"])
            u["place"] = _place_frames(u)
            for k in ("slots", "lap_of", "_lum", "_lap_prev"):
                u.pop(k, None)
        del u["all"]
        # the camera turning under a mosaic: its footprint is turned frame by frame (plan); a toss-up's too, which a
        # window draws as a mosaic as well (a ring strip: 033RI_AZDKMRHPH001 turns 135 degrees, 081RI_AZSCANDRK001
        # 32, and one angle drew their mosaics' tiles off the canvas)
        if (u["kind"] in ("mosaic", "mosaic_movie") or u["kind"] == "movie" and u.get("tossup")) and _twist(u, turned) > TWIST * FRAME:
            u["twist"] = {fr[1]: turned[fr[1]] for fr in u["frames"] if fr[1] in turned}
        # (and a mosaic whose filters aside a lone frame near the middle had decided: its plan draws other filters)
        u["aside"] = u["kind"] in ("mosaic", "mosaic_movie") and _aside(u["frames"], u) != _aside(u["frames"], u, 0, False)
        u["relaid"] = bool(relaid or u["revisit"] or u["drift"] or u["slot_laps"] or u.get("joined") or u.get("twist")
                           or u["aside"])
    # (TRACK_SPAN, the scan rule, the islands or a ride-along pan judged a pass otherwise can join or split passes: every pass)
    laid = laid or any(u.get("tossup") and u.get("twist") and u["kind"] == "movie" or u.get("drifting")
               or u.get("zoom_ground") or u.get("scattered") for u in out)
    for u in out:
        u["retracked"], u["rescanned"], u["islands"], u["panned"] = retracked, rescanned, islands, panned
        u["stripped"], u["laid"] = stripped, laid
    with _lock:
        _units[(target, obs, cam)] = out
    return out


LAP_TAIL_BODIES = ("SATURN", "JUPITER")   # (_lap_tails) the planets, whose rasters go round lap after lap as Cassini
                                          # closes in; a moon's flyby mosaics at two distances stay two (000PH, 194TI)


def _lap_tails(laps):
    """(units) A raster split at ZOOM in the middle of a lap (Cassini closing in, the camera going round the same
    places): the frames at the start of the pass after the split that finish the lap, at places of the pass before it
    its last lap has not taken yet, go back to that pass, and a pass that is all such frames joins it. The 2017-04-26
    north pole movie (271SA_NPOLMOV001 W) was cut at 02:43 and 05:12: its third lap lost its last pointing to the next
    pass, and its fifth lap's last four pointings were a pass of their own (a 4-tile mosaic). A frame's place there
    is on the pass's own canvas (scaled to its distance, as tiles are) and must lie within half the pass's step of
    one of its slots. The passes are judged again; a move that would change the first pass's kind (other than a
    mosaic becoming a mosaic movie) is not made. True when frames moved (the passes are renumbered, LAID's folder)."""
    moved, n = False, 0
    while n + 1 < len(laps):
        took = _lap_tail(laps[n], laps[n + 1])
        moved = moved or took
        if took and not laps[n + 1]["frames"]:
            del laps[n + 1]   # (and the pass after it may finish the lap further)
            continue
        n += 1
    return moved


def _lap_tail(a, b):
    """(_lap_tails) Moves the frames at the start of pass b that finish pass a's last lap into a; True when it did."""
    if not (b.get("zoomed") and a["key"][0] in LAP_TAIL_BODIES and a.get("kind") in ("mosaic", "mosaic_movie") and a.get("z") and b["frames"]
            and b["frames"][0][3] - a["last"] <= GAP):
        return False
    where = slots(a)
    lap = lap_of(a)
    at = {}
    for fr, i in zip(a["frames"], where):
        if i is not None and fr[7]:
            at.setdefault(i, []).append((-fr[5] * fr[7] / a["z"], -fr[6] * fr[7] / a["z"]))
    if len(at) < MIN_PLACES:
        return False
    centre = {i: np.mean(v, 0) for i, v in at.items()}
    pts = list(centre.values())
    step = float(np.median([min(max(abs(p[0] - q[0]), abs(p[1] - q[1])) for q in pts if q is not p) for p in pts]))
    last = max(lap)
    open_ = set(centre) - {i for i, n in zip(where, lap) if n == last and i is not None}
    if not open_:
        return False
    take, here = 0, None
    for fr in b["frames"]:
        if not fr[7]:
            break
        p = (-fr[5] * fr[7] / a["z"], -fr[6] * fr[7] / a["z"])
        i = min(centre, key=lambda k: max(abs(p[0] - centre[k][0]), abs(p[1] - centre[k][1])))
        if max(abs(p[0] - centre[i][0]), abs(p[1] - centre[i][1])) > step / 2 or not (i in open_ or i == here):
            break
        open_.discard(i)
        here = i
        take += 1
    if not take:
        return False
    t_end = b["frames"][take - 1][3]
    cut = sum(1 for x in b["all"] if x[3] <= t_end)   # ("all" and "taken" hold every frame, in the same order)
    trial = dict(a, frames=a["frames"] + b["frames"][:take], all=a["all"] + b["all"][:cut],
                 taken=a["taken"] + b["taken"][:cut], last=t_end)
    for k in ("slots", "lap_of", "_lum", "_lap_prev", "_lap_lead"):
        trial.pop(k, None)
    _judge(trial)
    if trial["kind"] != a["kind"] and not (a["kind"] == "mosaic" and trial["kind"] == "mosaic_movie"):
        return False
    rest = {"frames": b["frames"][take:], "all": b["all"][cut:], "taken": b["taken"][cut:]}
    a.clear()
    a.update(trial, tails=True)
    b.update(rest)
    for k in ("slots", "lap_of", "_lum", "_lap_prev", "_lap_lead"):
        b.pop(k, None)
    if b["frames"]:
        b["z"] = next((fr[7] for fr in b["frames"] if fr[7]), b["z"])
        _judge(b)
    return True


def _pictures(frames, gap):
    """The frames of a pass that are pictures (tiles) of their own: frames [(path, id, filter, t, nm, x, y, z)] in time
    order less the repeat exposures, a frame of a filter within gap seconds of a picture of that filter at the same
    pointing (stacking.repeat_of), which stacking.load_hdr merges into it. A frame at another pointing is a picture
    of its own however soon after: Phoebe 2004-06-11 goes back and forth between two pointings a minute apart, and
    the frames of one were merged into the other's tiles (its shadows over the other's bright ground)."""
    out, kept = [], {}
    for fr in frames:
        mine = kept.setdefault(fr[2], [])
        if stacking.repeat_of(mine, fr[3], fr[5:], gap) is None:
            mine.append((fr[3], fr[5:], fr))
            out.append(fr)
    return out


def _drop_strays(u):
    """Takes out of pass u the frames that are not of its sky: patches of frames (frames within STRAY_LINK frames
    of one another) away from the biggest one, together less than STRAY_SHARE of its placed frames, repeats too.
    The Jupiter approach's 2x2 laps have clear frames or one UV1 frame 38 to 430 frames off Jupiter, which
    made the lap's footprint too wide for a mosaic, so its tiles played on their own and split the mosaic movie in
    two. Their ids go in u["off"] (unit_of leaves them out of the pass, so they show as themselves) and the pass
    is regrouped (GROUPING). A pass whose frames all lie within MAX_FRAMES of one another is left as it is."""
    pts = [(q, -fr[5] * fr[7] / u["z"] / FRAME, -fr[6] * fr[7] / u["z"] / FRAME)
           for q, fr in enumerate(u["all"]) if fr[7] and u["z"]]
    if len(pts) < 2:
        return
    xy = np.array([(x, y) for _, x, y in pts])
    if (xy.max(0) - xy.min(0)).max() < MAX_FRAMES:
        return
    # patches: grid cells STRAY_LINK frames wide, a cell joined to the cells round it
    cells = {}
    for (q, x, y) in pts:
        cells.setdefault((math.floor(x / STRAY_LINK), math.floor(y / STRAY_LINK)), []).append(q)
    parent = {c: c for c in cells}

    def root(c):
        while parent[c] != c:
            c = parent[c]
        return c
    for (a, b) in cells:
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                if (a + da, b + db) in cells and root((a + da, b + db)) != root((a, b)):
                    parent[root((a + da, b + db))] = root((a, b))
    patch = {}
    for c, qs in cells.items():
        patch.setdefault(root(c), []).extend(qs)
    main = max(patch.values(), key=len)
    strays = {q for qs in patch.values() if qs is not main for q in qs}
    if not strays or len(strays) >= STRAY_SHARE * len(pts):
        return
    u["off"] = {u["all"][q][1] for q in strays}
    u["all"] = [fr for q, fr in enumerate(u["all"]) if q not in strays]
    u["taken"] = [fr for q, fr in enumerate(u["taken"]) if q not in strays]
    u["frames"] = [fr for fr in u["frames"] if fr[1] not in u["off"]]


def _piece(prev, u):
    """Pass u is the rest of mosaic prev's last lap: a few frames taken after a pause (too few places for a mosaic
    of their own, the camera not staying on them: a lap stopped short), at least LAP_INSIDE of them inside prev's
    footprint. 18ATM2X2A139's three frames at one place between two laps were a pass of their own, a movie, which
    kept the laps either side of it from being one mosaic movie."""
    if u["mosaic"] or not u["frames"] or (u["dwell"] or 0) >= MOVIE_DWELL or u["track"]:
        return False
    if len({i for i in u["place"] if i is not None}) >= MIN_PLACES:
        return False
    p, q = _box(prev, prev["z"]), _box(u, prev["z"])
    if not p or not q:
        return False
    w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
    return max(w, 0) * max(h, 0) >= LAP_INSIDE * (q[2] - q[0]) * (q[3] - q[1])


def _restare(prev, u):
    """Pass u takes up prev's movie again: both movies of one view (a stare, not a track, a pan or a ring strip),
    through a filter in common, their footprints sharing LAP_OVERLAP. The lap join in units then makes them one pass
    (its gap and distance rules: LAP_GAP, ZOOM)."""
    if not prev or not u["frames"]:
        return False
    still = lambda v: v["kind"] == "movie" and not (v.get("track") or v.get("panned") or v.get("strip") or v.get("tossup"))
    if not (still(prev) and still(u)):
        return False
    if not {fr[2] for fr in prev["frames"]} & {fr[2] for fr in u["frames"]}:
        return False
    return _overlap(prev, u) >= LAP_OVERLAP


def _box(u, z):
    """The footprint of pass u's placed frames (x0, y0, x1, y1, reference pixels at distance z from the body's centre)."""
    pts = [(-x * fz / z, -y * fz / z) for *_, x, y, fz in u["frames"] if fz]
    if not pts:
        return None
    pts = np.array(pts)
    return (*(pts.min(0) - HALF), *(pts.max(0) + HALF))


def _overlap(a, b):
    """How much the footprints of passes a and b cover the same ground: area both cover over area either covers."""
    p, q = _box(a, a["z"]), _box(b, a["z"])
    if not p or not q:
        return 0.0
    w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
    both = max(w, 0) * max(h, 0)
    either = (p[2] - p[0]) * (p[3] - p[1]) + (q[2] - q[0]) * (q[3] - q[1]) - both
    return both / either if either > 0 else 0.0


def _zoom_box(prev, u):
    """_zoom_join's tests on the rectangles: None when u cannot join prev at all (not both mosaics, more than GAP
    apart, a frame beyond JOIN_ZOOM), else (boxed, held, ...): boxed when the rectangles touch and u's is not
    LAP_INSIDE inside prev's, held when it is."""
    if prev["kind"] != "mosaic" or u["kind"] != "mosaic" or not u["frames"] or not prev["z"]:
        return None
    if u["frames"][0][3] - prev["last"] > GAP:
        return None
    zs = [fr[7] for fr in u["frames"] if fr[7]]
    if not zs or not (1 / JOIN_ZOOM < min(zs) / prev["z"] and max(zs) / prev["z"] < JOIN_ZOOM):
        return None
    p, q = _box(prev, prev["z"]), _box(u, prev["z"])
    if not p or not q:
        return None
    w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
    boxed = not (w <= 0 or h <= 0 or w * h >= LAP_INSIDE * (q[2] - q[0]) * (q[3] - q[1]))
    return boxed, w > 0 and h > 0 and not boxed


def _zoom_join(prev, u, nxt=None):
    """Joins pass u into prev when the two are one map that units split where the distance changed by ZOOM (Titan's
    042TI_GLOBMAP001: its middle, then the ring round it as Cassini closed in, drawn as two mosaics with a hole in the
    second): both mosaics, u straight after prev (within GAP), every frame of u within JOIN_ZOOM of prev's distance,
    u's footprint touching prev's and not a closer look at ground prev already took (LAP_INSIDE of it inside prev's),
    and the two still a mosaic together (tiles at another distance are scaled to the pass's, as ever). True when
    joined (prev is the joined pass). Touching and inside are measured on the ground the frames themselves cover
    (_ground), not on the rectangles round them: 129DI_REGMAP001's middle column, split at ZOOM from the ring of
    frames round Dione before it, lay inside that ring's rectangle, so it was taken for a closer look at ground the
    ring had taken and drawn as a pass of its own (the window showed half of Dione). A rule the rectangles judged
    otherwise marks both passes zoom_ground (LAID)."""
    box = _zoom_box(prev, u)
    if box is None:
        return False
    boxed, held = box   # (held: u's rectangle inside prev's, the only case the ground judges again)
    a, b = _ground(prev, prev["z"]), _ground(u, prev["z"])
    near = {(i + di, j + dj) for i, j in a for di in (-1, 0, 1) for dj in (-1, 0, 1)}
    # (the ground only adds joins: a pass the rectangles join stays joined, 016DI_TARGFLYBY001's closer look kept on)
    grounded = boxed or held and bool(b & near) and len(a & b) < LAP_INSIDE * len(b)
    if not (boxed or grounded):
        return False
    joined = dict(prev, **{k: prev[k] + u[k] for k in ("frames", "all", "taken")})
    joined.update(last=u["last"], off=prev.get("off", set()) | u.get("off", set()))
    _judge(joined)
    if joined["kind"] != "mosaic":
        return False
    # (a join only the ground allows is one map, not two scans the islands would cut apart again: 016DI_TARGFLYBY001's
    # two flyby mosaics joined were cut into other pieces than the two it had, splitting its second mosaic)
    if grounded and not boxed and len(_retargets(dict(joined))) > 1:
        grounded = False
    # (nor does the ground take u from the pass after it, that the rectangles join u to: 016DI_TARGFLYBY001's second
    # flyby mosaic, 40 frames then 29 at another distance, lost its first 40 to the mosaic before it)
    if grounded and not boxed and nxt is not None:
        ahead = _zoom_box(u, nxt)
        if ahead and ahead[0]:
            grounded = False
    if boxed != grounded:
        prev["zoom_ground"] = u["zoom_ground"] = joined["zoom_ground"] = True
    if not grounded:
        return False
    prev.clear()
    prev.update(joined, joined=True)
    return True


def _ahead(out, n, key):
    """The unit after out[n], judged as the laps loop will judge it (a copy: the loop judges it again), or None."""
    if n + 1 >= len(out):
        return None
    v = dict(out[n + 1], key=key)
    _judge(v)
    return v


def _ground(u, z):
    """The ground pass u's frames cover, at distance z: the cells (STRIP_GRID a frame) their squares cover, at their
    places turned frame by frame (_flat)."""
    G = STRIP_GRID
    xy = _flat(u) * (u["z"] / z) / FRAME
    ks = [fr[7] / z for fr in u["frames"] if fr[7]]
    cells = set()
    for (x, y), k in zip(xy, ks):
        for i in range(math.floor((x - k / 2) * G), math.ceil((x + k / 2) * G)):
            for j in range(math.floor((y - k / 2) * G), math.ceil((y + k / 2) * G)):
                cells.add((i, j))
    return cells


def _retargets(u):
    """Pass u in pieces where it re-points to sky it never comes back to: a movie is cut between two frames when no
    frame after them shares any ground with a frame before (their footprints, frames at the pass's distance, do not
    touch: a Grand Finale retarget's four ring patches in one movie, 287RI_PROPRETRG001, which jumped from view to
    view). A mosaic is cut there only between two islands (_island), not both on the body's disk: separate scans in one
    pass, each a mosaic of its own (the two ring ansae of a CIRS ride-along, 113RI_VTMPN60MP001 and 108RI_TMAPN30LP001;
    282RI_HIRESAFRG001's three strips of the A ring's edge), drawn as one mosaic of strips far apart on a canvas mostly
    empty. A sparse scan, its frames not touching one another (a satellite search, a ring scan of lone frames), has no
    islands and stays whole. A ride-along pan (_judge's panned) is cut as the movie it creeps as is: its two pans,
    one over each ansa (079RI_TEMPN20LP001), are two mosaics.
    [u] when there is nothing to cut (a pass going back and forth between two patches comes back, so is never cut)."""
    if u["kind"] not in ("movie", "mosaic", "mosaic_movie"):
        return [u]
    pts = [(q, -fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) for q, fr in enumerate(u["all"]) if fr[7]]
    if len(pts) < 2:
        return [u]
    xy = np.array([(x, y) for _, x, y in pts])
    movie = u["kind"] == "movie" or u.get("panned")
    if movie:
        lo, hi = np.minimum.accumulate(xy), np.maximum.accumulate(xy)   # the frames up to each one
        rlo, rhi = np.minimum.accumulate(xy[::-1])[::-1], np.maximum.accumulate(xy[::-1])[::-1]   # ... and from it on
        cuts = [i + 1 for i in range(len(pts) - 1) if ((rlo[i + 1] - hi[i] >= FRAME) | (lo[i] - rhi[i + 1] >= FRAME)).any()]
    else:
        # a mosaic, frame by frame (the frames before and after a cut each round the other's boxes, 282RI's third
        # strip between the first two): the latest frame each frame's footprint comes within ISLAND_GAP of
        near = (np.abs(xy[:, None] - xy[None]) < (1 + ISLAND_GAP) * FRAME).all(2)
        reach = np.maximum.accumulate(np.array([np.flatnonzero(row).max() for row in near]))
        cuts = [i + 1 for i in range(len(pts) - 1) if reach[i] <= i]
    if cuts and not movie:
        # (pts between two cuts: a mosaic keeps a cut only with an island either side of it)
        parts = list(zip([0] + cuts, cuts + [len(pts)]))
        ts = [u["all"][q][3] for q, _, _ in pts]
        pics = np.array([(-fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"], fr[3]) for fr in u["frames"] if fr[7]])
        solid = [_island(xy[a:b], pics[(pics[:, 2] >= ts[a]) & (pics[:, 2] <= ts[b - 1]), :2]) for a, b in parts]
        # (and two islands on the body's disk are pieces of one map, its middle drawn by another pass or not taken:
        # 129DI_REGMAP001's ring of frames round Dione, the middle closer in, split at ZOOM)
        radius = (RADIUS.get(u["key"][0]) or SMALL_RADIUS.get(u["key"][0], 0)) / (u["z"] * IFOV[u["key"][2]])
        on = [bool((np.hypot(*xy[a:b].T) < radius).any()) for a, b in parts]   # (a frame's middle on the disk)
        cuts = [b for k, (_, b) in enumerate(parts[:-1]) if solid[k] and solid[k + 1] and not (on[k] and on[k + 1])]
    if not cuts:
        return [u]
    cuts = [pts[i][0] for i in cuts]
    pieces = []
    for a, b in zip([0] + cuts, cuts + [len(u["all"])]):
        part = u["all"][a:b]
        z = next((fr[7] for fr in part if fr[7]), None)
        pieces.append({"key": u["key"], "all": part, "taken": u["taken"][a:b], "z": z, "last": part[-1][3],
                       "frames": [fr for fr in u["frames"] if part[0][3] <= fr[3] <= part[-1][3]], "turns": u.get("turns"),
                       **({"off": u["off"]} if u.get("off") else {})})
    if not movie:
        # (each island a mosaic of its own, or the pass stays whole: a feature track or a time series in one of them
        # is a pass the rules above judged as a whole)
        for v in pieces:
            v["island"] = True
            _judge(v)
        if any(v["kind"] not in ("mosaic", "mosaic_movie") for v in pieces):
            return [u]
    return pieces


def _island(xy, pics):
    """(_retargets) Frames at canvas places xy (reference pixels, repeats too) are an island: its pictures (at pics)
    at MIN_PLACES places at least (mosaic.min_step apart), every frame's footprint joined to the others' through
    footprints less than ISLAND_GAP apart. A colour set at one pointing is no island, nor a pair of filters, nor a few
    lone frames."""
    places = []
    for p in pics:
        if all(np.abs(p - q).max() >= mosaic.min_step * FRAME for q in places):
            places.append(p)
    if len(places) < MIN_PLACES:
        return False
    near = (np.abs(xy[:, None] - xy[None]) < (1 + ISLAND_GAP) * FRAME).all(2)
    seen, todo = {0}, [0]
    while todo:
        for j in np.flatnonzero(near[todo.pop()]):
            if j not in seen:
                seen.add(int(j))
                todo.append(int(j))
    return len(seen) == len(xy)


def _twist(u, turned):
    """How far (reference pixels) the camera turning under pass u (reel.turns: degrees from north up, frame by frame)
    moves its frames from where the turn of its first frame placed well off the body (as plan measures it) puts them."""
    ref = next((turned[fr[1]] for fr in u["frames"] if fr[7] and fr[1] in turned and math.hypot(fr[5], fr[6]) > 200), None)
    if ref is None or not u["z"]:
        return 0.0
    most = 0.0
    for fr in u["frames"]:
        if fr[7] and fr[1] in turned:
            d = (math.radians(turned[fr[1]] - ref) + math.pi) % (2 * math.pi) - math.pi
            most = max(most, abs(d) * math.hypot(fr[5], fr[6]) * fr[7] / u["z"])
    return most


def _flat(u, frames=None, turned=True):
    """Where pass u's frames (u["frames"], or frames: u["all"]) with a place sit on its canvas (reference pixels at its
    distance from the body's centre, an N x 2 array, in order): -x, -y scaled to the pass's distance, and, on a pass
    the camera turns under (TWIST, its frames' turns u["turns"] from reel.turns), turned frame by frame to its first
    turned frame's angle, as footprint draws them (the camera's own axes otherwise turn with it: 175SA_NPOLVORT001
    rolls 28 degrees over its seven laps of the polar vortex, so the same view, 16,000 px from Saturn's centre, seemed
    to step a frame a lap; 281SA_HIRESWACS001 turns 70 degrees along its strip). turned False: on the camera's axes
    alone, as the layout rules judged before LAID."""
    frames = u["frames"] if frames is None else frames
    k = [(fr[1], -fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) for fr in frames if fr[7]]
    if not k:
        return np.zeros((0, 2))
    xy = np.array([(x, y) for _, x, y in k], float)
    turns = u.get("turns") or {}
    if not turned or not turns or _twist(u, turns) <= TWIST * FRAME:
        return xy
    ref = next((turns[fid] for fid, _, _ in k if fid in turns), None)
    a = np.radians([ref - turns[fid] if fid in turns else 0.0 for fid, _, _ in k])
    c, s = np.cos(a), np.sin(a)
    return np.stack([c * xy[:, 0] - s * xy[:, 1], s * xy[:, 0] + c * xy[:, 1]], 1)


def _turns(u):
    """Pass u is one the camera turns under (TWIST): _flat turns its frames' places."""
    turns = u.get("turns") or {}
    return bool(turns) and bool(u.get("z")) and _twist(u, turns) > TWIST * FRAME


def _touching(xy, ks):
    """(N x N) which frames at canvas places xy (reference pixels), each ks of a frame across (its distance over the
    pass's), touch: their squares overlap, or are no more than TOUCH_GAP of a frame apart."""
    side = ((ks[:, None] + ks[None]) / 2 + TOUCH_GAP) * FRAME
    return (np.abs(xy[:, None] - xy[None]) < side[..., None]).all(2)


def _lone(u, frames=None, turned=True):
    """The ids of mosaic u's lone frames: the frames at a place (mosaic.min_step) that no frame at another of its places
    touches, so its tile stands apart on the canvas, with black sky round it (006TI_HIGHRESNA001's five stares at Titan
    two to three frames apart, 101SA_AURORA002's pointings four frames apart, 281SA_HIRESWACS001's two frames off the
    end of its strip). A colour set at one pointing touches only itself, so a mosaic of one place has none."""
    placed = [fr for fr in (u["frames"] if frames is None else frames) if fr[7]]
    if len(placed) < 2:
        return set()
    xy = _flat(u, placed, turned)
    ks = np.array([fr[7] / u["z"] for fr in placed])
    places, at = [], []
    for p in xy:
        q = next((j for j, c in enumerate(places) if np.abs(p - c).max() < mosaic.min_step * FRAME), None)
        if q is None:
            places.append(p)
            q = len(places) - 1
        at.append(q)
    at = np.array(at)
    if len(places) < 2:
        return set()
    touch = _touching(xy, ks) & (at[:, None] != at[None])
    lone_place = {j for j in range(len(places)) if not touch[at == j].any()}
    return {fr[1] for fr, j in zip(placed, at) if j in lone_place}


def _scatter(u):
    """Mosaic u with its lone frames (_lone, repeats too) out: fewer than LONE_SHARE of its frames, they show as single
    pictures (u["off"], as _drop_strays' strays do) and the rest stays the mosaic it is ([u], u changed); more, or
    what is left no mosaic, and it is no mosaic but frames scattered over the sky (a sparse scan: a satellite search,
    006TI_HIGHRESNA001's stares, 101SA_AURORA002's pointings round one long stare), cut between every two frames in a
    row that do not touch into pieces, each judged on its own (a colour set, a stare, a picture). Either marks the
    pieces scattered (LAID). [u] as it was when it has none."""
    if u["kind"] != "mosaic":
        return [u]
    lone = _lone(u, u["all"])
    if not lone:
        return [u]
    placed = sum(1 for fr in u["all"] if fr[7])
    if len(lone) < LONE_SHARE * placed:
        keep = [q for q, fr in enumerate(u["all"]) if fr[1] not in lone]
        v = dict(u, all=[u["all"][q] for q in keep], taken=[u["taken"][q] for q in keep],
                 frames=[fr for fr in u["frames"] if fr[1] not in lone], off=set(u.get("off", ())) | lone)
        v["last"] = v["all"][-1][3]
        _judge(v)
        if v["kind"] in ("mosaic", "mosaic_movie"):
            u.clear()
            u.update(v, scattered=True)
            return [u]
    pts = [q for q, fr in enumerate(u["all"]) if fr[7]]
    xy = _flat(u, u["all"])
    ks = np.array([u["all"][q][7] / u["z"] for q in pts])
    touch = _touching(xy, ks)
    cuts = [pts[i + 1] for i in range(len(pts) - 1) if not touch[i, i + 1]]
    pieces = []
    for a, b in zip([0] + cuts, cuts + [len(u["all"])]):
        part = u["all"][a:b]
        z = next((fr[7] for fr in part if fr[7]), None)
        v = {"key": u["key"], "all": part, "taken": u["taken"][a:b], "z": z, "last": part[-1][3],
             "frames": [fr for fr in u["frames"] if part[0][3] <= fr[3] <= part[-1][3]], "turns": u.get("turns"),
             "scattered": True, **({"off": u["off"]} if u.get("off") else {})}
        _judge(v)
        pieces.append(v)
    return pieces


def _one_view(u):
    """Pass u shows one view, not a mosaic: the frames its mosaic draws (its luminance base's filters, as plan and
    luminance_of choose them) all lie within mosaic.min_step of the first, or the camera drifts through a set of
    filters (each frame within REGISTER_GAP and SAME_PLACE of the one before, or all on a steady drift, at least
    three filters and none taken more than twice: a storm rider's five filters sliding 0.7 of a frame, the Moon's nine
    in 1999, Mimas's fifteen in 072MI_MIDIECLN001), so its mosaic is offset strips of one picture. Its frames and colour sets show as themselves."""
    aside = _aside(u["frames"], u)
    count = collections.Counter(fr[2] for fr in u["frames"] if fr[2] not in aside) or collections.Counter(fr[2] for fr in u["frames"])
    grey = max(count, key=count.get)
    pts = [(f, t, -x * z / u["z"], -y * z / u["z"]) for _, _, f, t, _, x, y, z in u["frames"]
           if z and f in count and (f == grey or not _polarizer(f))]
    if not pts:
        return False
    if all(max(abs(p[2] - pts[0][2]), abs(p[3] - pts[0][3])) < mosaic.min_step * FRAME for p in pts):
        return True
    taken = collections.Counter(p[0] for p in pts)
    if len(taken) < 3 or max(taken.values()) > 2:
        return False
    if any(b[1] - a[1] > REGISTER_GAP for a, b in zip(pts, pts[1:])):
        return False
    if all(math.hypot(b[2] - a[2], b[3] - a[3]) <= SAME_PLACE * FRAME for a, b in zip(pts, pts[1:])):
        return True
    # or the camera drifts at a steady rate through the set, further than SAME_PLACE between two long exposures, but
    # less than DRIFT_SET in all (the B ring edge sets, 063RI_BEDG4FILT001 to 065RI: UV3, GRN, RED, IR2 sliding 0.6 to
    # 1.3 of a frame, 0.004 of a frame a second; drawn as a mosaic they were a staircase of seams)
    t = np.array([p[1] for p in pts]) - pts[0][1]
    xy = np.array([p[2:] for p in pts]) / FRAME
    if not t[-1] or np.hypot(*(xy[-1] - xy[0])) >= DRIFT_SET:
        return False
    rate = (xy[-1] - xy[0]) / t[-1]
    return bool(np.abs(xy - xy[0] - t[:, None] * rate).max() <= DRIFT_FIT)


def _revisits(u):
    """Pass u is a time series, not a mosaic: most of its frames that take a filter again (REVISIT_SHARE) come back
    after a pause (REVISIT_PAUSE) to the view of one frame of that filter taken before the pause (LAP_OVERLAP of the
    frame), a little way off, so they counted as new places, and they come back at least twice (one return is a
    two-tile mosaic with a wide overlap): Saturn's limb sampled every 28 minutes (267SA_LIMBINT002), the WAC beside a
    NAC feature track (191SA_FEATRAK001), a CIRS feature track's two or three filters every few minutes (FTRACK),
    Titan's cloud monitors. A mosaic steps on to new ground, even where it overlaps its earlier columns
    (221DI_REGMAP001's interleaved columns, 242SA_NHEMOSAIC001's slow steps); a dense strip overlaps the frames just
    before it, taken without a pause. A scan that pauses between its pointings steps on too, though its frames after a
    pause overlap the ones before it (_scan); u["rescanned"] says the time-series rule alone would have called it one."""
    u["rescanned"] = False
    fr = [(f, t, -x * z / u["z"] / FRAME, -y * z / u["z"] / FRAME) for _, _, f, t, _, x, y, z in u["frames"] if z]
    if len(fr) < 3:
        return False
    gaps = np.diff([q[1] for q in fr])
    pause = max(REVISIT_PAUSE * float(np.median(gaps)), REGISTER_GAP)
    seen, start, back, again, returns = {}, 0, 0, 0, set()
    for i, (f, t, x, y) in enumerate(fr):
        if i and gaps[i - 1] >= pause:
            start = i   # (frames before start were taken before a pause)
        mine = seen.setdefault(f, [])
        if mine:
            again += 1
            if any(j < start and (1 - abs(a - x)) * (1 - abs(b - y)) >= LAP_OVERLAP
                   for j, a, b in mine if abs(a - x) < 1 and abs(b - y) < 1):
                back += 1
                returns.add(start)
        mine.append((i, x, y))
    if not (len(returns) >= 2 and back >= REVISIT_SHARE * again):
        return False
    if _reraster(u) or _named_map(u):
        return False
    u["rescanned"] = _scan(np.array([q[2:] for q in fr]), np.split(np.arange(len(fr)), np.flatnonzero(gaps >= pause) + 1))
    return not u["rescanned"]


RERASTER_ORDER = 0.75   # (_reraster) of the steps between the places a raster takes again, this share at least follow
                        # the order it first took them in ...
RERASTER_STEP = 0.3     # ... and its first lap steps (median) at least this much of a frame from place to place, as a
                        # mosaic's tiles do; a camera creeping along with the clouds steps less (234SA_WIND5HR005: 0.2)


def _reraster(u):
    """(_revisits) Pass u's returns are a raster taken again, not a time series: after its first return to a place,
    the camera goes round at least MIN_PLACES of the places it took before, in the order it first took them (most
    steps, RERASTER_ORDER, from one place to the place it first took next), as a mosaic movie's laps do. A time
    series comes back to one view or a few (267SA_LIMBINT002, Titan's cloud monitors, a FTRACK's filters), or creeps
    along with what it follows in steps smaller than a mosaic's (RERASTER_STEP: the 5-hour wind movies). The 2017
    north pole movie, 271SA_NPOLMOV001, split at ZOOM as Cassini closed in: its fourth lap and the start of its fifth
    were judged a time series, so its whole frames were single tiles."""
    seq = []
    for p in u.get("place") or []:
        if p is not None and (not seq or seq[-1] != p):
            seq.append(p)
    first, seen = None, set()
    for k, p in enumerate(seq):
        if p in seen:
            first = k
            break
        seen.add(p)
    if first is None:
        return False
    order = {p: k for k, p in enumerate(dict.fromkeys(seq[:first]))}
    at = u.get("places_at") or []
    lap = [at[p] for p in order if p < len(at)]
    if len(lap) < 2 or float(np.median([max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(lap, lap[1:])])) < RERASTER_STEP * FRAME:
        return False
    again = [p for p in seq[first:] if p in order]
    if len(set(again)) < MIN_PLACES:
        return False
    steps = list(zip(again, again[1:]))
    return sum(order[b] == order[a] + 1 for a, b in steps) >= RERASTER_ORDER * len(steps)


MAP_NAMES = ("MAP", "MOSAIC")   # (_named_map) a Saturn observation's purpose naming a map or a mosaic


def _named_map(u):
    """(_revisits) Pass u's observation is named a map or a mosaic (MAP_NAMES in its purpose, _name): its frames
    retaking neighbouring views after pauses are a tight map, one pointing every few minutes, not a time series. The
    2017 north pole maps (261SA_NPOLMAP001, 267SA_NPOLMAP002, 292SA_NPOLEMAP001: WAC frames overlapping by 0.6-0.8
    of a frame, each pointing after a pause) played as movies of single tiles. A time series is named for what it
    watches (LIMBINT, FEATRAK, FTRACK, MONITOR, CLOUD). Saturn only: a Titan map's WAC frames each holding most of
    the disk, a fifth of a frame apart, stay movies (059TI_GLOBMAP001, 153TI_FIRNADMAP001)."""
    name = _name(u["key"][1])
    return bool(u["key"][0] == "SATURN" and name and any(m in name[3:] for m in MAP_NAMES))


def _drifting(u):
    """Pass u is a time series of one view drifting over the canvas: its frames are laps (a lap ends where a filter
    comes again), at least MIN_PLACES of them, the places of laps in a row overlapping by at least DRIFT_LAPS of a
    frame (median), and the camera creeps rather than steps: its frames' places follow a smooth curve in time (within
    DRIFT_FIT of a frame of a parabola), as a raster's steps between its pointings do not. The camera holds a feature
    while the view of it changes: 175SA_NPOLVORT001 takes its seven filters of Saturn's north polar vortex every 50
    minutes for six hours as Cassini climbs, and the pole moves 2,200 px across the canvas (half a frame a lap, slowing
    to a tenth), so drawn as a mosaic the one vortex showed five times. Places are turned frame by frame where the
    camera turns under the pass (_flat: it rolls 28 degrees). u["drifting"] says it (LAID)."""
    placed = [fr for fr in u["frames"] if fr[7]]
    if len(placed) < 2 * MIN_PLACES:
        return False
    xy = _flat(u, placed) / FRAME
    laps, seen = [[]], set()
    for i, fr in enumerate(placed):
        if fr[2] in seen:
            laps.append([])
            seen = set()
        seen.add(fr[2])
        laps[-1].append(i)
    if len(laps) < MIN_PLACES or min(len(a) for a in laps) < 2:
        return False
    at = np.array([xy[a].mean(0) for a in laps])
    if np.ptp(at, 0).max() < mosaic.min_step:
        return False   # (one place: no drift, the rules above judge it)
    if float(np.median(np.clip(1 - np.abs(np.diff(at, axis=0)), 0, 1).prod(1))) < DRIFT_LAPS:
        return False
    t = np.array([fr[3] for fr in placed], float)
    t = (t - t[0]) / max(t[-1] - t[0], 1.0)
    if max(np.abs(np.polyval(np.polyfit(t, xy[:, k], 2), t) - xy[:, k]).max() for k in (0, 1)) > DRIFT_FIT:
        return False
    u["drifting"] = True
    return True


def _name(obs):
    """The purpose an observation's name gives, without its number: ISS_262RI_PROPRETRG003_PRIME -> RI_PROPRETRG
    (the target code and the activity; the instrument in charge and the riders are left out); None for a name not
    in the planning form (ICO_CALLAMPS)."""
    m = re.match(r"^[A-Z]+_(?:C\d+|\d{3}|\d{2}[A-Z]|000)([A-Z]{2})_([A-Z0-9]+?)\d*_[A-Z]+$", obs)
    return m and m.group(1) + "_" + m.group(2)


def _ride_along(u):
    """Pass u is the WAC riding along on a CIRS ring scan (RIDE_ALONG)."""
    name = _name(u["key"][1])
    return bool(u["key"][2] == "W" and name and name[:2] in RINGS and name[3:].startswith(RIDE_ALONG))


def _ring(u):
    """Pass u looks at Saturn's rings: Saturn its target and a ring its name's target code (RINGS)."""
    name = _name(u["key"][1])
    return bool(u["key"][0] == "SATURN" and name and name[:2] in RINGS)


def _strip(u):
    """(units) Pass u's frames, each a frame square at its place, cover a long thin strip: the rectangle with their
    union's area A and perimeter P (L + W = P / 2, L W = A, on a grid of STRIP_GRID cells a frame), which follows an
    arc of ring as it does a straight strip, is at least STRIP_LONG frames long and at most STRIP_WIDE wide."""
    pts = np.array([(-x * z / u["z"], -y * z / u["z"]) for *_, x, y, z in u["frames"] if z]) / FRAME
    if len(pts) < 2:
        return False
    k = STRIP_GRID
    lo = pts.min(0) - 0.5
    w, h = np.ceil((pts.max(0) + 0.5 - lo) * k).astype(int) + 2
    if w * h > 4e6:
        return False
    grid = np.zeros((h, w), bool)
    for p in pts:
        x, y = np.round((p - 0.5 - lo) * k).astype(int) + 1
        grid[y:y + k, x:x + k] = True
    area = grid.sum() / k ** 2
    half = (np.sum(grid[:, 1:] != grid[:, :-1]) + np.sum(grid[1:] != grid[:-1])) / k / 2
    root = math.sqrt(max(half * half - 4 * area, 0))
    return bool((half + root) / 2 >= STRIP_LONG and (half - root) / 2 <= STRIP_WIDE)


def _scan(xy, runs):
    """(_revisits) The frames of a pass at canvas places xy (in frames), in runs between pauses, are a scan that pauses
    between its pointings, not a time series: each run steps over places of its own (median, mosaic.min_step: a CIRS
    ride-along stepping across the rings, IOSIC_113RI_VTMPN60MP001; a whole map taken lap after lap,
    C23JU_NSMAP101), or the runs' pointings step on by one step each way they head (a raster: SCAN_STEP, SCAN_EVEN,
    SCAN_TURN; 028RI_HIPHASE001's colour set at each of a 2 x 4 raster, 026RI_LATPHASE001 stepping up the rings).
    A time series drifts unevenly or not at all (267SA_LIMBINT002), stops (Titan's cloud monitors) or speeds up (the
    wind movies); a heading taken once says nothing of its step."""
    if np.median([np.ptp(xy[r], 0).max() for r in runs]) >= mosaic.min_step:
        return True
    steps = np.diff(np.array([np.median(xy[r], 0) for r in runs]), axis=0)
    if len(steps) < 2:
        return False
    size = np.abs(steps).max(1)
    heads, way = [], []
    for w in np.arctan2(steps[:, 1], steps[:, 0]):
        k = next((k for k, h in enumerate(heads) if abs((w - h + math.pi) % (2 * math.pi) - math.pi) < math.radians(SCAN_TURN)), None)
        if k is None:
            heads.append(w)
            k = len(heads) - 1
        way.append(k)
    way = np.array(way)
    return bool(size.min() >= SCAN_STEP and np.bincount(way).min() >= 2
                and all(np.abs(size[way == k] - np.median(size[way == k])).max() <= SCAN_EVEN for k in range(len(heads))))


def _slot_laps(u):
    """How many times (median over its slots, in one filter) pass u comes back to a slot: a lap over places a little
    way off the last lap's (slots) counts as a lap, not as new places."""
    where, runs = _slot_of(u, u["place"]), {}
    for fr, i in zip(u["frames"], where):
        if i is not None:
            seq = runs.setdefault(fr[2], [])
            if not seq or seq[-1] != i:
                seq.append(i)
    visits = [max(seq.count(i) for seq in runs.values()) for i in {i for i in where if i is not None}]
    return int(np.median(visits)) if visits else 0


def repeat_window(u):
    """How close two frames of one filter must be for stacking to merge them as repeat exposures, for pass u:
    REPEAT_GAP, or in a movie (u["movie"]) whose same-filter frames come more often than twice that, half the
    median time between them, so the movie's frames are not stacked into one another (which blurs what moves
    and puts later frames into earlier ones)."""
    if not u.get("movie"):
        return mosaic_benchmark.REPEAT_GAP
    last, gaps = {}, []
    for fr in u["all"]:
        if fr[2] in last:
            gaps.append(fr[3] - last[fr[2]])
        last[fr[2]] = fr[3]
    g = float(np.median(gaps)) if gaps else 2 * mosaic_benchmark.REPEAT_GAP
    return min(mosaic_benchmark.REPEAT_GAP, round(g / 2, 1)) if g < 2 * mosaic_benchmark.REPEAT_GAP else mosaic_benchmark.REPEAT_GAP


def _place_frames(u):
    """u["place"] for each of u["frames"]: the index of the nearest of the pass's places (u["places_at"], _judge's,
    on the pass's canvas), None when SPICE has no place for the frame."""
    places, out = u["places_at"], []
    for *_, x, y, z in u["frames"]:
        if not z or not places:
            out.append(None)
            continue
        p = (-x * z / u["z"], -y * z / u["z"])
        out.append(min(range(len(places)), key=lambda j: max(abs(p[0] - places[j][0]), abs(p[1] - places[j][1]))))
    return out


def _judge(u):
    """Sets u["movie"] (the camera creeps or stares), u["jump_frac"], u["dwell"], u["mosaic"] (enough places,
    footprint not too big, not a movie), u["whole"] (the body's disk inside it), u["place"], u["repeats"] and
    u["kind"]: "movie", "mosaic", "mosaic_movie" (a mosaic whose places are taken lap after lap) or None, and
    u["track"] (the camera follows a moving feature: a movie); a pass the later layout rules judge says which
    (u["slot_laps"], u["drift"], u["revisit"])."""
    for k in ("slots", "lap_of", "_lum"):   # (worked out from the frames the pass had when last judged)
        u.pop(k, None)
    pts = [(-x * z / u["z"], -y * z / u["z"]) for _, _, _, _, _, x, y, z in u["frames"] if z]
    # the steps between consecutive frames of one filter, in frames: a mosaic jumps, a movie creeps. A creep that
    # adds up to a jump over one repeat window is a jump too: the step is also taken from the filter's latest frame
    # at least REPEAT_GAP (and at most twice that) earlier, as long as the camera only crept since. Every frame at a
    # pointing of its own is a picture (stacking.repeat_of), so a scan sweeping on a little each frame
    # (ISS_013RI_AZSCNHIPH001: 0.1 of a frame every 73 s, 13 frames of ring in all) creeps under mosaic.min_step
    # frame to frame, but jumps over the window, as it did when each window's frames made one tile
    gap, creep, steps, own = mosaic_benchmark.REPEAT_GAP, {}, [], []
    for _, _, f, t, _, x, y, z in u["frames"]:
        if z:
            p = (-x * z / u["z"], -y * z / u["z"])
            run = creep.setdefault(f, collections.deque())   # the filter's frames since its last jump
            if run:
                step = max(abs(p[0] - run[-1][1][0]), abs(p[1] - run[-1][1][1])) / FRAME
                own.append(step)
                if step >= mosaic.min_step:
                    run.clear()
                else:
                    while run and t - run[0][0] > 2 * gap:
                        run.popleft()
                    back = next((q for w, q in reversed(run) if t - w >= gap), None)
                    if back is not None:
                        step = max(step, abs(p[0] - back[0]) / FRAME, abs(p[1] - back[1]) / FRAME)
                steps.append(step)
            run.append((t, p))
    # no filter taken twice: the luminance base draws every filter's tiles in one gray mosaic, so the steps are
    # counted between consecutive frames whatever their filter. A scan that steps one filter a pointing (a limb
    # scan, a methane band map) jumps every frame and is a mosaic; a stare cycling its filters stays put and is a movie
    if not steps:
        prev = None
        for _, _, f, _, _, x, y, z in u["frames"]:
            if z:
                p = (-x * z / u["z"], -y * z / u["z"])
                if prev is not None:
                    steps.append(max(abs(p[0] - prev[0]), abs(p[1] - prev[1])) / FRAME)
                prev = p
    u["jump_frac"] = float(np.mean([s >= mosaic.min_step for s in steps])) if steps else None
    # ... but only a pass that can be a mosaic is one for creeping over the window, and only when the creep takes it
    # past its own field: a ring survey too big for one (ISS_241RI_PROPSURVY001, 057RI_AZSCAN001), or a propeller
    # retarget's view drifting under a frame in all (ISS_277RI_PROPRETRG001), creeping frame to frame, stays the movie
    # it plays as
    crept = bool(own) and float(np.mean([s >= mosaic.min_step for s in own])) < MOVIE_JUMPS
    if crept and pts and max(np.ptp([p[0] for p in pts]), np.ptp([p[1] for p in pts])) < FRAME:
        u["jump_frac"] = float(np.mean([s >= mosaic.min_step for s in own]))
    # dwell: over every frame taken (repeat exposures too, which the tiles merge), how many frames of one filter
    # the camera takes at a place before it jumps. A raster takes one to a few per pointing; a movie films the
    # same field for minutes (a spoke movie going back and forth between two patches of ring, one frame every
    # 11 s, looks like a jump every tile once its repeats are merged)
    last, runs = {}, []
    for f, x, y, z in u.get("taken", ()):
        if not z:
            continue
        p = (-x * z / u["z"], -y * z / u["z"])
        if f in last and max(abs(p[0] - last[f][0][0]), abs(p[1] - last[f][0][1])) < mosaic.min_step * FRAME:
            last[f] = [p, last[f][1] + 1]   # from the frame before, so a field drifting slowly stays one place
        else:
            if f in last:
                runs.append(last[f][1])
            last[f] = [p, 1]
    runs += [n for _, n in last.values()]
    u["dwell"] = float(np.median(runs)) if runs else None
    # track: the camera follows something that moves across the body (a cloud feature, FEATRAK), so the filters of
    # one pointing do not land on one another: ISS_191SA_FEATRAK001 creeps 0.13 of a frame over each 10-filter visit
    # (and one CB3 frame sits 585 px off), ISS_222SA_FEATRAK001 drifts all the way through. Drawn as a mosaic that
    # makes narrow colour strips and doubled limbs, so it plays as a movie. A visit is a run of frames through
    # different filters, each within REGISTER_GAP and SAME_PLACE of the one before; in a mosaic a visit holds still
    # (SPICE within REGISTER_MAX, what registration believes), in a track its frames spread over more than TRACK_SPAN
    # (median over the pass's visits of three or more frames). A raster stepping a pointing every frame has no visits.
    # The spread is where SPICE puts each frame on the pass's canvas (body centred, at its reference distance), which
    # already follows the spacecraft; what is left in a close flyby is the view turning as Cassini passes (parallax).
    # So on a body whose turning is known (SPIN) a pass is a track only where that turning can carry a surface feature
    # across at least TRACK_CARRY of the spread in a visit's time: Saturn's clouds 10 km/s, a moon's surface centimetres
    # to metres a second, so a moon's regional map stays a mosaic. A target with no body (rings named by themselves,
    # the sky) keeps the spread alone.
    spans, visit, took = [], [], []
    for _, _, f, t, _, x, y, z in u["frames"]:
        if not z:
            continue
        p = (-x * z / u["z"], -y * z / u["z"], t, f)
        if visit and (t - visit[-1][2] > REGISTER_GAP or f in {q[3] for q in visit}
                      or math.hypot(p[0] - visit[-1][0], p[1] - visit[-1][1]) > SAME_PLACE * FRAME):
            if len(visit) >= 3:
                spans.append(max(math.hypot(a[0] - c[0], a[1] - c[1]) for a in visit for c in visit) / FRAME)
                took.append(visit[-1][2] - visit[0][2])
            visit = []
        visit.append(p)
    if len(visit) >= 3:
        spans.append(max(math.hypot(a[0] - c[0], a[1] - c[1]) for a in visit for c in visit) / FRAME)
        took.append(visit[-1][2] - visit[0][2])
    spread = float(np.median(spans)) if len(spans) >= TRACK_VISITS else 0.0
    spin = SPIN.get(u["key"][0])
    carried = (2 * math.pi * spin[0] / (spin[1] * 3600) * float(np.median(took)) / (u["z"] * IFOV[u["key"][2]]) / FRAME
               if spread and spin and u["z"] else None)

    def track(span):
        return bool(spread > span and (carried is None or carried >= TRACK_CARRY * spread))
    u["retracked"] = track(TRACK_SPAN_WAS) != track(TRACK_SPAN)

    def movie(lean):
        # (lean 1 toward a movie, -1 away from one: each threshold moved by its LEAN margin, to find the toss-ups,
        # whose both kinds prebuild.make_pass draws; an island of a mosaic, _retargets, steps over MIN_PLACES places
        # however slowly it creeps: 108RI_TMAPN30LP001's second ring ansa steps 0.14 of a frame, under
        # mosaic.min_step, every 527 s)
        span = TRACK_SPAN - lean * LEAN_SPAN
        slow = (u["jump_frac"] is not None and not u.get("island")
                and (u["jump_frac"] < MOVIE_JUMPS + lean * LEAN_JUMPS
                     or (u["dwell"] or 0) >= MOVIE_DWELL - lean * LEAN_DWELL))
        return u["jump_frac"] is not None and (slow or track(span)), track(span)
    u["tossup"] = movie(-1)[0] != movie(1)[0]
    u["movie"], u["track"] = movie(0)
    places = []
    for p in pts:
        if all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) >= mosaic.min_step * FRAME for q in places):
            places.append(p)
    # u["place"]: for each of u["frames"], the place it was taken at (index into places; None when SPICE has no
    # place for it). visits: how many separate times the camera comes back to a place in one filter; a mosaic
    # takes each place once per filter, a mosaic movie goes round the same places again and again (laps)
    u["places_at"] = places
    u["place"] = _place_frames(u)
    runs = {}
    for fr, i in zip(u["frames"], u["place"]):
        if i is None:
            continue
        seq = runs.setdefault(fr[2], [])
        if not seq or seq[-1] != i:
            seq.append(i)
    visits = [max(seq.count(i) for seq in runs.values()) for i in range(len(places))] if runs else []
    u["repeats"] = int(np.median(visits)) if visits else 0
    # laps over places the camera drifted off (slots, as a mosaic movie plays them) are laps, not new places
    laps = _slot_laps(u)
    u["slot_laps"] = len(places) >= 2 and u["repeats"] < MOVIE_LAPS <= laps
    u["repeats"] = max(u["repeats"], laps)
    # a CIRS ride-along panning across the rings a little each frame (RIDE_PAN) shows new ring every frame: a strip
    # mosaic, as its sister passes that step faster are (057RI_TEMPL10LP001 against 061RI_TEMPL30MP001). Its pans and
    # its holds creep alike, so only the observation's purpose tells them from a pan along a ring (one view, a movie)
    u["panned"] = bool(u["movie"] and not u["track"] and len(pts) >= 2 and _ride_along(u)
                       and max(math.dist(a, b) for a in pts for b in pts) >= RIDE_PAN * FRAME)
    u["movie"] = u["movie"] and not u["panned"]
    # (a pan along a ring, where every frame shows nearly the same rings, looks like a movie, but a pan across the
    # rings is a good strip mosaic, and the pointing alone cannot tell them apart: the window's chip decides those)
    u["mosaic"] = u["whole"] = u["revisit"] = u["drift"] = u["rescanned"] = u["drifting"] = False
    u["kind"] = "movie" if u["movie"] else None
    if u.get("views"):
        # laps of one view (units): a time series, a movie (C44SA_APPRMOVB001's colour set of Saturn every 104 minutes)
        u["movie"], u["kind"], u["revisit"], u["pair"], u["slot_laps"], u["panned"] = True, "movie", True, False, False, False
        return
    # two places whose tiles touch (ISS_C24JU_1X2NITE, a 2x2 seen by one camera as two) are a 1x2 mosaic
    u["pair"] = len(places) == 2 and max(abs(places[0][0] - places[1][0]), abs(places[0][1] - places[1][1])) <= PAIR_STEP * FRAME
    if len(places) < MIN_PLACES and not u["pair"] or u["movie"]:
        u["pair"] = u["slot_laps"] = False
        if crept and not u.get("island") or u["panned"]:
            u["movie"], u["kind"], u["panned"] = True, "movie", False
        return
    pts = np.array(pts)
    lo, hi = pts.min(0) - FRAME / 2, pts.max(0) + FRAME / 2
    if (hi - lo).max() >= MAX_FRAMES * FRAME:
        u["pair"] = u["slot_laps"] = False
        if crept and not u.get("island") or u["panned"]:
            u["movie"], u["kind"], u["panned"] = True, "movie", False
        return
    kind = "mosaic_movie" if len(places) >= 2 and u["repeats"] >= MOVIE_LAPS else "mosaic"
    if kind == "mosaic" and _one_view(u):
        # a filter set taken as the camera drifts, or one place: its frames and colour sets, no mosaic (and a
        # ride-along pan stays the movie it creeps as)
        if u["panned"]:
            u["movie"], u["kind"], u["panned"], u["pair"] = True, "movie", False, False
            return
        u["drift"], u["pair"] = True, False
        return
    if kind == "mosaic" and (_revisits(u) or _drifting(u)):
        # a time series: a movie
        u["movie"], u["kind"], u["revisit"], u["pair"], u["panned"] = True, "movie", True, False, False
        return
    u["mosaic"] = True
    u["kind"] = kind
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    u["whole"] = bool(radius and (lo < -radius).all() and (hi > radius).all())


_unit_of = {}   # frame id -> unit_of's answer (the passes of an observation are worked out once, units)
UNIT_OF_KEEP = 200000


def unit_of(frame_id):
    """(unit, index of the newest tile at that frame) for the pass frame_id is in, or None."""
    with _lock:
        if frame_id in _unit_of:
            return _unit_of[frame_id]
    idx, row = _row_of()
    q = row.get(frame_id)
    if q is None:
        return None
    r = idx.iloc[q]
    cam = "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W"
    t = float(r["seconds_1970"])
    found = None
    for u in units(r["TARGET_NAME"], r["OBSERVATION_ID"], cam):
        ts = [fr[3] for fr in u["frames"]]
        if ts and ts[0] <= t <= u["last"]:
            # (a frame _drop_strays took out of the pass is in none)
            found = None if frame_id in u.get("off", ()) else (u, sum(1 for x in ts if x <= t + 1) - 1)
            break
    with _lock:
        if len(_unit_of) >= UNIT_OF_KEEP:
            _unit_of.clear()
        _unit_of[frame_id] = found
    return found


def mosaic_steps(u, p=None):
    """The frames of mosaic pass u that movie mode stops on (indices into u["frames"], in order), passing over those
    whose mosaic is the
    same picture as the frame before's (layout gives a frame of no filter drawn the same name: a polarizer, a colour
    filter before the pass's colour is whole, a clear frame where the grey filter is another), and those whose
    pointing's next frames add another filter to it before the camera moves on (a pointing's clear tile, gray, then
    its colour set over it), so a step of the movie is a new place of the mosaic, finished, not each frame it is
    built from
    (Sam 2026-10-30: at high frame rates mosaic construction steps counted as frames, the same picture again, and
    a new place's edge flickered gray before its colour came). p: the pass's plan (its colour, grey and luminance
    filters), else worked out from the frames as plan does (_filters). Every frame SPICE placed is taken to have its
    tile (layout counts placed tiles); a frame before the mosaic has anything to draw is a step (the window shows the
    frame itself). The pass's repeat exposures, which units leaves out of its frames, show the mosaic of the frame
    before them: never a step."""
    frames = u["frames"]
    if not frames:
        return set()
    if p is None:
        count, _, _, colour = _filters(u)
        grey = max(count, key=count.get)
        p = {"colour": colour, "grey": grey, "luminance": {"filters": [grey] + sorted(f for f in count if f != grey and not _polarizer(f))}}
    colour, grey, lum = p["colour"], p["grey"], lum_frames(u, p)
    names, count, base = [], {}, []
    for j, fr in enumerate(frames):
        if fr[7]:
            count[fr[2]] = count.get(fr[2], 0) + 1
            if j in lum:
                base.append(fr[2])
        used = colour if colour and all(count.get(f) for f in colour) else [grey] if count.get(grey) else \
            [max(dict.fromkeys(base), key=base.count)] if base else None
        names.append(None if used is None else (tuple(count[f] for f in used), len(base) if any(f not in used for f in base) else 0))

    def at(fr):
        return (-fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) if fr[7] and u.get("z") else None
    # the pointings: runs of frames within SAME_PLACE of a frame of the run's first
    run, first = [], None
    for j, fr in enumerate(frames):
        q = at(fr)
        if q is None or first is None or math.hypot(q[0] - first[0], q[1] - first[1]) > SAME_PLACE * FRAME:
            first = q
            run.append(j)
        else:
            run.append(run[-1])
    new = [j for j in range(len(frames)) if names[j] is not None and (j == 0 or names[j] != names[j - 1])]
    # a new picture whose pointing's later frames add another filter to it is a step on the way (one filter again
    # over the same place, a slow scan creeping a little a frame, is a new picture each time)
    later = {}   # pointing -> the filters of its new pictures from here on
    step = set()
    for j in reversed(new):
        mine = later.setdefault(run[j], set())
        if not mine - {frames[j][2]}:
            step.add(j)
        mine.add(frames[j][2])
    return [j for j in range(len(frames)) if names[j] is None or j in step]


def kind_of(frame_id, cache=None):
    """What the camera windows do with the frames of frame_id's observation (one camera): {"mosaic": its pass is
    a mosaic, "movie": every pass of the observation with the camera moving is a movie or a stare, so its frames
    never make a mosaic of any kind and the window need not ask, "kind": its pass's kind (mosaic, movie,
    mosaic_movie or None), "repeats": its laps, "lap_ends": the ids of the frames that finish a lap of its mosaic
    movies, when it has any, "mosaic_steps": the ids of the frames of its mosaic passes movie mode stops on
    (mosaic_steps; by the pass's plan when cache holds it), when it has any}."""
    found = unit_of(frame_id)
    if not found:
        return {"mosaic": False, "movie": False, "kind": None}
    us = units(*found[0]["key"][:3])
    judged = [v for v in us if v["jump_frac"] is not None]
    # lap_ends: the frames of the observation's mosaic movies that finish a lap, for Whole mosaics (lap_ends)
    ends = [v["frames"][j][1] for v in us for j in lap_ends(v)]
    steps = [v["frames"][j][1] for v in us if v["mosaic"] and not v["movie"] and v.get("kind") != "mosaic_movie"
             for j in mosaic_steps(v, _plan_if_made(v, cache))]
    return {"mosaic": bool(found[0]["mosaic"]), "movie": bool(judged) and all(v["movie"] for v in judged),
            "kind": found[0]["kind"], "repeats": found[0]["repeats"], **({"lap_ends": ends} if ends else {}),
            **({"mosaic_steps": steps} if steps else {})}


def _plan_if_made(u, cache):
    """The pass's plan when it is made already (kept, or in its file), else None: never makes one."""
    if cache is None:
        return None
    rec = _record(u, cache)
    if rec is not None:
        return rec["plan"]
    path = _plan_path(u, cache)
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def folder(u, cache):
    # a movie's frames stacked with a shorter repeat window are other pictures than the ones made before it
    gap = u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP)
    suffix = (("" if gap >= mosaic_benchmark.REPEAT_GAP else f"_r{gap:g}")
              + (LAID if u.get("laid") else STRIPPED if u.get("stripped") else PANNED if u.get("panned") else ISLANDS if u.get("islands")
                 else RESCANNED if u.get("rescanned") else RETRACKED if u.get("retracked") else RELAID if u.get("relaid")
                 else GROUPING if u.get("regrouped") else "")
              + (SET_COLOUR if _set_coloured(u) else ""))
    return os.path.join(cache, f"{VERSIONS[calibration.style()]}{calibration.variant()}-q{QUALITY}", "_".join(map(str, u["key"])) + suffix)


def drawn(u, cache):
    """The folder of the pass's mosaics as drawn (its filter mosaics and pictures, its mosaic movie's): the pass's own
    folder with the blend step off, as they were drawn before it, else a folder of it named for the blend and level
    steps (mosaic.drawing). The tiles, the plan and the seams do not depend on them and stay in the pass's folder."""
    name = mosaic.drawing()
    return os.path.join(folder(u, cache), name) if name else folder(u, cache)


def _ulock(u):
    with _lock:
        return _unit_locks.setdefault(u["key"], threading.RLock())


PLAN_FILE = "plan4.json"   # renamed when the plan's rules change, so cached plans are worked out again
# a movie's footprint (movie_footprint), worked out with the plan and named after it, so a new plan redoes it
# (movie_footprint2: every frame's own drawn box on the pass's axes, pass_boxes, in place of a margin round the samples
# and the geometry footprint's north-up diagonals, so a stare is drawn a frame across)
FOOTPRINT_FILE = "movie_footprint2-" + PLAN_FILE
# a feature track's steady places (track_places), and its footprint drawn from them; renamed (with the track's movie
# frames, movie_webp) whenever the rule changes
TRACK_FILE = "track2-" + PLAN_FILE
TRACK_FOOTPRINT_FILE = "movie_footprint-" + TRACK_FILE


def _tiles(u, cache, scale):
    """The folder of the pass's tiles made on this display scale: a plan that changes its scale (its rules
    changed) makes its tiles again instead of drawing them next to tiles on the old one."""
    return os.path.join(folder(u, cache), "tiles-" + hashlib.md5(json.dumps(scale, sort_keys=True).encode()).hexdigest()[:8])


def _pic(u, cache, scale, t):
    """The picture tile t is drawn from: its own (_tiles/<n>.png), or the one its layout gave it (t["pic"]: its
    surface redrawn as at the mosaic's epoch, surface_pictures)."""
    return t.get("pic") or os.path.join(_tiles(u, cache, scale), f"{t['n']}.png")


# ---------- what the cache holds of a pass, kept in memory ----------
# A pass's plan, its movie footprint and its tiles' reports are each written once and never change (the plan file is
# renamed when its rules change, the tiles' folder is named after the plan's display scale): each is read from the
# cache once and kept here, so the layout of the pass's mosaic at tile n (the reports of tiles 0..n), which every
# mosaic, mosaic movie picture, tile map and look-ahead works out, comes from memory instead of a file per tile per
# request. A pass's record is kept with its plan file's identity (inode and mtime), which every plan() looks at: a
# pass whose cache folder was cleared or made again is read from the cache afresh. Only what is made is kept, so a
# tile not in memory is looked for in the cache (a server sharing the cache may have made it).
PASSES_KEEP = 64   # passes kept in memory, the most recently used (a pass's tile reports are ~1 KB each)
# plan file -> {"stamp", "plan", "scale", "tiles_dir", "tiles": {n: report}, "made": tiles seen in the cache (not read),
# "footprint", "rolled": {(size, out, fade): frames whose mosaic movie picture is made, rolling_ahead}, "mapped": the last
# tile whose mosaic's tile map is worked out, _map_later}
_passes = collections.OrderedDict()


def _stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns


def _plan_path(u, cache):
    return os.path.join(folder(u, cache), PLAN_FILE)


def _record(u, cache):
    """The pass's record in memory, while its plan file is the one it was read from (one stat); else None."""
    path = _plan_path(u, cache)
    with _lock:
        rec = _passes.get(path)
    if rec is None:
        return None
    if _stamp(path) != rec["stamp"]:
        with _lock:
            if _passes.get(path) is rec:
                del _passes[path]
        return None
    with _lock:
        if path in _passes:
            _passes.move_to_end(path)
    return rec


def _keep_plan(u, cache, p, stamp):
    rec = {"stamp": stamp, "plan": p, "scale": p["display_scale"], "tiles_dir": _tiles(u, cache, p["display_scale"]),
           "tiles": {}, "made": set(), "footprint": None, "track_footprint": None, "track": None, "steady": None, "exposure": None, "rolled": {}}
    path = _plan_path(u, cache)
    with _lock:
        _passes[path] = rec
        _passes.move_to_end(path)
        while len(_passes) > PASSES_KEEP:
            _passes.popitem(last=False)
    return rec


# every tile's report of a pass made whole (prebuild.make_pass), in one file beside its tiles' folder (reports-<that
# folder>.json, out of the tools' tiles-*/*.json): a server's first look at the pass (its mosaic's layout, its tiles
# made ahead, its tile maps) reads that file instead of one file a tile
REPORTS_FILE = "reports-{}.json"


def _reports_path(tiles_dir):
    return os.path.join(os.path.dirname(tiles_dir), REPORTS_FILE.format(os.path.basename(tiles_dir)))


def keep_reports(u, cache, p):
    """Every tile's report of the pass in REPORTS_FILE, as each reads back from its own file; once every tile is
    made (it makes those that are not)."""
    path = _reports_path(_tiles(u, cache, p["display_scale"]))
    if not os.path.exists(path):
        reports = {str(j): tile(u, j, cache, p["display_scale"]) for j in range(len(u["frames"]))}
        reel._cached(path, lambda: json.dumps(reports).encode())


def _kept_reports(rec):
    """The pass's tile reports from its REPORTS_FILE into its record rec, when the pre-build kept them so."""
    try:
        with open(_reports_path(rec["tiles_dir"])) as fh:
            reports = json.load(fh)
    except (OSError, ValueError):
        return
    with _lock:
        for n, report in reports.items():
            rec["tiles"].setdefault(int(n), report)


def _kept_tiles(u, cache, scale):
    """The pass's record when scale is its kept plan's display scale (no stat: plan() looked at it); else None."""
    with _lock:
        rec = _passes.get(_plan_path(u, cache))
    return rec if rec is not None and rec["scale"] is scale else None


def _reports(u, cache, p, js):
    """The reports of tiles js of the pass (on its plan p's scale), in that order: from memory, the others from the
    cache (or made, as tile() does)."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _lock:
        kept = dict(rec["tiles"]) if rec is not None else {}
    return [kept.get(j) or tile(u, j, cache, p["display_scale"]) for j in js]


def _has_tile(u, j, cache, p):
    """Whether tile j of the pass is made: known in memory, or its report file in the cache (then remembered: a
    pass's tiles stay while its plan file does)."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    if rec is not None and (j in rec["tiles"] or j in rec["made"]):
        return True
    there = os.path.exists(os.path.join(rec["tiles_dir"] if rec is not None else _tiles(u, cache, p["display_scale"]), f"{j}.json"))
    if there and rec is not None:
        with _lock:
            rec["made"].add(j)
    return there


def _all_made(u, cache, p, first, last, look=False):
    """Whether tiles first..last of the pass are all made, as far as memory knows (read once, or seen in the
    cache); look: those memory does not know are looked for in the cache (a server started on a made cache)."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    if rec is None:
        return False
    with _lock:
        unknown = [j for j in range(first, last + 1) if j not in rec["tiles"] and j not in rec["made"]]
    return not unknown or (look and all(_has_tile(u, j, cache, p) for j in unknown))


def _filters(u):
    """The filters plan() draws pass u in, from its frames alone: (tiles per filter, each filter's wavelength, the
    filters aside, the colour filters or None); the grey filter is the one taken most (max of the count)."""
    frames = u["frames"]
    count, nms = {}, {}
    for fr in frames:
        count[fr[2]] = count.get(fr[2], 0) + 1
        nms[fr[2]] = fr[4]
    # the filters chosen from those pointed at the body: a pass whose most taken filter looks beside it (the
    # clear frames of ISS_C23RI_RMOV001_PRIME are a frame further off Jupiter, on dark sky) is drawn in
    # the filters that see the body, not as a black mosaic of that sky
    aside = _aside(frames, u)
    count = {f: c for f, c in count.items() if f not in aside} or count
    colour = colour_of(count, nms)
    u["set_colour"] = False
    # a movie plays only a colour set holding every colour filter (set_of): colours that no set of its holds together
    # never play, and it stayed grey. Janus ISS_059JA_GEOLOG001_PRIME takes RED and BL1 once each, side by side, and
    # GRN only in its two UV3, GRN, IR1, IR3 sets: its counts made it true colour, and none of its 49 frames was in
    # colour. Such a movie takes the colours of its sets (_set_colour), as a movie its counts make grey does
    if u.get("kind") == "movie" and (colour is None or not any(set(colour) <= {f for f, _ in run} for run in colour_sets(frames))):
        mine = _set_colour(frames, count, nms)
        if mine is not None or colour is None:
            colour = mine
            u["set_colour"] = colour is not None
    if colour is None:
        # a pass its counts make grey whose sets are a pair with an approximate color (calibration.approximate_pair):
        # Titan's cloud watches and maps take CB3 three times a set and MT1 once (133TI_CLOUD002: 120 CB3, 40 MT1),
        # so MT1 never reached half of CB3's count and the pass played and mosaicked grey (Sam 11-08)
        pair = _pair_colour(u, count, nms)
        if pair is not None:
            colour = pair
            u["set_colour"] = u.get("kind") == "movie"
    return count, nms, aside, colour


PAIR_SETS = 2   # sets of a pair (_pair_colour) a pass takes at least, as a movie's colour takes (COLOUR_STEPS)


def _pair_colour(u, count, nms):
    """The two colour filters, [longer, shorter], of a pass whose sets (colour_sets) take a pair drawn in approximate
    color (calibration.approximate_pair: a body's surface window pair, Titan's CB3 with MT1, IR1, RED...), at least
    PAIR_SETS times: the pair taken most; None without one."""
    seen = {}
    for run in colour_sets(u["frames"]):
        fs = tuple(sorted({f for f, _ in run}, key=lambda f: -nms[f]))
        if len(fs) == 2 and all(f in count for f in fs) and \
                calibration.approximate_pair(u["key"][2], list(fs), u["key"][0]):
            seen[fs] = seen.get(fs, 0) + 1
    best = max(seen, key=seen.get) if seen else None
    return list(best) if best and seen[best] >= PAIR_SETS else None


def _set_coloured(u):
    """Whether the pass is a movie _set_colour colours (folder: its own folder, SET_COLOUR)."""
    if u.get("kind") != "movie":
        return False
    if "set_colour" not in u:
        _filters(u)
    return u["set_colour"]


def _set_colour(frames, count, nms):
    """The colour filters of a movie whose tile counts make it grey (colour_of) though it takes colour sets of three
    or more filters (colour_sets, the camera windows' sets): the channels (sets_passes.channels) its sets use most
    often, the widest in wavelength among those as often, then the newest; None without such a set. Sam 2026-10-30:
    the NAC's Titan wind stares of 2005-06-04 (ISS_009TI_1X1WND10001..) take CB3 three times a cycle and every other
    filter once, so no filter but CB3 reached half of CB3's count and the movie played grey, while its windows showed
    each cycle's CB3, MT1 and UV1 set in colour."""
    seen = {}
    for n, run in enumerate(colour_sets(frames)):
        filters = [f for f, _ in run]
        if len(set(filters)) < 3 or any(f not in count for f in filters):
            continue
        kind, use = sets_passes.channels(filters, [nms[f] for f in filters])
        rgb = tuple(filters[j] for j in use)
        seen[rgb] = (seen.get(rgb, (0,))[0] + 1, nms[rgb[0]] - nms[rgb[-1]], n)
    return list(max(seen, key=seen.get)) if seen else None


def plan(u, cache):
    """The pass's display scale, rotation, footprint, view mode and colour filters, worked out once and kept."""
    path = _plan_path(u, cache)
    rec = _record(u, cache)
    if rec is not None:
        return rec["plan"]
    with _ulock(u):
        rec = _record(u, cache)
        if rec is not None:
            return rec["plan"]
        if os.path.exists(path):
            stamp = _stamp(path)
            with open(path) as fh:
                p = json.load(fh)
            _kept_reports(_keep_plan(u, cache, p, stamp))
            return p
        frames = u["frames"]
        count, nms, aside, colour = _filters(u)
        # a long movie's scale from frames spread evenly over it, each filter's on its own (a step in time could
        # fall in step with the filter wheel and miss a filter): the same scale, without reading every frame first
        picks = []
        for f in count:
            mine = [fr for fr in frames if fr[2] == f]
            picks += mine[::max(1, math.ceil(len(mine) / SCALE_FRAMES))]
        levels = {}
        scale = pass_scale(sorted(picks, key=frames.index), u, colour or [max(count, key=count.get)],
                           bool(colour and len(colour) == 3 and colour[1] == "GRN" and colour[2] in reel.TRUE_BLUES),
                           lit_levels=levels)
        # the rotation from the camera's frame to north up: the angle between where the geometry cache puts
        # the body and where processed_frame does, from the first tile placed well off the body's centre
        angle, ref = 0.0, None
        for k, fr in enumerate(frames):
            if fr[7] and math.hypot(fr[5], fr[6]) > 200:
                rep = tile(u, k, cache, scale)
                if "native_offset" in rep:
                    fo = rep["native_offset"]
                    angle = math.atan2(fo[1], fo[0]) - math.atan2(-fr[6], -fr[5])
                    ref = fr[1]
                    break
        x0, y0, x1, y1 = footprint(u, angle, ref, aside)
        view = [x1 - x0, y1 - y0]
        p = {"key": list(u["key"]), "display_scale": scale, "angle": angle, "footprint": [x0, y0, x1, y1],
             "fixed": True, "view": view, "k": CANVAS / max(view), "colour": colour,
             "grey": max(count, key=count.get), "whole": u["whole"]}
        p["luminance"] = luminance_of(count, p["grey"], levels)
        reel._cached(path, lambda: json.dumps(p).encode())
        stamp = _stamp(path)
        if stamp is not None:
            # kept as it reads back from its file (lists, not tuples): the plan every later request gets
            p = json.loads(json.dumps(p))
            _keep_plan(u, cache, p, stamp)
        return p


def footprint(u, angle, ref, aside=()):
    """The canvas rectangle [x0, y0, x1, y1] round pass u's frames (but those of the filters aside), turned north up
    by angle, which the frame ref was measured at (plan). A pass the camera turns under (TWIST: 033RI_AZDKMRHPH001
    turns 134 degrees, 173RI_DRCLOSE001 5 degrees 22,000 px from Saturn's centre) has each frame turned by its own
    angle from the geometry cache (processed_frame turns it by that angle), measured from frame ref (or, with none,
    by that angle alone): one angle for the whole pass put its footprint where the tiles are not, and cut them off
    or left the canvas nearly empty."""
    turned = u.get("twist") or {}

    def turn(fid):
        if fid not in turned:
            return angle
        return angle + math.radians(turned[ref] - turned[fid]) if ref in turned else math.pi - math.radians(turned[fid] - view_turn(u))
    pts, ks = [], []
    # the footprint of the filters drawn: frames of a filter left out (aside) would only hold empty canvas
    for _, fid, f, _, _, x, y, z in u["frames"]:
        if z and f not in aside:
            k = z / u["z"]
            c, s = math.cos(turn(fid)), math.sin(turn(fid))
            pts.append(((c * -x - s * -y) * k, (s * -x + c * -y) * k))
            ks.append(k)
    if not pts:
        pts, ks = [(0.0, 0.0)], [1.0]
    # (and room round them for what registration may move a tile by, REGISTER_MAX and PANEL_MAX)
    room = HALF + ((REGISTER_MAX + PANEL_MAX) * FRAME if turned else 0)
    return [min(p[0] - room * k for p, k in zip(pts, ks)), min(p[1] - room * k for p, k in zip(pts, ks)),
            max(p[0] + room * k for p, k in zip(pts, ks)), max(p[1] + room * k for p, k in zip(pts, ks))]


ASIDE_SHARE = 0.25   # of the frames of the filter taken most: a filter with fewer never sets where the pass points (_aside)


def _aside(frames, u, share=ASIDE_SHARE, disk=True):
    """The filters whose frames point, as a rule, more than half a frame further from the body's centre than the
    filter pointed closest (median over each filter's placed frames, at the pass's reference distance) among those
    taken at least share as often as the filter taken most, and off the body's disk (RADIUS, when disk and the body's
    size is known). In ISS_C23RI_RMOV001_PRIME the colour frames sit 316 px from Jupiter's centre, on the disk, and
    the clear and IR1 frames 1331 px out, beside it; the filters of a mosaic share their pointings and come out within
    pixels. (Measured from any filter, a lone frame near the middle, the one IR2/IR1 frame of 044RI_PHOTDRK003's 96,
    put every other filter aside, and the mosaic was that one frame; so did a close flyby's frames scattered over
    Titan's disk, 005TI_HIGHRESNA001's one MT1 frame left of five.)"""
    far = {}
    for fr in frames:
        if fr[7]:
            far.setdefault(fr[2], []).append(math.hypot(fr[5], fr[6]) * fr[7] / u["z"])
    med = {f: sorted(v)[len(v) // 2] for f, v in far.items()}
    if not med:
        return set()
    most = max(len(v) for v in far.values())
    near = min(m for f, m in med.items() if len(far[f]) >= share * most)
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]]) if disk and u["z"] else 0
    return {f for f, m in med.items() if m > near + FRAME / 2 and m > radius}


# filter sets with a colour mapping of their own, looked up before the general rule in colour_of: frozenset of the
# pass's filters (as units() names them, e.g. "MT3", "CB2", "BL1") -> [red, green, blue] filters. Empty for now;
# the per-filter-set rules for false colour (color plan phase 2b) go here
COLOUR_SETS = {}


def colour_of(count, nms):
    """The pass's colour filters, [red, green, blue], or None for grey. count = tiles per filter, nms = each
    filter's wavelength. (Near) true colour when the pass takes GRN and a blue at a good share of its tiles, with
    RED or else the continuum filter nearest red (not a methane band); otherwise false colour from the filters
    taken at most tiles, the three nearest the visible (sets_passes.nearest_visible, longest wavelength red). Polarizers are left out (they are not a colour). A pass of two
    colour filters (CB2 and MT2) is [longer, shorter], drawn as a two-filter composite is (calibration.two_bands:
    green their mean); a clear filter is not one of the two."""
    most = max(count.values())
    # a clear frame is no color: it is left out wherever the color filters still make a set of their own (it
    # sees several times their light, so as a channel it outshines them, green on Saturn's rings)
    plain = [f for f in count if f != "CL1/CL2" and not _polarizer(f)]
    if len([f for f in plain if count[f] >= most / 2]) >= 3:
        count = {f: count[f] for f in plain}
        most = max(count.values())
    good = [f for f in count if count[f] >= most / 4 and not _polarizer(f)]
    for filters, rgb in COLOUR_SETS.items():
        if filters <= set(good):
            return list(rgb)
    blue = next((b for b in reel.TRUE_BLUES if b in good), None)
    reds = [f for f in good if "/" not in f and not f.startswith("MT") and nms[f] > 600]
    red = "RED" if "RED" in good else min(reds, key=lambda f: abs(nms[f] - 650)) if reds else None
    common = sorted([f for f in count if count[f] >= most / 2 and not _polarizer(f)], key=lambda f: -nms[f])
    if blue and red and "GRN" in good:
        return [red, "GRN", blue]
    if len(common) >= 3:
        # the three nearest the visible, methane bands last (the filter sets' rule, sets_passes.nearest_visible)
        return [common[j] for j in sets_passes.nearest_visible(common, [nms[f] for f in common])]
    two = [f for f in common if f in plain]
    return two if len(two) == 2 else None


def _polarizer(f):
    return any(p.startswith("IRP") or (p.startswith("P") and p[1:2].isdigit()) for p in f.split("/"))


# ---------- the luminance base (placed tiles) ----------
# A pass's mosaic is drawn on a gray base made from every tile it has placed so far, each where SPICE puts it, and its
# colour is laid over that base only where all three colour filters have the picture, fading into the gray at that
# edge. So the mosaic never shrinks when its colour begins (the colour picture alone is only the ground all three
# filters cover), and its gray never changes filter part way through a pass. The gray is the plan's grey filter
# wherever the pass takes it; the pass's other filters fill in only the places that filter never covers (a scan
# that steps one filter a pointing, a colour pointing without a clear frame), each brought to the grey filter's
# brightness by its gain.
LUM = "L"                # the luminance base, where a filter's name goes (filter_mosaic, its cache files)
LUM_GAIN = (0.25, 4.0)   # the furthest a band's gain to the grey filter's level goes
LUM_FEATHER = 64         # px on the benchmark's 0.5 scale canvas (as mosaic.feather_px): colour fades into gray over this


def luminance_of(count, grey, levels):
    """The plan's luminance base: {"filters": the filters it may draw (the pass's less polarizers, the grey filter
    first), "gains": {filter: linear gain bringing its lit median (pass_scale's levels) to the grey filter's}}."""
    filters = [grey] + sorted(f for f in count if f != grey and not _polarizer(f))
    ref = levels.get(grey) or 0.0
    gains = {}
    for f in filters[1:]:
        if ref > 0 and levels.get(f, 0) > 0:
            gains[f] = round(float(np.clip(ref / levels[f], *LUM_GAIN)), 4)
    return {"filters": filters, "gains": gains}


def _luminance(p):
    # (a plan made before the luminance base: its grey filter alone)
    return p.get("luminance") or {"filters": [p["grey"]], "gains": {}}


def lum_frames(u, p):
    """The frames the pass's luminance base draws (indices into u["frames"], as tiles are numbered): every frame of
    the grey filter, and a frame of another of its filters where no frame of the grey filter is at that place
    (within SAME_PLACE of a frame) anywhere in the pass, from the geometry cache, so the set only grows as the pass
    goes on and each mosaic grows from the one before. Kept with the pass."""
    lum = _luminance(p)
    key = tuple(lum["filters"])
    hit = u.get("_lum")
    if hit and hit[0] == key:
        return hit[1]
    grey, allowed = lum["filters"][0], set(lum["filters"])

    def at(fr):
        return (-fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) if fr[7] and u["z"] else None
    greys = [q for q in (at(fr) for fr in u["frames"] if fr[2] == grey) if q]
    out = set()
    for j, fr in enumerate(u["frames"]):
        if fr[2] == grey:
            out.add(j)
        elif fr[2] in allowed:
            q = at(fr)
            if q is None or not any(math.hypot(q[0] - g[0], q[1] - g[1]) <= SAME_PLACE * FRAME for g in greys):
                out.add(j)
    out = frozenset(out)
    u["_lum"] = (key, out)
    return out


LOST_FILL = 0.01   # of a frame: a tile that lost this much in downlink (lines no repeat or fill made up) has a gap to fill


def _lossy(t):
    """True when tile report t leaves a gap where its frame is: not placed (left out: 8LSB, saturated all over, a
    silhouette), or LOST_FILL of it lost in downlink (a partial frame most of all). A frame's usual few lost lines at
    its edge (0.4%) are not."""
    return "offset" not in t or t.get("lost", 0.0) >= LOST_FILL


def lum_fills(u, p, tiles):
    """The frames (indices, as tiles are numbered) of the luminance base's other filters that fill in under a place
    whose every frame of the grey filter lost lines in downlink or was left out (_lossy), from the tiles made: lum_frames leaves out a frame of another filter wherever a grey frame
    is at its place, so the part of a grey frame lost in downlink stayed a hole though a frame of another filter
    covered it (Titan ISS_021TI_GLOBMAPNA001: CB3 N1519692683_2 lost a third of its lines, MT1 N1519692611_1 beside
    it). Decided only once every grey frame at the place is made, so the set only grows as the pass goes on. The
    base draws these under its other tiles (under_first), so they show only where nothing else is."""
    lum = _luminance(p)
    grey, allowed = lum["filters"][0], set(lum["filters"])
    frames = u["frames"]
    made = {t["n"]: t for t in tiles}
    last = max(made) if made else -1
    if not any(t["filter"] == grey and _lossy(t) for t in tiles):
        return set()   # (the usual pass: every grey frame whole and placed)

    def at(fr):
        return (-fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) if fr[7] and u["z"] else None
    base = lum_frames(u, p)
    greys = [(j, at(fr)) for j, fr in enumerate(frames) if fr[2] == grey and at(fr)]
    out = set()
    for t in tiles:
        n = t["n"]
        if n in base or t["filter"] not in allowed or "offset" not in t or partial(t):
            continue
        q = at(frames[n])
        if q is None:
            continue
        there = [j for j, g in greys if math.hypot(q[0] - g[0], q[1] - g[1]) <= SAME_PLACE * FRAME]
        if there and all(j <= last and j in made and _lossy(made[j]) for j in there):
            out.add(n)
    return out


def _mine(u, p, tiles, f):
    """The placed tiles filter_mosaic draws for f: the filter's own, or for LUM the luminance base's (lum_frames),
    a band other than the grey filter carrying its gain (applied by _shade, times a mosaic movie copy's own lap gain)."""
    if f != LUM:
        return [t for t in tiles if t["filter"] == f and "offset" in t]
    lum = _luminance(p)
    # (a mosaic movie's picture marks its own base, rolling_base)
    rolling = any("base" in t for t in tiles)
    frames = {t["n"] for t in tiles if t.get("base")} if rolling else lum_frames(u, p)
    fills = set() if rolling else lum_fills(u, p, tiles)
    gamma = p["display_scale"].get("gamma", 2.2)
    out = []
    for t in tiles:
        if "offset" in t and (t["n"] in frames or t["n"] in fills):
            g = lum["gains"].get(t["filter"], 1.0)
            t = dict(t, gain=round(g * t.get("gain", 1.0), 4), gamma=gamma) if g != 1.0 else t
            out.append(dict(t, fill=True) if t["n"] in fills else t)
    return out


_luts = {}


def _shade(part, t):
    """A tile's picture (RGBA at its canvas size) with its tile dict's "gain" applied: the luminance base's gain of
    a band other than the grey filter, or a movie frame's exposure gain, on linear brightness (the pass's display
    gamma, t["gamma"]), alpha as it is. The same array when the tile has none. A gain under 1 leaves white white:
    a clipped pixel (CLIP_FROM and up, eased in to 255) is at least as bright as white, so dimmed it would draw a
    floor as a value: the sun's saturated glare in the 2006 backlit Saturn movie (028RG HIPHASE002, exposure gain
    0.7) came out a flat grey blob among frames where it is white."""
    g = t.get("gain")
    if not g or g == 1.0:
        return part
    key = (g, t.get("gamma", 2.2))
    lut = _luts.get(key)
    if lut is None:
        v = np.arange(256, dtype=np.float64) / 255
        lin = calibration.encode(np.clip(calibration.decode(v, key[1]) * g, 0, 1), key[1])
        if g < 1.0:
            w = np.clip((v * 255 - CLIP_FROM) / (255 - CLIP_FROM), 0, 1)
            lin = lin + w * w * (3 - 2 * w) * (v - lin)
        lut = _luts[key] = (lin * 255 + 0.5).astype(np.uint8)
    out = part.copy()
    out[..., :3] = lut[part[..., :3]]
    return out


def _shade_rgb(rgba, g, gamma):
    """A colour picture (RGBA) times exposure gain g on linear brightness, as _shade does a band's tile, with white
    kept white by its brightest band: the same share of every band, so a white body clipped in one band stays white
    rather than taking that band's hue."""
    v = np.arange(256, dtype=np.float64) / 255
    lut = (calibration.encode(np.clip(calibration.decode(v, gamma) * g, 0, 1), gamma) * 255).astype(np.float32)
    rgb = rgba[..., :3]
    dim = lut[rgb]
    if g < 1.0:
        top = rgb.max(axis=2).astype(np.float32)
        w = np.clip((top - CLIP_FROM) / (255 - CLIP_FROM), 0, 1)
        w = (w * w * (3 - 2 * w))[..., None]
        dim = dim + w * (rgb.astype(np.float32) - dim)
    out = rgba.copy()
    out[..., :3] = np.clip(dim + 0.5, 0, 255).astype(np.uint8)
    return out


def lum_base(u, p, tiles, used, base=None):
    """Whether the mosaic of these tiles, drawn in the filters used, needs its luminance base under it: a tile of
    the base sits where the picture would otherwise have nothing (no tile of every colour filter at its place, or,
    drawn in gray, a tile of a filter other than the one drawn). base: the base's tiles (lum_frames' by default)."""
    if any("base" in t for t in tiles):
        return any(t.get("base") for t in tiles)   # (a mosaic movie's picture: rolling_base said)
    if base is None:
        frames = lum_frames(u, p) | lum_fills(u, p, tiles)
        base = [t for t in tiles if "offset" in t and t["n"] in frames]
    if len(used) == 1:
        return any(t["filter"] != used[0] for t in base)
    by = {f: [t["offset"] for t in tiles if t["filter"] == f and "offset" in t] for f in used}
    near = lambda o, os_: any(math.hypot(o[0] - q[0], o[1] - q[1]) <= SAME_PLACE * FRAME for q in os_)
    # (or a colour tile with lines lost in downlink: the colour is only where all its filters are, so its lost lines were
    # a black strip, Dione ISS_016DI_TARGFLYBY001's GRN N1507742100_3; or a frame filling in under a lossy grey one)
    return (any(not all(near(t["offset"], by[f]) for f in used) for t in base)
            or any(t["filter"] in used and "offset" in t and _lossy(t) for t in tiles) or bool(lum_fills(u, p, tiles))
            or (bool(base) and mixes(u, p, tiles, used)))


LUM_MATCH = (0.25, 4.0)   # the furthest the gray's match to the colour it borders goes, per channel
LUM_MATCH_MIN = 500       # lit pixels each side needs for the match; fewer, and the gray stays as it is


def match_grey(colour, grey, ca, only, feather, gamma):
    """The gain per channel (linear brightness) that brings the gray base to the colour it borders: the colour's
    median over the gray's where both lie under the picture, or, where the gray only goes on past the colour (a
    colour tile beside gray ones), the colour's within two feathers of that edge over the gray's within two feathers
    on its side. So the gray continues the colour's brightness and its average hue (Titan's gray reads orange beside
    its orange disk, a dim clear-filter gray is lifted to the colour beside it), and the detail stays the gray's.
    None when either side has too little lit picture to measure."""
    lin = lambda v: calibration.decode(v.astype(np.float32) / 255, gamma)
    ga = grey[..., 3] > 250
    both = (ca > 0.99) & ga
    if both.sum() >= LUM_MATCH_MIN:
        cside, gside = both, both
    else:
        near = 2 * feather
        to_only = cv2.distanceTransform((~only).astype(np.uint8), cv2.DIST_L2, 5)
        to_colour = cv2.distanceTransform((ca < 0.99).astype(np.uint8), cv2.DIST_L2, 5)
        cside, gside = (ca > 0.99) & (to_only <= near), only & ga & (to_colour <= near)
    g = lin(grey[..., 0])
    rgb = lin(colour[..., :3] / np.maximum(ca, 1 / 255)[..., None])
    gl = g[gside]
    cl = rgb[cside]
    # lit: above a tenth of each side's bright end, so sky and the night side do not set the match
    gl = gl[gl > 0.1 * np.percentile(gl, 99)] if gl.size else gl
    cl = cl[cl.mean(axis=1) > 0.1 * np.percentile(cl.mean(axis=1), 99)] if len(cl) else cl
    if gl.size < LUM_MATCH_MIN or len(cl) < LUM_MATCH_MIN or np.median(gl) <= 0:
        return None
    return np.clip(np.median(cl, axis=0) / np.median(gl), *LUM_MATCH).astype(np.float32)


def grey_gain(colour, grey, k, gamma=2.2):
    """The match over_grey gives the gray base under this colour picture (match_grey), or None (no match, or no
    gray past the colour)."""
    ca = colour[..., 3].astype(np.float32) / 255
    only = (grey[..., 3].astype(np.float32) / 255 > 0.5) & (ca < 0.5)
    if not only.any():
        return None
    return match_grey(colour, grey, ca, only, max(8, round(LUM_FEATHER * k / 0.5)), gamma)


def tinted(grey, gain, gamma=2.2):
    """The gray (its first channel, levels) given the per channel gain on linear brightness: levels, float, 3 channels."""
    if gain is None:
        return np.repeat(grey[..., :1].astype(np.float32), 3, axis=2)
    return calibration.encode(np.clip(calibration.decode(grey[..., :1].astype(np.float32) / 255, gamma) * gain, 0, 1), gamma) * 255


def over_grey(colour, grey, k, gamma=2.2, gain=...):
    """The colour picture (colour_picture: its colour times where all three filters cover) laid over the luminance
    base (grey, RGBA on the same canvas): colour where all three filters cover, the gray elsewhere, the colour fading
    into the gray over LUM_FEATHER (at this canvas's scale) inward from where the gray goes on past it. The gray is
    first matched to the colour it borders (match_grey), so the join shows no step in brightness or hue. Where
    nothing lies beyond the colour (the mosaic's own edge) it keeps its edge as colour_picture drew it. gain: the
    match worked out already (grey_gain, on the whole mosaic: a native mosaic's blocks, mosaic_native)."""
    ca = colour[..., 3].astype(np.float32) / 255
    ga = grey[..., 3].astype(np.float32) / 255
    only = (ga > 0.5) & (ca < 0.5)   # the gray goes on past the colour
    if not only.any():
        return colour
    feather = max(8, round(LUM_FEATHER * k / 0.5))
    if gain is ...:
        gain = match_grey(colour, grey, ca, only, feather, gamma)
    under = grey[..., :3].astype(np.float32) if gain is None else tinted(grey, gain, gamma)
    dist = cv2.distanceTransform((~only).astype(np.uint8), cv2.DIST_L2, 5)
    w = ca * np.clip(dist / feather, 0, 1)
    rgb = colour[..., :3].astype(np.float32) / np.maximum(ca, 1 / 255)[..., None]
    out = rgb * w[..., None] + under * (ga * (1 - w))[..., None]
    alpha = w + ga * (1 - w)
    return np.dstack([np.clip(out + 0.5, 0, 255).astype(np.uint8), np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8)])



# a clouded body's colour mosaic (clouded: Saturn, Jupiter, Titan, the rings) shows colour only where the three filters'
# frames on top at a place were taken within MIX_SPAN of one another. Each filter's mosaic is drawn on its own, its
# newest frame on top, so where a pointing took only some of the filters (195RI HIPHASEC001: 21 of 51 pointings), or
# laps an hour apart overlap (Jupiter C23 NSMAP101: 15 of 21 pointings), red came from one visit and blue from
# another, while the clouds turned between them (Jupiter turns 26 degrees in 43 minutes): green and pink blotches in
# the bands, flat green and magenta blocks on Saturn's night side. There the gray base (its own frames, matched to the
# colour round it, over_grey) shows instead
MIX_SPAN = sets_passes.SET_GAP   # s: frames on top taken further apart than this mix visits (a camera set's own count as one)
MIX_LEAST = 0.15   # of a frame: a mixed patch narrower than this keeps its colour (a seam's strip where one filter of the newer visit reaches less far: 195RI, up to a tenth of a frame)


def mixes(u, p, tiles, colour):
    """True when a clouded pass's colour mosaic of these tiles mixes visits: set_mask's rule on the tiles' boxes, on a
    grid of MIX_CELL reference px, each filter's newest tile on top (a coarse set_times), so the luminance base
    (lum_base) is drawn for the gray set_mask leaves. Where tiles of one filter overlap, the newest shows: the laps of
    a repeated mosaic (Saturn ISS_003SA_3X3MOVIEB001's eleven, each a whole set at the same places) and neighbouring
    pointings at their seams (the newer pointing's filters all on top) do not mix; a pairwise test of the boxes counted
    both, and the 3x3 took the luminance of its MT2 base (drawn mid-grey)."""
    # (a mosaic movie's picture shows each place's newest lap by design: rolling_layout, its tiles marked "base")
    if not colour or len(colour) < 2 or not clouded(u) or _rolling.get() or any("base" in t for t in tiles):
        return False
    if len(visit_tiles(u, tiles, colour)) < len(tiles):
        return True   # (a partial visit left out of the colour: the gray shows there)
    mine = [t for t in tiles if t["filter"] in colour and "offset" in t]
    if not all(any(t["filter"] == f for t in mine) for f in colour):
        return False
    box = lambda t: (t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1],
                     t["offset"][0] + t["box"][0] + t["box"][2], t["offset"][1] + t["box"][1] + t["box"][3])
    edges = np.array([box(t) for t in mine], float)
    gx, gy = edges[:, 0].min(), edges[:, 1].min()
    shape = (int(math.ceil((edges[:, 3].max() - gy) / MIX_CELL)) + 1, int(math.ceil((edges[:, 2].max() - gx) / MIX_CELL)) + 1)
    times = []
    for f in colour:
        grid = np.full(shape, np.nan)
        for t in sorted((t for t in mine if t["filter"] == f), key=lambda t: t["n"]):
            x0, y0, x1, y1 = box(t)
            grid[int(round((y0 - gy) / MIX_CELL)):int(round((y1 - gy) / MIX_CELL)),
                 int(round((x0 - gx) / MIX_CELL)):int(round((x1 - gx) / MIX_CELL))] = set_time(u, t["n"])
        times.append(grid)
    return set_mask(times, 1 / MIX_CELL) is not None


MIX_CELL = 16   # reference px: the grid mixes() lays the tiles' boxes on


def visit_frames(u, colour):
    """The frames (indices) of a clouded pass's colour filters that take part in a whole colour visit: every other
    colour filter has a frame within SAME_PLACE of a frame at its place and taken within MIX_SPAN of it (set_time).
    A pointing that took only some of the filters (Jupiter C23 NSMAP101: 15 of 21) is drawn in the gray base instead of
    the colour, so the colour under it is a whole visit's, not one filter of each visit. Decided on the pass's frames
    from the geometry cache (as lum_frames), so it only grows as the pass goes on; every frame on any other body."""
    key = tuple(colour)
    hit = u.get("_visits")
    if hit and hit[0] == key:
        return hit[1]
    frames = u["frames"]

    def at(fr):
        return (-fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) if fr[7] and u["z"] else None
    whole = set(range(len(frames)))
    if clouded(u) and len(colour) >= 2:
        by = {f: [(j, at(fr), set_time(u, j)) for j, fr in enumerate(frames) if fr[2] == f] for f in colour}
        whole = {j for j, fr in enumerate(frames) if fr[2] not in colour}
        for f in colour:
            for j, q, t in by[f]:
                if q is not None and all(any(r is not None and abs(t - tg) <= MIX_SPAN
                                             and math.hypot(q[0] - r[0], q[1] - r[1]) <= SAME_PLACE * FRAME
                                             for _, r, tg in by[g]) for g in colour if g != f):
                    whole.add(j)
    whole = frozenset(whole)
    u["_visits"] = (key, whole)
    return whole


LONG_LEAST = 0.01   # of a frame: (long_repeats) the least saturated share that can make a frame a long repeat


def long_repeats(tiles, colour):
    """The tiles (n) of the colour filters that are a long exposure taken again at a place where the same filter has a
    shorter one in the same visit: saturated OVER_LEAST of the frame or more (or OVER_EXPOSED of its lit part), and OVER_STEP times as much as that
    filter's other frame within SAME_PLACE of it and MIX_SPAN of its time (unfit's long exposure among short ones,
    for a mosaic). The HIPHASE ring mosaics take a colour set, then one filter again for longer to bring up the faint
    rings: drawn as the newest tile of its filter, the long frame's clipped rings and lifted sky stood in for the set's
    own frame, one band of three at that place (269RI HIPHASEFB001: RED again 2.3x, 8-36% saturated, at the ansae,
    magenta patches; 195RI HIPHASEC001: GRN again, green patches by the limb). They go under (colour_planes), so they
    still fill where the set's own frame does not reach."""
    placed = [t for t in tiles if t["filter"] in colour and "offset" in t and "t" in t]
    out = set()
    for t in placed:
        s = t.get("saturated", 0.0)
        # (or most of what is lit in it, when little of the frame is lit: 269RI's RED again at the right ansa,
        # W1870769631_1, 4.9% of the frame and 88% of its lit part)
        if s < OVER_LEAST and (s < LONG_LEAST or s < OVER_EXPOSED * t.get("lit", 1.0)):
            continue
        reach = SAME_PLACE * max(t["box"][2], t["box"][3])
        if any(o["n"] != t["n"] and o["filter"] == t["filter"] and abs(o["t"] - t["t"]) <= MIX_SPAN
               and math.hypot(o["offset"][0] - t["offset"][0], o["offset"][1] - t["offset"][1]) <= reach
               and s >= OVER_STEP * o.get("saturated", 0.0) for o in placed):
            out.add(t["n"])
    return out


def visit_tiles(u, tiles, colour):
    """The tiles a colour picture draws (visit_frames): the same list when every colour tile is part of a whole visit
    and none is a long exposure taken again (long_repeats, marked "long": drawn under the others)."""
    if _rolling.get() or any("base" in t for t in tiles):
        return tiles   # (a mosaic movie's picture shows each place's newest lap: rolling_layout)
    keep = visit_frames(u, colour)
    # (and a pointing the camera saturated far more than its filters' other tiles: clipped_pointings, as a mosaic
    # movie's picture draws it)
    longs = long_repeats(tiles, colour) | (clipped_pointings(u, [t for t in tiles if t["filter"] in colour]) if colour else set())
    out = [dict(t, long=True) if t["n"] in longs else t for t in tiles if t["filter"] not in colour or t["n"] in keep]
    return tiles if len(out) == len(tiles) and not longs else out


def set_times(shape, placed):
    """When the frame on top at each canvas pixel was taken (float, NaN where none): placed yields (time, alpha,
    left, top) in the order the filter's mosaic draws its tiles (under_first), each alpha (uint8) at left, top."""
    out = np.full(shape, np.nan, np.float64)
    H, W = shape
    for when, alpha, left, top in placed:
        h, w = alpha.shape
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + w, W), min(top + h, H)
        if x1 <= x0 or y1 <= y0:
            continue
        on = alpha[y0 - top:y1 - top, x0 - left:x1 - left] > 127
        out[y0:y1, x0:x1][on] = when
    return out


def placed_tiles(u, p, mine, rect, cache):
    """set_times' input for a filter's tiles (mine) on the view rect's canvas, as _window places them."""
    k = p["k"]
    for t in under_first(mine):
        bx, by, bw, bh = t["box"]
        left = round((t["offset"][0] + bx - rect[0]) * k)
        top = round((t["offset"][1] + by - rect[1]) * k)
        sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
        yield set_time(u, t["n"]), _part(_pic(u, cache, p["display_scale"], t), sw, sh)[..., 3], left, top


def set_time(u, n):
    """When frame n's visit began: the first frame of its camera set (colour_sets), or its own time outside one, so a
    set's filters count as one visit however long the set took (a moon's 12 filter set)."""
    if "_set_time" not in u:
        first = {}
        for run in _pass_sets(u):
            t0 = min(u["frames"][j][3] for _, j in run)
            for _, j in run:
                first[j] = t0
        u["_set_time"] = first
    return u["_set_time"].get(n, u["frames"][n][3])


def set_mask(times, k):
    """Where a colour picture mixes visits (bool, canvas pixels): every colour filter has a frame on top there
    (times: set_times of each) and the first and last were taken more than MIX_SPAN apart, less patches narrower
    than MIX_LEAST of a frame (at k canvas px per reference px). None when nowhere."""
    stack = np.stack(times)
    every = ~np.isnan(stack).any(axis=0)
    if not every.any():
        return None
    with np.errstate(invalid="ignore"):
        spread = np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)
    mixed = (every & (spread > MIX_SPAN)).astype(np.uint8)
    r = max(1, round(MIX_LEAST * FRAME * k / 2))
    mixed = cv2.morphologyEx(mixed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    return mixed.astype(bool) if mixed.any() else None


def unmixed(colour, mixed, grey):
    """The colour picture (colour_picture's RGBA) left out where it mixes visits (set_mask) and the gray base (grey)
    lies under it, so over_grey draws the gray there, fading the colour into it over its feather."""
    if mixed is None:
        return colour
    out = colour.copy()
    out[..., 3][mixed & (grey[..., 3] > 127)] = 0
    return out

FILLED = 0.5       # a pass is all body when the body's disk covers the middle of more than this share of its frames
FILL_DISK = 0.5    # ... and its white is its disk's (DISK_WHITE) when the disk covers less than this share of them
DETAIL = 2.0       # filled passes: how much the local contrast is raised (detail())
DETAIL_SIGMA = 0.05  # ... over this much of a frame
DETAIL_EDGE = 32.0  # ... and on a difference from that mean of this many levels or more, less and less (d = DETAIL x / (1 + |x| /
                    # DETAIL_EDGE)): faint texture (Titan's few per cent) is raised in full, a terminator, a limb against bright
                    # Saturn or a crater's shadow beside its sunlit wall (already all the contrast there is) only up to
                    # DETAIL x DETAIL_EDGE, so they get no black halo or blown rim (Sam, 11-06: crescent moons, the 165TI transit)
DETAIL_KNEE = 0.5   # ... and a change toward white or black takes up to this share of the room the pixel has left
                    # there as it is, the rest rolled off (_soft_detail), so detail never pushes a pixel flat to 0 or 255
FILLED_TOE = 0.04   # filled passes (balanced look) with no sky toe of their own: a soft toe this share of white wide
                    # over black (calibration.display), black lowered by half of it so the midtones are where they were


SKY_MIN = 0.05   # balanced: the share of a pass's pixels that must be dark sky for its blacks to be set from the sky
# ... measured on the darker half of the sky: the noise floor at this percentile above its median (a single
# picture's is the 98th; lower here, since a long-exposure pass's whole sky can glow faintly, Saturn's Shadow's E ring)
SKY_FLOOR_PCT = 90
SKY_TOP_PCT = 99     # ... and each band's black at least this percentile of that dark sky (a single picture's SKY_DARK)
SKY_SMOOTH = 9      # ... on the sky less its mean over this many pixels (of the quarter-size frames, 36 full size)
SKY_TOE = 1.0    # ... and the soft toe above those blacks, this many times the black's height over the sky wide
                 # (calibration.display): the sky's scan lines, not its pixel noise, set how far grain reaches
LONG_EXPOSURE = 10   # pass_scale: frames of a pass exposed this many times longer than the frame that sets its white ...
LONG_FAINT = 0.2     # ... off the body's disk, all fainter than this share of that white (a faint plume's 22 s frames among
                     # a lit crescent's 0.26 s ones, ISS_155EN_PLMHPHR001_PIE), take a white of their own (tile_scale)
SKY_SPREAD = 98     # tile_scale: a movie frame's sky in whole codes (the median rule): its black at least this percentile
                    # of it, as a single picture's (color_image's sky_percentile)
SKY_OUTLIER = 6  # a movie frame's own sky (tile_scale): pixels further under its median than the sky's threshold (5% of
                 # the 99.9th percentile) or this many times its noise are not sky (a lost line calibrates to ~-1 I/F)


def _sky_fine(iofs, masks):
    """The sky's fine structure in the pictures iofs (sky masks): the sky less its own mean over SKY_SMOOTH pixels
    (row and column stray-light stripes, compression blocks, noise), on the darker half of the sky by its 5 pixel
    mean, as one array. Smooth faint light (haze, a ring, the body's glow) is not in it."""
    local = [cv2.blur(i, (5, 5)) for i in iofs]
    sky = np.concatenate([l[m] for l, m in zip(local, masks)])
    return np.concatenate([(i - cv2.blur(i, (SKY_SMOOTH, SKY_SMOOTH)))[m & (l <= np.median(sky))]
                           for i, l, m in zip(iofs, local, masks)])


def tile_scale(scale, f, own_sky=False, seen=None, disk=None, on_body=False, exposure=None, t=None, codes=True):
    """The display scale of one tile of filter f: the pass's, and with own_sky (a movie's frames, each shown
    alone) a black raised to the frame's own sky level plus the band's height over it (sky_tops) where that sky
    sits above the pass's: in the Jupiter approach movie one color set's stray light lifts its sky over the
    pass's level, and its frame showed as an olive square that the next set's didn't. Never lowered (the sky's
    stripes would come back as a veil), and never in a mosaic, whose tiles meet (one tile's black of its own
    shows as a step), unless the body is small (small_body: its tiles are all sky, which meets sky). disk: the
    body's disk on the frame (x, y, radius: _disk_mask's, full resolution pixels) when it is small: a frame lit all
    over by stray light round a moon a few pixels across (Pallene, Hati, Kiviuq) has no dark sky to find, so its sky
    is everything off the disk, and its own black takes the veil away (it went from white to black over the pass
    as the stray light faded). seen: a dict the raised black is put in. on_body: the frame's middle is on the body's
    disk (on_disk), so a frame with no dark sky is the body, never a glow. exposure, t: the frame's exposure (s) and
    time, which put a movie frame off the disk in one of the pass's runs of long exposures (pass_scale's "long") on
    their white. codes: a sky in whole codes is measured as such (black_of); False for a ring pass, whose faint rings in
    the shadow (032RI's silhouette) are in the sky the rule would take under black."""
    out = {**scale, "blacks": [scale["blacks"].get(f, 0.0)]}
    long = scale.get("long")
    if (long and own_sky and not on_body and exposure is not None and exposure >= long["exposure"] and t is not None
            and any(a <= t <= b for a, b in long["runs"])):
        out["white"] = long["white"]
        if seen is not None:
            seen["white"] = long["white"]
    top = scale.get("sky_tops", {}).get(f)
    if not own_sky or (top is None and disk is None and on_body):
        return out   # (a frame of the body, in a pass with no sky height of its own: the pass's black, as before #279)
    # (a pass with no sky height of its own and no small body: only a frame lit all over by a glow gets a black of its
    # own, every other frame keeps the pass's)
    glow_only = top is None and disk is None and not on_body
    black = out["blacks"][0]

    def black_of(iof):
        # the frame's sky as pass_scale finds it, at the size it measures on
        q = iof[::4, ::4].astype(np.float32)
        top_of_sky = 0.05 * np.percentile(q, 99.9)
        m = _dark_sky(q)
        veiled = glow = False
        if disk is not None and disk[2] < SPECK_PX:
            # a body under a pixel across (Earth from Saturn, a few km moon far off): the frame is all sky, and a dark
            # sky found under 5% of its brightest is still the veil's lower part, whose line bands and other filters'
            # levels then showed over black (195RI: N1752968916_1's gray lines, N1752969019_1 a red wash over its set)
            m = np.zeros(q.shape, bool)
        # (a glow's flat floor is what _dark_sky takes for a sky with an offset in it; whether a frame of a pass with no
        # sky height of its own has dark sky is measured from 0, as before _dark_sky)
        unlit = (q < top_of_sky).mean() <= SKY_MIN
        if glow_only and not unlit:
            return None
        if (glow_only or m.mean() <= SKY_MIN) and unlit and disk is None and not on_body:
            # no dark sky under 5% of the top: a frame lit all over by a glow (the forward-scattered light round a
            # backlit plume, ISS_155EN_PLMHPHR001_PIE's jet frames: their sky at a sixth of the jets' root, every one
            # of them a flat gray square in the movie) has a flat floor, its sky; a frame a lit body fills (its darkest
            # quarter terrain) does not, and keeps the pass's black
            lo, floor, hi = (float(v) for v in np.percentile(q, [1, GLOW_FLOOR_PCT, 99.9]))
            if not (hi > floor and floor - lo <= GLOW_FLAT * (hi - floor)):
                return None
            m, top_of_sky, glow = q <= floor, floor, True
        elif m.mean() <= SKY_MIN:
            if disk is None:
                # no dark sky and no small body to take the sky off from (a frame the body fills, 191SA FEATRAK001):
                # the pass's black (the guard the #279 merge lost: 75 of that movie's 120 tiles failed with TypeError)
                return None
            # no dark sky: a small body's frame lit all over (stray light), its sky everything off the disk
            m = ~_disk_mask(q.shape, iof.shape, *disk)
            top_of_sky, veiled = float(np.percentile(q[m], 99.9)) if m.any() else 0.0, True
            if m.mean() <= SKY_MIN:
                return None
        # pixels far under the sky are not sky: a line lost in downlink calibrates to about -1 I/F, and the mean over
        # SKY_SMOOTH pixels below spread a ninth of it onto the rows beside it, which the darker half of the sky then
        # picked up as grain; a faint frame's black went to ~0.09 I/F, over everything in it (35 of the 57 black
        # frames of 425 lit movie passes). They are left out of the sky and given its median, so they spread nothing
        median = float(np.median(q[m]))
        steps = np.abs(np.diff(q, axis=1))[m[:, 1:] & m[:, :-1]]
        noise = 1.4826 * float(np.median(steps)) / math.sqrt(2) if steps.size else 0.0
        low = q < median - max(abs(top_of_sky), SKY_OUTLIER * noise)
        if low.any():
            m &= ~low
            q = np.where(low, np.float32(median), q)
            if m.mean() <= SKY_MIN:
                return None
        (level,), margin = calibration.sky_levels([[q]], [[m]])
        spread, before = 0.0, None
        if codes and not (glow or veiled) and level < median - noise:
            # a sky whose spread is not its pixel noise (a frame stored in 8 bits, its sky a few whole codes in blocks and
            # column stripes, the pixel-to-pixel steps mostly 0): sky_levels' level (its 20th percentile plus 0.84 of
            # that noise, the median on a sky of noise alone) is a code or more under the sky's median, and the upper
            # half of the sky drew as a veil over the movie's black: 089MI's GRN gray, Atlas's RED halo (2016-17 PIE
            # movies). The level is the sky's median
            before, level = level, median
            # and the band's height over it at least the sky's own spread up to its SKY_SPREAD percentile (what that
            # noise measure misses), as a single picture's black sits: the sky's blocks and column stripes over its
            # median, and the faint stray light round the moon they show in, are under black, as in the frame alone
            # (089MI's 2 s UV3 drew its columns as stripes round the moon on the median alone)
            spread = float(np.percentile(q[m], SKY_SPREAD)) - median
            if seen is not None:
                seen["whole_codes"] = True
        if glow:
            # (the glow's floor is its far side, a gentle slope up to the jets' halo: black over the frame's middle,
            # GLOW_BLACK_PCT of it smoothed, so the frame's edge does not show as a square; the jets and the halo
            # close round them stay over it)
            level = float(np.percentile(cv2.blur(q, (SKY_SMOOTH, SKY_SMOOTH)), GLOW_BLACK_PCT))
        if veiled:
            # (the veil is all stray light, smooth, brighter on one side: black over the top of it, SKY_SMOOTH pixels
            # round, so none of it shows; stars and the moon are sharp and stay over it)
            # The mean is taken along the lines and along the columns, each on its own, and black goes over the higher:
            # a round box spread the veil's 2 Hz line bands and column stripes over their neighbours, so the bands
            # rose over a black set under them (195RI, Day the Earth Smiled: thin lines up to 23 of 255 on the first
            # colour set, N1752968916_1's and N1752969019_1's line bands)
            level = max(float(np.percentile(cv2.blur(q, k)[m], VEIL_TOP)) for k in ((SKY_SMOOTH, 1), (1, SKY_SMOOTH)))
        # the band's height over the sky at least this frame's own (its sky's fine structure, as pass_scale measures
        # the pass's): a frame lit by stray light has a grainier sky than the pass's typical one, and in the Jupiter
        # approach movie its red and green grain rose over a black set by the pass's height, a faint red cast
        fine = _sky_fine([q], [m])
        own = float(np.percentile(fine, SKY_TOP_PCT) - np.median(fine)) if fine.size > 100 else 0.0
        # (a pass with no dark sky has no height of its own: the frame's noise margin, as a single picture's)
        raised = level + max(margin if top is None else top, own, spread)
        # and never at or over the frame's lit median (its pixels over the sky): a black there draws the frame black
        # (a veiled or glowing frame's lit pixels are its veil or glow: the sky, which is what goes black)
        lit = q[q >= top_of_sky]
        if before is not None and lit.size and raised >= float(np.median(lit)):
            # (a whole-code sky's black that would draw the frame black: the black it had without that rule, so the
            # frame is never drawn on a lower black than before: 155EN's faint plume frames)
            raised = before + max(margin if top is None else top, own)
            if seen is not None:
                seen.pop("whole_codes", None)
        if raised <= black:
            return None
        if not (veiled or glow) and lit.size and raised >= float(np.median(lit)):
            return None
        if seen is not None:
            seen["black"] = raised
        return {"black": raised, "toe": scale.get("toe")}

    out["black_of"] = black_of
    return out


DISK_WHITE = 99.5   # pass_scale: the percentile of the body's disk that the pass's white is at least
DISK_MARGIN = (0.2, 16)   # ... the disk taken this much wider (of its radius, and full resolution pixels) for SPICE's error
DISK_LEAST = 16     # ... measured only on at least this many pixels of the quarter-size frames


def _disk_pixels(q, shape, x, y, radius):
    """The pixels of q (a frame's I/F at a quarter of its shape, rows and columns [::4]) on the body's disk where the
    geometry cache puts it (x, y: the shift that centres the body, full resolution pixels, bootleg_autonav.find_target;
    radius: the disk's, full resolution pixels), DISK_MARGIN wider. Empty when the disk is not on the frame."""
    if radius <= 0:
        return q[:0, 0]
    return q[_disk_mask(q.shape, shape, x, y, radius)]


def _disk_mask(qshape, shape, x, y, radius):
    """_disk_pixels' disk as a mask of the quarter size frame (qshape) of a frame of the given shape; DISK_MARGIN
    round the disk even when its radius is 0 (a body under a pixel across: SPICE's error round its place)."""
    reach = max(radius, 0) * (1 + DISK_MARGIN[0]) + DISK_MARGIN[1]
    k = 1024 / shape[0]   # (the frame's pixels are full resolution ones scaled to 1024)
    cy, cx = (511.5 - y) / k, (511.5 - x) / k
    r = reach / k
    rows = np.arange(0, shape[0], 4, dtype=np.float32)[:qshape[0], None]
    cols = np.arange(0, shape[1], 4, dtype=np.float32)[None, :qshape[1]]
    return (rows - cy) ** 2 + (cols - cx) ** 2 < r * r


SPECK_PX = 1.0      # tile_scale: a small body under this radius (full resolution px) always takes the veil's black
VEIL_TOP = 99       # tile_scale: a small body's veiled frame's black is over this percentile of its smoothed sky
GLOW_FLOOR_PCT = 25  # tile_scale: a movie frame with no dark sky, lit all over by a glow: its sky is under this percentile
GLOW_BLACK_PCT = 50  # ... and its black over this percentile of the frame, smoothed
GLOW_FLAT = 0.1      # ... when that floor is flat: from the 1st percentile to it under this share of the way on to the top
SMALL_BODY = 0.02   # of a frame: a body whose disk's radius is under this is small (small_body): a speck, not
                   # Enceladus 64 px across the edge of a plume movie, whose plume fills the frame


def _speck(u):
    """True when pass u's body is small (small_body) on most of its placed frames."""
    placed = [fr for fr in u["frames"] if fr[7]]
    return bool(placed) and sum(small_body(u, fr) is not None for fr in placed) * 2 > len(placed)


def small_body(u, frame):
    """The disk (x, y, radius in full resolution pixels) of pass u's body on frame (one of u["frames"]) when the body
    is small on it (under SMALL_BODY of a frame in radius: a small moon, a speck), else None: the sky round it is
    the whole frame but the disk (tile_scale)."""
    *_, x, y, z = frame
    km = RADIUS.get(u["key"][0]) or SPECKS.get(u["key"][0])
    if not z or not km:
        return None   # (a target with no disk of its own, rings or sky, is not one)
    radius = km / (z * IFOV[u["key"][2]])
    return (x, y, radius) if radius < SMALL_BODY * FRAME else None


def on_disk(u, frame):
    """True when frame's middle is on pass u's body's disk (SPICE): the frame shows the body, so a frame of it with no
    dark sky is not lit by a glow (tile_scale). Titan ISS_021TI's full-frame movie frames are its haze all over, a
    flat floor like the 155EN jets' glow, and 66 to 100% of each went black."""
    *_, x, y, z = frame
    km = RADIUS.get(u["key"][0])
    return bool(z and km and math.hypot(x, y) < km / (z * IFOV[u["key"][2]]))


SKY_OFFSET_MOST = 0.25   # _dark_sky: a frame's floor up to this share of its 99.9th percentile is an offset in its sky


def _dark_sky(q):
    """pass_scale's dark sky of a frame (quarter size, I/F): under 5% of the way from its floor (1st percentile, at
    least 0) to its 99.9th percentile. Measured from 0, a sky the calibration left a small even offset in failed the
    test wherever the body was too small to set the 99.9th percentile far above that offset: Phoebe in 2004
    (ISS_000PH_FULROTIN001_PRIME) is 30 px across, its RED, IR1 and UV3 skies sit at 8 to 21% of their 99.9th
    percentile, under 1% of them counted as sky, and every band's black stayed at its 1st percentile, under the sky. On
    the gamma 3 scale the offsets came out as a blue-grey sky behind the moon (RED 2, GRN 18, BL1 32 levels). A floor
    over SKY_OFFSET_MOST of the 99.9th percentile is a lit body, not an offset sky (a moon or Titan's haze filling the
    frame, whose darkest part is no sky): measured from 0 then, as before."""
    top = float(np.percentile(q, 99.9))
    floor = float(np.percentile(q, 1))
    floor = floor if 0.0 < floor <= SKY_OFFSET_MOST * top else 0.0
    return q - floor < 0.05 * (top - floor)


def pass_scale(frames, u, drawn=None, true_colour=False, sky_tops=None, lit_levels=None):
    """The display scale of every tile of the pass (calibration.shared_scale over its frames merged in I/F, as
    mosaic_benchmark.display_scale): {"blacks": {filter: I/F}, "white": I/F, "gamma"}. Where the body fills
    the frames (the middle of most frames on its disk, as in Titan's maps), black goes to the darkest of the body, white to
    the 99.5th percentile and the gamma is eased, and the mosaic's local contrast is raised (detail), so
    the surface's few per cent of contrast shows; passes with dark sky keep the benchmark's scale.
    drawn = the filters the mosaic is drawn from (plan's colour, or its grey filter); true_colour = they are a
    true colour set; sky_tops = optional {filter: I/F} overriding how far above its sky each filter's black sits
    (the measured values come back as "sky_tops", with the soft "toe" above black). lit_levels: a dict given here gets
    each filter's lit median on the scale (linear, white = 1), which the luminance base's gains come from; the
    scale itself is the same with or without it."""
    by, disks, each = {}, {}, []
    # the frames read and calibrated MOVIE_WORKERS at once (in order: the same scale), so a cold pass's plan is not
    # one frame after another (021TI REGMAPNA001: 67 frames, 28 s of a 100 s first movie frame)
    mode = calibration.mode()

    def read(fr):
        with calibration.in_mode(mode):
            lbl, iof, _ = stacking.load_hdr(fr[0], u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP))
        # (only the quarter size picture kept, the frame's size and its exposure: pass_scale's long exposures)
        return None if iof is None else (iof[::4, ::4].astype(np.float32), iof.shape, _exposure(lbl))
    with concurrent.futures.ThreadPoolExecutor(MOVIE_WORKERS) as pool:
        read_all = list(pool.map(read, frames))
    for fr, got in zip(frames, read_all):
        path, _, f, _, _, x, y, z = fr
        if got is not None:
            q, shape, exposure = got
            by.setdefault(f, []).append(q)
            each.append((f, q, exposure, on_disk(u, fr), fr[3]))
            if z:
                km = RADIUS.get(u["key"][0]) or SPECKS.get(u["key"][0], 0)
                disks.setdefault(f, []).append(_disk_pixels(q, shape, x, y, km / (z * IFOV[u["key"][2]])))
    if not by:
        return {"blacks": {}, "white": 1.0, "gamma": 3.0, "filled": False}
    scale = calibration.shared_scale(list(by.values()), 99.9, gamma=3.0)
    blacks, white = dict(zip(by, scale["blacks"])), scale["white"]
    # a body small in the frames (Jupiter ~20 px across a WAC frame, Hyperion, a small moon in a faint stare): the
    # 99.9th percentile of the pass is sky, so the body sits far above white and clips flat. White is at least the
    # DISK_WHITE percentile of the pixels on the body's disk (where SPICE puts it, DISK_MARGIN round it for the
    # pointing's error), as a single picture measures white on its lit pixels; a body that fills enough of the frames
    # to set the pass's 99.9th percentile is not changed by it
    on = {f: np.concatenate(v) for f, v in disks.items() if sum(a.size for a in v) >= DISK_LEAST}
    if on:
        white = max(white, max(float(np.percentile(on[f] - blacks[f], DISK_WHITE)) for f in on))
    # all body: the geometry cache puts the middle of most frames on the body's disk (a plume or limb pass of
    # mostly sky, however bright its scattered light, is not)
    radius = FILL_RADIUS.get(u["key"][0], 0) / IFOV[u["key"][2]]
    inside = [math.hypot(x, y) < radius / z for *_, x, y, z in frames if z]
    floor = float(np.mean(inside)) if inside else 0.0
    filled = floor > FILLED
    gamma = 3.0
    if filled and calibration.look() == "balanced":
        # The classic gamma 1.5 (a steeper curve lifts the dark end's noise and steps into view). True colour: one black and white for the filters drawn, so the colour is what they saw
        # rather than how differently each was stretched (black the darkest one's 1st percentile, at most half the
        # brightest's 99.5th, which is white: a black above the white would stretch noise into colour). False
        # colour (methane bands, UV, IR: no natural colour to keep) and grey: each filter's black its own 1st
        # percentile, so every band shows its own contrast, under one white (the widest band's): a white per band
        # would stretch a dim band's (MT2's) tile-to-tile errors several times over into coloured tiles
        lows = {f: float(np.percentile(np.concatenate([i.ravel() for i in iofs]), 1)) for f, iofs in by.items()}
        tops = {f: float(np.percentile(np.concatenate([i.ravel() for i in iofs]), 99.5)) for f, iofs in by.items()}
        mine = [f for f in (drawn or by) if f in by] or list(by)
        gamma = 1.5
        if true_colour:
            top = max(tops[f] for f in mine)
            black = min(min(lows[f] for f in mine), top / 2)
            blacks, white = {f: black for f in by}, top - black
        else:
            blacks, white = dict(lows), max(tops[f] - lows[f] for f in by)
    elif filled:
        blacks = {f: float(np.percentile(np.concatenate([i.ravel() for i in iofs]), 1)) for f, iofs in by.items()}
        white = max(float(np.percentile(np.concatenate([i.ravel() for i in iofs]) - blacks[f], 99.5))
                    for f, iofs in by.items())
        gamma = 1.5
    small = filled and on and sum(v.size for v in on.values()) < FILL_DISK * sum(i.size for iofs in by.values() for i in iofs)
    if small:
        # a body in the middle of the frames but small in them (Titan 40 px across in 000TI's movie, Dione in 038DI's, an
        # Enceladus plume movie): the 99.5th percentile of the frames is on the sky or in the body's middle, and the
        # body clipped white. White at least the DISK_WHITE percentile of its disk, as a body against the sky has (a
        # body over most of the frames already sets their 99.5th percentile: left as it is)
        white = max(white, max(float(np.percentile(on[f] - blacks[f], DISK_WHITE)) for f in on))
    toe = None
    if calibration.look() == "balanced":
        # where the pass has dark sky, no band's black below that sky's level plus the noise margin, as a single
        # picture's (calibration.sky_levels): the 1st percentile of a pass that is mostly sky sits in the sky's
        # noise, so the sky came out a gray, scan-lined veil around the body once the tiles were put together
        masks = {f: [_dark_sky(i) for i in iofs] for f, iofs in by.items()}
        if all(sum(int(m.sum()) for m in ms) > SKY_MIN * sum(m.size for m in ms) for ms in masks.values()):
            levels, margin = calibration.sky_levels(list(by.values()), list(masks.values()))
            # How far each band's black sits over its sky is measured on the sky's fine structure only: the sky
            # less its own mean over SKY_SMOOTH pixels (its row and column stray-light stripes, compression
            # blocks and noise), on the darker half of the sky. Smooth faint light (Saturn's Shadow's haze and E
            # ring, a haze limb, the body's glow) is not in it, so it stays above black
            fine = {f: _sky_fine(iofs, masks[f]) for f, iofs in by.items()}
            # with a noise floor (the noisiest band's SKY_FLOOR_PCT percentile above the median): the pixel-difference
            # noise is about 0 on frames stored in 8 bits
            margin = max(margin, calibration.noise_floor(list(fine.values()), SKY_FLOOR_PCT))
            # and each band on its own over SKY_TOP_PCT of that fine structure: the false color gains (MT3's up to
            # 5x) lift whatever of a dim band's sky is left above its black far more than the others'
            tops = {}
            for f, v in fine.items():
                if sky_tops and f in sky_tops:
                    tops[f] = float(sky_tops[f])
                else:
                    top = float(np.percentile(v, SKY_TOP_PCT) - np.median(v)) if v.size > 100 else 0.0
                    tops[f] = max(margin, top)
            toe = SKY_TOE * max(tops.values())
            blacks = {f: max(blacks[f], level + tops[f]) for f, level in zip(by, levels)}
    if calibration.look() == "balanced" and white > 0:
        # a bright subject (a moon's limb, lit rings) sits in the top tenth of the range on the benchmark's gamma 3.0
        # and reads as blown out: the gamma eases toward the single pictures' (calibration.EASE_PASS) by the pass's lit
        # median (its brightest filter's, white = 1), as a single picture's highlights do (calibration.tone)
        lit = max(calibration.lit_median((np.concatenate([i.ravel() for i in iofs]) - blacks[f]) / white)
                  for f, iofs in by.items())
        gamma = calibration.eased_gamma(gamma, lit, calibration.EASE_PASS)
    # the local contrast (detail) only where the body fills the frames: on a small disk against the sky (Dione 180 px
    # across in 038DI ZEROPHASE001's 1024 px movie, Rhea in 056RH's) the neighbourhood's mean is half sky, so every
    # pixel of the disk was raised by DETAIL times its own brightness and the disk came out flat white
    out = {"blacks": blacks, "white": white, "gamma": gamma, "filled": filled, "floor": round(floor, 3),
           "detail": bool(filled and not small)}
    long = _long_white(each, blacks, white) if u.get("movie") and not filled else None
    if long:
        out["long"] = long
    if toe:
        out["toe"], out["sky_tops"] = toe, tops
    if calibration.look() == "balanced":
        # the brightest of the pass rolls off past the shoulder instead of clipping flat at white, as a single
        # picture's does (calibration.display): a filled pass's white is its 99.5th percentile, so its sunlit crater
        # walls and bright limb, half a percent of every tile, were one flat 255 with a hard edge (Sam, 11-06: "hard
        # lines" on the moons; 164TE's mosaic 5.5% at 255 against 0.03% in its frames drawn alone)
        out["shoulder"] = calibration.SHOULDER
        if filled and not toe and white > 0:
            # and its shadows fade into black over a toe instead of clipping at the 1st percentile: black lowered by
            # half the toe, so from there up the picture is as before and the darkest percent keeps its shape
            out["toe"] = FILLED_TOE * white
            out["blacks"] = {f: b - out["toe"] / 2 for f, b in blacks.items()}
    mine = [f for f in (drawn or []) if f in by]
    if calibration.false_balanced() and len(mine) == 3 and not true_colour:
        # false color: each band's gain to bring the body's lit median (above that band's black) to the bands'
        # mean, so the planet comes out gray and only its differences between bands show (calibration.false_gains);
        # measured on the whole pass, so every tile has the same balance
        levels = []
        for f in mine:
            v = np.concatenate([i.ravel() for i in by[f]]) - blacks[f]
            lit = v[v > 0.2 * np.percentile(v, 99)]
            levels.append(float(np.median(lit)) if lit.size else 0.0)
        if min(levels) > 0:
            out["balance"] = dict(zip(mine, calibration.balance(levels, calibration.tint_of(u["key"][0]))))
            # and the body's typical color after it, so the broad-color flattening holds one color as tiles arrive
            shown = [out["balance"][f] * v for f, v in zip(mine, levels)]
            out["typical"] = {f: float(np.log(v * len(shown) / sum(shown))) for f, v in zip(mine, shown)}
    elif calibration.false_balanced() and len(mine) == 2:
        # two filters: each band's gain to the pair's mean, which calibration.color_mix balances as three channels
        # (two_bands), and the typical color of those three, a list (the green channel is no one filter's)
        levels = []
        for f in mine:
            v = np.concatenate([i.ravel() for i in by[f]]) - blacks[f]
            lit = v[v > 0.2 * np.percentile(v, 99)]
            levels.append(float(np.median(lit)) if lit.size else 0.0)
        mix = calibration.color_mix(u["key"][2], mine, u["key"][0], [sum(levels) / 2 / v for v in levels], obs=u["key"][1]) \
            if min(levels) > 0 else None
        if mix is not None and not isinstance(mix, calibration.FalseMix):
            # (an approximate color pair: its levels, for a band the body's table lacks, calibration.pair_mix)
            out["balance"] = {f: sum(levels) / 2 / v for f, v in zip(mine, levels)}
        if isinstance(mix, calibration.FalseMix):
            out["balance"] = {f: sum(levels) / 2 / v for f, v in zip(mine, levels)}
            shown = [g * v for g, v in zip(np.diagonal(mix).tolist(), calibration.two_bands(levels))]
            out["typical"] = [float(np.log(v * len(shown) / sum(shown))) for v in shown]
    if lit_levels is not None:
        for f, iofs in by.items():
            v = (np.concatenate([i.ravel() for i in iofs]) - blacks[f]) / white
            lit = v[v > 0.2 * np.percentile(v, 99)]
            lit_levels[f] = float(np.median(lit)) if lit.size else 0.0
    return out


def _exposure(lbl):
    """A frame's exposure in s from its label (EXPOSURE_DURATION, ms), or None (bootleg_autonav.exposure_s)."""
    import bootleg_autonav as ba
    return ba.exposure_s(lbl)


def _long_white(each, blacks, white):
    """pass_scale: the white of a movie's runs of long exposures, {"exposure": s, "white": I/F, "runs": [[t0, t1]...]},
    or None. One white per pass draws a faint subject the pass takes in long exposures against the white its short
    exposures of a lit body set: the 155EN plume movie's jets (22 s frames, 50 to 60 codes over their sky) came out
    under 57 of 255 on the white of its 0.26 s crescent frames. A run of frames in a row exposed LONG_EXPOSURE times
    longer than the frame that sets the pass's white (the brightest above its black), none of them on the body's disk
    and every one under LONG_FAINT of that white, takes the white of all such runs: the 99.9th percentile of their
    frames above their blacks over LONG_FAINT, so they keep one scale among themselves, and a run at LONG_FAINT of the
    pass's white is drawn the same either way (a full white on the jets' roots lifted the glow round them into a gray
    square with the frame's line bands in it, 155EN's second plume pass). A run with a frame on the disk (Titan's
    full-disk frames, the plume movie's own long UV exposures of the lit body) keeps the pass's. each: (filter,
    quarter size I/F, exposure s or None, on the body's disk, time) per frame, in time order."""
    known = [(float(np.percentile(q, 99.9)) - blacks.get(f, 0.0), e) for f, q, e, *_ in each if e]
    if not known:
        return None
    threshold = LONG_EXPOSURE * max(known)[1]
    runs, run = [], []
    for fr in each + [None]:
        if fr is not None and fr[2] and fr[2] >= threshold:
            run.append(fr)
            continue
        if run and not any(d for _, _, _, d, _ in run) and \
                all(float(np.percentile(q, 99.9)) - blacks.get(f, 0.0) < LONG_FAINT * white for f, q, *_ in run):
            runs.append(run)
        run = []
    if not runs:
        return None
    own = float(np.percentile(np.concatenate([(q - blacks.get(f, 0.0)).ravel() for r in runs for f, q, *_ in r]), 99.9))
    own /= LONG_FAINT
    return {"exposure": threshold, "white": own, "runs": [[r[0][4], r[-1][4]] for r in runs]} if own > 0 else None


def _lit_crop(image, side):
    """A tile's picture: image (an RGBA canvas, unlit outside the frame on it) at side x side px, the bytes PIL's
    LANCZOS resize of the whole canvas gives (the canvas itself when side is its size), cut to its lit pixels: (the
    cut, its top row, its left column), or None when no pixel is lit. Made from the lit part: PIL resizes RGBA
    premultiplied (RGBa), across and then down, each row and then each column on its own, and an unlit pixel is 0
    premultiplied, so only the rows with a lit pixel are resized across, and only the columns those leave lit are
    resized down (a movie tile's 3072 px canvas is ~1400 px lit, and the whole canvas's resize was half of making
    the tile). The lit boxes are PIL's getbbox, one pass over the pixels in C, and the resized canvas is never made
    whole (both cost more than the lit part's resize)."""
    h, w = image.shape[:2]
    box = Image.fromarray(image).getbbox(alpha_only=True)
    if box is None:
        return None
    c0, r0, c1, r1 = box
    if side == h:
        return image[r0:r1, c0:c1].copy(), r0, c0
    strip = Image.new("RGBa", (w, r1 - r0))
    strip.paste(Image.fromarray(np.ascontiguousarray(image[r0:r1, c0:c1])).convert("RGBa"), (c0, 0))
    across = strip.resize((side, r1 - r0), Image.LANCZOS)
    # the columns with anything in them, colour or alpha
    used = across.getbbox(alpha_only=False)
    if used is None:
        return None
    x0, x1 = used[0], used[2]
    tall = Image.new("RGBa", (x1 - x0, h))
    tall.paste(across.crop((x0, 0, x1, r1 - r0)), (0, r0))
    down = tall.resize((x1 - x0, side), Image.LANCZOS)
    box = down.getbbox(alpha_only=True)
    if box is None:
        return None
    return np.asarray(down.crop(box).convert("RGBA")), box[1], x0 + box[0]


def tile(u, n, cache, scale=None):
    """Tile n of the pass, made once: its picture north up, scaled to the pass's reference distance and cropped
    (_tiles/<n>.png), and its report: offset = where the frame's middle sits from the body's centre and box = the
    crop around it (reference pixels); no offset when SPICE could not place it."""
    if scale is None:
        scale = plan(u, cache)["display_scale"]
    rec = _kept_tiles(u, cache, scale)
    if rec is not None:
        with _lock:
            kept = rec["tiles"].get(n)
        if kept is not None:
            return kept
    return _tile(u, n, cache, scale, rec["tiles_dir"] if rec is not None else _tiles(u, cache, scale), rec)


def _tile(u, n, cache, scale, there, rec=None):
    """Tile n's report from the cache, or the tile made (tile) and its report, as it reads back from the cache;
    kept in the pass's record rec, so it is read once."""
    base = os.path.join(there, str(n))
    # one lock per tile, so a movie's frames made ahead can be made side by side
    with _lock:
        lock = _tile_locks.setdefault((u["key"], calibration.mode(), n), threading.RLock())
    with lock:
        if rec is not None:
            with _lock:
                kept = rec["tiles"].get(n)
            if kept is not None:
                return kept
        out = _tile_made(u, n, cache, scale, base)
        if rec is not None:
            with _lock:
                out = rec["tiles"].setdefault(n, out)
        return out


def _tile_made(u, n, cache, scale, base):
    """(_tile, holding the tile's lock) the report in base.json, or the tile made and its report."""
    if os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            out = json.load(fh)
        if out.get("lost", 0.0) > MOVIE_LOST and "lost_inside" not in out and os.path.exists(base + ".png"):
            # (a tile made before its report kept lost_inside: worked out from its picture, as lost_held reads it)
            try:
                out["lost_inside"] = lost_inside(np.asarray(Image.open(base + ".png"))[..., 3])
            except (OSError, IndexError, ValueError):
                pass
        return out
    path, fid, f, t, nm, x, y, z = u["frames"][n]
    k = z / u["z"] if z else 1.0
    seen = {}
    disk = small_body(u, u["frames"][n])
    # (a pass with long exposures of their own white: this frame's exposure, from its label)
    exposure = _exposure(label_handler.label(path, as_png=True)) if (scale or {}).get("long") else None
    try:
        with (calibration.hdr_capture() if HDR_ON else contextlib.nullcontext(None)) as sink:
            image, _, rep = color_image.processed_frame([path], hdr=True, scale=tile_scale(scale, f, bool(u.get("movie") or disk), seen, disk,
                                                                                           on_disk(u, u["frames"][n]), exposure, t,
                                                                                           not _ring(u)),
                                                        repeat_window=u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP),
                                                        around=_around(u, n) if u.get("movie") else _same_pointing(u, n),
                                                        turn=view_turn(u))
    except Exception as e:
        image, rep, sink = None, {"why": f"{type(e).__name__}: {e}"[:200]}, None
    if (image is not None and u.get("mosaic") and rep.get("calibrated") is False and calibration.step("calibrate")
            and f in ((scale or {}).get("blacks") or {})):
        # a frame that can't be calibrated (an 8LSB frame: only its low 8 bits were sent, which wrap round into a black
        # and white lace where the ground is bright) among tiles of its filter that are: left out, as a colour set leaves
        # out such a channel. Phoebe 2004-06-11 has them at pointings of their own
        image, rep = None, {**rep, "why": "can't be calibrated (8LSB or an unknown filter or gain): left out of the mosaic"}
    share = float(rep.get("saturated_share") or 0.0) if image is not None else 0.0
    if image is not None and u.get("mosaic") and share >= SATURATED_ALL and calibration.step("calibrate"):
        # a frame the camera saturated all over carries no picture: calibrated, it is one flat field at the top of the
        # camera's range over its exposure, so a long exposure's is dark and a short one's bright (101SA SPOLEDYN001 W
        # took 10 to 82 s frames between its 2.6 s ones: its places flickered black and white lap to lap). Left out
        image, rep = None, {**rep, "why": f"saturated all over ({share:.0%}): left out of the mosaic"}
    out = {"n": n, "id": fid, "filter": f, "t": t, "stacked": rep.get("stacked"), "calibrated": rep.get("calibrated"), **seen}
    if rep.get("spikes_px"):
        out["spikes_px"] = rep["spikes_px"]
    if rep.get("lost_px"):
        # the share of the frame lost in downlink that no repeat or fill made up (load_aligned's lost_px): partial()
        out["lost"] = round(rep["lost_px"][1] / FRAME ** 2, 4)
    if share:
        # the share of the frame the camera saturated in every exposure merged (load_aligned's, the pixels drawn white:
        # over_exposed), and the share of it that is lit (LIT_LEVEL), what over_exposed measures it against
        out["saturated"] = share
        if image is not None:
            inside = image[..., 3] > 0
            lit = inside & (image[..., :3].max(axis=2) >= LIT_LEVEL)
            out["lit"] = round(float(lit.sum()) / max(1, int(inside.sum())), 4)
    if image is not None and disk is None:
        # what the tile shows, levels on the display scale: its floor (1st percentile) and top (99.99th: a hundred
        # pixels of a frame, a small lit crescent) inside its alpha, what empty() measures (a speck's frame, whose
        # body is under a hundred pixels, is never empty: none written)
        inside = image[..., 3] > 0
        if inside.any():
            v = image[..., :3].max(axis=2)[inside]
            out["floor"], out["top"] = (int(x) for x in np.percentile(v, [1, EMPTY_TOP_PCT], method="lower"))
    os.makedirs(os.path.dirname(base), exist_ok=True)
    if image is not None and "frame_offset" in rep:
        side = round(image.shape[0] * k)
        lit = _lit_crop(image, side)
        if lit is not None:
            crop, a, c = lit
            b, d = a + crop.shape[0], c + crop.shape[1]
            Image.fromarray(crop).save(base + ".png", compress_level=1)
            _keep_made(base + ".png", crop)
            _keep_tile_map(sink, image, side, crop, base)
            out.update({"native_offset": rep["frame_offset"], "offset": [v * k for v in rep["frame_offset"]],
                        "box": [int(c) - side / 2, int(a) - side / 2, int(d - c), int(b - a)]})
            _register(u, n, out, crop, cache, scale)
            out["outline"] = _corners(out, crop[..., 3])
            if out.get("lost", 0.0) > MOVIE_LOST:
                out["lost_inside"] = lost_inside(crop[..., 3])
    else:
        out["why"] = rep.get("why", "not placed by SPICE")
    data = json.dumps(out, default=str)
    reel._cached(base + ".json", data.encode)
    return json.loads(data)


def _around(u, n):
    """The paths of the frames of tile n's filter just before and just after it in the pass (None at either end):
    what a movie's frame is checked against for one-frame spikes (color_image.load_aligned, image_correction.spikes)."""
    frames, f = u["frames"], u["frames"][n][2]
    before = next((frames[j][0] for j in range(n - 1, -1, -1) if frames[j][2] == f), None)
    after = next((frames[j][0] for j in range(n + 1, len(frames)) if frames[j][2] == f), None)
    return [before, after]


SPIKE_GAP = 600      # s: a frame of the pass this near in time, at the same pointing, is what a tile's spikes are checked against
SPIKE_FRAMES = 2


def _same_pointing(u, n):
    """The paths of the frames of the pass at tile n's pointing (SAME_PLACE, by the geometry cache), up to SPIKE_FRAMES
    of them nearest in time within SPIKE_GAP, any filter: what a mosaic's tile is checked against for one-frame spikes
    (color_image.load_aligned, image_correction.spikes), as a movie's frame is against its neighbours (_around). A
    cosmic ray is in one frame only, a star in every filter at that pointing, so the long exposures of a moon's dark
    side (Pandora ISS_253PA_PANDORA001_PIE) no longer speckle the mosaic with them. None for a frame SPICE has no place
    for or with no other frame at its pointing."""
    frames = u["frames"]
    _, _, f, t, _, x, y, z = frames[n]
    if not z:
        return None
    k = z / u["z"] if u["z"] else 1.0
    near = sorted((abs(tj - t), pj) for j, (pj, _, fj, tj, _, xj, yj, zj) in enumerate(frames)
                  if j != n and zj and abs(tj - t) <= SPIKE_GAP and math.hypot(x - xj, y - yj) * k <= SAME_PLACE * FRAME)
    return [p for _, p in near[:SPIKE_FRAMES]] or None


REGISTER_GAP = 180   # s: a tile of another filter taken this soon before, at the same pointing, is what it is registered to
REGISTER_MAX = 0.04  # of a frame: the largest correction to SPICE's placement that is believed
REGISTER_BODY_MAX = 0.15  # ... or up to this much, when another measure agrees with it (_register)
REGISTER_AGREE = 3.0      # px: how near another measure's move must be to the match's ...
REGISTER_SHARE = 0.05     # ... or this share of the move, the larger
# of a frame, per camera: a camera whose tiles are searched only this near SPICE's place (and their edges left out,
# REGISTER_INSET), a larger move being a false match. The WAC: between the filters of one pointing it drifts 3 to 5 px
# more than SPICE shows (stars of W1752982634_1..722_16), and a whole search let false matches on a black scene move
# 61 tiles of Day the Earth Smiled (W1752982722_16) by 15 to 40 px. Not the NAC: its pixels are ten times finer and
# SPICE's place of a frame is often 20 to 30 px off the others' on a close moon (Rhea ISS_018RH_REGCOL001, +22,-18
# on 22 tiles; Iapetus ISS_049IA_REGMAPTRL001), which a 12 px search could not reach (the filters landed apart)
REGISTER_NEAR = {"W": 8 / 1024}
REGISTER_INSET = 16  # px: each tile's edge (where its alpha ends) is left out of the match by this much
# of a frame, per camera: two colour filters' tiles of one pointing that do not match within REGISTER_NEAR (or match
# only by the lit area's centroid) are searched this far, and a match is believed where phase correlation over the
# whole overlap peaks high (REGISTER_SURE[2]), or where it and the edges' (peaks of REGISTER_SURE[0] and [1] at least)
# agree (image_correction.WEAK_AGREE). 195RI HIPHASEC001's RED and GRN frames on the rings sit 10 to 29 px off their
# BL1 (peaks of 0.4 to 1.0), past the WAC's 8 px, and kept SPICE's places: red and green rims on every ring edge. The
# false matches the near search keeps out were black scenes and violet or infrared frames, which this does not search
REGISTER_FAR = {"W": 32 / 1024}
REGISTER_SURE = (0.2, 0.1, 0.5)   # least peaks: phase, edges with it, phase alone


def _register_to(u, n):
    """The tile tile n is registered to (_register): of the frames of the pass in another filter at its pointing
    (SAME_PLACE, by the geometry cache) taken at most REGISTER_GAP before it (only the colour filters' when n is in a
    colour filter and there are some, below), the one nearest it in wavelength (the first of those as near), so each
    filter lands on the one most like it and through it on that pointing's first frame; None for a pointing's first frame, or one SPICE (the geometry cache) has no place for. Nearest in
    wavelength, not simply the first: a Titan cycle through many filters (215TI M90R1CLD125: CB3, MT1, MT3, RED, GRN,
    BL1, ...) put RED and GRN each on MT3, where Titan's haze looks nothing like it does in the visible, and the two
    matches (edges, centroid) landed 4 px apart, a magenta and green rim round Titan in the movie; GRN now lands on
    RED and BL1 on GRN."""
    frames = u["frames"]
    _, _, f, t, nm, x, y, z = frames[n]
    if not z:
        return None
    k = z / u["z"] if u["z"] else 1.0
    there = [j for j in range(n) if frames[j][2] != f and frames[j][7] and 0 <= t - frames[j][3] <= REGISTER_GAP
             and math.hypot(x - frames[j][5], y - frames[j][6]) * k <= SAME_PLACE * FRAME]
    if not there:
        return None
    # a colour filter's frame lands on a frame in a colour filter, when there is one: the others
    # (a violet or infrared frame taken first) can look nothing like it (195RI HIPHASEC001's VIO frames near the limb
    # are black, its IR3 frames another scene), so the match failed and RED and GRN kept SPICE's places, 5 to 12 px off
    # BL1: red and green rims on every ring edge
    colour = _colour_filters(u)
    if f in colour:
        there = [j for j in there if frames[j][2] in colour] or there
    # of those, the one nearest in wavelength (the first of those as near)
    return min(there, key=lambda j: abs((frames[j][4] or 0) - (nm or 0)))


def _colour_filters(u):
    """The pass's colour filters (_filters), worked out once; none when a frame has no wavelength (a test's)."""
    if "_colour_filters" not in u:
        known = all(fr[4] is not None for fr in u["frames"])
        u["_colour_filters"] = frozenset((_filters(u)[3] if known else None) or ())
    return u["_colour_filters"]


def _register(u, n, out, crop, cache, scale):
    """C8, the filters registered to each other: SPICE places each frame on its own, and the few pixels its pointing
    is off differ from frame to frame, so the filters of one pointing landed a little apart and every limb had a red
    and a cyan rim (Dione). Tile n (its report out, crop its picture as made) is moved onto the tile it is registered
    to (_register_to) by the pipeline's own alignment of a set's channels (image_correction.align_with_masks: phase
    correlation, then on edges, then by the lit area's centroid) over the part of the view both cover; out["offset"]
    is changed by the shift found (out["spice_offset"] keeps SPICE's), out["registered"] says to what and how. A
    shift past REGISTER_MAX of a frame, or none found, leaves SPICE's place."""
    j = _register_to(u, n)
    if j is None or not calibration.step("align"):   # Settings > Processing: SPICE's places as they are
        return
    q = tile(u, j, cache, scale)
    path = os.path.join(_tiles(u, cache, scale), f"{j}.png")
    if "offset" not in q or not os.path.exists(path):
        return
    with _lock:
        ref = _made_pictures.get(path)
    if ref is None:
        ref = np.asarray(Image.open(path).convert("RGBA"))
    near = REGISTER_NEAR.get(u["key"][2])
    shift, how = _shift_onto(q, ref, q["offset"], out, crop, out["offset"], within=near * FRAME if near else None)
    far = REGISTER_FAR.get(u["key"][2])
    colour = _colour_filters(u)
    if (shift is None and how == "not aligned" or how is not None and how.startswith("centroid")) and far \
            and u["frames"][n][2] in colour and u["frames"][j][2] in colour:
        # (a centroid's match too: 195RI's W1752977411_1 landed 5.8 px from SPICE by it, 19 px off its BL1)
        wide, said = _shift_onto(q, ref, q["offset"], out, crop, out["offset"], within=far * FRAME, sure=REGISTER_SURE)
        if wide is not None or shift is None:
            shift, how = wide, said
    if shift is None and how is not None and how.startswith("failed"):
        out["registered"] = {"to": q["id"], "why": how[7:]}
        return
    if shift is not None and REGISTER_MAX * FRAME < math.hypot(*shift) <= REGISTER_BODY_MAX * FRAME:
        # SPICE's pointing of a moon can jump tens of px between frames seconds apart: Dione's 038DI ZEROPHASE001 20 to
        # 45 px (N1549196942_1 sits 42 px from the frames either side), Hyperion's 153HY 70 to 110 px, Helene's 149HE
        # 30 to 45 px. A set's channels whose match was just under REGISTER_MAX were moved and those just over it were
        # not, so one set's channels were drawn at two places: three Diones in a column (N1549197025_1), a second
        # Hyperion beside the first, a yellow and blue Helene. A match past REGISTER_MAX is believed, up to
        # REGISTER_BODY_MAX, when another measure finds the same move (within REGISTER_AGREE, or REGISTER_SHARE of the
        # move): the whole overlap's phase correlation with REGISTER_SURE's bars (the WAC's wide search below), or the
        # lit area's centroid when the whole body is in both tiles
        agree = max(REGISTER_AGREE, REGISTER_SHARE * math.hypot(*shift))
        same = lambda m: m is not None and math.hypot(m[0] - shift[0], m[1] - shift[1]) <= agree
        wide, _ = _shift_onto(q, ref, q["offset"], out, crop, out["offset"], within=REGISTER_BODY_MAX * FRAME, sure=REGISTER_SURE)
        if same(wide):
            how = f"{how}, wide search agrees ({wide[0]:+.1f},{wide[1]:+.1f})"
        else:
            # (a match that is itself the centroid's is not confirmed by it: Atlas N1870697837_1's 112 px)
            c = None if how.startswith("centroid") else _centroid_onto(q, ref, q["offset"], out, crop, out["offset"])
            if not same(c):
                out["registered"] = {"to": q["id"], "how": how, "kept": "SPICE's place"}
                return
            how = f"{how}, centroid agrees ({c[0]:+.1f},{c[1]:+.1f})"
    elif shift is None or math.hypot(*shift) > REGISTER_MAX * FRAME:
        if how is not None:
            out["registered"] = {"to": q["id"], "how": how, "kept": "SPICE's place"}
        return
    # align_with_masks moves the picture by -shift to land on the reference: its place moves the same way
    dx, dy = shift
    out["spice_offset"] = out["offset"]
    out["offset"] = [out["offset"][0] - dx, out["offset"][1] - dy]
    out["registered"] = {"to": q["id"], "how": how, "shift": [round(dx, 2), round(dy, 2)]}


def _tile_overlap(q, ref, at_q, t, crop, at_t, around=None, where=None):
    """The part of the view tiles q (picture ref, middle at at_q) and t (picture crop, middle at at_t) both cover:
    ([q's, t's] grey BGR crops, [their alpha masks], the rounding of each crop's corner to whole pixels as
    ([x of q, x of t], [y of q, y of t])), or None when they overlap by under 64 px either way. around = (x, y, half):
    only the square of half side half round (x, y) of it, unless that leaves under 64 px (_shift_onto's); where, a
    dict, is given the part's corner (x0, y0) and whether around cut it ("cut")."""
    corners = []
    for s, at, im in ((q, at_q, ref), (t, at_t, crop)):
        corners.append((at[0] + s["box"][0], at[1] + s["box"][1], im))
    x0 = max(c[0] for c in corners)
    y0 = max(c[1] for c in corners)
    x1 = min(c[0] + c[2].shape[1] for c in corners)
    y1 = min(c[1] + c[2].shape[0] for c in corners)
    if x1 - x0 < 64 or y1 - y0 < 64:
        return None
    cut = False
    if around is not None:
        ax, ay, half = around
        box = (max(x0, ax - half), max(y0, ay - half), min(x1, ax + half), min(y1, ay + half))
        if box[2] - box[0] >= 64 and box[3] - box[1] >= 64:
            x0, y0, x1, y1 = box
            cut = True
    if where is not None:
        where.update(x0=x0, y0=y0, cut=cut)
    imgs, masks = [], []
    for cx, cy, im in corners:
        left, top = int(round(x0 - cx)), int(round(y0 - cy))
        part = im[top:top + int(y1 - y0), left:left + int(x1 - x0)]
        gray = cv2.cvtColor(np.ascontiguousarray(part[..., :3]), cv2.COLOR_RGB2GRAY)
        imgs.append(cv2.cvtColor(np.where(part[..., 3] > 0, gray, 0).astype(np.uint8), cv2.COLOR_GRAY2BGR))
        masks.append(part[..., 3] > 0)
    h = min(i.shape[0] for i in imgs)
    w = min(i.shape[1] for i in imgs)
    rest = [(cx - x0) - round(cx - x0) for cx, _, _ in corners], [(cy - y0) - round(cy - y0) for _, cy, _ in corners]
    return [i[:h, :w] for i in imgs], [m[:h, :w] for m in masks], rest


def _centroid_onto(q, ref, at_q, t, crop, at_t):
    """How far tile t is from tile q by the lit area's centroid (image_correction.centroid_shift) over the part of
    the view both cover, as _shift_onto measures (reference pixels t's place moves back by); None when the body is
    not wholly inside that part in both."""
    got = _tile_overlap(q, ref, at_q, t, crop, at_t)
    if got is None:
        return None
    imgs, _, rest = got
    c = image_correction.centroid_shift(imgs[0], imgs[1], max_shift=REGISTER_BODY_MAX * FRAME)
    return None if c is None else (c[0] + rest[0][1] - rest[0][0], c[1] + rest[1][1] - rest[1][0])


def _shift_onto(q, ref, at_q, t, crop, at_t, within=None, sure=None, around=None, holes=(), kept=None):
    """How far tile t (its picture crop, its middle put at at_t) is from tile q (picture ref, middle at at_q) over
    the part of the view both cover, by the pipeline's own alignment of a set's channels
    (image_correction.align_with_masks: phase correlation, then on edges, then by the lit area's centroid): (dx, dy),
    reference pixels, that t's place moves back by to land on q, and how it was found; (None, how) when nothing was
    found, (None, None) when the two hardly overlap there, (None, "failed <why>") when the alignment broke.
    within = px: only a move this small from where the two are placed is searched (image_correction.guided_shift's
    search round no shift), and each tile's edge (REGISTER_INSET) is left out of both, so neither tile's border is
    matched as if it were the scene (_register); None: the whole alignment, as the stabilization chains use it.
    sure = least phase correlation peaks (REGISTER_SURE) for REGISTER_FAR's wider search, over the whole overlap
    (image_correction.find_shift_whole): a match is believed when its peak is high, or when the edges' match agrees with it.
    around = (x, y, half): only the square of half side half round (x, y) is matched (the stabilization chain's
    target, steady_chain), unless that leaves under 64 px; holes = [(x, y, r, behind)]: discs left out of both
    pictures (other bodies, steady_chain), behind for a body further off than the target, whose disc stops at
    kept = (x, y, r), the target's own disk, which is in front of it; a hole over the square round a small target
    (around) matches nothing: (None, "other body"). All in the coordinates of at_q and at_t."""
    where = {}
    got = _tile_overlap(q, ref, at_q, t, crop, at_t, around, where)
    if got is None:
        return None, None
    imgs, masks, rest = got
    if holes:
        # (the same discs out of both, so neither picture's other body is matched, and the holes themselves stay put)
        h, w = masks[0].shape
        x0, y0 = where["x0"], where["y0"]
        yy, xx = np.mgrid[0:h, 0:w]
        disc = lambda cx, cy, r: (xx + 0.5 + x0 - cx) ** 2 + (yy + 0.5 + y0 - cy) ** 2 <= r * r
        out, behind = np.zeros((h, w), bool), np.zeros((h, w), bool)
        for hx, hy, r, back in holes:
            if back:
                behind |= disc(hx, hy, r)
            else:
                out |= disc(hx, hy, r)
        out |= behind & ~disc(*kept) if kept is not None else behind
        if out.any() and where["cut"]:
            # another body over the square round a small target: what is left is too little of it to match on its own
            # (on a square mostly sky the alignment takes a star fit), so SPICE alone places the frame
            return None, "other body"
        if out.any():
            imgs = [np.where(out[..., None], 0, i).astype(np.uint8) for i in imgs]
            masks = [m & ~out for m in masks]
            if min(int(m.sum()) for m in masks) < 32 * 32:
                return None, "other body"
    if within is not None:
        # only where both tiles have picture, well inside each: the same ground in both
        k = np.ones((2 * REGISTER_INSET + 1, 2 * REGISTER_INSET + 1), np.uint8)
        both = np.logical_and.reduce([cv2.erode(m.astype(np.uint8), k, borderValue=1) > 0 for m in masks])
        imgs = [np.where(both[..., None], i, 0).astype(np.uint8) for i in imgs]
    # (rest: the rounding of each crop's corner to whole pixels, put back on the shift found)
    if sure is not None:
        pa = image_correction.find_shift_whole(imgs[0], imgs[1], within, sure[0])
        pe = image_correction.find_shift_whole(image_correction.edges(imgs[0]), image_correction.edges(imgs[1]), within, sure[1]) \
            if pa is not None else None
        if pa is not None and pa[2] >= sure[2]:
            got, how = pa[:2], "phase"
        elif pe is not None and math.hypot(pa[0] - pe[0], pa[1] - pe[1]) <= image_correction.WEAK_AGREE:
            got, how = ((pa[0] + pe[0]) / 2, (pa[1] + pe[1]) / 2), "phase and edges"
        else:
            return None, "not aligned"
        return (got[0] + rest[0][1] - rest[0][0], got[1] + rest[1][1] - rest[1][0]), f"{how}, {within:.0f} px search"
    shifts, how = [], []
    try:
        image_correction.align_with_masks(imgs, masks, 0, how, found=shifts, within=within)
    except Exception as e:
        return None, f"failed {type(e).__name__}: {e}"[:200]
    if shifts[1] is None:
        return None, how[1]
    return (shifts[1][0] + rest[0][1] - rest[0][0], shifts[1][1] + rest[1][1] - rest[1][0]), how[1]


# of a frame: the largest correction to SPICE's place of a pointing that registration is believed for. SPICE's pointing
# is 3 to 5 px off on the moons' mapping mosaics once the surface's motion between panels is taken out (median; 11 at
# most, panel_motion); a larger match is the surface's own motion, or a planet's clouds turning (Jupiter's matched 35
# px off), and moving a panel that far puts its limb off the body
PANEL_MAX = 12 / 1024
PANEL_MATCHES = 6    # earlier tiles a pointing's first tile is measured against at most (those it overlaps most)
PANEL_NARROW = 24    # px: the narrowest overlap (across) a pair of tiles is measured on
PANEL_AREA = 6000    # px: ... and the least area the two share
PANEL_NCC = 0.25     # the least the two overlaps must agree (normalized cross-correlation, detail only) once moved
PANEL_GAIN = 0.02    # ... and how much better than at SPICE's places they must agree, for a move of over half a pixel
PANEL_LEAST = 0.3    # px: a smaller move is the measure's own noise, and the pointing stays where SPICE put it
PANEL_AGREE = 2.0    # px: matches further than this from the others' median are left out
# ... a pointing further off than PANEL_MAX is moved too, up to PANEL_FAR, when its surface is redrawn (surface_pictures:
# the body's turning is taken out, so what is left is SPICE's pointing) and at least PANEL_FAR_MATCHES matches, each
# agreeing at PANEL_FAR_NCC once moved, all agree (PANEL_AGREE). Rhea ISS_018RH_REGCOL001's first pointing is 19 px off
# its other three (6 matches +18.6 to +21.2, ncc 0.86 once moved; the other three agree with each other within a
# pixel), so its limb stepped at both of its joins (spot check 7, panel_probe on the Mini)
PANEL_FAR = 32 / 1024
PANEL_FAR_MATCHES = 3
PANEL_FAR_NCC = 0.6
# a pass's panel registration (panel_places), kept with it; renamed whenever the rule changes
PANEL_FILE = "panels2-" + PLAN_FILE   # (2: PANEL_FAR)
PANEL_TAG = "-p2"    # in the name of a layout whose tiles registration moved (layout), so its pictures are its own
# a clouded body's (SURFACE_CLOUDED: Saturn, Titan, the rings) pointings are measured on edges only (edge_shift): its
# clouds turn with it and drift on its winds between panels (on Saturn's disk the turning alone is tens to hundreds of
# px in a few minutes), so its detail matches that motion, never SPICE's pointing, and #169 kept SPICE's places there,
# 5 to 60 px apart (26 of 303 mosaics, quality check 10-28). The limb, the terminator, a ring's edge and the shadows
# on the disk stay where they are on the sky while the clouds move, so the lit edge against the dark is measured
EDGE_LEVEL = 0.3     # of the way from the overlap's floor (1st percentile) to its lit top (99th): what is brighter
EDGE_DARK = 0.1      # is lit (disk, haze, ring), what is darker than this is dark (the sky and its noise, the night
EDGE_CONTRAST = 24   # side, a gap); and the top is this many levels over the floor at least, or nothing is lit
EDGE_SIDE = 0.03     # the share of the overlap each side, lit and dark, holds at least, for it to hold an edge
EDGE_LENGTH = 64     # px: the least edge (lit-ness changing by more than EDGE_STEEP a pixel) the overlap holds
EDGE_STEEP = 0.03
EDGE_SPAN = 128     # px: a patch of the lit or the dark shorter than this every way (a dark storm or cloud on a disk, a
#                       star or a small moon in the sky) is a feature that moves, not an edge, and is filled in (_lit)
EDGE_INSET = 12      # px: the overlap measured this far inside both tiles, so neither tile's dark rim is an edge
EDGE_SIGMA = 4.0     # px: the detail of the lit-ness measured (_detail), a band this wide along each edge
# the edge's structure: where its gradients' second direction holds less than this share of the first (a limb or a
# ring edge a few hundred px long is nearly straight), it is one line and says only how far across it the tile is
# off; the move along it is left as SPICE has it (min-norm, _combine)
EDGE_LINE = 0.1
# a match whose correlation has a rival peak this high (of its own) more than EDGE_APART px away, across the edge for a
# straight one, is not believed: parallel ringlets, gaps and ring shadows a few px to tens of px apart match one
# another as well as themselves (the probe's 007RI ring scan moved 30 px onto the next ringlets and doubled them)
EDGE_RIVAL = 0.7
EDGE_RESPONSE = 0.15  # the least phase correlation peak believed (007RI's wrong ring matches were 0.04 to 0.08, the
#                       Jupiter, Saturn limb and ring shadow matches the probe confirmed 0.2 to 0.7)
EDGE_APART = 4
EDGE_MAX = 64 / 1024  # of a frame: the largest move believed (the quality check's worst was 60 WAC px on Titan)
EDGE_NCC = 0.5       # the least the two edges must agree once moved
EDGE_GAIN = 0.05     # ... and how much better than at SPICE's places, for a move of over half a pixel
EDGE_AGREE = 3.0     # px: matches further than this (across their own edges) from the others' fit are left out
# a limb sits higher or lower with the filter (Saturn's haze in UV3 stands ~8 px over its MT3 limb, Titan's in RED over
# CB3, probe 10-29): edges are measured between tiles of one filter only
EDGE_FILE = "edges4-"  # before PANEL_FILE: a clouded body's registration, kept apart from #169's; renamed when the rule changes
EDGE_TAG = "-pe4"    # in the name of a layout whose tiles edge registration moved, instead of PANEL_TAG


def _detail(gray, mask, sigma=6.0):
    """A tile's overlap for registration: its detail (the picture less its mean over sigma, measured on the mask only,
    so the tile's own edge adds none), scaled to unit spread on the mask, 0 off it."""
    m = mask.astype(np.float32)
    low = cv2.GaussianBlur(gray * m, (0, 0), sigma) / np.maximum(cv2.GaussianBlur(m, (0, 0), sigma), 1e-3)
    d = (gray - low) * m
    sd = float(d[mask].std()) if mask.any() else 0.0
    return d / sd if sd > 1e-6 else None


def _even(a):
    """a padded with 0 to a size cv2.phaseCorrelate measures without bias: it pads to an optimal DFT size itself, and
    where that is odd its peak comes out half a pixel off (a strip 218 px wide shifted 0 measured +0.5)."""
    h, w = a.shape
    H, W = cv2.getOptimalDFTSize(h), cv2.getOptimalDFTSize(w)
    H, W = H if H % 2 == 0 else cv2.getOptimalDFTSize(H + 1), W if W % 2 == 0 else cv2.getOptimalDFTSize(W + 1)
    return cv2.copyMakeBorder(a, 0, H - h, 0, W - w, cv2.BORDER_CONSTANT, value=0)


def _agree(a, b, mask):
    """Normalized cross-correlation of a and b on mask."""
    x, y = a[mask], b[mask]
    x, y = x - x.mean(), y - y.mean()
    d = math.sqrt(float((x * x).sum()) * float((y * y).sum()))
    return float((x * y).sum()) / d if d > 0 else 0.0


def panel_shift(q, ref, at_q, t, crop, at_t, most=None):
    """How far tile t (its picture crop, its middle put at at_t) is from tile q (picture ref, middle at at_q), where
    two pointings of a mosaic overlap: (dx, dy) reference pixels that t's place moves back by to land on q (as
    _shift_onto), and what was measured {"ncc": [at SPICE's places, moved], "area", "response"}; (None, why) when
    the overlap is too small, featureless, or the match is not believed. Measured by phase correlation (as the
    pipeline's alignment of a set's channels, image_correction.find_shift) on the detail of the two pictures over
    the part both cover, each tapered to that part's edge, so neither tile's own outline (where SPICE put it) is
    matched, and believed only when the two agree better moved than not (PANEL_NCC, PANEL_GAIN)."""
    corners = [(at[0] + s["box"][0], at[1] + s["box"][1], im) for s, at, im in ((q, at_q, ref), (t, at_t, crop))]
    x0 = max(c[0] for c in corners)
    y0 = max(c[1] for c in corners)
    x1 = min(c[0] + c[2].shape[1] for c in corners)
    y1 = min(c[1] + c[2].shape[0] for c in corners)
    if x1 - x0 < PANEL_NARROW or y1 - y0 < PANEL_NARROW:
        return None, "apart"
    grays, masks = [], []
    for cx, cy, im in corners:
        left, top = int(round(x0 - cx)), int(round(y0 - cy))
        part = im[top:top + int(y1 - y0), left:left + int(x1 - x0)]
        grays.append(part[..., :3].astype(np.float32).mean(axis=2))
        masks.append(part[..., 3] > 0)
    h, w = min(g.shape[0] for g in grays), min(g.shape[1] for g in grays)
    grays, masks = [g[:h, :w] for g in grays], [m[:h, :w] for m in masks]
    both = cv2.erode((masks[0] & masks[1]).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    area = int(both.sum())
    if area < PANEL_AREA or min(np.ptp(np.nonzero(both)[0]), np.ptp(np.nonzero(both)[1])) < PANEL_NARROW - 8:
        return None, "little overlap"
    ds = [_detail(g, both) for g in grays]
    if ds[0] is None or ds[1] is None:
        return None, "featureless"
    taper = cv2.GaussianBlur(both.astype(np.float32), (0, 0), 4.0) * both
    (dx, dy), response = cv2.phaseCorrelate(*(_even(d * taper) for d in ds))
    # (the rounding of each crop's corner to whole pixels, put back on the shift found)
    rx = [(cx - x0) - round(cx - x0) for cx, _, _ in corners]
    ry = [(cy - y0) - round(cy - y0) for _, cy, _ in corners]
    before = _agree(ds[0], ds[1], both)
    moved = image_correction.shift_image(ds[1], dx, dy)
    inner = cv2.erode(both.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=int(math.ceil(max(abs(dx), abs(dy)))) + 1) > 0
    if inner.sum() < PANEL_AREA / 2:
        return None, "little overlap once moved"
    after = _agree(ds[0], moved, inner)
    seen = {"ncc": [round(before, 3), round(after, 3)], "area": area, "response": round(float(response), 3)}
    shift = (dx + rx[1] - rx[0], dy + ry[1] - ry[0])
    if math.hypot(*shift) > (most or PANEL_MAX) * FRAME:
        return None, f"too far {shift[0]:+.1f},{shift[1]:+.1f}"
    if after < PANEL_NCC or (math.hypot(*shift) > 0.5 and after < before + PANEL_GAIN):
        return None, f"not believed {shift[0]:+.1f},{shift[1]:+.1f} ncc {before:.2f}->{after:.2f}"
    return shift, seen


def _lit(gray, inside):
    """A tile's lit-ness over the overlap: 0 on the dark sky (or night side, or a ring gap) up to EDGE_DARK of the
    way from the overlap's floor to its lit top, rising to 1 at EDGE_LEVEL and staying 1 above it, so the clouds on a
    disk and the sky's noise are all one and only the edges between the lit and the dark are left. None where the
    overlap holds nothing lit (EDGE_CONTRAST), or nothing dark: its darkest is over EDGE_DARK of its top (a disk's
    clouds, the sky's black being near 0 on the pass's display scale)."""
    if not inside.any():
        return None
    floor, top = (float(v) for v in np.percentile(gray[inside], [1, 99]))
    if top - floor < EDGE_CONTRAST or floor > EDGE_DARK * top:
        return None
    span = top - floor
    lit = np.clip((gray - floor - EDGE_DARK * span) / ((EDGE_LEVEL - EDGE_DARK) * span), 0, 1).astype(np.float32)
    # (patches of either side shorter than EDGE_SPAN every way, and the soft rim round them, take the side round them)
    for side, fill in ((lit < 0.95, 1.0), (lit > 0.05, 0.0)):
        count, labels, stats, _ = cv2.connectedComponentsWithStats(side.astype(np.uint8), connectivity=8)
        small = np.zeros(count, bool)
        small[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) < EDGE_SPAN
        if small.any():
            spots = cv2.dilate(small[labels].astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
            lit[spots] = fill
    return lit


def _line(lit, weight):
    """The main direction of the gradients of lit-ness lit (structure tensor, weighted), a unit vector, and whether
    the edge is one line (EDGE_LINE: then that is its normal); (None, None) with no gradient."""
    gx = cv2.Sobel(lit, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lit, cv2.CV_32F, 0, 1, ksize=3)
    j = np.array([[float((gx * gx * weight).sum()), float((gx * gy * weight).sum())],
                  [float((gx * gy * weight).sum()), float((gy * gy * weight).sum())]])
    vals, vecs = np.linalg.eigh(j)
    if vals[1] <= 0:
        return None, None
    return vecs[:, 1], vals[0] < EDGE_LINE * vals[1]


def _rival(a, b, normal):
    """How high the best other peak of the phase correlation of a and b stands, as a share of its highest, more than
    EDGE_APART px from it and within EDGE_MAX of a frame of no shift, the correlation taken across the edges' main
    direction (normal) only, its best along each line across it: along an edge the peak is a ridge, and parallel
    edges (ringlets, bands) are what match one another."""
    fa, fb = np.fft.fft2(a), np.fft.fft2(b)
    cross = fa * np.conj(fb)
    surface = np.fft.fftshift(np.real(np.fft.ifft2(cross / np.maximum(np.abs(cross), 1e-12))))
    h, w = surface.shape
    yy, xx = np.mgrid[0:h, 0:w]
    yy, xx = yy - h // 2, xx - w // 2
    inside = np.hypot(xx, yy) <= EDGE_MAX * FRAME
    across = np.round(xx * normal[0] + yy * normal[1]).astype(int)
    keys = across[inside]
    profile = np.full(keys.max() - keys.min() + 1, -np.inf)
    np.maximum.at(profile, keys - keys.min(), surface[inside])
    k = int(np.argmax(profile))
    far = np.abs(np.arange(len(profile)) - k) > EDGE_APART
    return float(profile[far].max() / profile[k]) if far.any() and profile[k] > 0 else 0.0


def edge_shift(q, ref, at_q, t, crop, at_t):
    """panel_shift on a clouded body (SURFACE_CLOUDED): how far tile t is from tile q where they overlap, measured on
    the edges between the lit and the dark only (_lit: the limb, the terminator, a ring's edge or gap, a shadow), which
    stay put on the sky while the clouds between them turn and drift. The same phase correlation as panel_shift, on the
    detail of the two lit-nesses over the part both cover, EDGE_INSET inside each; believed only when that part holds
    an edge (lit and dark both, EDGE_SIDE, and EDGE_LENGTH of edge) and the two edges agree better moved than at
    SPICE's places (EDGE_NCC, EDGE_GAIN). An edge that is one line (_line) says only how far across it t is off: the
    shift is that, along its normal, and seen["normal"] says which way. (dx, dy) and seen as panel_shift's, or
    (None, why). Tiles of two filters are not measured: a limb's height differs with the filter."""
    if q["filter"] != t["filter"]:
        return None, "other filter"
    corners = [(at[0] + s["box"][0], at[1] + s["box"][1], im) for s, at, im in ((q, at_q, ref), (t, at_t, crop))]
    x0 = max(c[0] for c in corners)
    y0 = max(c[1] for c in corners)
    x1 = min(c[0] + c[2].shape[1] for c in corners)
    y1 = min(c[1] + c[2].shape[0] for c in corners)
    if x1 - x0 < PANEL_NARROW + 2 * EDGE_INSET or y1 - y0 < PANEL_NARROW + 2 * EDGE_INSET:
        return None, "apart"
    grays, masks = [], []
    for cx, cy, im in corners:
        left, top = int(round(x0 - cx)), int(round(y0 - cy))
        part = im[top:top + int(y1 - y0), left:left + int(x1 - x0)]
        grays.append(part[..., :3].astype(np.float32).mean(axis=2))
        masks.append(part[..., 3] > 0)
    h, w = min(g.shape[0] for g in grays), min(g.shape[1] for g in grays)
    grays, masks = [g[:h, :w] for g in grays], [m[:h, :w] for m in masks]
    common = np.pad(masks[0] & masks[1], 1).astype(np.uint8)
    both = cv2.erode(common, np.ones((2 * EDGE_INSET + 1, 2 * EDGE_INSET + 1), np.uint8))[1:-1, 1:-1] > 0
    area = int(both.sum())
    if area < PANEL_AREA or min(np.ptp(np.nonzero(both)[0]), np.ptp(np.nonzero(both)[1])) < PANEL_NARROW - 8:
        return None, "little overlap"
    lits = [_lit(g, both) for g in grays]
    if lits[0] is None or lits[1] is None:
        return None, "no edge"
    for lit in lits:
        steep = np.hypot(cv2.Sobel(lit, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(lit, cv2.CV_32F, 0, 1, ksize=3)) / 8
        if ((lit >= 0.9) & both).sum() < EDGE_SIDE * area or ((lit <= 0.1) & both).sum() < EDGE_SIDE * area \
                or ((steep > EDGE_STEEP) & both).sum() < EDGE_LENGTH:
            return None, "no edge"
    ds = [_detail(lit, both, EDGE_SIGMA) for lit in lits]
    if ds[0] is None or ds[1] is None:
        return None, "no edge"
    taper = cv2.GaussianBlur(both.astype(np.float32), (0, 0), 4.0) * both
    main, line = _line(lits[0], taper)
    if main is None:
        return None, "no edge"
    normal = main if line else None
    pair = [_even(d * taper) for d in ds]
    (dx, dy), response = cv2.phaseCorrelate(*pair)
    rival = _rival(*pair, main)
    if response < EDGE_RESPONSE:
        return None, f"weak {dx:+.1f},{dy:+.1f} response {response:.2f}"
    if rival > EDGE_RIVAL:
        return None, f"ambiguous {dx:+.1f},{dy:+.1f} rival {rival:.2f}"
    if normal is not None:
        # (a straight edge's match slides along it: only the part across it is measured)
        across = dx * normal[0] + dy * normal[1]
        dx, dy = across * normal[0], across * normal[1]
    rx = [(cx - x0) - round(cx - x0) for cx, _, _ in corners]
    ry = [(cy - y0) - round(cy - y0) for _, cy, _ in corners]
    before = _agree(ds[0], ds[1], both)
    moved = image_correction.shift_image(ds[1], dx, dy)
    inner = cv2.erode(both.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=int(math.ceil(max(abs(dx), abs(dy)))) + 1) > 0
    if inner.sum() < PANEL_AREA / 2:
        return None, "little overlap once moved"
    after = _agree(ds[0], moved, inner)
    seen = {"ncc": [round(before, 3), round(after, 3)], "area": area, "response": round(float(response), 3), "edge": True,
            "rival": round(rival, 3)}
    shift = (dx + rx[1] - rx[0], dy + ry[1] - ry[0])
    if normal is not None:
        across = float(shift[0] * normal[0] + shift[1] * normal[1])
        shift = (across * float(normal[0]), across * float(normal[1]))
        seen["normal"] = [round(float(normal[0]), 4), round(float(normal[1]), 4)]
    if math.hypot(*shift) > EDGE_MAX * FRAME:
        return None, f"too far {shift[0]:+.1f},{shift[1]:+.1f}"
    if after < EDGE_NCC or (math.hypot(*shift) > 0.5 and after < before + EDGE_GAIN):
        return None, f"not believed {shift[0]:+.1f},{shift[1]:+.1f} ncc {before:.2f}->{after:.2f}"
    return shift, seen


def _combine(found):
    """The move of a pointing from its matches on edges [(where it lands by that match (x, y), the edge's normal or
    None)]: the least-squares place that agrees with each across its own edge (all ways for a match that is not one
    line), the move along a lone straight edge left as SPICE has it (min-norm; and along edges nearly parallel to one
    another, whose small differences in angle would otherwise say how far along them: Saturn's equatorial map moved a
    panel 580 px so); matches further than EDGE_AGREE from the others' fit are left out one at a time, the worst
    first. None when no more than half of them agree (one alone is believed), or the move adds up to more than
    EDGE_MAX of a frame (a chain of panels, each a few px off, that a limb seen in another light runs away with)."""
    rows = []
    for (x, y), n in found:
        proj = np.eye(2) if n is None else np.outer(n, n)
        rows.append((proj, np.array([x, y], float)))
    keep = list(range(len(rows)))
    while keep:
        a = sum(rows[i][0] for i in keep)
        b = sum(rows[i][0] @ rows[i][1] for i in keep)
        move = np.linalg.pinv(a, rcond=EDGE_LINE) @ b
        off = [(float(np.linalg.norm(rows[i][0] @ (move - rows[i][1]))), i) for i in keep]
        worst = max(off)
        if worst[0] <= EDGE_AGREE:
            break
        keep.remove(worst[1])
    if not keep or not (len(keep) * 2 > len(rows) or len(rows) == 1) or math.hypot(*move) > EDGE_MAX * FRAME:
        return None
    return move


def clouded(u):
    """True when pass u's body shows clouds or haze that move on their own (SURFACE_CLOUDED; the rings are Saturn's
    passes): its panels are registered on edges only (edge_shift) and its surface is not redrawn."""
    return u["key"][0] in SURFACE_CLOUDED


def _pointing_root(u, n, roots):
    """The tile whose correction tile n takes: the tile C8 registers it to (_register_to, a frame of its pointing in
    another filter), followed back to the pointing's first; n itself for a pointing's first tile."""
    j = _register_to(u, n)
    return roots.get(j, j) if j is not None else n


SURFACE_STEP = 16    # reference px: the grid a tile's surface motion (reproject.sky_field) is worked out on
# a pass's tiles redrawn as at its epoch (surface_pictures), kept beside its tiles; renamed whenever the rule changes
SURFACE_DIR = "surface7"
SURFACE_TAG = "-s7"  # in the name of a layout whose tiles are redrawn so (layout), so its pictures are its own
# a tile registered to another filter's (C8, _register) is redrawn from the time of the tile it was registered to,
# not its own: the registration's shift already took out the surface's motion between the two frames (the body turning
# and Cassini moving, ~17 px a filter on Rhea's mapping mosaics), so redrawn from its own time it moved that far twice.
# On Rhea ISS_162RH_REGMAP001 the GRN tiles landed 14 px and the IR1 tiles 30 px off the UV3 and the gray base under
# them: doubled craters and rainbow edges all over the mosaic (surface6; surface5 redrew from the tile's own time)
REDRAW_AT_REFERENCE = True
# a redrawn tile's picture is drawn on its box grown by the furthest its surface moves (and cut to what is on it): the
# ground the redrawing moves past the tile's own box stays in the picture. Drawn inside the box as taken (surface4),
# that ground was cut off, and the strip it left on the other side lay empty: where a neighbor's ground had moved in
# from beside, nothing filled it, and the moons' mapping mosaics had curved black slots inside their disks
# (Enceladus ISS_004EN_REGEO002, Rhea ISS_162RH_REGMAP001, where SPICE's frames overlap). Its box is kept beside it
SURFACE_BOX = ".json"
SURFACE_REACH = 256  # reference px (a whole number of SURFACE_STEPs): the furthest round its box a tile's ground is kept
# what is seen of these is cloud or haze that moves on its own, not a surface turning with the body (Titan's
# mapping mosaic came out 25 px apart redrawn, Saturn's rings pass lost its one match): their tiles stay as taken
SURFACE_CLOUDED = frozenset({"SATURN", "JUPITER", "TITAN", "URANUS", "NEPTUNE", "VENUS", "EARTH"})
# a tile whose redrawing would stretch or squeeze its picture by more than this (the shift's change per pixel, where
# it fades to none at the limb or the terminator) stays as taken: on Rhea's mapping mosaic a limb panel shifted
# ~40 px squeezed its limb out of the picture and streaked its night side (round 5 of the panel probe)
SURFACE_STRETCH = 0.5
# a tile more than this share of whose ground would move further than SURFACE_REACH stays as taken too: its redrawn
# picture keeps only what lands within SURFACE_REACH of its box, so the rest was cut off. Over a close flyby the ground
# moves far in the pass's time (Rhea ISS_162RH_REGMAP001, 2012-03-10: up to 1,300 px from the middle frame, a tile is
# 1,100), and its first pointings' tiles kept 7% of their picture: a hole on the mosaic's right edge, with a thin
# wedge of ground floating beside it (spot check 7)
SURFACE_LOST = 0.05
# the tiles found to stay as taken (SURFACE_STRETCH, or across New Year), kept in SURFACE_DIR beside the redrawn ones:
# a later layout skips them instead of working each out again (the year's kernels, its picture, its sky field) for
# every mosaic, tile map and look-ahead of the pass
SURFACE_TAKEN = "taken.json"
_spice_lock = threading.RLock()


def _with_kernels(t):
    """SPICE kernels loaded for the year of a frame taken at t (s since 1970), as label_handler.auto_center loads
    them (one year at a time); False when they cannot be."""
    import label_handler as lh
    import bootleg_autonav as ba
    year = time.gmtime(t).tm_year
    if getattr(lh, "cur_year", None) != year:
        try:
            ba.unload_kernels()
            lh.cur_year = year
            ba.load_kernels(year, year)
        except Exception as e:
            print(f"no kernels for {year}: {e}", flush=True)
            return False
    return True


def _ets(ids):
    """{frame id: et} of frames, from the geometry cache (find_target's time, IMAGE_MID_TIME)."""
    import bootleg_autonav as ba
    if not ba.GEOMETRY_CACHE or not os.path.exists(ba.GEOMETRY_CACHE):
        return {}
    db, out = ba._geometry_db(), {}
    for k in range(0, len(ids), 900):
        part = ids[k:k + 900]
        out.update(db.execute(f"SELECT frame, et FROM target WHERE version = ? AND error IS NULL AND frame IN "
                              f"({','.join('?' * len(part))})", (ba.GEOMETRY_VERSION, *part)).fetchall())
    return out


def _surface_taken(u, cache, p, out_dir):
    """The tiles of the pass that surface_pictures keeps as taken (SURFACE_TAKEN): read once, then from the pass's
    record."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _lock:
        taken = rec.get("surface_taken") if rec is not None else None
    if taken is None:
        try:
            with open(os.path.join(out_dir, SURFACE_TAKEN)) as fh:
                taken = set(json.load(fh))
        except (OSError, ValueError):
            taken = set()
        if rec is not None:
            with _lock:
                taken = rec.setdefault("surface_taken", taken)
    return taken


def surface_pictures(u, cache, p, tiles):
    """Surface reprojection of a mosaic's panels: {tile n: the path of its picture redrawn as at the pass's epoch}.
    A mosaic's panels are taken minutes apart, and the body turns and Cassini moves in between, so the surface under
    one place on the sky moves between panels (8 to 18 px on the moons' mapping mosaics, which SPICE predicts to 3 to
    5 px, panel_motion) while every tile is put on the body's centre: craters double or step at the seams. Each tile's
    lit surface is moved to where it was at the epoch (the pass's middle frame's time, fixed before any tile is made,
    so a mosaic grown a tile at a time stays as drawn), with SPICE's shape, orientation and Cassini's position
    (reproject.sky_field, warp_sky); the sky, the rings, the night side and the limb's edge stay where they are. Made
    once per tile and kept. {} with Settings > Processing's surface step off, for a body SPICE has no shape for, or
    when the kernels or the geometry cache cannot say; none for a clouded body (SURFACE_CLOUDED), and not a tile
    the redrawing would distort (SURFACE_STRETCH), which keeps SPICE's place and the panels step's nudge (found
    once and kept too, SURFACE_TAKEN)."""
    if not calibration.step("surface") or not tiles or clouded(u):
        return {}
    import reproject as rp
    there = _tiles(u, cache, p["display_scale"])
    out_dir = os.path.join(there, SURFACE_DIR)
    taken = _surface_taken(u, cache, p, out_dir)
    out, todo = {}, []
    for t in tiles:
        if "offset" not in t or t["n"] in taken:
            continue
        path = os.path.join(out_dir, f"{t['n']}.png")
        if os.path.exists(path) and os.path.exists(path + SURFACE_BOX):
            out[t["n"]] = path
        elif os.path.exists(os.path.join(there, f"{t['n']}.png")):
            todo.append(t)
    if not todo:
        return out
    fr = u["frames"]
    mid = fr[len(fr) // 2]
    by_id = {t["id"]: t for t in tiles}
    ets = _ets([mid[1]] + [t["id"] for t in todo] + [w for w in (_redraw_from(t, by_id) for t in todo) if w])
    if mid[1] not in ets:
        return out
    km_px = IFOV[u["key"][2]] * u["z"]
    with _spice_lock:
        if not _with_kernels(mid[3]):
            return out
        try:
            epoch = rp.sky_view(u["key"][0], ets[mid[1]])
        except Exception as e:
            print(f"no surface for {u['key'][0]}: {type(e).__name__}: {e}"[:200], flush=True)
            return out
        os.makedirs(out_dir, exist_ok=True)
        found = set()
        roots = {}
        for t in tiles:
            if "offset" in t:
                roots[t["n"]] = _pointing_root(u, t["n"], roots)
        for t in todo:
            # the filters of one pointing are redrawn or kept alike, as its first tile was (SURFACE_STRETCH is
            # measured on it): a pointing half redrawn put its colours apart and left the min of their edges as a gap
            # (Rhea ISS_162RH_REGMAP001: UV3 redrawn, GRN and IR1 of the same pointing kept)
            root = roots.get(t["n"], t["n"])
            if root != t["n"] and (root in taken or root in found):
                found.add(t["n"])
                continue
            if time.gmtime(t["t"]).tm_year != time.gmtime(mid[3]).tm_year:
                # (one year's kernels at a time: a pass across New Year keeps those tiles as they are, without loading
                # the other year's kernels for them and the epoch's again for the next tile)
                found.add(t["n"])
                continue
            if t["id"] not in ets or not _with_kernels(t["t"]):
                continue
            # (from the time of the tile it is registered to, when it was moved onto it: REDRAW_AT_REFERENCE)
            when = _redraw_from(t, by_id) or t["id"]
            if when not in ets:
                continue
            try:
                view = rp.sky_view(u["key"][0], ets[when])
            except Exception as e:
                print(f"no surface for {t['id']}: {type(e).__name__}: {e}"[:200], flush=True)
                continue
            src = os.path.join(there, f"{t['n']}.png")
            with _lock:
                image = _made_pictures.get(src)
            if image is None:
                image = np.asarray(Image.open(src).convert("RGBA"))
            # (the field worked out SURFACE_REACH round the tile too, where its ground may move to: surface_redrawn)
            dx, dy, weight = surface_field(rp, epoch, view, image.shape[:2], t, km_px, view_turn(u))
            path = os.path.join(out_dir, f"{t['n']}.png")
            r = SURFACE_REACH // SURFACE_STEP
            stretch = rp.field_stretch(dx[r:-r, r:-r], dy[r:-r, r:-r], weight[r:-r, r:-r], SURFACE_STEP)
            if stretch > SURFACE_STRETCH and (root == t["n"] or root not in out):
                print(f"surface: tile {t['n']} kept as taken (stretch {stretch:.2f})", flush=True)
                found.add(t["n"])
                continue
            lost = surface_lost(dx[r:-r, r:-r], dy[r:-r, r:-r], weight[r:-r, r:-r])
            if lost > SURFACE_LOST and (root == t["n"] or root not in out):
                print(f"surface: tile {t['n']} kept as taken ({lost:.0%} of its ground moves past SURFACE_REACH)", flush=True)
                found.add(t["n"])
                continue
            picture, box = surface_redrawn(rp, image, t, dx, dy, weight)
            # (the box first, so a picture never sits there without it)
            with open(path + SURFACE_BOX, "w") as fh:
                json.dump(box, fh)
            Image.fromarray(picture).save(path + ".part.png", compress_level=1)
            os.replace(path + ".part.png", path)
            out[t["n"]] = path
        if not found <= taken:
            taken |= found
            kept = os.path.join(out_dir, SURFACE_TAKEN)
            part = f"{kept}.{os.getpid()}.{threading.get_ident()}.part"
            try:
                with open(part, "w") as fh:
                    json.dump(sorted(taken), fh)
                os.replace(part, kept)
            except OSError as e:
                print(f"cannot keep {kept} in the cache ({e})", flush=True)
    return out


def surface_lost(dx, dy, weight):
    """The share of a tile's ground (sky_field's grid over its box, on the body) that its redrawing moves further than
    SURFACE_REACH: surface_redrawn keeps no more than that round the box, so that much of its picture would be cut."""
    on = weight > 0.5
    if not on.any():
        return 0.0
    return float((np.hypot(dx, dy)[on] > SURFACE_REACH).mean())


def _redraw_from(t, by_id=None):
    """The frame whose time tile t's surface is redrawn from instead of its own (REDRAW_AT_REFERENCE): the tile C8
    moved it onto (_register: its "registered" shift), followed back through tiles that were themselves moved onto
    another (by_id: the pass's tiles by frame id; a chain of filters, each registered to the one before it, lands on
    the first's surface), else None."""
    if not REDRAW_AT_REFERENCE:
        return None
    when, seen = None, set()
    while True:
        reg = t.get("registered") or {}
        if not reg.get("shift") or reg.get("to") in seen:
            return when
        when = reg["to"]
        seen.add(when)
        t = (by_id or {}).get(when)
        if t is None:
            return when


def surface_field(rp, epoch, view, shape, t, km_px, turn=0.0):
    """reproject.sky_field for tile t (its picture shape, h x w) on SURFACE_STEP's grid over its box grown by
    SURFACE_REACH each way: the grid's point (SURFACE_REACH // SURFACE_STEP, the same) is the tile's pixel (0, 0), at
    the tile's corner on the sky, so the grid's inner part is the field over the tile's own box. turn: the pass's axes
    (view_turn), turn degrees short of the sky's north up that sky_field works on: places are turned onto the sky
    and the shifts back."""
    h, w = shape
    m = SURFACE_REACH
    gy, gx = np.mgrid[-m:h + m + SURFACE_STEP:SURFACE_STEP, -m:w + m + SURFACE_STEP:SURFACE_STEP].astype(np.float64)
    x0, y0 = t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1]
    if not turn:
        return rp.sky_field(epoch, view, gx + x0, gy + y0, km_px)
    # a place p on the pass's canvas is R(turn) p on the north-up sky (R as cv2.getRotationMatrix2D turns), and a
    # shift on the sky R(-turn) d on the canvas
    a = math.radians(turn)
    c, sn = math.cos(a), math.sin(a)
    x, y = gx + x0, gy + y0
    dx, dy, w = rp.sky_field(epoch, view, c * x + sn * y, c * y - sn * x, km_px)
    return (c * dx - sn * dy).astype(np.float32), (sn * dx + c * dy).astype(np.float32), w


def surface_redrawn(rp, image, t, dx, dy, weight):
    """Tile t's picture (image, RGBA, on its box t["box"] about t["offset"]) redrawn as at the epoch: (picture, box),
    the picture on the box grown by the furthest its surface moves (up to SURFACE_REACH) and cut to its drawn
    pixels, and that box (reference px about the tile's offset, as t["box"]). dx, dy, weight: surface_field's."""
    h, w = image.shape[:2]
    r = SURFACE_REACH // SURFACE_STEP
    inner = weight[r:-r, r:-r] > 0
    reach = float(max(np.abs(dx[r:-r, r:-r][inner]).max(), np.abs(dy[r:-r, r:-r][inner]).max())) if inner.any() else 0.0
    # the grown box: a whole number of grid steps out, up to SURFACE_REACH
    steps = min(r, math.ceil(reach / SURFACE_STEP))
    pad = steps * SURFACE_STEP
    cut = slice(r - steps, dx.shape[0] - (r - steps)), slice(r - steps, dx.shape[1] - (r - steps))
    picture = rp.warp_sky(np.pad(image, ((pad, pad), (pad, pad), (0, 0))), dx[cut], dy[cut], weight[cut], SURFACE_STEP)
    found = Image.fromarray(picture).getbbox(alpha_only=True)
    if found is None:
        return np.ascontiguousarray(image), list(t["box"])
    c0, r0, c1, r1 = found
    return (np.ascontiguousarray(picture[r0:r1, c0:c1]),
            [t["box"][0] - pad + c0, t["box"][1] - pad + r0, c1 - c0, r1 - r0])


def surface_box(path, t):
    """The box (SURFACE_BOX) of the redrawn picture at path, of tile t; t's own box when none is kept."""
    with _lock:
        box = _surface_boxes.get(path)
    if box is None:
        try:
            with open(path + SURFACE_BOX) as fh:
                box = json.load(fh)
        except (OSError, ValueError):
            return t["box"]
        with _lock:
            if len(_surface_boxes) > 200000:
                _surface_boxes.clear()
            _surface_boxes[path] = box
    return box


_surface_boxes = {}


def panel_places(u, cache, p, tiles, pic=None, report=None):
    """Panel registration: {tile n: [dx, dy]}, how far each tile is moved from SPICE's place (reference pixels), so
    a mosaic's pointings line up where they overlap. SPICE places each frame on its own and its pointing is a few
    pixels off, differently for each pointing (more where the c-smithed pointing is missing, PR #5), so panels of a
    mosaic land a little apart and a limb or a crater rim steps at their seam. A pointing's first tile is measured
    (panel_shift) against the earlier tiles of other pointings it overlaps most (PANEL_MATCHES, its own filter
    first), each where it was itself put, and moved by the median of the matches that agree (PANEL_AGREE); the
    other filters of the pointing (registered onto it by C8) move with it, so its colours stay together. A pointing
    nothing matches keeps SPICE's place. Earlier pointings never move for a later one, so a mosaic grown a tile at a
    time stays as it was drawn, and every tile is worked out once and kept with the pass. A clouded body's
    (SURFACE_CLOUDED) pointings are measured on their edges only (edge_shift) and moved by the place that agrees with
    each across its edge (_combine), kept in a file of their own (EDGE_FILE). {} with Settings > Processing's panels
    (or align) step off. report: a dict that gets each tile's measurements."""
    if not (calibration.step("align") and calibration.step("panels")):
        return {}
    # (measured on the tiles as drawn: their surface redrawn as at the epoch, or not, each kept apart)
    surfaced = any("pic" in t for t in tiles)
    edges = clouded(u)
    path = os.path.join(folder(u, cache), (SURFACE_DIR + "-" if surfaced else "") + (EDGE_FILE if edges else "") + PANEL_FILE)
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _ulock(u):
        name = "panels" + SURFACE_TAG * surfaced + EDGE_TAG * edges
        kept = rec.get(name) if rec is not None else None
        if kept is None:
            kept = {}
            if os.path.exists(path):
                with open(path) as fh:
                    kept = {int(n): v for n, v in json.load(fh).items()}
            if rec is not None:
                rec[name] = kept
        todo = [t for t in tiles if "offset" in t and t["n"] not in kept]
        if not todo:
            return {n: v[:2] for n, v in kept.items() if v[:2] != [0, 0]}
        there = _tiles(u, cache, p["display_scale"])
        pics = {}

        def picture(j):
            if pic is not None:
                return pic(j)
            if j not in pics:
                fp = by_n[j].get("pic") or os.path.join(there, f"{j}.png")
                with _lock:
                    pics[j] = _made_pictures.get(fp)
                if pics[j] is None:
                    pics[j] = np.asarray(Image.open(fp).convert("RGBA")) if os.path.exists(fp) else None
            return pics[j]
        by_n = {t["n"]: t for t in tiles if "offset" in t}
        roots = {}
        for t in tiles:
            if "offset" in t:
                roots[t["n"]] = _pointing_root(u, t["n"], roots)
        for t in sorted(todo, key=lambda t: t["n"]):
            n = t["n"]
            if roots[n] != n:
                kept[n] = list(kept.get(roots[n], [0, 0, "root"])[:2]) + [f"with {roots[n]}"]
                continue
            here = t["offset"]
            cands = []
            for s in by_n.values():
                if s["n"] >= n or roots.get(s["n"]) == n or s["n"] not in kept or edges and s["filter"] != t["filter"]:
                    continue
                a, b = s["offset"], here
                w = min(a[0] + s["box"][0] + s["box"][2], b[0] + t["box"][0] + t["box"][2]) - max(a[0] + s["box"][0], b[0] + t["box"][0])
                h = min(a[1] + s["box"][1] + s["box"][3], b[1] + t["box"][1] + t["box"][3]) - max(a[1] + s["box"][1], b[1] + t["box"][1])
                if w >= PANEL_NARROW and h >= PANEL_NARROW:
                    cands.append((s["filter"] != t["filter"], -w * h, s["n"]))
            found, seen, far = [], {}, []
            mine = picture(n)
            for _, _, j in sorted(cands)[:PANEL_MATCHES]:
                ref = picture(j)
                if ref is None or mine is None:
                    continue
                s = by_n[j]
                # measured where SPICE put both (the overlap SPICE says, the same however far the earlier one has
                # been moved), and taken from where the earlier one now is
                shift, how = (edge_shift(s, ref, s["offset"], t, mine, here) if edges else
                              panel_shift(s, ref, s["offset"], t, mine, here, PANEL_FAR if surfaced else None))
                seen[j] = how if shift is None else {**how, "shift": [round(shift[0], 2), round(shift[1], 2)]}
                if shift is not None:
                    was = kept.get(j, [0, 0])
                    found.append(((was[0] - shift[0], was[1] - shift[1]), how.get("normal")) if edges else
                                 (was[0] - shift[0], was[1] - shift[1]))
                    if not edges:
                        far.append(how["ncc"][1] if math.hypot(*shift) > PANEL_MAX * FRAME else None)
            move = [0.0, 0.0]
            if found and edges:
                fit = _combine(found)
                if fit is not None and math.hypot(*fit) >= PANEL_LEAST:
                    move = [round(float(v), 2) for v in fit]
            elif found:
                beyond = [v for v in far if v is not None]
                if beyond and not (len(found) >= PANEL_FAR_MATCHES and min(beyond) >= PANEL_FAR_NCC
                                   and (np.hypot(*(np.array(found) - np.median(found, axis=0)).T) <= PANEL_AGREE).all()):
                    # (a match past PANEL_MAX is believed only when every match agrees with it: otherwise the near
                    # ones decide, as before)
                    found = [xy for xy, v in zip(found, far) if v is None]
            if found and not edges:
                f = np.array(found)
                mid = np.median(f, axis=0)
                ok = f[np.hypot(*(f - mid).T) <= PANEL_AGREE]
                if len(ok) and (len(ok) * 2 > len(f) or len(f) == 1) and math.hypot(*ok.mean(axis=0)) >= PANEL_LEAST:
                    move = [round(float(v), 2) for v in ok.mean(axis=0)]
            kept[n] = move + [f"{len(found)} of {len(seen)}"]
            if report is not None:
                report[n] = {"move": move, "matches": seen}
        # (kept again as it grows: a later tile's moves add to it, earlier ones never change)
        part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(part, "w") as fh:
                json.dump({str(n): v for n, v in sorted(kept.items())}, fh)
            os.replace(part, path)
        except OSError as e:
            print(f"cannot keep {path} in the cache ({e})", flush=True)
        return {n: v[:2] for n, v in kept.items() if v[:2] != [0, 0]}


def view_rect(p, tiles=None):
    """The view (x0, y0, w, h in reference pixels from the body's centre): the pass's whole footprint, the same
    for every tile, so what is drawn stays drawn."""
    x0, y0, x1, y1 = p["footprint"]
    return x0, y0, x1 - x0, y1 - y0


def under_first(tiles):
    """The tiles in the order a mosaic draws them, each over the ones before: the luminance base's fills (lum_fills)
    lowest, then partial frames (partial) and tiles far darker than the picture before them (dim_under, marked
    "under"), a colour set's long exposure taken again (long_repeats), the newest lowest (as _grown leaves a tile it draws
    under the picture so far), then the rest as given."""
    fill = lambda t: bool(t.get("fill"))
    low = lambda t: not fill(t) and (partial(t) or t.get("under") or t.get("long"))
    return ([t for t in tiles if fill(t)] + sorted((t for t in tiles if low(t)), key=lambda t: -t["n"])
            + [t for t in tiles if not fill(t) and not low(t)])


DIM_UNDER = 0.7     # of the picture drawn before it, on their overlap: a tile darker than this goes under it (dim_under)
DIM_K = 0.125       # canvas scale (of full resolution pixels) the overlaps are measured at
DIM_LEAST = 200     # pixels at DIM_K: the least lit overlap that says anything
DIM_FILE = "under1-{}.json"


def dim_under(u, p, f, mine, cache):
    """The tiles of mine (one filter's, in time order) that a pass's mosaic draws under the picture before them: those
    whose overlap with the earlier tiles, where those are lit, is under DIM_UNDER as bright in linear brightness (the
    median of the ratio, over every earlier tile it overlaps that is not itself under). Such a tile is the same ground
    seen again from far round the body, past the terminator: Dione 221DI's last 20 tiles, shot 1.7 hours after the
    rest, show the right side of the disk 4 to 20 times darker on their overlaps and were drawn over it as a dark column.
    Under the picture, they fill only where nothing else is. A tile's brightness is its own (no gain here: what the
    seams and leveling take out is a few per cent). Measured once per tile (each on the tiles before it only) and kept
    in the pass's folder. {n: ratio} for the tiles that go under."""
    path = os.path.join(folder(u, cache), DIM_FILE.format(f.replace("/", "_")))
    kept = {}
    if os.path.exists(path):
        try:
            with open(path) as fh:
                kept = {int(n): v for n, v in json.load(fh).items()}
        except (OSError, ValueError):
            kept = {}
    gamma = p["display_scale"].get("gamma", 2.2)
    if any(t["n"] not in kept for t in mine):
        drawn, out = [], {}
        for t in mine:
            bx, by, bw, bh = t["box"]
            pic = _pic(u, cache, p["display_scale"], t)
            a = np.asarray(Image.open(pic).convert("RGBA").resize((max(1, round(bw * DIM_K)), max(1, round(bh * DIM_K))),
                                                                  Image.BILINEAR)).astype(np.float32)
            x0, y0 = round((t["offset"][0] + bx) * DIM_K), round((t["offset"][1] + by) * DIM_K)
            me = (x0, y0, a)
            if t["n"] in kept:
                ratio = kept[t["n"]]
            else:
                logs, weights = [], []
                for xi, yi, b in drawn:
                    X0, Y0 = max(x0, xi), max(y0, yi)
                    X1, Y1 = min(x0 + a.shape[1], xi + b.shape[1]), min(y0 + a.shape[0], yi + b.shape[0])
                    if X1 <= X0 or Y1 <= Y0:
                        continue
                    A, B = a[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0], b[Y0 - yi:Y1 - yi, X0 - xi:X1 - xi]
                    on = (A[..., 3] == 255) & (B[..., 3] == 255) & (B[..., :3].mean(axis=2) > LIT_LEVEL)
                    if on.sum() < DIM_LEAST / 4:
                        continue
                    la = calibration.decode(np.maximum(A[..., :3].mean(axis=2)[on], 1) / 255, gamma)
                    lb = calibration.decode(B[..., :3].mean(axis=2)[on] / 255, gamma)
                    logs.append(float(np.median(np.log(la / lb))))
                    weights.append(int(on.sum()))
                ratio = (round(math.exp(sum(l * w for l, w in zip(logs, weights)) / sum(weights)), 4)
                         if sum(weights) >= DIM_LEAST else 1.0)
            out[t["n"]] = ratio
            if ratio >= DIM_UNDER:
                drawn.append(me)
        kept = {**kept, **out}
        try:
            _rewrite(path, kept)
        except OSError:
            pass
    return {t["n"]: kept[t["n"]] for t in mine if kept.get(t["n"], 1.0) < DIM_UNDER}


def dim_places(u, p, f, mine, tiles, cache, among=None):
    """The tiles of mine (filter f's) a pass's mosaic draws under the picture before them (dim_under), decided once for
    every filter at a pointing so a colour set's filters go under together (decided filter by filter, a pointing just
    at the line went under in UV3 alone and its place came out blue): each of f's tiles takes the decision of its
    pointing's first tile (_pointing_root, the tile C8 registers the pointing's filters to), measured on that tile's
    own filter. The first tile is taken before the others, so its decision is there when each of them is first drawn
    and never changes as later tiles come in: a mosaic grown a tile at a time keeps what it drew (decided on the
    pointing's grey tile, taken last, Dione 221DI's colour tiles were drawn over the lit disk while the frames before
    the grey one came in, and the grown mosaic kept them there, a black square)."""
    if f == LUM:
        return set(dim_under(u, p, f, mine, cache))
    placed = sorted((t for t in tiles if "offset" in t), key=lambda t: t["n"])
    by_n = {t["n"]: t for t in placed}
    roots = {}
    for t in placed:
        roots[t["n"]] = _pointing_root(u, t["n"], roots)
    first = {t["n"]: by_n.get(roots.get(t["n"], t["n"]), t) for t in mine}
    if among:
        # (a colour picture's tiles take the decision of their pointing's first tile in one of its colour filters, not
        # of a filter it does not draw: 195RI HIPHASEC001's VIO frames near the limb came out black, 0.0001 of the
        # picture before them, and every colour tile of their pointings went under with them, drawn beneath the
        # pointings before in one filter and over them in another: green and purple blocks on the rings)
        keep = set(among)
        firsts = {}
        for t in placed:
            if t["filter"] in keep:
                firsts.setdefault(roots.get(t["n"], t["n"]), t)
        first = {n: firsts.get(roots.get(n, n), r) for n, r in first.items()}
    low = set()
    for g in dict.fromkeys(r["filter"] for r in first.values()):
        low |= set(dim_under(u, p, g, [t for t in placed if t["filter"] == g], cache))
    return {n for n, r in first.items() if r["n"] in low}


def _rewrite(path, kept):
    part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    with open(part, "w") as fh:
        json.dump({str(n): v for n, v in sorted(kept.items())}, fh)
    os.replace(part, path)


def _window(u, p, mine, rect, cache):
    """The tiles mine drawn on the view rect's canvas, one RGBA frame each, as mosaic.compose takes them:
    ([(frame, None, None, None)], the tiles that are in the view)."""
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)
    window, shown = [], []
    # partial frames (partial) first, under every whole tile, the newest of them lowest: as _grown, which draws a
    # partial tile under the picture so far, leaves them
    for t in under_first(mine):
        bx, by, bw, bh = t["box"]
        left = round((t["offset"][0] + bx - rect[0]) * k)
        top = round((t["offset"][1] + by - rect[1]) * k)
        sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
        if left >= W or top >= H or left + sw <= 0 or top + sh <= 0:
            continue
        part = _shade(_part(_pic(u, cache, p["display_scale"], t), sw, sh), t)
        frame = np.zeros((H, W, 4), np.uint8)
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
        frame[y0:y1, x0:x1] = part[y0 - top:y1 - top, x0 - left:x1 - left]
        window.append((frame, None, None, None))
        shown.append(t)
    return window, shown


SAME_PLACE = 0.25   # of a frame: tiles of different filters this close are the same pointing (seams)
# balanced look: solve the seams once per pointing on linear values (seams) instead of each filter on its own, as
# the classic look does. Off: on real passes it changed the faint sky's tile colours (Saturn's Shadow, the Jupiter
# approach mosaic's stray light) more often than it helped, and the gains it kept from collapsing to 0.909
# collapse evenly, which only dims a mosaic a little
SHARED_SEAMS = False


def seams(u, p, tiles, rect, ref, cache):
    """Balanced look: the seam correction of every pointing, solved once on the filter ref (the best covered of
    the filters drawn) on linear values, with the gains anchored (mosaic.seams, none pinned), for every filter's
    tile at that pointing, so the filters at one spot start from the same correction and keep their colour.
    {tile n: (gain, offset)}; a tile with no tile of ref at its pointing gets none. Kept in the cache."""
    mine = [t for t in tiles if t["filter"] == ref and "offset" in t]
    name = f"{ref.replace('/', '_')}-{len(mine)}-{'_'.join(str(round(v)) for v in rect)}.json"
    path = os.path.join(folder(u, cache), "seams", name)

    def make():
        window, shown = _window(u, p, mine, rect, cache)
        if len(window) < 2:
            return b"{}"
        with reel._mosaic_lock:
            gains, offsets = mosaic.seams([w[0] for w in window], None, p["display_scale"]["gamma"])
        return json.dumps({t["n"]: [float(g[0]), float(o[0])] for t, g, o in zip(shown, gains, offsets)}).encode()

    solved = {int(n): v for n, v in json.loads(reel._cached(path, make)).items()}
    by_n = {t["n"]: t for t in mine}
    out = {}
    for t in tiles:
        if "offset" not in t:
            continue
        if t["n"] in solved:
            out[t["n"]] = solved[t["n"]]
            continue
        # the tile of ref nearest this one's pointing, then nearest in time
        near = [(math.hypot(by_n[n]["offset"][0] - t["offset"][0], by_n[n]["offset"][1] - t["offset"][1]),
                 abs(by_n[n]["t"] - t["t"]), n) for n in solved]
        near = [x for x in near if x[0] <= SAME_PLACE * FRAME]
        if near:
            out[t["n"]] = solved[min(near)[2]]
    return out


GROW_FROM = 16   # tiles of one filter: a mosaic with more is the one before it with the new tile drawn over it


def _filter_path(u, f, count, rect, cache, solved_on=""):
    name = f"{f.replace('/', '_')}-{count}{solved_on}-{'_'.join(str(round(v)) for v in rect)}.png"
    return os.path.join(drawn(u, cache), "filters-level", name)


def _png(rgba):
    out = io.BytesIO()
    Image.fromarray(rgba).save(out, "PNG", compress_level=1)
    return out.getvalue()


def held_level(frames):
    """The seams' (gains, offsets) of frames on one calibrated scale, none pinned (mosaic.seams' pin None), for
    mosaic.compose's corrections. Pinned to none, the gains all sink together toward their limit as overlaps come
    in (the data asks only that they agree), so a mosaic dimmed about 9% while it filled: their mean log is held
    at 0 instead, so the pass keeps the level its scale gave it from the first tile to the last."""
    gains = mosaic.match_gains(frames, mosaic.calibrated_gain, None, mosaic.calibrated_overlap)
    gains = gains / np.exp(np.log(gains).mean(axis=0))
    return gains, mosaic.match_offsets(frames, gains, None, mosaic.calibrated_overlap)


def _compose(window, k, **kw):
    """mosaic.compose on the view's canvas, with the benchmark's soft edge on its 0.5 scale canvas at this
    canvas's scale."""
    feather = mosaic.feather_px
    with reel._mosaic_lock:
        try:
            mosaic.feather_px = max(8, round(64 * k / 0.5))
            mosaic.reset()
            if kw.get("pin", -1) is None and "corrections" not in kw and "gamma" not in kw and len(window) > 1:
                kw = {**kw, "corrections": held_level([np.asarray(w[0]) for w in window])}
            rgba = mosaic.compose(window, False, calibrated=True, **kw)
            mosaic.reset()
        finally:
            mosaic.feather_px = feather
    return rgba


def _over(u, p, rgba, t, rect, cache, match=True, kept=None):
    """Tile t composed over the mosaic rgba (in place) and matched to it (pin 0): only the tile's part of the
    canvas, and a margin for its soft edge, is composed, since nothing outside it changes. match=False: drawn
    over it with its soft edge as it is, on the pass's one scale (a mosaic movie's new lap is not pulled toward
    the older picture of its place under it). kept: as draw_over. A partial frame (partial) is drawn under the
    picture instead, so it shows only where nothing else is."""
    k = p["k"]
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    draw_over(rgba, lambda: _shade(_part(_pic(u, cache, p["display_scale"], t), sw, sh), t),
              left, top, sw, sh, k, match, kept, under=partial(t) or bool(t.get("under")) or bool(t.get("long")) or bool(t.get("fill")))


def draw_over(rgba, part, left, top, sw, sh, k, match=True, kept=None, under=False):
    """_over's drawing: the tile part() (RGBA, sw x sh canvas pixels, its top left corner at left, top) composed over
    the mosaic rgba in place, on the tile's part of the canvas and a margin for its soft edge. kept: a list that gets
    what the blend step decided for the tile (mosaic.composite's kept, at the canvas's pixels), or None. under: the
    tile drawn under the picture instead (matched to it, pin on the picture), and nothing kept for it."""
    H, W = rgba.shape[:2]
    pad = max(8, round(64 * k / 0.5)) + 1
    x0, y0 = max(left - pad, 0), max(top - pad, 0)
    x1, y1 = min(left + sw + pad, W), min(top + sh + pad, H)
    a0, b0 = max(left, 0), max(top, 0)
    a1, b1 = min(left + sw, W), min(top + sh, H)
    # (a tile wholly past the canvas's edge, only its soft edge's margin on it, has nothing to draw: SPICE, filter
    # registration or a person's tuning can put a tile outside the pass's footprint)
    if x1 > x0 and y1 > y0 and a1 > a0 and b1 > b0:
        part = part()
        frame = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        frame[b0 - y0:b1 - y0, a0 - x0:a1 - x0] = part[b0 - top:b1 - top, a0 - left:a1 - left]
        below = np.ascontiguousarray(rgba[y0:y1, x0:x1])
        same = (np.ones((2, 3)), np.zeros((2, 3)))
        # matched to the picture so far (pin 0), and with the level step leveled to it along its seams as well
        # (mosaic._levels, pinned to it): leveled alone (gains of 1, each tile on the pass's one scale away from its
        # seams), Saturn's 725 tile mosaic movie of 2013 drawn whole came out 12% darker at the bottom than matched
        if under:
            kw = {"corrections": same, "level": False} if not match else {"pin": 1}
            rgba[y0:y1, x0:x1] = _compose([(frame, None, None, None), (below, None, None, None)], k, under=1, **kw)
            if kept is not None:
                kept.append(None)
            return
        kw = {"corrections": same, "level": False} if not match else {"pin": 0}
        decided = [] if kept is not None else None
        rgba[y0:y1, x0:x1] = _compose([(below, None, None, None), (frame, None, None, None)], k, under=0, kept=decided, **kw)
        if kept is not None:
            kept.append(mosaic.moved(decided[-1], y0, x0) if decided else None)
    elif kept is not None:
        kept.append(None)


_grown_last = collections.OrderedDict()   # path of a grown filter mosaic -> its RGBA, the few made last
GROWN_KEEP = 6


def _grown(u, p, f, mine, rect, cache, tag=""):
    """The filter f's mosaic of mine (more than GROW_FROM tiles), grown a tile at a time: the mosaic of the
    tiles before the newest, as it was drawn, with the newest composed over it and matched to it (pin 0), so
    each new tile costs one tile's compose, not all of them again, and what is drawn stays as it was drawn.
    Only the newest tile's part of the canvas (and a margin for its soft edge) is composed, since nothing
    outside it changes. Starts from the largest of those mosaics already made (the first GROW_FROM tiles
    solved together otherwise) and keeps each one it makes on the way."""
    named = lambda m: _filter_path(u, f, m, rect, cache)[:-len(".png")] + tag + ".png"
    m = len(mine) - 1
    while m > GROW_FROM and named(m) not in _grown_last and not os.path.exists(named(m)):
        m -= 1
    rgba = filter_mosaic(u, p, f, mine[:m], rect, cache, tag=tag).copy()
    for j in range(m, len(mine)):
        _over(u, p, rgba, mine[j], rect, cache)
        path = named(j + 1)
        with _lock:
            _grown_last[path] = rgba.copy() if j + 1 < len(mine) else rgba
            _grown_last.move_to_end(path)
            while len(_grown_last) > GROWN_KEEP:
                _grown_last.popitem(last=False)
        if j + 1 < len(mine):
            reel._cached(path, lambda: _png(rgba))
    return _png(rgba)


_rolling = contextvars.ContextVar("rolling", default=False)   # drawing a laps=1 mosaic movie (rolling_webp)
_rolled = collections.OrderedDict()   # (pass, look, filter, view) -> [(tiles drawn, RGBA)]: each mosaic movie's last pictures
# mosaic movies whose last pictures are kept, whole passes (every filter of each), the least recently drawn let go
# first: one per thread drawing them at once and a window or two, so threads making different passes side by side
# (the pre-build) do not throw out each other's pictures and draw every frame whole (a canvas is up to 16 MB)
ROLLED_PASSES = int(os.environ.get("CASSINI_ROLLED_PASSES", "4"))
ROLLED_EACH = 2    # pictures kept of each filter


def rolled_room(passes):
    """Keep the last pictures of at least this many mosaic movies (a caller drawing that many at once)."""
    global ROLLED_PASSES
    with _lock:
        ROLLED_PASSES = max(ROLLED_PASSES, int(passes))


def _as_drawn(mine):
    """What a mosaic movie's picture of one filter is drawn from (_rolled): each tile and the gain it is drawn at."""
    return frozenset((t["n"], t.get("gain", 1.0)) for t in mine)


def _rolled_put(key, drawn, rgba):
    with _lock:
        kept = [x for x in _rolled.get(key, []) if x[0] != drawn][-(ROLLED_EACH - 1):] + [(drawn, rgba)]
        _rolled[key] = kept
        _rolled.move_to_end(key)
        # the pass (and look) is let go as a whole, the one drawn longest ago
        passes = list(dict.fromkeys(k[:2] for k in _rolled))
        for old in passes[:max(0, len(passes) - ROLLED_PASSES)]:
            for k in [k for k in _rolled if k[:2] == old]:
                del _rolled[k]
ROLL_STEPS = 8   # most new tiles a mosaic movie's picture grows by from its last one; further than that, it is drawn anew


def _roll(u, p, key, mine, rect, cache):
    """A mosaic movie's picture of one filter (every place's newest tile, mine), grown from the last one drawn
    (_rolled) by composing its new tiles over it, a tile's part of the canvas each (_over, as _grown does for a
    pass's mosaic), so a new frame costs one tile's compose instead of every place's again: a playing window
    gets its pictures about as fast as tiles are made. None when there is nothing to grow from (the first
    picture, a jump, a step back in time): the caller draws it whole."""
    with _lock:
        kept = list(_rolled.get(key, []))
    want = _as_drawn(mine)
    # only forward: what is kept of a picture is all still wanted or covered by a newer copy of its place; the
    # one kept with the fewest tiles to add (a tile drawn at another gain is not the same tile)
    best = None
    for drawn, rgba in kept:
        new = sorted(want - drawn)
        if new and len(new) <= ROLL_STEPS and (not drawn or new[0][0] > max(drawn)[0]) and (best is None or len(new) < len(best[0])):
            best = (new, rgba)
    if best is None:
        return None
    new, rgba = best
    rgba = rgba.copy()
    by_n = {t["n"]: t for t in mine}
    for n, _ in new:
        _over(u, p, rgba, by_n[n], rect, cache, match=False)
    return rgba


CLIPPED_TAG = "_cu"   # in a mosaic picture's name: a saturated pointing is drawn under the others (clipped_pointings)
VISIT_TAG = "-v"   # in the name of a colour filter's mosaic drawn without the partial visits (visit_tiles)


def colour_planes(u, p, colour, tiles, rect, cache, ref=None, tag=""):
    """The colour filters' mosaics a colour picture is made of (filter_mosaic of each), drawn of whole visits only
    (visit_tiles), under names of their own when that leaves tiles out; which tiles go under (dim_places) is decided
    on all of the pass's tiles, as for its other pictures."""
    mine = visit_tiles(u, tiles, colour)
    extra = VISIT_TAG if len(mine) < len(tiles) or any(t.get("long") for t in mine) else ""
    return [filter_mosaic(u, p, f, mine, rect, cache, ref, tag + extra, every=tiles) for f in colour]


def filter_mosaic(u, p, f, tiles, rect, cache, ref=None, tag="", every=None):
    """The filter f's mosaic of these tiles in the view rect, RGBA on the view's canvas (kept in the cache).
    ref = the filter the seams are solved on (balanced look, seams). Past GROW_FROM tiles it grows from the
    one before (_grown) instead of composing every tile again. tag names a set of tiles that is not every tile
    up to the newest (a mosaic movie's lap, rolling_layout): it has a name of its own and is not grown, since
    growing takes the tiles as the pass's first ones in time order. f = LUM: the pass's luminance base (_mine)."""
    mine = _mine(u, p, tiles, f)
    # every tile up to the newest (less a colour filter's partial visits, VISIT_TAG: those are left out from the start)
    plain = tag[:-len(VISIT_TAG)] if tag.endswith(VISIT_TAG) else tag
    whole = plain in ("", PANEL_TAG, EDGE_TAG, SURFACE_TAG, SURFACE_TAG + PANEL_TAG)
    if whole and not _rolling.get() and calibration.step("level") and not all("under" in t for t in mine):
        # a pass's mosaic (not a mosaic movie's lap): a tile far darker than the picture before it goes under it
        # (decided here on all the pass's tiles; the mosaic of fewer tiles _grown starts from keeps the decisions)
        colour = p.get("colour") or []
        low = dim_places(u, p, f, mine, tiles if every is None else every, cache, colour if f in colour else None)
        mine = [dict(t, under=t["n"] in low) for t in mine]
    balanced = calibration.look() == "balanced" and SHARED_SEAMS and f != LUM
    ref = ref or f
    solved_on = f"-{ref.replace('/', '_')}{sum(1 for t in tiles if t['filter'] == ref and 'offset' in t)}" if balanced else ""
    path = _filter_path(u, f, len(mine), rect, cache, solved_on)
    path = path[:-len(".png")] + tag + ".png"
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)

    roll = (u["key"], calibration.mode(), f, tuple(round(v) for v in rect)) if tag and _rolling.get() and not balanced else None
    drew = {}

    def make():
        # (panel registration's tiles are every tile up to the newest too, each kept where it was first put)
        # (and not a base with fills, lum_fills: one joins it under the tiles before it, not as the newest on top)
        if not balanced and whole and len(mine) > GROW_FROM and not any(t.get("fill") for t in mine):
            return _grown(u, p, f, mine, rect, cache, tag)
        window, shown = _window(u, p, mine, rect, cache)
        corrections = None
        if balanced and window:
            # ref's seams at each pointing; another filter's own overlaps then adjust them where they clearly
            # differ (a frame's own exposure error), pulled toward them, so the filter keeps their overall level
            solved = seams(u, p, tiles, rect, ref, cache)
            pick = [solved.get(t["n"], (1.0, 0.0)) for t in shown]
            corrections = (np.array([[g] * 3 for g, _ in pick]), np.array([[o] * 3 for _, o in pick]))
            if f != ref:
                corrections = mosaic.seams([w[0] for w in window], None, p["display_scale"]["gamma"], corrections)
        if not window:
            rgba = np.zeros((H, W, 4), np.uint8)
        elif corrections:
            rgba = _compose(window, k, pin=None, gamma=p["display_scale"]["gamma"], corrections=corrections)
        else:
            rgba = _compose(window, k, pin=None)
        drew["rgba"] = rgba
        return _png(rgba)

    with _lock:
        kept = _grown_last.get(path)
        same = [x[1] for x in _rolled.get(roll, []) if x[0] == _as_drawn(mine)] if roll else []
    if kept is not None:
        return kept
    # a mosaic movie's filter whose tiles did not change since one of its last pictures (the new tile is another
    # filter's): that picture again, though the movie's picture has a new name
    if same:
        return same[0]
    # a mosaic movie's next picture, grown from one before it: kept in memory only (the movie's picture made of
    # it is kept in the cache), as writing the filter's whole canvas costs more than growing it
    grew = _roll(u, p, roll, mine, rect, cache) if roll and not os.path.exists(path) else None
    if grew is not None:
        _rolled_put(roll, _as_drawn(mine), grew)
        return grew
    data = reel._cached(path, make)
    with _lock:
        kept = _grown_last.get(path)
    if kept is not None:
        return kept
    rgba = drew.get("rgba")
    if rgba is None:
        rgba = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))
    if roll:
        # a picture the mosaic movie's next ones grow from (_roll)
        _rolled_put(roll, _as_drawn(mine), rgba)
    return rgba


_parts = collections.OrderedDict()   # (tile file, width, height) -> the tile at that size, most recently used last
_parts_bytes = [0]
PARTS_KEEP = int(os.environ.get("CASSINI_MOSAIC_PARTS_MB", "256")) << 20
_made_pictures = collections.OrderedDict()   # tile file -> its picture (RGBA) as it was made and written, the newest last
_made_pictures_bytes = [0]
MADE_KEEP = int(os.environ.get("CASSINI_MOSAIC_MADE_MB", "64")) << 20


def _keep_made(path, picture):
    """A tile's picture as made and written to path, kept in memory (the newest, up to MADE_KEEP bytes): a movie
    frame or a mosaic draws its new tile right after making it (_part), the next filter's tile at its pointing is
    registered to it (_register), and reading the PNG back cost ~35 ms each time."""
    picture = picture.view()
    picture.flags.writeable = False
    with _lock:
        old = _made_pictures.pop(path, None)
        if old is not None:
            _made_pictures_bytes[0] -= old.nbytes
        _made_pictures[path] = picture
        _made_pictures_bytes[0] += picture.nbytes
        while _made_pictures and _made_pictures_bytes[0] > MADE_KEEP:
            _made_pictures_bytes[0] -= _made_pictures.popitem(last=False)[1].nbytes


def _part(path, w, h):
    """A tile at w x h canvas pixels (RGBA): read and resized to that size (no sharpening since 11-08: #249's unsharp
    mask came out) once, and kept in memory (up to PARTS_KEEP bytes), since
    every mosaic of a pass is drawn again from all of its tiles and a tile never changes once made."""
    key = (path, w, h)
    with _lock:
        part = _parts.get(key)
        if part is not None:
            _parts.move_to_end(key)
            return part
        made = _made_pictures.get(path)
    # a tile just made is resized from its picture in memory, the pixels its PNG holds
    im = Image.fromarray(made) if made is not None else Image.open(path).convert("RGBA")
    part = np.asarray(im.resize((w, h), Image.LANCZOS))
    with _lock:
        if key not in _parts:
            _parts[key] = part
            _parts_bytes[0] += part.nbytes
            while _parts_bytes[0] > PARTS_KEEP and len(_parts) > 1:
                _parts_bytes[0] -= _parts.popitem(last=False)[1].nbytes
    return part


def sharpens(scale):
    """True when pictures on the display scale end in detail(): a pass whose body fills its frames (pass_scale's
    "detail"; a scale made before it had one, its "filled")."""
    return bool(scale.get("detail", scale.get("filled")))


def detail(rgba, sigma):
    """Raises the local contrast of a mosaic of a body that fills the frames (Titan's surface is a few per cent
    against its haze): each pixel moved away from its neighbourhood's mean (a Gaussian of sigma canvas pixels,
    over the mosaic's own pixels only, so the empty canvas does not darken its edges) by DETAIL times the
    difference. Local, so a new tile only changes the mosaic next to it. Balanced look: on the luminance only
    (the mean of the channels), the same change added to every channel, so the small misregistration between
    filters does not turn into rainbow texture."""
    import cv2
    a = rgba[..., 3].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32)
    weight = cv2.GaussianBlur(a, (0, 0), sigma)
    if calibration.look() == "balanced":
        # the channels' mean: 8-bit values, so the sum is exact and this is numpy's mean(axis=2) to the bit (all
        # 2^24 colours), without its slow reduce over three
        lum = (rgb[..., 0] + rgb[..., 1] + rgb[..., 2]) / 3
        mean = cv2.GaussianBlur(lum * a, (0, 0), sigma) / np.maximum(weight, 1e-3)
        x = lum - mean
        d = DETAIL * x / (1 + np.abs(x) / np.float32(DETAIL_EDGE))
        # (the room a pixel has: up to its brightest channel's 255, down to its darkest's 0, so one change for all
        # three keeps its color)
        room = np.where(d > 0, 255 - rgb.max(axis=2), rgb.min(axis=2))
        out = np.clip(rgb + _soft_detail(d, room)[..., None], 0, 255)
        return np.dstack([out.round().astype(np.uint8), rgba[..., 3]])
    mean = cv2.GaussianBlur(rgb * a[..., None], (0, 0), sigma) / np.maximum(weight, 1e-3)[..., None]
    x = rgb - mean
    d = DETAIL * x / (1 + np.abs(x) / np.float32(DETAIL_EDGE))
    out = np.clip(rgb + _soft_detail(d, np.where(d > 0, 255 - rgb, rgb)), 0, 255)
    return np.dstack([out.round().astype(np.uint8), rgba[..., 3]])


def _soft_detail(d, room):
    """detail()'s change d (float32, levels) where a pixel has room levels left in its direction: as it is up to
    DETAIL_KNEE of that room, past it rolled off toward the room's end (over / (over + rest): no step in slope, and
    slow enough that a strong change keeps its order instead of piling up a level under the end, as tanh did) instead
    of running into 0 or 255 and clipping. A crater's sunlit wall beside its shadow, already near white and near black, was
    pushed flat to both ends by DETAIL's tripled contrast: hard white blotches and black holes along every rim."""
    room = room.astype(np.float32)
    knee = np.float32(DETAIL_KNEE) * room
    mag = np.abs(d)
    past = mag > knee
    if not past.any():
        return d
    rest = room - knee
    over = mag - knee
    soft = knee + rest * over / np.maximum(over + rest, np.float32(1e-6))
    return np.where(past, np.sign(d) * soft, d).astype(np.float32)


def layout(u, n, cache):
    """What the pass's mosaic with tiles 0..n is made of: (plan, tiles, view rect, placed tiles per filter, the
    filters drawn, a name for that picture); None before any tile is placed. Frames whose tile is not one of
    the filters drawn (a moon's 30 filter colour pass draws 3) give the same picture and the same name.
    The filters used are the plan's colour filters once each has a tile, before that its grey filter (or, until
    the grey filter's first tile, the luminance base's filter most taken so far); the picture is drawn on the
    luminance base (so_far), whose tiles the name counts (L<n>) when it holds more than the filters used. None
    before a tile of the base is placed: the gray never starts in a filter it then leaves."""
    p = plan(u, cache)
    tiles = [_silhouette(t) for t in _reports(u, cache, p, range(n + 1))]
    rect = view_rect(p, tiles)
    # each tile's surface redrawn as at the pass's epoch (surface reprojection), then each pointing moved onto the
    # ones before it where they overlap (panel registration: what is left is SPICE's pointing, a few pixels)
    surfaced = surface_pictures(u, cache, p, tiles)
    if surfaced:
        tiles = [dict(t, pic=surfaced[t["n"]], box=surface_box(surfaced[t["n"]], t)) if t["n"] in surfaced else t
                 for t in tiles]
    moved = panel_places(u, cache, p, tiles)
    if moved:
        tiles = [dict(t, offset=[t["offset"][0] + moved[t["n"]][0], t["offset"][1] + moved[t["n"]][1]], spice_place=t["offset"])
                 if t["n"] in moved and "offset" in t else t for t in tiles]
    count = {}
    for t in tiles:
        if "offset" in t:
            count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not count:
        return None
    colour = p["colour"]
    frames = lum_frames(u, p) | lum_fills(u, p, tiles)
    base = [t["filter"] for t in tiles if "offset" in t and t["n"] in frames]
    if colour and all(count.get(f) for f in colour):
        used = colour
    elif count.get(p["grey"]):
        used = [p["grey"]]
    elif base:
        used = [max(dict.fromkeys(base), key=base.count)]   # (ties: the filter taken first)
    else:
        return None
    name = "_".join(f"{f.replace('/', '-')}{count[f]}" for f in used)
    if any(f not in used for f in base):
        name += f"_L{len(base)}"
    if colour and used == colour and clipped_pointings(u, [t for t in tiles if t["filter"] in colour]):
        name += CLIPPED_TAG   # (its colour planes draw a saturated pointing under: visit_tiles)
    return p, tiles, rect, count, used, name + "_" + "_".join(str(round(v)) for v in rect) + (SURFACE_TAG if surfaced else "") + ((EDGE_TAG if clouded(u) else PANEL_TAG) if moved else "")


TUNE_MAX = 0.5   # furthest a pointing can be moved, as a fraction of the picture


def parse_tune(tune, hide):
    """The person's changes to a mosaic's tiles (Cassini Studio) from the request: tune "3:0.012:-0.004,7:0:0.02"
    (pointing n as tile_map numbers them, moved by dx, dy fractions of the picture) and hide "2,9" (pointings left
    out). ({n: (dx, dy)}, {n}); ValueError when it does not read."""
    moves, gone = {}, set()
    for part in filter(None, (tune or "").split(",")):
        n, dx, dy = part.split(":")
        dx, dy = float(dx), float(dy)
        if not (math.isfinite(dx) and math.isfinite(dy)):
            raise ValueError(part)
        moves[int(n)] = (max(-TUNE_MAX, min(TUNE_MAX, dx)), max(-TUNE_MAX, min(TUNE_MAX, dy)))
    for n in filter(None, (hide or "").split(",")):
        gone.add(int(n))
    if len(moves) + len(gone) > 400:
        raise ValueError("too many")
    return moves, gone


def tuned_layout(made, mapped, moves, gone):
    """A layout (layout()) with the person's changes laid over SPICE's placement: each moved pointing's tiles (every
    filter of it, so its colours stay together) offset by its move, hidden pointings' tiles left out. The tiles'
    own pictures, the plan and the view are untouched: the mosaic is composed from them by mosaic.compose as
    always, under a name of its own (-tune<hash>), so the untouched mosaic stays as it is, one request away.
    mapped: tile_map() of the same frame (its pointing numbers). made unchanged when there is nothing to change."""
    if not made or not mapped or not (moves or gone):
        return made
    p, tiles, rect, count, used, name = made
    by = {q["n"]: q["tiles"] for q in mapped["pointings"]}
    shift, out = {}, set()
    for q, (dx, dy) in moves.items():
        for n in by.get(q, []):
            shift[n] = (dx * rect[2], dy * rect[3])
    for q in gone:
        out.update(by.get(q, []))
    shift = {n: v for n, v in shift.items() if v != (0.0, 0.0)}
    if not shift and not out:
        return made
    tiles = [dict(t, offset=[t["offset"][0] + shift[t["n"]][0], t["offset"][1] + shift[t["n"]][1]]) if t["n"] in shift and "offset" in t else t
             for t in tiles if t["n"] not in out]
    count = {}
    for t in tiles:
        if "offset" in t:
            count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not any(count.get(f) for f in used):
        return None
    for f in used:
        count.setdefault(f, 0)
    key = json.dumps([sorted((n, round(v[0], 2), round(v[1], 2)) for n, v in shift.items()), sorted(out)])
    return p, tiles, rect, count, used, f"{name}-tune{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def _despiked(planes, gamma):
    """A colour set's placed planes (RGBA, the pass's display scale) with each one-filter spike (a cosmic ray or hot
    pixel in one filter only) set to what is round it: calibration._clean_spikes, the still composites' cleaner
    (natural: 5x5, and where not every other filter peaks), in linear light."""
    lin = [calibration.decode(a[..., 0].astype(np.float32) / 255, gamma) for a in planes]
    seen = np.min([a[..., 3] for a in planes], axis=0) > 0
    out = []
    # (its grain over all the picture: a display scale's sky is mostly crushed to black, no grain to measure)
    for a, c in zip(planes, calibration._clean_spikes(lin, seen if seen.sum() >= 100 else np.ones(seen.shape, bool), True)):
        a = a.copy()
        a[..., :3] = (calibration.encode(np.clip(c, 0, 1), gamma) * 255 + 0.5).astype(np.uint8)[..., None]
        out.append(a)
    return out


CLIP_FROM = 240   # (colour_picture) a band this bright and up is taken as clipped, wholly so at 255
CLIP_REACH = 1 / 16   # (colour_picture) of the picture's side: how far round a clipped band its colour is read from


TINT_LIT = 0.1      # of the bright end: lit pixels, where a tinted frame's brightness match and mean hue are measured
TINT_CLIP = 200     # display levels: from here up to CLIP_FROM a tinted frame eases over to the set's own picture (the
#                     shoulder squeezes a frame's last levels before it clips: Saturn behind the 2012 Titan transit)
TINT_HUE = (0.6, 1.6)   # how far a pixel's hue strays from the set's mean, per channel: a set's colour fringes (a body
#                         moving between its filters: red and blue edges on Titan's limb) are not carried into the frame
TINT_FEATHER = 0.012   # of the picture's side: how far a tinted frame eases over to the set where it clipped
TINT_LOCAL = 0.06      # of the picture's side: the reach of the local brightness match that fill is brought to
TINT_EDGE = 0.012   # of the picture's side: how far inside what the set saw its own hue starts
LUM_REACH = 2 * sets_passes.SET_GAP   # s: (2 HOLD_AGE) how far a set's frame looks for the gray frame it is drawn from (shown_of): a set's
#                            channels span minutes, so a polarizer run between two clear frames 10 minutes apart still
#                            takes one (259EP EPIMETHEU001's P0/GRN frames played the misregistered, spiky set)
TINT_SATURATED = 0.02   # of a frame: a gray frame saturated over more than this gives a set's frames no luminance
TINT_TRUST = 1.25   # a pixel's hue this far from the set's mean (per channel, either way) is the set's own; further, it
#                     fades to the mean by TINT_HUE
TINT_DARK = 0.08    # of the bright end: below it a set's hue fades to gray (sky noise, a shadow: no hue of their own)
TINT_BLUR = 1.5     # px at the picture's size: the set's hue is smoothed this much, so its grain and edges stay the frame's
TINT_MATCH = (0.67, 1.5)   # the furthest a tinted frame's brightness is moved to the set's: both are on the pass's one
#                            display scale already, and a set showing another scene (the rings a moon was framed on, the
#                            frame on Saturn's night side) would otherwise set it (221EN PLMHPMR003 came out near black)


TINT_SHIFT = 0.04      # of the picture's side: the furthest a set's picture is moved onto the frame it tints (_onto_frame)


TINT_OUTLINE_GAIN = 0.8   # _outline_shift: a move kept only when the outlines then differ at most this share of as taken


def _outline_shift(im1, im2, both, reach, step=4):
    """(dx, dy) moving im2's lit outline onto im1's (as image_correction.limb_shift's shift), by the least difference of
    their blurred lit masks (Otsu, over both) within reach px: a coarse search every step px, then every px round the
    best; None unless it differs at most TINT_OUTLINE_GAIN of what it did as taken. For a set's filter whose limb the
    pipeline's limb_shift refuses (its terminator or haze rim unlike the frame's: Titan's MT1 against CB3)."""
    if both.mean() < 0.05:
        return None

    def lit(im):
        v = cv2.GaussianBlur(im.astype(np.float32), (0, 0), 2)
        t, _ = cv2.threshold(np.clip(v[both], 0, 255).astype(np.uint8).reshape(-1, 1), 0, 255,
                             cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return cv2.GaussianBlur((v > t).astype(np.float32), (0, 0), 3)
    a, b = lit(im1), lit(im2)
    inner = cv2.erode(both.astype(np.uint8), np.ones((15, 15), np.uint8), borderValue=0) > 0
    if inner.sum() < 1000:
        return None
    small = lambda x: cv2.resize(x, (x.shape[1] // step, x.shape[0] // step), interpolation=cv2.INTER_AREA)
    sa, sb, sm = small(a), small(b), small(inner.astype(np.float32)) > 0.99
    cost, cost_small = _shift_cost(a, b, inner), _shift_cost(sa, sb, sm)
    r = int(reach // step)
    best = min((cost_small(dx, dy), dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1))
    best = min((cost(best[1] * step + dx, best[2] * step + dy), best[1] * step + dx, best[2] * step + dy)
               for dx in range(-step, step + 1) for dy in range(-step, step + 1))
    if best[0] > TINT_OUTLINE_GAIN * cost(0, 0):
        return None
    return float(best[1]), float(best[2])


def _shift_cost(x, y, m):
    """cost(dx, dy): how far y moved by whole pixels (dx, dy) differs from x under mask m, the mean absolute difference
    of the two over m with y's pixels moved in from outside it 0, as a cv2.warpAffine of y by (-dx, -dy) (INTER_LINEAR,
    its border 0) gave it, to the bit: y's pixels are copied into place over m's bounding box only, so each of
    _outline_shift's ~520 tries a set's plane costs under half of what warping and comparing the whole picture did (a
    Jupiter WAC color movie frame 2.7 s at nice 19 on the Mini, 80% of it this search, 2026-11-08). The same
    differences in the same order, so the same mean and the same move chosen."""
    if not m.any():
        return lambda dx, dy: float("nan")   # (the mean of nothing, as before)
    rows, cols = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
    r0, r1, c0, c1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
    H, W = y.shape
    xb, mb = x[r0:r1, c0:c1], m[r0:r1, c0:c1]

    def cost(dx, dy):
        moved = np.zeros(xb.shape, y.dtype)
        # moved[i, j] = y[r0 + i + dy, c0 + j + dx], where that is inside y
        sr0, sr1, sc0, sc1 = max(r0 + dy, 0), min(r1 + dy, H), max(c0 + dx, 0), min(c1 + dx, W)
        if sr1 > sr0 and sc1 > sc0:
            moved[sr0 - dy - r0:sr1 - dy - r0, sc0 - dx - c0:sc1 - dx - c0] = y[sr0:sr1, sc0:sc1]
        return float(np.abs(xb - moved)[mb].mean())
    return cost


def _onto_frame(colour, grey):
    """A set's picture or one filter's plane (RGBA) moved onto the frame it tints (grey: RGBA) by the pipeline's limb
    registration (image_correction.limb_shift: their lit outlines matched, the move kept only when the outlines then
    differ less), when that is under TINT_SHIFT of the picture's side; else as it is. A set's filters are taken a minute
    or more from each other and from the frame, each placed by its own pointing, so the body can sit 20 to 40 px apart
    in them: their limbs, whose hue is the set's own (a hazy rim blue, a filter's lone edge orange), then crossed the
    frame's disk as ghost arcs (133TI CLOUD002, CB3 + MT1; Sam 11-08)."""
    look = lambda a: np.ascontiguousarray(a[..., :3].mean(axis=2) if a.shape[2] == 4 and not np.array_equal(
        a[..., 0], a[..., 1]) else a[..., 0]).astype(np.uint8)
    shift, _ = image_correction.limb_shift(look(grey), look(colour), grey[..., 3] > 0, colour[..., 3] > 0)
    if shift is None:
        shift = _outline_shift(look(grey), look(colour), (grey[..., 3] > 0) & (colour[..., 3] > 0),
                               TINT_SHIFT * max(grey.shape[:2]))
    if shift is None or math.hypot(*shift) > TINT_SHIFT * max(grey.shape[:2]) or math.hypot(*shift) < 0.5:
        return colour
    m = np.float32([[1, 0, -shift[0]], [0, 1, -shift[1]]])
    return cv2.warpAffine(colour, m, (colour.shape[1], colour.shape[0]), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def tinted_frame(colour, grey, gamma=2.2, same=False):
    """A movie frame's own picture (grey: RGBA, its first channel the frame on the pass's display scale) drawn in the
    colour of a colour set (colour: colour_picture's RGBA on the same canvas): in linear light, the set's hue (each
    channel over its luminance) times the frame's brightness, brought to the set's over the lit part both cover. Where
    the set has no picture, or is dark, the hue is the set's mean over its lit part, so the frame keeps its whole
    place in one colour. The frame's alpha. (set_shown: the frames between sets play their own moment in colour.)"""
    lin = lambda v: calibration.decode(v.astype(np.float32) / 255, gamma)
    colour = _onto_frame(colour, grey)
    ca = colour[..., 3].astype(np.float32) / 255
    ga = grey[..., 3].astype(np.float32) / 255
    rgb = lin(colour[..., :3] / np.maximum(ca, 1 / 255)[..., None] / 1.0)
    rgb = np.clip(rgb, 0, None)
    if TINT_BLUR > 0:
        # (premultiplied: blurred unweighted, the picture's edge took in the empty canvas past it, a colored seam)
        ca0 = ca
        ca = cv2.GaussianBlur(ca0, (0, 0), TINT_BLUR)
        rgb = cv2.GaussianBlur(rgb * ca0[..., None], (0, 0), TINT_BLUR) / np.maximum(ca, 1e-3)[..., None]
    y = rgb @ np.asarray([0.2126, 0.7152, 0.0722], np.float32)
    g = lin(grey[..., 0])
    # (a clipped pixel of the frame says nothing of its brightness: left out of the match, and drawn from the set)
    near = np.clip((grey[..., 0].astype(np.float32) - TINT_CLIP) / max(1.0, CLIP_FROM - TINT_CLIP), 0, 1)
    clipped = near > 0
    both = (ca > 0.99) & (ga > 0.99) & ~clipped
    top_y = float(np.percentile(y[both], 99)) if both.any() else 0.0
    top_g = float(np.percentile(g[both], 99)) if both.any() else 0.0
    lit = both & (y > TINT_LIT * top_y) & (g > TINT_LIT * top_g)
    if lit.sum() >= LUM_MATCH_MIN and np.median(g[lit]) > 0:
        match = float(np.median(y[lit]) / np.median(g[lit]))
        hue = np.median(rgb[lit] / np.maximum(y[lit], 1e-6)[:, None], axis=0)
    else:
        match = float(np.median(y[both]) / max(np.median(g[both]), 1e-6)) if both.sum() >= LUM_MATCH_MIN else 1.0
        hue = np.ones(3, np.float32)
    # (same: the frame was taken with the set, the same moment, so its brightness is brought to the set's whole; a frame
    # further off only within TINT_MATCH)
    match = float(np.clip(match, *((1 / LUM_MATCH[1], LUM_MATCH[1]) if same else TINT_MATCH)))
    own = rgb / np.maximum(y, 1e-6)[..., None]
    # how far a pixel's hue strays from the set's mean, its largest per channel: past TINT_TRUST it fades to the mean,
    # gone at TINT_HUE (a channel lit where the others are not, the set's channels apart on a limb against the frame's
    # sharp one: a lime rim round Epimetheus, 259EP EPIMETHEU001; a cosmic ray in one channel)
    dev = np.abs(np.log(np.maximum(own, 1e-6) / np.maximum(hue, 1e-6)[None, None, :])).max(axis=2)
    trust = np.clip((math.log(TINT_HUE[1]) - dev) / (math.log(TINT_HUE[1]) - math.log(TINT_TRUST)), 0, 1)
    own = hue[None, None, :] * np.clip(own / np.maximum(hue, 1e-6)[None, None, :], *TINT_HUE)
    # the set's own hue where it is lit, held back from the edges of what it saw (its channels part there: magenta and
    # green seams); elsewhere, where the frame is lit (off the set's edge, or where the body has turned or moved since
    # the set: 153HY HYPERION001's cap came out gray), the set's mean hue, and gray only where the frame is dark too
    side = max(colour.shape[:2])
    seen = (ca * np.clip(y / max(TINT_DARK * top_y, 1e-6), 0, 1)).astype(np.float32)
    k = max(3, int(round(TINT_EDGE * side)) | 1)
    seen = cv2.GaussianBlur(cv2.erode(seen, np.ones((k, k), np.uint8)), (0, 0), k / 2)
    frame_lit = np.clip(g / max(TINT_DARK * top_g, 1e-6), 0, 1)[..., None]
    # (and only where the frame itself is lit: its dark sky takes no hue from the set's cosmic rays and hot pixels)
    w = (seen * trust)[..., None] * frame_lit
    rest = hue[None, None, :] * frame_lit + (1 - frame_lit)
    h = own * w + rest * (1 - w)
    out = np.clip(h * (g * match)[..., None], 0, 1)
    # where the frame clipped (a clear frame over-exposed on the planet behind the body it was exposed for) its
    # brightness says nothing: the set's own picture there, fading in from CLIP_FROM, so no flat white blotch
    clip = np.clip(cv2.GaussianBlur(near, (0, 0), max(4 * TINT_BLUR, TINT_FEATHER * side)), 0, 1) * ca
    if clip.any():
        # the set's picture brought to the frame's brightness round it, so the fill meets the frame without a seam
        # (the set was taken at another time and exposure: drawn as it is it made a patch of another brightness and
        # contrast over Saturn, cut along the frame's clipping, behind the 2012 Titan transit)
        valid = lit.astype(np.float32)
        sigma = TINT_LOCAL * side
        # (normalized convolution: the ratio of the blurred frame to the blurred set over where both are measured, at
        # two reaches, the wide one where the near one has nothing to go on deep inside the clipped part)
        local = np.ones(g.shape, np.float32)
        for reach in (4 * sigma, sigma):
            num = cv2.GaussianBlur(g * match * valid, (0, 0), reach)
            den = cv2.GaussianBlur(y * valid, (0, 0), reach)
            cover = cv2.GaussianBlur(valid, (0, 0), reach)
            known = np.clip(cover / 0.05, 0, 1)
            local = local * (1 - known) + np.where(den > 1e-9, num / np.maximum(den, 1e-9), 1.0) * known
        local = np.clip(local, *TINT_MATCH).astype(np.float32)
        # (the set's brightness there in the trusted hue, h: its own colors as they are carried the set's limb
        # misregistration in, a lime rim round Epimetheus' clipped clear frames, 259EP EPIMETHEU001)
        fill = np.clip(h * (y * local)[..., None], 0, 1)
        out = out * (1 - clip[..., None]) + fill * clip[..., None]
    rgb8 = (calibration.encode(out, gamma) * 255 + 0.5).astype(np.uint8)
    return np.dstack([rgb8, grey[..., 3]])


# a movie's color frame with another body in it (_per_body_planes)
PER_BODY_HAZE = (0.2, 24)   # of a body's radius past its disk that is moved with it (Titan's haze ring), for any
                            # other body at most this many reference px (Saturn's 1,300 px radius is no wider a glow)
PER_BODY_GROW = 3      # canvas px more (its blur)
PER_BODY_TITAN = 0.4   # of Titan's radius past its disk moved with it: its haze's glow reaches that far (153DI)
PER_BODY_LIT = 0.1     # of a plane's brightest: lit, where a ratio between planes is measured
PER_BODY_TARGET = 0.25  # _target_off: the most a plane's target is looked for from the shown plane's, of its radius
PER_BODY_WIDE = 0.5     # _target_off's search for the target itself, of its radius (158TI's Titan 37 px a filter)
PER_BODY_BETTER_TARGET = 0.05   # ... the target's own (its whole limb is matched, nothing else in the ring)
PER_BODY_STILL = 0.3    # of its edges' top: an edge this strong in both pictures at no move is still (_target_off)
PER_BODY_BETTER = 0.3   # how much better (correlation) the pictures' place of a body must line up than SPICE's
PER_BODY_MEASURE = 600  # canvas px of radius: a bigger body (Saturn) is moved by SPICE's offsets alone, not looked for
PER_BODY_LEAST = 10    # canvas px of radius: a smaller body (Pandora, Telesto, a speck) is not moved
PER_BODY_SLOP = 10      # canvas px (_per_body_planes)
PER_BODY_INSIDE = 0.25  # of the target's limb over the body's floor: inside SPICE's limb, that much over it is all target
PER_BODY_FRONT = (4, 0.15)   # canvas px and share of its radius round the target's disk (its blurred limb and glare, and the hold a few px off: Dione 8 px off in 153DI)
                             # that is not moved with a body behind it, nor taken from it


def _per_body_planes(u, js, places, planes, rect, k, radius, s):
    """A color frame's planes (one per filter: tiles js, each at its place [(drawn offset, SPICE's offset)]) with every
    other body SPICE puts on all of them moved, in each plane, to where it is in the plane of the frame shown (the
    tile nearest s): the planes are held on the target (steady_places), and a body moving against it between the
    filters (Titan behind Rhea, 37 px a filter in 154RH MUTUALEVE002; Tethys over Titan, 158TE) came out as red, green
    and blue copies. SPICE's place of one body from another on a frame is right (its pointing moves them both), so each
    plane's copy is moved by the difference of the two planes' SPICE offsets of the body from the target
    (other_bodies). Where the copy was and is no longer, the plane takes the shown plane's picture times its ratio to
    it on the target (what the body hid there: sky, or the target); where the target hid the body in that plane and
    not in the shown one, the shown plane's picture times its ratio to it on the body. Returns (planes, {name: [dx, dy]
    canvas px of each plane}) or (planes, None) when no other body is on every plane."""
    others = other_bodies(u, names=True)
    if len(planes) < 2 or not all(others.get(j) for j in js):
        return planes, None
    ref = min(range(len(js)), key=lambda i: abs(js[i] - s))
    named = [{b[0]: b[1:] for b in others[j]} for j in js]
    common = sorted(set(named[0]).intersection(*named[1:]))
    if not common:
        return planes, None
    H, W = planes[0].shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    def spice_target(i):
        (px, py), (sx, sy) = places[i]
        return (px - sx - rect[0]) * k + seen_off[0], (py - sy - rect[1]) * k + seen_off[1]
    # (where the shown plane's picture has the target's limb, when it is clearly off SPICE's place: Dione drawn 29 px
    # off it in 153DI MUTUALEVE002, so the zone round the target that a body behind it is not moved into sat off
    # Dione, and the moved Titan cut a wedge out of it, drawn blue, yellow and green; the other bodies go with it, as
    # SPICE's place of one from another is right)
    seen_off = (0.0, 0.0)
    if u["key"][0] not in PER_BODY_HAZY:
        # (not a hazy target, Titan's soft limb in 153TE SFAD002 lost to Tethys's sharp one; nor on the other bodies)
        at = spice_target(ref)
        others_at = [(at[0] + x * k, at[1] + y * k, r * k * 1.15 + PER_BODY_LIMB * radius * k + PER_BODY_GROW)
                     for x, y, r, _ in named[ref].values()]
        seen_off = _limb_centre(planes[ref][..., 0].astype(np.float32), at, radius * k, others_at) or seen_off
    lined = {}

    def target(i):
        return lined.get(i) or spice_target(i)

    def disk(c, r):
        return (xx - c[0]) ** 2 + (yy - c[1]) ** 2 <= r * r

    gray = [a[..., 0].astype(np.float32) for a in planes]
    front = PER_BODY_FRONT[0] + PER_BODY_FRONT[1] * radius * k
    out, moves = list(planes), {}
    away = np.zeros((H, W), bool)
    # the target itself first: where SPICE's place of it is off by the pointing between the filters and the hold did
    # not take it out (Titan 37 px a filter in 158TI MUTUALEVE001, the planes held on Rhea, Titan in red, yellow and
    # blue rings), each plane is moved so its target's limb lies on the shown plane's (_target_off over every other
    # body's disk left out), when that lines up clearly better than as it is
    tr = target(ref)
    # (the bodies in front of it left out; one behind it, Saturn behind Titan in 165TI, is what its limb is seen on)
    ex = [(tr[0] + x * k, tr[1] + y * k, r * k * 1.2 + PER_BODY_GROW) for x, y, r, behind in named[ref].values() if not behind]
    for i in range(len(planes)):
        if i == ref:
            continue
        off = _target_off(gray[ref], gray[i], tr, radius * k, exclude=ex, wide=True)
        if off is None or math.hypot(*off) < 1.0:
            continue
        m = np.float32([[1, 0, -off[0]], [0, 1, -off[1]]])
        out[i] = cv2.warpAffine(out[i], m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        gray[i] = out[i][..., 0].astype(np.float32)
        # (its bodies moved with it: SPICE's offsets of them from the target now count from the shown plane's target)
        lined[i] = tr
        moves.setdefault("_target", [None] * len(planes))[i] = [round(-off[0], 1), round(-off[1], 1)]

    for name in common:
        xr, yr, rr, behind = named[ref][name]
        if rr * k < PER_BODY_LEAST:
            continue
        tr = target(ref)
        cr = (tr[0] + xr * k, tr[1] + yr * k)
        # the target in front of the body hides it (a body behind), so its disk is left as it is
        front_r = disk(tr, radius * k + front) if behind else np.zeros((H, W), bool)
        haze = PER_BODY_TITAN if name == "TITAN" else min(PER_BODY_HAZE[0], PER_BODY_HAZE[1] / max(rr, 1e-6))
        new = disk(cr, rr * k * (1 + haze) + PER_BODY_GROW) & ~front_r
        if not new.any():
            continue
        away |= new
        g_ref = gray[ref]
        lit = g_ref > PER_BODY_LIT * max(float(g_ref.max()), 1.0)
        on_target = disk(tr, radius * k) & lit & ~new
        moves[name] = []
        for i in range(len(planes)):
            if i == ref:
                moves[name].append(None)
                continue
            x, y, r, _ = named[i][name]
            ti = target(i)
            ci = (ti[0] + x * k, ti[1] + y * k)
            # (where the body's limb is in this plane, looked for round where SPICE's offsets put it: the planes may
            # be held on it rather than the target, Rhea in 158TI MUTUALEVE001, so SPICE's move alone split it)
            seen = _target_off(gray[ref], gray[i], cr, rr * k, (ci[0] - cr[0], ci[1] - cr[1]),
                               exclude=(tr[0], tr[1], radius * k + front))
            if seen is not None:
                ci = (cr[0] + seen[0], cr[1] + seen[1])
            dx, dy = cr[0] - ci[0], cr[1] - ci[1]
            moves[name].append([round(dx, 1), round(dy, 1)])
            if math.hypot(dx, dy) < 0.5:
                continue
            # (what is moved of this plane stops PER_BODY_SLOP further out than the target's zone: the hold puts the
            # target a few px off, Dione 8 px in 153DI, and its limb came along with the body behind it; that band of
            # the body's new place is filled from the shown plane, as a hole is)
            front_i = disk(ti, radius * k + front + PER_BODY_SLOP) if behind else np.zeros((H, W), bool)
            was = disk(ci, r * k * (1 + haze) + PER_BODY_GROW) & ~front_i
            g = gray[i]
            m = np.float32([[1, 0, dx], [0, 1, dy]])
            moved = cv2.warpAffine(g * was, m, (W, H), flags=cv2.INTER_LINEAR)
            seen = cv2.warpAffine(was.astype(np.float32), m, (W, H), flags=cv2.INTER_LINEAR)
            ok = new & (seen > 0.99)
            moved = np.where(ok, moved / np.maximum(seen, 1e-3), moved)

            def ratio(where, fallback):
                both = where & (g_ref > 0)
                return float(np.median(moved[both] / g_ref[both])) if both.sum() >= 50 else fallback
            on_t = on_target & ~was
            r_target = float(np.median(g[on_t] / g_ref[on_t])) if on_t.sum() >= 50 else 1.0
            r_body = ratio(ok & lit, r_target)
            h = g.copy()
            # (where the body was, the band PER_BODY_SLOP leaves unmoved too)
            gone = disk(ci, r * k * (1 + haze) + PER_BODY_GROW) & ~new & \
                ~(disk(ti, radius * k + front) if behind else np.zeros((H, W), bool))
            h[gone] = g_ref[gone] * r_target
            h[ok] = moved[ok]
            # (on the body's disk; past it, in its glow, the plane's own: a fill there from the shown plane drew
            # Dione's place, which the far body's copy was cut round, as a blue crescent in the sky beside it)
            hole = new & ~ok
            h[hole] = g_ref[hole] * r_body
            if behind:
                # (round the target's limb, where its blur and glare lie over the body and each filter saw them over
                # another part of it: the shown plane's, or green and orange arcs ring the target)
                # (where the body is, or was in this plane, its disks whole: was and new leave this zone out)
                bodies_here = disk(ci, r * k * (1 + haze) + PER_BODY_GROW + 2) | disk(cr, rr * k * (1 + haze) + PER_BODY_GROW + 2)
                # (from PER_BODY_SLOP inside SPICE's limb: the hold puts the target a few px off, so its limb on the
                # dark side lay inside SPICE's disk and this plane's own body showed there, an orange edge round Rhea)
                ring = disk(ti, radius * k + front + 1) & ~disk(ti, radius * k - PER_BODY_SLOP) & bodies_here
                # (from the target's color at its limb to the body's at the ring's outer edge)
                # (off the body, over the sky, the target's own: Dione's glow beside Titan came out blue and green)
                # (each pixel there is the target's blurred limb and the body behind it, mixed: its ratio is the
                # target's and the body's in the share its brightness puts it between the two, the target's just
                # inside its limb and the body's just outside the ring. The target's ratio alone turned Titan's light
                # round Rhea blue and orange, the body's alone Rhea's limb glare, 154RH)
                t_in = disk(ti, radius * k - 2) & ~disk(ti, radius * k - 8) & lit
                b_out = disk(ti, radius * k + front + 8) & ~disk(ti, radius * k + front + 2) & new
                lt = float(np.median(g_ref[t_in])) if t_in.sum() >= 20 else float(g_ref.max())
                lb = float(np.median(g_ref[b_out])) if b_out.sum() >= 20 else 0.0
                on_body = disk(cr, rr * k * (1 + haze) + PER_BODY_GROW)
                # (either way round: a dark Titan over a bright Saturn, 165TI, as a bright Rhea over Titan)
                # (the body's brightness taken where it is seen just outside the zone in each pixel's own direction:
                # one median for the whole zone put Titan's dimmer side under Rhea's glare as part target, a gray
                # ring with a hard outer edge round Rhea, 154RH)
                lb = _radial_floor(g_ref, ti, radius * k + front + 4, lb)
                wt = np.clip((g_ref - lb) / np.maximum(lt - lb, 1.0), 0, 1) if np.any(np.abs(lt - lb) > 1) else np.ones_like(g_ref)
                # (inside SPICE's limb the target's own dimmer limb, under the body's floor or a little over it, is
                # still the target: only what is no brighter than the body there is taken as the body)
                inside = disk(ti, radius * k - 1)
                if np.any(np.abs(lt - lb) > 1):
                    wt = np.where(inside, np.clip((g_ref - lb) / np.maximum((lt - lb) * PER_BODY_INSIDE, 1.0), 0, 1), wt)
                wt = np.where(on_body, wt, 1.0)
                h[ring] = g_ref[ring] * (r_target * wt[ring] + r_body * (1 - wt[ring]))
            plane = out[i].copy()
            plane[..., :3] = np.clip(h + 0.5, 0, 255).astype(np.uint8)[..., None]
            out[i] = plane
            gray[i] = h
    if moves:
        moves["_away"] = away
    return out, (moves or None)


PER_BODY_HAZY = ("TITAN", "SATURN")   # targets whose limb is a haze: not looked for by _limb_centre
PER_BODY_LIMB = 0.75    # _limb_centre: the most a target's limb is looked for from SPICE's place, of its radius ...
PER_BODY_LIMB_LIT = 0.5     # ... of the brightest round it: the body's lit part, which ...
PER_BODY_LIMB_SHARE = (0.9, 0.1)   # ... must lie this much in the circle found, and this much more than in SPICE's
PER_BODY_LIMB_BETTER = 1.3   # ... and how much stronger its edges must lie on the circle there than at SPICE's place


def _limb_centre(g, at, r, exclude=()):
    """How far (canvas px) the centre of the circle of radius r that lies best on picture g's brightness edges is
    from at (SPICE's place of a body of that radius), searched to PER_BODY_LIMB of r, a pixel then a quarter pixel;
    None when it is no clearly better place (PER_BODY_LIMB_BETTER) or the body is too small or big to measure. The
    lit half of a limb is enough: each circle is scored on the stronger half of the edges along it. exclude: disks
    [(x, y, r)] whose edges are not counted (other bodies and their glow)."""
    if r < 8 or r > PER_BODY_MEASURE:
        return None
    reach = PER_BODY_LIMB * r
    half = int(r + reach + 6)
    x0, y0 = max(int(at[0]) - half, 0), max(int(at[1]) - half, 0)
    x1, y1 = min(int(at[0]) + half, g.shape[1]), min(int(at[1]) + half, g.shape[0])
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    a = cv2.GaussianBlur(np.ascontiguousarray(g[y0:y1, x0:x1]), (0, 0), 1.0)
    e = np.hypot(cv2.Sobel(a, cv2.CV_32F, 1, 0), cv2.Sobel(a, cv2.CV_32F, 0, 1))
    if exclude:
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        for ex, ey, er in exclude:
            e[(xx - ex) ** 2 + (yy - ey) ** 2 <= er * er] = 0
    th = np.linspace(0, 2 * np.pi, max(64, int(2 * np.pi * r)), endpoint=False).astype(np.float32)
    cx, cy = np.cos(th) * r, np.sin(th) * r

    def score(dx, dy):
        mx = (at[0] - x0 + dx + cx).astype(np.float32)
        my = (at[1] - y0 + dy + cy).astype(np.float32)
        v = cv2.remap(e, mx[None], my[None], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)[0]
        v = np.sort(v)
        return float(v[len(v) // 2:].mean())
    base = score(0.0, 0.0)
    best = (base, 0.0, 0.0)
    n = int(reach)
    for dx in range(-n, n + 1):
        for dy in range(-n, n + 1):
            if dx * dx + dy * dy <= reach * reach:
                v = score(dx, dy)
                if v > best[0]:
                    best = (v, float(dx), float(dy))
    for dx in np.arange(-0.75, 0.76, 0.25) + best[1]:
        for dy in np.arange(-0.75, 0.76, 0.25) + best[2]:
            v = score(dx, dy)
            if v > best[0]:
                best = (v, float(dx), float(dy))
    if best[0] < PER_BODY_LIMB_BETTER * max(base, 1e-6) or math.hypot(best[1], best[2]) < 1.0:
        return None
    # (and the body's lit part must lie in that circle, clearly more of it than in SPICE's: an edge of Titan's haze,
    # a ring line or a terminator lines up with a circle too, 158DI MUTUALEVE001 frame 20 pulled 33 px onto Titan)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    free = np.ones(a.shape, bool)
    for ex, ey, er in exclude:
        free &= (xx - ex) ** 2 + (yy - ey) ** 2 > er * er
    if not free.any():
        return None
    lit = (a > PER_BODY_LIMB_LIT * float(a[free].max())) & free
    if lit.sum() < 50:
        return None

    def share(dx, dy):
        return float((lit & ((xx - at[0] - dx) ** 2 + (yy - at[1] - dy) ** 2 <= (r * 1.05) ** 2)).sum()) / lit.sum()
    if share(best[1], best[2]) < PER_BODY_LIMB_SHARE[0] or share(best[1], best[2]) < share(0.0, 0.0) + PER_BODY_LIMB_SHARE[1]:
        return None
    return best[1], best[2]


def _radial_floor(g, c, r_out, fallback):
    """g's brightness at radius r_out from c in each pixel's own direction (a picture the size of g), smoothed along
    the circle; fallback where that point is off the picture."""
    H, W = g.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.maximum(np.hypot(xx - c[0], yy - c[1]), 1e-3)
    mx = c[0] + (xx - c[0]) * (r_out / d)
    my = c[1] + (yy - c[1]) * (r_out / d)
    sm = cv2.GaussianBlur(np.ascontiguousarray(g, dtype=np.float32), (0, 0), 3.0)
    out = cv2.remap(sm, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=-1.0)
    return np.where(out < 0, np.float32(fallback), out)


def _target_off(ref, g, at, r, guess=(0.0, 0.0), exclude=None, wide=False):
    """How far (canvas px) a body's limb in plane g is from its limb in the shown plane ref (at, radius r): the move
    (searched over PER_BODY_TARGET of its radius round no move and round guess, a pixel then a quarter pixel) that
    best correlates the two pictures' brightness edges in the ring round its limb (from 0.8 to 1.3 of its radius: the
    body behind it and the sky beyond add little there); (0, 0) for a small target or one mostly off the picture (None
    with a guess, which then stands)."""
    if r < 8 or r > PER_BODY_MEASURE:
        return None if guess != (0.0, 0.0) else (0.0, 0.0)
    reach = (PER_BODY_WIDE if wide else PER_BODY_TARGET) * r
    half = int(r * 1.3 + reach + 4 + math.hypot(*guess))
    # (cut to the canvas: a body near its edge is looked for on what is there of it)
    x0, y0 = max(int(at[0]) - half, 0), max(int(at[1]) - half, 0)
    x1, y1 = min(int(at[0]) + half, ref.shape[1]), min(int(at[1]) + half, ref.shape[0])
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None if guess != (0.0, 0.0) else (0.0, 0.0)

    def edges(a):
        a = cv2.GaussianBlur(np.ascontiguousarray(a[y0:y1, x0:x1]), (0, 0), 1.0)
        e = np.hypot(cv2.Sobel(a, cv2.CV_32F, 1, 0), cv2.Sobel(a, cv2.CV_32F, 0, 1))
        return e / max(float(np.percentile(e, 99)), 1e-6)
    ea, eg = edges(ref), edges(g)
    yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0].astype(np.float32)
    d = np.hypot(xx + x0 - at[0], yy + y0 - at[1])
    ring = (d > 0.8 * r) & (d < 1.3 * r)
    # (not over another disk and its glow: its limb would be matched as well, Titan under Rhea in 154RH)
    for ex in ([exclude] if exclude and not isinstance(exclude[0], (tuple, list)) else exclude or ()):
        ring &= np.hypot(xx + x0 - ex[0], yy + y0 - ex[1]) > ex[2]
    if not wide and guess != (0.0, 0.0):
        # (edges strong in both pictures where they are: what does not move between the filters, an edge-on ring line
        # across Titan in 153DI, which matched at no move and split Titan in three)
        ring &= ~((ea > PER_BODY_STILL) & (eg > PER_BODY_STILL))
    if ring.sum() < 0.3 * math.pi * (1.3 ** 2 - 0.8 ** 2) * r * r:
        return None if guess != (0.0, 0.0) else (0.0, 0.0)

    def coster(ea, eg, ring, q):
        a = ea[ring]
        na = float(np.sqrt((a * a).sum())) or 1.0

        def cost(dx, dy):
            # (minus the normalized correlation of the two rings' edges: an empty part of the sky is no match, as it
            # was for a difference of the two, 158TI's Rhea taken 110 px off)
            moved = cv2.warpAffine(eg, np.float32([[1, 0, -dx / q], [0, 1, -dy / q]]), eg.shape[::-1],
                                   flags=cv2.INTER_LINEAR)[ring]
            return -float((a * moved).sum()) / (na * (float(np.sqrt((moved * moved).sum())) or 1.0))
        return cost
    cost = coster(ea, eg, ring, 1.0)
    # (anywhere from no move to SPICE's guess and reach round both: the planes may be held on this body already, or on
    # neither, 158TI's Rhea 48 px off where SPICE said 110; on the pictures shrunk to about 60 px of radius every 2 of
    # its px, then every pixel round the best at full size)
    q = max(1.0, r / 60)
    if q > 1:
        small = lambda e: cv2.resize(e, (max(1, int(e.shape[1] / q)), max(1, int(e.shape[0] / q))), interpolation=cv2.INTER_AREA)
        sring = cv2.resize(ring.astype(np.uint8), small(ea).shape[::-1], interpolation=cv2.INTER_NEAREST) > 0
        coarse = coster(small(ea), small(eg), sring, q)
    else:
        coarse = cost
    gx, gy = guess
    step = 2.0 * q
    xs = np.arange(min(0.0, gx) - reach, max(0.0, gx) + reach + 0.5, step)
    ys = np.arange(min(0.0, gy) - reach, max(0.0, gy) + reach + 0.5, step)
    _, bx, by = min((coarse(dx, dy), dx, dy) for dx in xs for dy in ys)
    near = np.arange(-step / 2, step / 2 + 0.5, 1.0)
    _, bx, by = min((cost(bx + dx, by + dy), bx + dx, by + dy) for dx in near for dy in near)
    best = min(((cost(bx + dx, by + dy), bx + dx, by + dy) for dx in np.arange(-0.75, 0.8, 0.25) for dy in np.arange(-0.75, 0.8, 0.25)))
    if wide and best[0] > cost(0.0, 0.0) - PER_BODY_BETTER_TARGET:
        return 0.0, 0.0
    if guess != (0.0, 0.0) and best[0] > cost(gx, gy) - PER_BODY_BETTER:
        # (SPICE's guess stands unless the pictures line up clearly better elsewhere: Titan under the ring line and
        # Tethys, 158TE, was matched on the ring)
        return None
    return float(best[1]), float(best[2])


def colour_picture(u, p, colour, planes, away=None):
    """The colour picture of a pass's three colour filters' planes (RGBA, each on the pass's display scale), RGBA:
    the pass's mosaic and its movie frames mixed alike. Natural color: a true color pass turned into what an eye
    would see, a false color one balanced so the body comes out gray, on the pass's own measure of its body
    (pass_scale's balance); without the mix the bands stay on the grey scale, where the blue and green of a red
    body are close to black. away: pixels a clipped band's color is not measured on (other bodies, movie_frame)."""
    scale = p["display_scale"]
    if len(planes) == 2:
        # two filters: green their mean in linear light, as a two-filter composite draws it (calibration.two_bands)
        g = scale.get("gamma", 2.2)
        lin = [calibration.decode(a[..., 0].astype(np.float32) / 255, g) for a in planes]
        mid = (calibration.encode(np.clip(calibration.two_bands(lin)[1], 0, 1), g) * 255 + 0.5).astype(np.uint8)
        rgb = np.dstack([planes[0][..., 0], mid, planes[1][..., 0]])
    else:
        rgb = np.dstack([a[..., 0] for a in planes])
    bal = scale.get("balance")
    mix = calibration.color_mix(u["key"][2], colour, u["key"][0], [bal[f] for f in colour] if bal else None, obs=u["key"][1])
    typical = scale.get("typical")
    if isinstance(mix, calibration.FalseMix) and typical:
        mix.typical = typical if isinstance(typical, list) else [typical[f] for f in colour]
    alpha = np.min([a[..., 3] for a in planes], axis=0)
    clipped = [(rgb[..., i] >= CLIP_FROM) & (alpha > 0) for i in range(3)]
    if any(c.any() for c in clipped) and not all(np.array_equal(clipped[0], c) for c in clipped[1:]):
        # a band clipped where another is not (the camera saturated in it, or it is past the scale's white): filled
        # from the bands that are not, as a colour set's camera window draws it (calibration.tone's fill_saturated),
        # then mixed and rolled off with the brightest band, so it keeps a colour: left at white, a clipped red over a
        # green that just was not drew pink patches with ragged edges along the green's own clipping (North Pole
        # map movie, 175SA NPOLMAP001: RED saturated over 70% of the disk, GRN over 44%)
        g = scale["gamma"]
        x = calibration.decode(np.moveaxis(rgb.astype(np.float32) / 255, -1, 0), g).astype(np.float32)
        # (away: the other bodies of a movie frame (_per_body_planes), whose color is not the clipped body's: Rhea
        # saturated over Titan took Titan's orange)
        filled, every = calibration.fill_saturated(list(x), clipped, CLIP_REACH * max(x.shape[1:]),
                                                   where=None if away is None else ~away)
        # never under what the band read: a clipped band is at least as bright as its clipped value, and the ratio
        # the fill reads is measured where the band did not clip, its dimmer part, so where most of a frame clipped
        # it came out under the band's own reading and turned the tile green, blue or flat yellow with ragged edges
        # along each band's clipping (289SA SHEMMAP001, a VIMS ride-along map: RED saturated over 17-90% of every
        # frame, GRN up to 66%, BL1 up to 67%). Floored, a band meets its own clipping edge without a step.
        # Not for a band clipped over most of the picture (calibration.mostly_saturated), whose fill keeps the others'
        # colour, as the camera window's fill does.
        lit = calibration.lit_of(x)
        filled = [f if calibration.mostly_saturated(m, lit) else np.maximum(f, c) for f, c, m in zip(filled, x, clipped)]
        # (eased in from CLIP_FROM to white: a tile's clipped white, resampled and blended onto the canvas, comes in a
        # few levels under 255 along its edges)
        w = np.clip((rgb.astype(np.float32) - CLIP_FROM) / (255 - CLIP_FROM), 0, 1)
        w = np.moveaxis(w * w * (3 - 2 * w), -1, 0)
        x = x + w * (np.stack(filled) - x)
        if every is not None:
            every &= np.logical_and.reduce([c >= 255 for c in np.moveaxis(rgb, -1, 0)])
        if mix is not None:
            x = calibration.apply_mix(mix, x)
        calibration._shoulder(x, calibration.SHOULDER)
        if every is not None:
            x[:, every] = 1.0
        rgb = np.moveaxis((calibration.encode(np.clip(x, 0, 1), g) * 255 + 0.5).astype(np.uint8), 0, -1)
    elif mix is not None:
        rgb = calibration.mix_display(rgb, mix, scale["gamma"])
    # only where every filter has the picture: past one filter's edge the others alone are a coloured rim
    rgb = (rgb * (alpha[..., None] / np.float32(255)) + 0.5).astype(np.uint8)
    return np.dstack([rgb, alpha])


# the last picture so_far or movie_frame made on this thread, kept for the next size asked: the pre-build and the
# segment pre-render ask for each frame's mosaic, mosaic movie picture or movie frame at 1024 and 512 in turn
# (make_pass), and both sizes are made at OUT and shrunk after, so the second was the same picture made again. Kept
# up to OUT only (a full view's larger picture is not); each call gets a copy, as the callers shrink theirs in place
_last_made = threading.local()


def _kept_for_next_size(make, key_of):
    def kept(*args, **kwargs):
        key = key_of(*args, **kwargs)
        last = getattr(_last_made, "picture", None)
        if key is not None and last is not None and last[0] == key:
            return last[1].copy(), dict(last[2])
        im, rep = make(*args, **kwargs)
        _last_made.picture = (key, im.copy(), dict(rep)) if key is not None and im is not None else None
        return im, rep
    kept.__doc__ = make.__doc__
    return kept


def so_far(u, n, cache, made=None, out=OUT):
    """The pass's mosaic with tiles 0..n, RGBA out px (OUT unless asked for more, up to CANVAS) on its longest
    side, and its report; (None, None) before any tile is placed. made: layout(u, n, cache), when already
    worked out."""
    made = made or layout(u, n, cache)
    if not made:
        return None, None
    p, tiles, rect, count, used, name = made
    # a set of tiles other than every tile up to n has a name of its own (tag): a mosaic movie's lap, a tuned layout
    plain, _, tuned = name.partition("-tune")
    # (and a layout whose tiles panel registration moved: its tiles are not where the pre-built pictures have them)
    tag = ("-" + plain.rsplit("-", 1)[1] if plain.startswith("lap-") else "") + \
        "".join(x for x in (SURFACE_TAG, PANEL_TAG, EDGE_TAG) if x in plain) + ("-tune" + tuned if tuned else "")
    # the seams are solved on the best covered filter drawn and shared by all (balanced look)
    ref = max(used, key=lambda f: count[f])
    # the luminance base under the picture, where it holds tiles the picture would not show (a mosaic movie's
    # picture too: rolling_layout's name counts the base's tiles)
    base = lum_base(u, p, tiles, used)
    if len(used) > 1:
        colour = used
        acc = colour_planes(u, p, colour, tiles, rect, cache, ref, tag)
        rgba, used = colour_picture(u, p, colour, acc), colour
        if base:
            grey = filter_mosaic(u, p, LUM, tiles, rect, cache, None, tag)
            if mixes(u, p, tiles, colour):
                shape = rgba.shape[:2]
                rgba = unmixed(rgba, set_mask([set_times(shape, placed_tiles(u, p, _mine(u, p, visit_tiles(u, tiles, colour), f), rect, cache))
                                               for f in colour], p["k"]), grey)
            rgba = over_grey(rgba, grey, p["k"], p["display_scale"]["gamma"])
    elif base:
        rgba = filter_mosaic(u, p, LUM, tiles, rect, cache, None, tag)
    else:
        rgba = filter_mosaic(u, p, used[0], tiles, rect, cache, ref, tag)
    hdr = _mosaic_map(u, p, tiles, rect, used, base, rgba.shape, cache) if HDR_ON else None
    if sharpens(p["display_scale"]):
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * p["k"])
    im = Image.fromarray(rgba, "RGBA")
    s = min(out, CANVAS) / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    if hdr is not None:
        im.info["hdr"] = cv2.resize(hdr, im.size, interpolation=cv2.INTER_AREA)
    # the label counts the tiles of the filters the plan draws (its colour filters, or its grey one), taken so far
    # of all the pass takes, so its total stays the same while the grey mosaic turns to colour
    drawn = p["colour"] or [p["grey"]]
    # a mosaic movie counts laps: the lap is how many times the camera has come back to a place by tile n
    laps = {"kind": u.get("kind"), "lap": lap_of(u)[min(n, len(u["frames"]) - 1)] if u["frames"] else 1, "laps": u.get("repeats"), "places": len(set(x for x in u.get("place", []) if x is not None))}
    return im, {**laps, "mosaic": sum(count.get(f, 0) for f in drawn), "filters": len(used), "filter_names": used,
                "observation": u["key"][1], "pass": u["key"][3], "of": sum(1 for fr in u["frames"] if fr[2] in drawn),
                "fixed": p["fixed"], "luminance": bool(base), "width": im.width, "height": im.height}


def _mosaic_map(u, p, tiles, rect, used, base, shape, cache):
    """so_far's recovery map: the tiles of each filter it draws (and of its luminance base) placed as _over places
    them, the ones drawn under the picture first; None when no tile has a map"""
    try:
        k = p["k"]
        placed = []
        for f in ([LUM] if base else []) + list(used):
            mine = _mine(u, p, tiles, f)
            under = lambda t: partial(t) or bool(t.get("under")) or bool(t.get("long")) or bool(t.get("fill"))
            for t in [t for t in mine if under(t)] + [t for t in mine if not under(t)]:
                bx, by, bw, bh = t["box"]
                placed.append((f, _pic(u, cache, p["display_scale"], t), round((t["offset"][0] + bx - rect[0]) * k),
                               round((t["offset"][1] + by - rect[1]) * k), max(1, round(bw * k)), max(1, round(bh * k))))
        return hdr_map(placed, shape[1], shape[0])
    except Exception as e:
        print(f"No HDR map for the mosaic: {e}")
        return None


# the same layout, tile and size: named in the cache by folder and layout name (_mosaic_path)
so_far = _kept_for_next_size(so_far, lambda u, n, cache, made=None, out=OUT:
                             (drawn(u, cache), made[5], n, out) if made and out <= OUT else None)


def _footprint_file(u):
    return TRACK_FOOTPRINT_FILE if u.get("track") else FOOTPRINT_FILE


def _footprint_kept(u, rec):
    """The pass's movie footprint kept in its record rec, or None (a track's is kept apart: track_footprint)."""
    return None if rec is None else rec.get("track_footprint" if u.get("track") else "footprint")


def movie_footprint(u, cache, p=None):
    """The ground a movie's frames cover (x0, y0, x1, y1, reference pixels from the body's centre), from where SPICE
    put the tiles themselves rather than the geometry cache (which can be a third of a frame off by the end of a
    movie tracking a propeller): MOVIE_SAMPLES tiles spread over the pass, with MOVIE_MARGIN round them for the
    frames between. A feature track's is every tile at its steady place (track_places). Worked out once and kept
    with the pass."""
    p = p or plan(u, cache)
    rec = _kept_tiles(u, cache, p["display_scale"])
    if _footprint_kept(u, rec) is not None:
        return _footprint_kept(u, rec)
    path = os.path.join(folder(u, cache), _footprint_file(u))
    if os.path.exists(path):
        with open(path) as fh:
            fp = json.load(fh)
        if rec is not None:
            rec["track_footprint" if u.get("track") else "footprint"] = fp
        return fp
    track = track_places(u, cache, p) if u.get("track") else None
    n = len(u["frames"])
    picks = sorted({round(i * (n - 1) / max(1, MOVIE_SAMPLES - 1)) for i in range(MOVIE_SAMPLES)}) if n else []
    if track:
        picks = sorted(track)
    else:
        # (and every tile of the pass already made: its own place, where the geometry cache's can be tens of px off)
        there = _tiles(u, cache, p["display_scale"])
        picks = sorted(set(picks) | {j for j in range(n) if os.path.exists(os.path.join(there, f"{j}.json"))})
    boxes = []
    # the samples made side by side (MOVIE_WORKERS at once): a cold pass's first steady frame waits on them
    mode = calibration.mode()

    def one(j):
        with calibration.in_mode(mode):
            return tile(u, j, cache, p["display_scale"])
    with concurrent.futures.ThreadPoolExecutor(MOVIE_WORKERS) as pool:
        made = list(pool.map(one, picks))
    for t in made:
        if "offset" in t:
            ox, oy = track[t["n"]] if track else t["offset"]
            bx, by, bw, bh = t["box"]
            boxes.append((ox + bx, oy + by, ox + bx + bw, oy + by + bh))
    # every frame's own drawn box on the pass's axes (pass_boxes, from the geometry cache), so no frame between the
    # tiles made falls outside the footprint, with STEADY_REACH round it: the furthest stabilization moves a tile
    # from its SPICE place (and about what the geometry cache is off from the tiles' places at worst); a track's
    # footprint has every frame at its steady place (places the geometry cache does not know), with MOVIE_MARGIN
    # round it, as has a pass the geometry cache has none of
    own = None if track else pass_boxes(u)
    if own is not None:
        boxes.append((*own[:, :2].min(0), *own[:, 2:].max(0)))
    if boxes:
        m = MOVIE_MARGIN * FRAME if own is None else STEADY_REACH
        fp = [min(b[0] for b in boxes) - m, min(b[1] for b in boxes) - m, max(b[2] for b in boxes) + m, max(b[3] for b in boxes) + m]
        # the plan's footprint too where the frames' own boxes are not known (the geometry cache has none of them)
        g = p["footprint"]
        if not track and own is None:
            fp = [min(fp[0], g[0]), min(fp[1], g[1]), max(fp[2], g[2]), max(fp[3], g[3])]
    else:
        fp = list(p["footprint"])
    fp = [float(v) for v in fp]
    reel._cached(path, lambda: json.dumps(fp).encode())
    if rec is not None:
        rec["track_footprint" if u.get("track") else "footprint"] = fp
    return fp


TRACK_MAX = 0.1   # of a frame: the largest step between a track's frames that registration is believed for


def _every_tile(u, cache, p):
    """Every tile of the pass made (MOVIE_WORKERS at once), and pic(j): tile j's picture (the newest 16 read kept)."""
    mode = calibration.mode()

    def one(j):
        with calibration.in_mode(mode):
            return tile(u, j, cache, p["display_scale"])
    with concurrent.futures.ThreadPoolExecutor(MOVIE_WORKERS) as pool:
        made = list(pool.map(one, range(len(u["frames"]))))
    there, pics = _tiles(u, cache, p["display_scale"]), collections.OrderedDict()

    def pic(j):
        if j not in pics:
            path = os.path.join(there, f"{j}.png")
            with _lock:
                pics[j] = _made_pictures.get(path)
            if pics[j] is None:
                pics[j] = np.asarray(Image.open(path).convert("RGBA"))
            while len(pics) > 16:
                pics.popitem(last=False)
        return pics[j]
    return made, pic, there


def _chain(made, pic, there, believed, step, guide=None):
    """Each placed tile registered to the tile before it ({n: [x, y]} and how), the chain track_places and
    steady_places are made of. Tile n is put first where step(j, n) says it is from tile j's place, and registered
    there to the tile before it, or to the newest earlier tile of its own filter (another filter can look too
    different: a methane band after a continuum), by the pipeline's own alignment of a set's channels (_shift_onto,
    as C8 registers a pointing's filters); a shift of at most believed (reference pixels) moves it, otherwise it
    keeps step's place from the tile before it. step(places, j, n) reads the places made so far. The first tile keeps
    SPICE's place. guide(places, j, n, at): what the match is held to, {"around", "holes"} for _shift_onto and
    "reach", how far from the tile's own SPICE place the place found may be (steady_chain's: the pass's target as
    SPICE puts it); None: the whole overlap, no reach (track_places)."""
    places, hows, prev, newest = {}, {}, None, {}
    for t in made:
        n = t["n"]
        if "offset" not in t or not os.path.exists(os.path.join(there, f"{n}.png")):
            continue
        if prev is None:
            places[n], hows[n] = list(t["offset"]), "first"
        else:
            for j in dict.fromkeys(j for j in (prev, newest.get(t["filter"])) if j is not None):
                at = step(places, j, n)
                g = guide(places, j, n, at) if guide else {}
                shift, how = _shift_onto(made[j], pic(j), (0.0, 0.0), t, pic(n), (at[0] - places[j][0], at[1] - places[j][1]),
                                         around=g.get("around"), holes=g.get("holes", ()), kept=g.get("kept"))
                if shift is not None and math.hypot(*shift) <= believed:
                    found = [at[0] - shift[0], at[1] - shift[1]]
                    # (further from SPICE's own place than SPICE is ever off: what moved is not the target)
                    if g.get("reach") is not None and math.hypot(found[0] - t["offset"][0], found[1] - t["offset"][1]) > g["reach"]:
                        continue
                    places[n] = found
                    hows[n] = f"{how} to {j}"
                    break
            else:
                places[n], hows[n] = step(places, prev, n), f"held from {prev}"
        prev = n
        newest[t["filter"]] = n
    return places, hows


def _chained(u, cache, p, name, key, work):
    """A pass's chain kept with it (in the file name and its record's key): {n: [x, y]}, made by work() once."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    if rec is not None and rec.get(key) is not None:
        return rec[key]
    path = os.path.join(folder(u, cache), name)
    with _ulock(u):
        if rec is not None and rec.get(key) is not None:
            return rec[key]
        if not os.path.exists(path):
            places, hows, *more = work()
            data = json.dumps({"places": {str(n): [round(v, 2) for v in xy] for n, xy in places.items()}, "how": hows,
                               **(more[0] if more else {})})
            reel._cached(path, data.encode)
        with open(path) as fh:
            kept = {int(n): xy for n, xy in json.load(fh)["places"].items()}
        if rec is not None:
            rec[key] = kept
        return kept


def track_places(u, cache, p=None):
    """A feature track's steady places: {tile n: [x, y]}, where each placed tile's middle is drawn (reference pixels,
    in the place of its offset), so the feature the camera follows holds still from frame to frame. The camera
    follows a cloud the planet's turning carries along (FEATRAK, WIND5HR), so where SPICE puts each frame round the
    body's centre moves 150 px a frame and more, while what the frames show hardly moves in the frame itself. Each
    tile is registered to the tile before it (_chain), with the two frames' middles on one another: the shift found
    is how far the feature moved in the frame, and the tile's steady place is the earlier tile's moved by it. One
    that matches neither the tile before it nor the newest of its own filter is held where the tile before it is:
    the camera follows the feature, so SPICE's step between two frames is that following, the very motion a track
    takes out (taking it added up to 11,000 px over ISS_191SA_FEATRAK001's 360 frames, and WIND5HR003's filters
    jumped 60 to 160 px back and forth). So a colour set's filters land on one another too (they are taken one after
    another), and the first tile keeps SPICE's place. This is steady_places with SPICE's motion left out altogether
    (no smoothing back towards it). Worked out once over every tile of the pass and kept with it; {} with
    Settings > Processing's alignment off (SPICE's places)."""
    p = p or plan(u, cache)
    if not calibration.step("align"):
        return {}

    def work():
        made, pic, there = _every_tile(u, cache, p)
        # a track's tile starts where the tile before it is
        return _chain(made, pic, there, TRACK_MAX * FRAME, lambda places, j, n: list(places[j]))
    return _chained(u, cache, p, TRACK_FILE, "track", work)


STEADY_MAX = 0.05     # of a frame: the largest correction to SPICE's step between two frames that registration is believed for
STEADY_REACH = image_correction.FIT_REACH   # px: the furthest a stabilized tile may be from its own SPICE place (SPICE
                      # is 3 to 5 px off, 27 to 30 at worst between a set's filters); a match further off followed
                      # something else that moves, another moon crossing the frame (Sam 2026-11-04)
STEADY_PAD = 4        # px round another body's disk left out of a stabilization match (steady_chain)
STEADY_AROUND = 32    # px: half the least square round a small target a stabilization match is made on, and twice what
                      # is added round its disk (CENTRE_MARGIN): SPICE's few px off, the disk most of the square, so the
                      # match is the disk's own (on a square mostly sky the alignment takes it for a star field)
STEADY_SMOOTH = 12    # frames: Settings > Movie's stabilization smoothing by default (0: SPICE's places)
STEADY_MOST = 60      # frames: the most smoothing asked for
# a movie's stabilization chain (steady_chain), kept with the pass; renamed (with the movie frames drawn on it,
# movie_webp) whenever the rule changes
STEADY_FILE = "steady4-" + PLAN_FILE   # steady2: held on the target (steady_guide); steady3: seen_places;
                                       # steady4: seen_places not where another body touches the moon
# a small moon that SPICE places badly (Sam 2026-11-04: "see variance between frames that are close together and then
# if it's a certain amount ... just use visual frame alignment"): where the pictures show the moon
# (color_image.find_small_body) and SPICE's place of it jumps between neighbouring frames by more than STEADY_JUMPY (in
# more than STEADY_JUMPS of the pairs), or is off by more than STEADY_REACH over the pass (median), the stabilization
# takes the pictures' places of the moon instead of SPICE's (seen_places)
STEADY_JUMPY = 8.0    # px
STEADY_JUMPS = 0.1    # of the neighbouring pairs
STEADY_EDGE = 16     # px: a blob found nearer the tile's edge than its radius and this is not the moon (seen_places)
STEADY_SEEN = 0.5     # of the placed tiles: the least share the moon must be found on for the pictures to be believed


def steady_chain(u, cache, p=None):
    """Image stabilization of a movie pass: {tile n: [x, y]}, each placed tile registered to the tile before it with
    SPICE's step between the two as the starting guess. SPICE puts each frame on its own, from where the spacecraft
    and the camera were said to point, and the pointing is a few pixels off, differently from frame to frame: a
    movie of a body wobbles by that much (C8 lands a pointing's filters on one another only within REGISTER_MAX and
    SAME_PLACE). Here tile n starts where SPICE's step from tile j's place puts it (_chain) and the pipeline's
    alignment of a set's channels (_shift_onto) moves it onto tile j by what the pictures show, up to STEADY_MAX of a
    frame; a tile that matches neither keeps SPICE's step. The chain follows the pictures frame to frame, so it
    drifts away from SPICE slowly (each registration is a fraction of a pixel off): steady_places holds it to SPICE
    over longer spans. The matches are held on the pass's target as SPICE puts it (steady_guide): only round its disk,
    with every other body SPICE puts in the frames left out, and never further than STEADY_REACH from SPICE's own
    place, so a second moon in the picture (a mutual event, a moon crossing another) cannot pull the chain onto
    itself. Worked out once over every tile of the pass and kept with it; {} with Settings > Processing's alignment
    off."""
    p = p or plan(u, cache)
    if not calibration.step("align"):
        return {}

    def work():
        made, pic, there = _every_tile(u, cache, p)
        held, why = seen_places(u, made, pic, there)
        if held:
            # SPICE's places of a small moon replaced by where the pictures show it: the chain starts there, steps
            # by it, and is held to it (steady_places)
            made = [dict(t, offset=held[t["n"]]) if t["n"] in held else t for t in made]

        def step(places, j, n):
            # SPICE's step from tile j to tile n, from where tile j was put
            return [places[j][0] + made[n]["offset"][0] - made[j]["offset"][0],
                    places[j][1] + made[n]["offset"][1] - made[j]["offset"][1]]
        places, hows = _chain(made, pic, there, STEADY_MAX * FRAME, step, steady_guide(u))
        return places, hows, {"held": {str(n): [round(v, 2) for v in xy] for n, xy in held.items()}, "seen": why}
    return _chained(u, cache, p, STEADY_FILE, "steady", work)


def steady_held(u, cache, p=None):
    """{tile n: [x, y]}: what steady_places holds pass u's chain to, SPICE's place of each tile (its offset) or, where
    seen_places took the pictures' places of a small moon, those."""
    p = p or plan(u, cache)
    steady_chain(u, cache, p)
    path = os.path.join(folder(u, cache), STEADY_FILE)
    held = {}
    if os.path.exists(path):
        with open(path) as fh:
            held = {int(n): xy for n, xy in (json.load(fh).get("held") or {}).items()}
    return held


def seen_places(u, made, pic, there):
    """({tile n: [x, y]}, why) for a pass whose target is a small moon SPICE places badly, else ({}, why): each placed
    tile's place with the moon where its picture shows it. The moon is looked for in each tile near where SPICE puts it
    (color_image.find_small_body: the one compact lit blob the size of its disk; None for a crescent or a frame-cut
    moon near SPICE's place, a speck, or a disk filling the frame). SPICE is off from the picture by d = seen - SPICE in
    each tile it is found on; when d jumps by more than STEADY_JUMPY between neighbouring tiles in more than STEADY_JUMPS
    of the pairs, or is past STEADY_REACH over the pass (median), SPICE is not believed: a tile it is found on takes the
    picture's place, the others SPICE's moved by the nearest found tiles' d (between two, in proportion). On fewer than
    STEADY_SEEN of the tiles nothing is believed of the pictures (SPICE's places stand). why: what was measured."""
    if not u.get("z"):
        return {}, None
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    half = max(STEADY_AROUND, radius * (1 + CENTRE_MARGIN) + STEADY_AROUND / 2)
    if not (0 < radius and half < FRAME / 2):
        return {}, None
    placed = [t for t in made if "offset" in t and os.path.exists(os.path.join(there, f"{t['n']}.png"))]
    # (on a tile where SPICE puts another body against the moon, within STEADY_AROUND of touching it, the blob found
    # may be the other one, or the two together: Rhea over Titan, 154RH MUTUALEVE002, whose tiles 11 to 18 took
    # Titan for Rhea, 145 px off, and the movie swung from one moon to the other. There a blob is the moon only when
    # it is nearer SPICE's place of the moon than SPICE's place of every such body by STEADY_AROUND, SPICE's offsets
    # between bodies on one frame being right (its pointing moves them all); otherwise that tile takes the moon's
    # place from the tiles either side, as tiles it is not found on do)
    others = other_bodies(u)
    near = {n: [(x, y) for x, y, r, _ in bodies if math.hypot(x, y) < radius + r + STEADY_AROUND]
            for n, bodies in others.items()}
    near = {n: xy for n, xy in near.items() if xy}
    off, rejected = {}, []
    for t in placed:
        # (a tile's picture is in reference pixels, its corner at its place plus box; SPICE's target at 0)
        bx, by = t["box"][0], t["box"][1]
        im = pic(t["n"])
        got = color_image.find_small_body(im, -t["offset"][0] - bx, -t["offset"][1] - by, radius)
        if got is not None:
            # (not a blob against the tile's edge: a bright wedge where the picture's corner is cut, which Pan
            # ISS_264PN_PAN001_PIE's methane frames locked onto 860 px from the moon)
            inside = cv2.distanceTransform(np.pad(im[..., 3] > 0, 1).astype(np.uint8), cv2.DIST_L2, 3)[1:-1, 1:-1]
            yi, xi = min(int(got[1]), im.shape[0] - 1), min(int(got[0]), im.shape[1] - 1)
            if inside[max(yi, 0), max(xi, 0)] < radius + STEADY_EDGE:
                got = None
        if got is not None:
            d = (-(bx + got[0]) - t["offset"][0], -(by + got[1]) - t["offset"][1])
            # (d is the blob from SPICE's moon with the sign of a place: the blob sits at -d from it, the other body at
            # x, y from it)
            if any(math.hypot(-d[0] - x, -d[1] - y) < math.hypot(*d) + STEADY_AROUND for x, y in near.get(t["n"], ())):
                rejected.append(t["n"])
                continue
            off[t["n"]] = d
    looked = len(placed) - len(rejected)
    if not placed or len(off) < STEADY_SEEN * looked or len(off) < 2:
        return {}, {"found": len(off), "of": looked, "other body": len(rejected)}
    ns = sorted(off)
    jumps = [math.hypot(off[b][0] - off[a][0], off[b][1] - off[a][1]) for a, b in zip(ns, ns[1:])]
    jumpy = float(np.mean([j > STEADY_JUMPY for j in jumps]))
    far = float(np.median([math.hypot(*off[n]) for n in ns]))
    why = {"found": len(off), "of": looked, "other body": len(rejected), "jumpy": round(jumpy, 3), "off": round(far, 1),
           "most": round(max(jumps), 1)}
    if jumpy <= STEADY_JUMPS and far <= STEADY_REACH:
        return {}, why
    order = [t["n"] for t in placed]
    at = {n: i for i, n in enumerate(order)}
    idx = [at[n] for n in ns]
    dx = np.interp(range(len(order)), idx, [off[n][0] for n in ns])
    dy = np.interp(range(len(order)), idx, [off[n][1] for n in ns])
    return {n: [placed[i]["offset"][0] + float(dx[i]), placed[i]["offset"][1] + float(dy[i])]
            for i, n in enumerate(order)}, why


def other_bodies(u, names=False):
    """{tile n: [(x, y, r, behind)]} ([(name, x, y, r, behind)] with names): every body but its target that SPICE puts on tile n of pass u
    (bootleg_autonav.bodies_of, the geometry cache's bodies table), its centre from the target's centre and its radius,
    on the pass's axes (view_turn), in the pass's reference pixels (where the tiles are drawn: frames_seen's turn and scale), and whether it
    is further off than the target (behind it). Tiles whose frame the table has not
    worked out, or with no other body, are left out."""
    import bootleg_autonav as ba
    frames = u["frames"]
    got = ba.bodies_of([fr[1] for fr in frames if fr[7]])
    if not any(got.values()):
        return {}
    angles = reel.north_angles([fr[1] for fr in frames if fr[1] in got])
    turn = view_turn(u)
    out = {}
    for n, fr in enumerate(frames):
        if not got.get(fr[1]) or not fr[7]:
            continue
        x, y, fz = fr[5], fr[6], fr[7]
        a = math.radians(angles.get(fr[1], 0.0) - turn)
        c, sn, k = math.cos(a), math.sin(a), fz / u["z"]
        # (the body from the target on the camera's axes: the target is at -x, -y from the frame's middle)
        out[n] = [((name,) if names else ()) +
                  ((c * (bx + x) + sn * (by + y)) * k, (c * (by + y) - sn * (bx + x)) * k, r * k, bool(km and km > fz))
                  for name, bx, by, r, km in got[fr[1]]]
    return out


def steady_guide(u):
    """What steady_chain's matches are held to (_chain's guide): the pass's target as SPICE puts it. Each match is
    made only on the square round the target's disk (CENTRE_MARGIN round it and STEADY_AROUND / 2 more, at least
    STEADY_AROUND each way) when the disk is smaller than a frame, with every other body SPICE puts in either frame
    (other_bodies, STEADY_PAD round its disk, but for the target's own disk in front of one behind it) left out of
    both, and the place found must stay within STEADY_REACH
    of the tile's own SPICE place. A tile's target sits at minus its place, in _chain's match coordinates (tile j's
    middle at 0)."""
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]]) if u.get("z") else 0
    half = max(STEADY_AROUND, radius * (1 + CENTRE_MARGIN) + STEADY_AROUND / 2)
    small = 0 < radius and half < FRAME / 2
    others = other_bodies(u)

    def guide(places, j, n, at):
        cx, cy = -places[j][0], -places[j][1]
        holes = [(cx + x, cy + y, r + STEADY_PAD, back) for k in (j, n) for x, y, r, back in others.get(k, ())]
        return {"around": (cx, cy, half) if small else None, "holes": holes, "kept": (cx, cy, radius + 1),
                "reach": STEADY_REACH}
    return guide


def steady_places(u, cache, p=None, smooth=STEADY_SMOOTH):
    """Each placed tile's stabilized place ({n: [x, y]}, in the place of its offset): the chain (steady_chain)
    held to SPICE over smooth frames. SPICE's place is right on average and the chain is right frame to frame, so
    the place is the chain plus a Gaussian average (sigma smooth placed frames) of how far SPICE is from the
    chain: the wobble from one frame to the next comes out, the slow drift of the chain does not build up, and the
    body stays where SPICE puts it over the pass. smooth 0: SPICE's places ({}); the more smoothing, the longer
    the pictures are believed over SPICE. A feature track (track_places) is the same chain with no smoothing back
    to SPICE at all, since SPICE's motion there is the camera following the feature."""
    if smooth <= 0:
        return {}
    p = p or plan(u, cache)
    chain = steady_chain(u, cache, p)
    if not chain:
        return {}
    ns = sorted(chain)
    to = steady_held(u, cache, p)
    held = held_to_spice([to.get(n) or tile(u, n, cache, p["display_scale"])["offset"] for n in ns],
                         [chain[n] for n in ns], smooth)
    return {n: xy for n, xy in zip(ns, held)}


def _gaussian(values, smooth):
    """values (one row per frame) averaged with a Gaussian of sigma smooth frames, cut at 3 sigma, normalized at the ends."""
    i = np.arange(len(values), dtype=float)
    w = np.exp(-0.5 * ((i[:, None] - i[None, :]) / smooth) ** 2)
    w[np.abs(i[:, None] - i[None, :]) > 3 * smooth] = 0
    return (w @ np.asarray(values, float)) / w.sum(axis=1).reshape((-1,) + (1,) * (np.ndim(values) - 1))


def _gaussian_line(values, smooth):
    """values (one row per frame) smoothed over smooth frames: at each frame, a straight line fitted to the frames round
    it weighted by a Gaussian of sigma smooth (cut at 3 sigma), read at that frame. A plain Gaussian average would bend
    a steady drift or brightening at the ends of the pass (only the frames on one side are there); the line keeps it."""
    y = np.asarray(values, float)
    i = np.arange(len(y), dtype=float)
    dist = i[None, :] - i[:, None]
    w = np.exp(-0.5 * (dist / smooth) ** 2)
    w[np.abs(dist) > 3 * smooth] = 0
    s0, s1, s2 = w.sum(axis=1), (w * dist).sum(axis=1), (w * dist * dist).sum(axis=1)
    flat = y.reshape(len(y), -1)
    t0, t1 = w @ flat, (w * dist) @ flat
    det = s0 * s2 - s1 * s1
    # (one frame, or every weight on one frame: the plain average)
    ok = det > 1e-9 * np.maximum(s0 * s2, 1e-300)
    out = np.where(ok[:, None], (s2[:, None] * t0 - s1[:, None] * t1) / np.where(ok, det, 1)[:, None], t0 / s0[:, None])
    return out.reshape(y.shape)


def held_to_spice(spice, chain, smooth):
    """steady_places' math on its own (pure, so it can be ported to the viewer with a conformance test): the places of
    a pass's placed frames in order, [[x, y], ...], from SPICE's [[x, y], ...] and the registration chain's, the chain
    plus a Gaussian average over smooth frames of how far SPICE is from it, rounded to 1/100 px."""
    spice, chain = np.asarray(spice, float), np.asarray(chain, float)
    held = chain + _gaussian(spice - chain, smooth)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in held]


EXPOSURE_SMOOTH = 8      # frames: Settings > Movie's exposure smoothing by default (0: each frame as the pass's scale draws it)
EXPOSURE_MOST = 30       # frames: the most smoothing asked for
EXPOSURE_FLASH = 3       # frames: a brightness change lasting fewer frames than this (one frame bright, then back) is taken out
EXPOSURE_GAIN = 4.0      # the most a frame is brightened or dimmed by
EXPOSURE_LIT = 0.04      # of the brightest: the pixels a brightness is measured on (the body, not the sky's noise)
EXPOSURE_SIDE = 160      # px: the movie pictures a pass's brightness is measured on (exposure_chain) are this big
# a movie's brightness chain (exposure_chain), kept with the pass for each way of drawing it; renamed (with the movie
# frames drawn with it, movie_webp) whenever the rule changes
EXPOSURE_FILE = "exposure6-{}-" + PLAN_FILE   # exposure6: measured on movie-3's views (movie_footprint2, follow_view)
EXPOSURE_ROLL = 0.75     # of a stretch's slow drift past EXPOSURE_FREE: how much the rolling scale takes out (evened_gains)
EXPOSURE_FREE = 0.26     # log brightness (about 30% either way of the stretch's middle): slow drift kept as it is
EXPOSURE_RULE = 8        # the way the gains are worked out from the chain: in the movie frames' names (movie_webp)
EXPOSURE_GREY_RUN = 6    # frames: a colour pass's grey frames (its filters coming in) evened only in a run this long
EXPOSURE_SAME = 0.5      # of the larger lit area: two pictures sharing less lit view than this show different scenes


def _lit_level(a, gamma):
    """The linear brightness of a movie picture's part (RGBA): the median of its lit pixels, None when few are lit."""
    v = calibration.decode(a[..., :3].astype(np.float64).mean(axis=2)[a[..., 3] > 0] / 255, gamma)
    if v.size < 64:
        return None
    lit = v[v > EXPOSURE_LIT * max(float(np.percentile(v, 99.5)), 1e-6)]
    return float(np.median(lit)) if lit.size >= 64 else None


def _exposure_name(colour, centre, steady):
    return EXPOSURE_FILE.format(f"c{int(bool(colour))}{int(bool(centre))}s{steady}")


def exposure_chain(u, cache, p=None, colour=True, centre=True, steady=0):
    """How the movie's brightness steps from one picture to the next ({frame n: log brightness}): the pass is drawn on
    one display scale, so a frame whose exposure the calibration did not fully even out, a frame lit by stray light,
    a colour set after a grey frame or a filter brighter than the one before shows as a jump or a flash. What is
    measured is the movie itself: each frame's picture as movie_frame draws it (colour, centre, steady as asked; no
    trail, EXPOSURE_SIDE px), against the picture before it, over the part of the view both show (one view for the
    pass), as the ratio of the medians of the lit pixels in linear brightness; the chain adds up the logs. A pair with
    too little lit in common adds nothing (the same brightness); a held colour set is the same picture. The chain is
    cut into stretches ({n: [log, stretch, in colour]}) where the picture changes kind (grey frames before the colour set is
    complete, then colour; another set of filters) or scene (the two share less than EXPOSURE_SAME of their lit
    view: a narrow ring arc between two wide views): a step there is the picture changing, not its exposure, and
    exposure_gains evens each stretch on its own. Worked out once over every frame of the pass, for each way of
    drawing it, and kept with it."""
    p = p or plan(u, cache)
    gamma = p["display_scale"].get("gamma", 2.2)
    key = ("exposure", bool(colour), bool(centre), steady)

    def work():
        logs, hows, last, stretch = {}, {}, None, 0

        def lit(a):
            v = calibration.decode(a[..., :3].astype(np.float64).mean(axis=2) / 255, gamma)
            return (a[..., 3] > 0) & (v > EXPOSURE_LIT * max(float(np.percentile(v[a[..., 3] > 0], 99.5)) if (a[..., 3] > 0).any() else 0, 1e-6))
        for n in range(len(u["frames"])):
            # (the other bodies where each filter saw them, as before _per_body_planes: what it moves is a body's
            # copies, which the exposure was measured with, and the chain's stretches cut where a body's copies left
            # the picture, 154RH's first frames drawn at 0.63)
            im, rep = movie_frame(u, n, cache, 0, colour, out=EXPOSURE_SIDE, centre=centre, steady=steady, per_body=False)
            if im is None:
                continue
            a, kind = np.asarray(im), tuple(rep.get("color") or ())
            if last is None:
                logs[n], hows[n] = [0.0, stretch, bool(kind)], "first"
            else:
                j, b, was = last
                la, lb = lit(a), lit(b)
                shared = (la & lb).sum() / max(1, la.sum(), lb.sum()) if a.shape == b.shape else 0.0
                if kind != was or shared < EXPOSURE_SAME:
                    stretch += 1
                    logs[n], hows[n] = [0.0, stretch, bool(kind)], "another kind of picture" if kind != was else f"another scene ({shared:.2f} shared)"
                else:
                    logs[n], hows[n] = [logs[j][0], stretch, bool(kind)], f"same as {j}"
                    both = (a[..., 3] > 0) & (b[..., 3] > 0)
                    levels = [_lit_level(np.where(both[..., None], q, 0), gamma) for q in (b, a)]
                    if None not in levels and min(levels) > 0:
                        step = math.log(levels[1] / levels[0])
                        logs[n], hows[n] = [logs[j][0] + step, stretch, bool(kind)], f"{math.exp(step):.3f} x {j}"
            last = (n, a, kind)
        if _speck(u):
            # a pass of a speck (small_body on most of its frames): its pictures are sky with the body a dot, and the
            # sky's noise and stars are all a brightness chain measures; evening them pumped that noise up 4x frame to
            # frame (Kiviuq 112OT, Pallene 139PL once their stray-light veil went). Nothing to even: one level
            logs = {n: [0.0] + v[1:] for n, v in logs.items()}
            hows = {n: "a speck's pass: not evened" for n in hows}
        return logs, hows

    rec = _kept_tiles(u, cache, p["display_scale"])
    kept = (rec.get("exposure") or {}).get(key) if rec is not None else None
    if kept is not None:
        return kept
    path = os.path.join(folder(u, cache), _exposure_name(colour, centre, steady))
    with _ulock(u):
        if not os.path.exists(path):
            logs, hows = work()
            data = json.dumps({"logs": {str(n): [round(v[0], 5), v[1], v[2]] for n, v in logs.items()}, "how": hows})
            reel._cached(path, data.encode)
        with open(path) as fh:
            kept = {int(n): v for n, v in json.load(fh)["logs"].items()}
        if rec is not None:
            with _lock:
                rec["exposure"] = {**(rec.get("exposure") or {}), key: kept}
        return kept


def exposure_gains(u, cache, p=None, smooth=EXPOSURE_SMOOTH, colour=True, centre=True, steady=0):
    """Each movie frame's exposure gain ({n: gain}, on linear brightness, one for the whole picture so a colour set
    keeps its colour): the movie's brightness (exposure_chain) moved to the brightness of the frames round it
    (evened_gains), each stretch of one kind of picture and one scene on its own: a flash of a frame or two brought
    to its neighbours' level, a jump spread over smooth frames. A stretch shorter than EXPOSURE_FLASH frames is left
    as it is (gain 1: too short to tell a flash from the picture), and so is a run of fewer than EXPOSURE_GREY_RUN grey
    frames in a pass that plays in colour (each a filter of the set filling in, as bright as that filter is: in the
    UV aurora stares' four, evening them out only moved their steps onto their neighbours; COMPHILIT001's ten flicker
    filter to filter and are evened). Slow changes (a body coming into sunlight over the
    pass) stay; the frames' data stays, only scaled. smooth 0: no gains ({})."""
    if smooth <= 0:
        return {}
    # (measured once per pass on SPICE's places, whatever the stabilization: a few px of it hardly change which lit
    # pixels two pictures share, and one chain serves every smoothing, here and in the viewer)
    logs = exposure_chain(u, cache, p, colour, centre, 0)
    stretches = collections.defaultdict(list)
    in_colour = any(v[2] for v in logs.values())
    gains = {}
    for n in sorted(logs):
        stretches[logs[n][1]].append(n)
    for key, ns in list(stretches.items()):
        if in_colour and not logs[ns[0]][2] and len(ns) < EXPOSURE_GREY_RUN:
            gains.update((n, 1.0) for n in ns)
            del stretches[key]
    for ns in stretches.values():
        gains.update(zip(ns, evened_gains([logs[n][0] for n in ns], smooth) if len(ns) >= EXPOSURE_FLASH else [1.0] * len(ns)))
    return gains


def evened_gains(logs, smooth):
    """exposure_gains' math on its own for a movie's frames in order (pure, so it can be ported to the viewer with a
    conformance test): their log brightnesses (exposure_chain) in, each frame's gain out: flashes shorter than
    EXPOSURE_FLASH frames taken out by a running median, the rest smoothed with a Gaussian over smooth frames and put
    through the rolling scale (rolled), the gain the smoothed brightness over the frame's own, within EXPOSURE_GAIN either way, to 1/200 (the movie frame's lookup
    table is made once per gain)."""
    L = np.asarray(logs, float)
    h = EXPOSURE_FLASH // 2
    pad = np.concatenate([np.repeat(L[:1], h), L, np.repeat(L[-1:], h)])
    steady = np.array([np.median(pad[k:k + EXPOSURE_FLASH]) for k in range(len(L))])
    # (a line through the frames round each, so a pass brightening all through keeps its brightening at its ends)
    target = _gaussian_line(steady, smooth)
    target = rolled(target)
    return [round(float(np.clip(math.exp(want - own), 1 / EXPOSURE_GAIN, EXPOSURE_GAIN)) * 200) / 200
            for own, want in zip(L, target)]


def rolled(target):
    """The rolling scale on a stretch's smoothed log brightnesses (evened_gains): a scene that brightens or darkens steadily
    over the stretch (the first dive 271SA, dark polar cloud to the lit equator: five times brighter) keeps its drift
    within EXPOSURE_FREE of the stretch's middle (the mean), and past that EXPOSURE_ROLL of it is taken out, so the scale
    follows the scene instead of drawing its start dark and its end white. A stretch that stays within it is unchanged."""
    t = np.asarray(target, float)
    # (summed in order, as the page does)
    dev = t - sum(float(v) for v in t) / len(t)
    return t - EXPOSURE_ROLL * np.sign(dev) * np.maximum(np.abs(dev) - EXPOSURE_FREE, 0)


def steady_table(frame_id, cache, centre=True, colour=False):
    """What a browser needs to stabilize the pass frame_id is in by itself (web/cassini-os/src/steady-local.js): the
    pass's stabilization chain (steady_chain), each tile's SPICE place and box, and the movie's view (movie_rect)
    with its scale at OUT, so steady_places and the integer place _place draws a tile at are worked out in the page
    for any smoothing, and a movie frame drawn at SPICE's places (steady 0, the pre-built frames) is moved by the
    difference. "fixed": the view is the pass's whole (it does not follow the tile), the case where a single
    tile's frame moved by that difference is the frame drawn at its steady place; a pass whose view follows its
    frames, a feature track and a pass with Settings > Processing's alignment off answer {"local": false} (the
    server draws them). None when the frame is in no pass; {"working": true} while the chain is not worked out
    (the page asks the server for the stabilized frames meanwhile)."""
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    return _steady_table(*found, cache, centre, colour)


def _steady_table(u, n, cache, centre=True, colour=False):
    """steady_table for frame n of pass u. "exposure": the pass's brightness chain as the movie is drawn (colour,
    centre; the steady-0 chain exposure_gains evens for every smoothing) and what exposure_gains needs besides, so the page evens it for
    any smoothing; "local" false where the gain cannot be put on the drawn frame (a tile with a gain of its own);
    null while the chain is worked out (in the background). "detail": a filled pass, whose frames end in detail()
    ("sigma", "amount"): the page gains, mixes and trails the frames drawn without it (sharpen False) and sharpens
    them itself."""
    if u.get("track") or not calibration.step("align"):
        return {"local": False}
    rec = _record(u, cache)
    if not _steady_ready(u, cache, rec):
        warm_movie(u, n, 6, cache, steady=True)
        return {"working": True}
    p = plan(u, cache)
    chain = steady_chain(u, cache, p)
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    fp = movie_footprint(u, cache, p)
    seen = pass_seen(u) if centre else None
    ns = sorted(chain)
    if follows(fp, movie_rect(fp, {"offset": (0.0, 0.0)}, radius, centre, seen)):
        return {"local": False}   # (a view following the frame: the server draws it, follow_view)
    held = steady_held(u, cache, p)
    tiles = {n: tile(u, n, cache, p["display_scale"]) for n in ns}
    rect = movie_rect(fp, tiles[ns[0]], radius, centre, seen)
    how = (bool(colour), bool(centre), 0)
    exposure = None
    if _exposure_ready(u, cache, rec, how):
        logs = exposure_chain(u, cache, p, *how)
        exposure = {"local": all(tiles[m].get("gain", 1.0) == 1.0 for m in ns),
                    "logs": {str(m): v for m, v in logs.items()}, "gamma": p["display_scale"].get("gamma", 2.2),
                    "flash": EXPOSURE_FLASH, "gain": EXPOSURE_GAIN, "greyRun": EXPOSURE_GREY_RUN, "most": EXPOSURE_MOST,
                    "roll": EXPOSURE_ROLL, "free": EXPOSURE_FREE}
    else:
        warm_movie(u, n, 6, cache, exposure=how)
    tile_of = lambda j: tiles.get(j) or {}
    not_shown = lambda j: unfit(u["frames"], j, tile_of)
    # (colour on: the frames a pass playing its grey filter shows another frame of that filter for, step_frame)
    step, tint = {}, []
    for m in ns if colour else ():
        s, got, tinted = shown_of(u, p, m, not_shown, tile_of)
        if tinted:
            tint.append(m)   # (a frame drawn in its set's colour, set_shown: the server draws it, steady-local.html want)
        if not got and s != held_of([fr[2] for fr in u["frames"]], m, not_shown, holds(tile_of, not_shown)):
            step[str(m)] = s
    return {"local": True, "fixed": True, "ids": [fr[1] for fr in u["frames"]], "n": ns, "exposure": exposure,
            "partial": [m for m in ns if not_shown(m)], "over": [m for m in ns if over_exposed(tiles[m])], "step": step, "tint": tint,
            "sets": _colour_recipes(u, p, cache, ns, tiles) if colour and p.get("colour") else None,
            "eye": _eye_recipes(u, p, ns, tiles) if colour and p.get("colour") else None,
            "filters": [fr[2] for fr in u["frames"]], "trail_most": TRAIL,
            "chain": [chain[n] for n in ns], "spice": [held.get(n) or tiles[n]["offset"] for n in ns],
            "box": [tiles[n]["box"] for n in ns], "view": list(rect), "out": OUT, "k": OUT / max(rect[2], rect[3]),
            "colour": bool(p.get("colour")), "most": STEADY_MOST, "detail": sharpens(p["display_scale"]),
            "sigma": DETAIL_SIGMA * FRAME * OUT / max(rect[2], rect[3]), "amount": DETAIL, "knee": DETAIL_KNEE, "edge": DETAIL_EDGE}


def page_evens(u, cache, colour=True, centre=True):
    """True when a browser evens the exposure of pass u's movie by itself (steady-local.html want(), with Exposure
    normalization on, its default): the pass's steady table is local, its brightness chain is on frames with no gain of
    their own, and a colour pass mixes in natural colour (a false colour set is drawn by the server). Otherwise the
    window asks the server for its frames with exposure= (the pre-build makes them, prebuild.make_evened). Works the
    pass's chains out first when they are not made (steady_chain, exposure_chain)."""
    if u.get("track") or not calibration.step("align"):
        return False
    p = plan(u, cache)
    steady_chain(u, cache, p)
    exposure_chain(u, cache, p, colour, centre, 0)
    t = _steady_table(u, 0, cache, centre, colour)
    return bool(t.get("local") and (t.get("exposure") or {}).get("local")
                and not (colour and t.get("colour") and not t.get("sets")))


def one_white(tiles, scale):
    """{id(tile): gain} that puts a colour set's tiles drawn on a run of long exposures' white (tile_scale: their
    "white", pass_scale's "long") on the pass's white, when the set mixes them with tiles drawn on the pass's own;
    empty when its tiles share one white. A set mixing them came out in one filter's color: 263RI HIPHASE001
    (2017-03-04) alternates short and long exposures through each filter, and its sets took a 2 s RED frame (long
    white 0.086 I/F) with 0.1-0.18 s GRN and BL1 frames (pass white 0.31): RED drawn 3.6 times as bright, the rings
    pink. scale None: only whether they are mixed (a gain of 1 per long tile)."""
    long = [t for t in tiles if t.get("white")]
    if not long or len(long) == len(tiles):
        return {}
    white = (scale or {}).get("white")
    return {id(t): (t["white"] / white if white else 1.0) for t in long}


def _colour_recipes(u, p, cache, ns, tiles):
    """How movie_frame draws each frame of a colour pass, for the page: {"filters", "mix" (colour_picture's 3x3
    natural mix, or None to draw the filters straight), "gamma", "shoulder", "by": {frame n: the tiles of its colour
    set in the filters' order, or absent when the frame is drawn alone}}; None for a false colour pass (its mix
    blurs and balances the picture: drawn by the server). The set is the one movie_frame picks at SPICE's places."""
    want = p["colour"]
    scale = p["display_scale"]
    bal = scale.get("balance")
    mix = calibration.color_mix(u["key"][2], want, u["key"][0], [bal[f] for f in want] if bal else None, obs=u["key"][1])
    if isinstance(mix, calibration.FalseMix) or len(want) != 3:
        return None   # (two filters: the green of their mean, colour_picture's, is the server's too)
    return {"filters": list(want), "mix": None if mix is None else np.asarray(mix, float).tolist(),
            "gamma": scale.get("gamma", 2.2), "shoulder": calibration.SHOULDER, "by": _colour_by(u, want, ns, tiles, p["grey"])}


def _colour_by(u, want, ns, tiles, grey):
    """{frame n: the tiles of its colour set in the filters' order} for the frames of ns drawn as a set (set_shown, the
    set movie_frame picks at SPICE's places; a frame drawn in its set's colour is left to the server, the steady
    table's "tint"); none when the pass plays its grey filter (plays_colour; grey: its plan's)."""
    by, placed = {}, set(ns)
    if not plays_colour(u, want, grey):
        return by
    not_shown = lambda j: j in placed and unfit(u["frames"], j, lambda i: tiles.get(i) or {})
    for n in ns:
        covers = lambda got: set_cover(tiles[n], [tiles[j] for j in got.values()]) >= HELD_COVER
        got, tinted = set_shown(u, n, want, not_shown, lambda j: j in placed, covers)
        if got and not tinted and not one_white([tiles[j] for j in got.values()], None):
            # (a set whose frames are drawn on two whites is evened by the server: one_white)
            by[str(n)] = [got[f] for f in want]
    return by


def _eye_recipes(u, p, ns, tiles):
    """How the page draws each frame of a colour pass in natural color emulation (Settings > Filter colors >
    Natural color (emulated), calibration.eye_mix), the same shape as _colour_recipes: {"filters", "mix" (the set's
    3x3 eye mix, or for a true color set its natural mix), "gamma", "shoulder", "by"}, for false color passes too: the
    eye mix is one matrix on the planes, what colour_picture draws with colors=eye. A two-filter set lists its longer
    filter's tile twice (colour_picture's green, their mean, has no weight in the eye mix), so the page mixes three
    planes as for any set. None when the set's filters have no eye mix."""
    want = p["colour"]
    if len(want) not in (2, 3):
        return None
    with calibration.coloring("eye"):
        mix = calibration.color_mix(u["key"][2], want, u["key"][0], obs=u["key"][1])
    if mix is None:
        return None
    by = _colour_by(u, want, ns, tiles, p["grey"])
    if len(want) == 2:
        by = {n: [a, a, b] for n, (a, b) in by.items()}
    return {"filters": list(want), "mix": np.asarray(mix, float).tolist(),
            "gamma": p["display_scale"].get("gamma", 2.2), "shoulder": calibration.SHOULDER, "by": by}


def movie_rect(fp, t, radius=0.0, centre=False, seen=None):
    """The view of a pass played as a movie (x0, y0, w, h in reference pixels from the body's centre): its whole
    footprint fp (movie_footprint) when that is at most MOVIE_FIT frames across, so the body holds still while the
    pointing wanders; otherwise a window MOVIE_FIT frames across centred on frame t, kept inside fp (a creeping
    ring or limb movie moves along), which movie_frame draws as the frame itself (follow_view). Either way one size
    for the whole pass, so the picture never rescales.
    centre: a square view centred on the body (radius: its disk, reference pixels), at least a frame or the disk with
    CENTRE_MARGIN round it and wide enough for what the frames show round it (fitted_half: a stare's rings stay in,
    a frame's corners turned north up do not widen it), up to MOVIE_FIT frames, when centre_half centres the pass (seen: its frames, pass_seen): the body sits in the
    middle of every frame, north up. A body bigger than that, one no frame looks at (a ring movie on both ansae, a
    plume stare above the limb) or a pass the square would cut (a mosaic or retarget reaching further) keeps the
    view above. All of it decided once for the pass (fp, radius and seen are the pass's)."""
    x0, y0, x1, y1 = fp
    side = MOVIE_FIT * FRAME
    half = centre_half(fp, radius, seen) if centre else None
    if half:
        return -half, -half, 2 * half, 2 * half
    if max(x1 - x0, y1 - y0) <= side:
        return x0, y0, x1 - x0, y1 - y0
    w, h = min(x1 - x0, side), min(y1 - y0, side)
    cx, cy = t["offset"]
    return min(max(cx - w / 2, x0), x1 - w), min(max(cy - h / 2, y0), y1 - h), w, h


def centre_half(fp, radius, seen):
    """Half the side of the square view centred on the body that movie_rect uses (reference pixels), or None when
    the body is not centred. It is centred when all three hold: its disk (radius) fits MOVIE_FIT frames with
    CENTRE_MARGIN round it; the body's centre is on at least one of the pass's frames (seen, pass_seen: the frames
    look at the body, not only round it, as a ring movie on both ansae does, whose footprint fp takes in Saturn's
    centre though no frame shows it); and the square, round the whole footprint up to MOVIE_FIT frames, keeps
    CENTRE_KEEP of the frames' area and part of every frame (a mosaic or retarget reaching further than that is not
    cut down to it, nor a stray frame dropped from the picture). The view is then drawn no bigger than what the
    frames show needs (fitted_half)."""
    x0, y0, x1, y1 = fp
    side = MOVIE_FIT * FRAME
    around = max(FRAME, 2 * radius * (1 + CENTRE_MARGIN))
    if not (radius > 0 and around <= side and seen and seen[0]):
        return None
    wide = min(side, max(around, 2 * max(-x0, x1, -y0, y1))) / 2
    inside = kept(seen, wide)
    if not (inside.mean() >= CENTRE_KEEP and inside.any(1).all()):
        return None
    return fitted_half(seen, around / 2, wide)


def fitted_half(seen, least, most):
    """How big a centred view is drawn (Sam 2026-11-03: the pictures looked zoomed out, the body a quarter of the
    window): half the side of the smallest square round the body's centre, from least (a frame, or the disk with
    CENTRE_MARGIN round it) to most (the whole footprint, centre_half's test), that keeps CENTRE_KEEP of what the
    frames show within the circle across each frame (SEEN_DISK of its seen points) and part of every frame. The
    corners of a frame turned north up swing out past a frame-wide square however the camera points (a frame turned
    45 degrees spans 1.41 frames), and MOVIE_MARGIN pads the footprint for the frames between its samples: sized to
    the footprint, a one-place moon movie was drawn about 1.9 frames across, half the size its single pictures
    (one frame, centre_view) show it at. The circle is the same however the frame is turned, so the view is a
    frame wide for frames on the body, and wider only as far as the pointing wanders off it."""
    pts = seen[1].reshape(-1, SEEN_GRID * SEEN_GRID, 2)[:, SEEN_DISK]
    need = np.abs(pts).max(2)   # the half side of the square round the body's centre each point needs to be in
    if not need.size:
        return most
    # the CENTRE_KEEP share of the points, and the nearest point of every frame
    share = float(np.quantile(need, CENTRE_KEEP, method="inverted_cdf"))
    return float(min(most, max(least, share, need.min(1).max())))


_g = (np.arange(SEEN_GRID) + 0.5) / SEEN_GRID - 0.5
SEEN_DISK = (np.add.outer(_g ** 2, _g ** 2) <= 0.25).ravel()   # a frame's seen points within the circle across it
del _g


def kept(seen, half):
    """Which of each frame's points (seen, pass_seen) the square of half side half round the body's centre keeps:
    one row of SEEN_GRID x SEEN_GRID per frame."""
    return (np.abs(seen[1]) <= half).all(1).reshape(-1, SEEN_GRID * SEEN_GRID)


def kept_share(seen, half):
    """The share of the frames' area (seen, pass_seen) inside the square of half side half round the body's centre."""
    return float(kept(seen, half).mean()) if len(seen[1]) else 0.0


def frames_seen(frames, z, turn=0.0):
    """What centre_half needs of a pass's frames (units' (path, id, filter, t, nm, x, y, fz) tuples; z, the pass's
    reference distance), from the geometry cache: (on, points). on: the body's centre is on at least one frame
    (find_target's shift, from the body's centre to the frame's middle, inside the frame). points: SEEN_GRID x
    SEEN_GRID points spread evenly over each placed frame, turned north up by the frame's own angle as the tiles are
    and put where the frame sits round the body's centre (reference pixels), so the share of the frames' area a
    view keeps is the share of the points in it. None when SPICE places none of the frames. turn: the axes the pass is
    drawn on (view_turn: its own orientation, short of north up)."""
    g = ((np.arange(SEEN_GRID) + 0.5) / SEEN_GRID - 0.5) * FRAME
    gx, gy = (a.ravel() for a in np.meshgrid(g, g))
    on, pts = False, []
    for fr, put in _on_axes(frames, z, turn):
        on = on or (abs(fr[5]) <= FRAME / 2 and abs(fr[6]) <= FRAME / 2)
        pts.append(np.stack(put(gx, gy), 1))
    return (on, np.concatenate(pts)) if pts else None


def _on_axes(frames, z, turn):
    """(frame, put) for each placed frame of frames (units' tuples; z, the pass's reference distance; turn, view_turn):
    put(dx, dy) takes points dx, dy from the frame's middle on the camera's axes to where they are drawn round the
    body's centre (reference pixels), turned by the frame's own angle less turn as cv2.getRotationMatrix2D turns its
    tile (label_handler.middle_rotation) and scaled to the pass's distance (frames_seen, frames_boxes)."""
    placed = [fr for fr in frames if fr[7]]
    angles = reel.north_angles([fr[1] for fr in placed]) if placed else {}
    for fr in placed:
        x, y, fz = fr[5], fr[6], fr[7]
        a = math.radians(angles.get(fr[1], 0.0) - turn)
        c, s, k = math.cos(a), math.sin(a), fz / z

        def put(dx, dy, x=x, y=y, c=c, s=s, k=k):
            px, py = x + dx, y + dy
            return (c * px + s * py) * k, (c * py - s * px) * k
        yield fr, put


_seen = {}   # pass key -> pass_seen's answer


def pass_seen(u):
    """frames_seen of pass u's frames at its reference distance, worked out once for the pass."""
    key = (u["key"], len(u["frames"]))
    with _lock:
        if key in _seen:
            return _seen[key]
    got = frames_seen(u["frames"], u["z"], view_turn(u)) if u.get("z") else None
    with _lock:
        if len(_seen) >= UNIT_OF_KEEP // 100:
            _seen.clear()
        _seen[key] = got
    return got


def frames_boxes(frames, z, turn=0.0):
    """Each placed frame's own box as the pass draws it (units' (path, id, filter, t, nm, x, y, fz) tuples; z, the
    pass's reference distance; turn, view_turn): the four corners of the frame, turned by its own angle less the
    pass's and scaled to the pass's distance as its tile is (frames_seen's points), put where the frame sits round
    the body's centre: an array of (x0, y0, x1, y1) rows, reference pixels. None when SPICE places none of them."""
    cx, cy = np.array([-1, 1, 1, -1]) * FRAME / 2, np.array([-1, -1, 1, 1]) * FRAME / 2
    out = []
    for _, put in _on_axes(frames, z, turn):
        X, Y = put(cx, cy)
        out.append((X.min(), Y.min(), X.max(), Y.max()))
    return np.array(out, float) if out else None


_boxes = {}   # pass key -> pass_boxes's answer


def pass_boxes(u):
    """frames_boxes of pass u's frames at its reference distance on its own axes, worked out once for the pass."""
    key = (u["key"], len(u["frames"]))
    with _lock:
        if key in _boxes:
            return _boxes[key]
    got = frames_boxes(u["frames"], u["z"], view_turn(u)) if u.get("z") else None
    with _lock:
        if len(_boxes) >= UNIT_OF_KEEP // 100:
            _boxes.clear()
        _boxes[key] = got
    return got


def follows(fp, rect):
    """True when a movie's view rect (movie_rect) follows the frame: its footprint fp is wider than MOVIE_FIT frames
    and the view is not centred on the body."""
    x0, y0, x1, y1 = fp
    return max(x1 - x0, y1 - y0) > MOVIE_FIT * FRAME and not (rect[0] == -rect[2] / 2 and rect[1] == -rect[3] / 2)


FOLLOW_SLACK = 2   # px: a following frame is drawn this much bigger than the picture and its middle cut out, so its
#                    edges (placed to the nearest pixel, then turned) never show a part-transparent row (_unturn)


def follow_view(u, s, t, out, pic=None):
    """How a movie that follows the frame (follows: a creeping ring or limb movie, a close-up sweeping across a
    planet) draws frame s (its tile t, at its place) out px across: the frame as Cassini took it, filling the picture
    (Sam 2026-11-08: a 271SA close-up sweep was drawn in a window two frames across, the frame a quarter of it and
    turned 24 degrees by the pass's roll, black round it). (rect, k, turn): the square round the frame turned by turn
    (degrees: its own angle less the pass's, view_turn, the turn its tile was drawn with) and k canvas px per reference
    px, FOLLOW_SLACK px more than out across the frame, which _unturn turns back and cuts to it. A frame the geometry
    cache has no angle for takes the turn its tile shows (pic: the tile's picture path, _drawn_turn)."""
    fz = u["frames"][s][7] if 0 <= s < len(u["frames"]) else 0
    side = FRAME * (fz / u["z"] if fz and u.get("z") else 1.0)
    own = reel.north_angles([t["id"]]).get(t["id"])
    vt = view_turn(u)
    if own is None and pic:
        own = _drawn_turn(pic) + vt   # (the turn its tile shows, on the pass's axes)
    # turned back by its roll, not its quarter: the frame square, a whole quarter (square_turn) from the camera's frame,
    # so it faces as the pass's other pictures do (north within 45 degrees of the top); drawn own - vt, square on its
    # own own - square_turn, so turned back by the difference
    axes = view_axes(u) if own is not None else None
    turn = 0.0 if own is None else wrapped(square_turn(own, quarter_of(vt, own if axes is None else axes)) - vt)
    a = math.radians(turn)
    big = side * (abs(math.cos(a)) + abs(math.sin(a)))
    cx, cy = t["offset"]
    return (cx - big / 2, cy - big / 2, big, big), (out + FOLLOW_SLACK) / side, turn


def _drawn_turn(path):
    """The turn (degrees, within 45 of none) a tile's picture at path was drawn with: the angle of the smallest
    rectangle round its drawn part. 0.0 when it cannot be read."""
    try:
        a = np.asarray(Image.open(path))[..., -1]
        pts = cv2.findNonZero((a > 127).astype(np.uint8))
        if pts is None or len(pts) < 16:
            return 0.0
        r = cv2.minAreaRect(pts)[2]
    except (OSError, IndexError, ValueError, cv2.error):
        return 0.0
    # (a rectangle's angle is known only up to a quarter turn: the one nearest none; drawn counter clockwise as
    # cv2.getRotationMatrix2D turns it, minAreaRect's angle runs the other way)
    return float(-((r + 45.0) % 90.0 - 45.0))


def follow_middle(t, rect, k):
    """Where tile t's middle is drawn on a canvas of view rect (k px per reference px), in pixel coordinates (cv2's:
    pixel i's centre at i), as _place puts it."""
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    return left + max(1, round(bw * k)) / 2 - 0.5, top + max(1, round(bh * k)) / 2 - 0.5


def _unturn(a, turn, middle, w, h):
    """Picture a (H x W [x C] array) drawn on a pass's axes, turned back by turn degrees about middle (the frame's
    middle, follow_middle: the turn follow_view took out) and cut to the w x h round it: the frame on its own axes."""
    H, W = a.shape[:2]
    cx, cy = middle
    if turn:
        m = cv2.getRotationMatrix2D((cx, cy), -turn, 1.0)
        a = cv2.warpAffine(a, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    x0, y0 = int(round(cx + 0.5 - w / 2)), int(round(cy + 0.5 - h / 2))
    x0, y0 = min(max(0, x0), max(0, W - w)), min(max(0, y0), max(0, H - h))
    return np.ascontiguousarray(a[y0:y0 + h, x0:x0 + w])


RING_REACH = 140500   # km from Saturn's centre: the F ring's outer edge; a Saturn pass whose frames reach this far shows
                     # Saturn's rings, which take Saturn's north as their up (body_in_view)


def body_in_view(target, cam, places):
    """True when a frame of places ((x, y, fz) each: find_target's shift that centres the body, full resolution
    pixels, and the frame's distance in km) shows its target: the body's disk (RADIUS), for Saturn its rings
    (RING_REACH), reaches into the frame, or for a body of no known size its centre is on the frame."""
    if not target:
        return False
    r_km = RING_REACH if target == "SATURN" else RADIUS.get(target, 0)
    for x, y, fz in places:
        r = r_km / (fz * IFOV.get(cam, IFOV["N"])) if fz else 0.0
        dx, dy = max(abs(x) - FRAME / 2, 0.0), max(abs(y) - FRAME / 2, 0.0)
        if dx * dx + dy * dy <= r * r:
            return True
    return False


def pass_turn(u=None, frame_id=None, target=None, cam=None):
    """The pass's orientation (degrees, as reel.north_angles: the turn that would put celestial north up), which
    every picture of the pass (a camera window's still, a movie's or mosaic's tile) is turned short of
    (color_image.processed_frame's turn). Every picture of a pass is drawn on the same axes, so a pass the camera
    does not roll under keeps the square frame as Cassini took it, corners and all, and one it rolls under turns
    only by how far the camera rolled from the pass's average (Sam 2026-11-08: pictures came out tilted a few
    degrees with their corners cut). The canvas of a pass is then the sky turned by this much: everything worked out
    on it (frames_seen, other_bodies, hold_of, footprint, surface_field) takes it out of the frames' own turns.
    Those axes are the camera's own (the circular mean m of the turns of pass u's placed frames, or frame_id's own
    turn for a frame in no pass) turned by the quarter turn (0, 90, 180 or 270 degrees) that brings north closest to
    the top: m less the multiple of 90 nearest it, so a picture is never turned more than 45 degrees from north up
    and never by an angle that cuts its corners (Sam 2026-11-08: square, untilted pictures, but many planets and moons
    came out sideways). North is SPICE's celestial north; the Saturn system's bodies and rings have their north within
    about 7 degrees of it, Jupiter within about 25. A pass that shows no body (body_in_view: sky, stars, a target
    off the frames) keeps the camera's axes (m). 0.0 (north up) when the geometry cache has none of its frames.
    target, cam: frame_id's (from the index when not given)."""
    if u:
        placed = [fr for fr in u["frames"] if fr[7]]
        places = [(fr[5], fr[6], fr[7]) for fr in placed]
        ids = [fr[1] for fr in placed]
        target, cam = (u.get("key") or (None, None, None))[0], (u.get("key") or (None, None, None))[2]
    else:
        ids = [frame_id]
        g = reel.geometry([frame_id]).get(frame_id)
        places = [tuple(g[:3])] if g and g[2] else []
        if target is None:
            try:
                idx, row = _row_of()
                r = idx.iloc[row[frame_id]]
                target, cam = r["TARGET_NAME"], "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W"
            except Exception:   # noqa: BLE001  (no index, or a frame not in it: no body known)
                target = None
    m = mean_turn(ids)
    if m is None:
        return 0.0
    if not body_in_view(target, cam, places):
        return m
    return round(m - 90.0 * round(m / 90.0), 2)


def mean_turn(ids):
    """The camera's own axes over the frames ids: the circular mean of their turns (reel.north_angles, degrees,
    rounded to 0.01), None when the geometry cache has none of them."""
    angles = list(reel.north_angles(list(ids)).values())
    if not angles:
        return None
    a = np.radians(angles)
    return round(float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean()))), 2)


ROLL_SQUARE = 5.0   # degrees: a frame the camera rolled further than this from its pass's axes is shown on its own
                    # (a still, a movie following the frame) square, turned a whole quarter (frame_quarter), not by
                    # its roll (Sam 2026-11-08: 271SA HIRESWACS001 rolls 70 degrees; its stills came out 24 off)


def wrapped(a):
    """a degrees as -180 to 180"""
    return (a + 180.0) % 360.0 - 180.0


def frame_quarter(own, q):
    """The quarter turns (0 to 3) a frame of turn own (reel.north_angles) is drawn by when shown square on its own:
    its pass's q (quarter_of) while that keeps north within 45 degrees of the top, else the quarter nearest north up
    for the frame itself, so a rolling pass changes quarter only where it has to."""
    if abs(wrapped(own - 90.0 * q)) <= 45.0:
        return q % 4
    return int(round(own / 90.0)) % 4


def square_turn(own, q):
    """The turn (degrees, -180 to 180, as processed_frame's turn) that draws a frame of turn own square on its own:
    a whole frame_quarter(own, q) quarters from the camera's frame."""
    return round(wrapped(own - 90.0 * frame_quarter(own, q)), 2)


def quarter_of(turn, m):
    """The quarter turns (0 to 3, counter clockwise) a pass drawn turn degrees short of north up turns its frames by
    from the camera's own axes m (pass_turn's circular mean)."""
    return int(round((m - turn) / 90.0)) % 4


def view_shown(view):
    """Auto center draws the still for view (centre_view's answer): centred, placed where it is on the pass's axes,
    or turned a whole quarter ("quarter", which may be 0 for the pass); otherwise the picture is shown as it is."""
    return bool(view and (view.get("centre") or view.get("north") or view.get("quarter") is not None))


_view_turns = {}   # pass key -> view_turn's answer


def view_turn(u):
    """pass_turn of pass u, worked out once for the pass (every tile of it is drawn on these axes)."""
    if not u.get("key"):
        return pass_turn(u)
    key = (tuple(u["key"]), len(u["frames"]))
    with _lock:
        hit = _view_turns.get(key)
    if hit is None:
        hit = pass_turn(u)
        with _lock:
            if len(_view_turns) > 100000:
                _view_turns.clear()
            _view_turns[key] = hit
    return hit


_view_axes = {}   # pass key -> view_axes's answer


def view_axes(u):
    """mean_turn of pass u's placed frames (the camera's own axes), worked out once for the pass."""
    key = (tuple(u.get("key") or ()), len(u["frames"]))
    with _lock:
        if key in _view_axes:
            return _view_axes[key]
    got = mean_turn([fr[1] for fr in u["frames"] if fr[7]])
    if u.get("key"):
        with _lock:
            if len(_view_axes) > 100000:
                _view_axes.clear()
            _view_axes[key] = got
    return got


_centre_views = {}   # pass key -> centre_view's decision for it
_centre_of = {}      # frame id -> centre_view's answer, for a frame SPICE places (a request per picture asks)


def centre_view(frame_id):
    """Auto center for a picture shown on its own (a frame or a color composite) in the camera windows: the rule
    of a movie centred on its body (centre_half), decided once for the pass the frame is in, from the geometry
    cache's footprint of the pass (_box), so a pass is centred all through or not at all. A frame in no pass is its
    own pass. Each picture keeps its frame's own scale: the view is one frame (FRAME full resolution pixels) square
    round the body, so the picture is the size it is today, only moved so the body is in the middle (a movie's view
    is the pass's, movie_rect). Answers {"centre": True, "side": FRAME, "radius": ..., "pass": [...]}, or
    {"centre": False, "north": True, "side": FRAME, "why": ...} for a close-up (frames on a body too big for the
    view): placed where it is on the pass's axes, so the surface holds still; both with "turn" (pass_turn: the
    pass's axes, the camera's own turned the quarter that brings north closest to the top, so each still is turned
    only by that quarter and how far the camera rolled during the pass); {"centre": False, "why": ...} for a ring,
    spoke or sky pass (Cassini kept those upright in the camera) or a frame SPICE has no place for, which keep the
    picture as it is, or, for such a pass that shows its body or Saturn's rings, {"centre": False, "quarter": q,
    "side": FRAME, "turn": ...}: the picture turned by the pass's quarter turn alone (q quarters counter clockwise),
    as the pass's movie and mosaic face (view_shown says which views draw a still)."""
    with _lock:
        hit = _centre_of.get(frame_id)
    if hit is not None:
        return dict(hit)
    idx, row = _row_of()
    q = row.get(frame_id)
    if q is None:
        return {"centre": False, "why": "not in the index"}
    g = reel.geometry([frame_id]).get(frame_id)
    if not g or not g[2]:
        # (not kept: the geometry cache may place the frame later)
        return {"centre": False, "why": "SPICE has no place for the frame"}
    found = unit_of(frame_id)
    if found:
        u = found[0]
        key, target, cam, z = u["key"], u["key"][0], u["key"][2], u["z"]
    else:
        r = idx.iloc[q]
        target, cam, z = r["TARGET_NAME"], "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W", g[2]
        key = (target, frame_id, cam)
    with _lock:
        hit = _centre_views.get(key)
    if hit is None:
        radius = RADIUS.get(target, 0) / (z * IFOV[cam])
        fp = _box(u, z) if found else (-g[0] - HALF, -g[1] - HALF, -g[0] + HALF, -g[1] + HALF)
        turn = view_turn(u) if found else pass_turn(frame_id=frame_id, target=target, cam=cam)
        seen = (pass_seen(u) if found else frames_seen([(None, frame_id, None, None, None, *g)], z, turn)) \
            if fp and radius else None
        half = centre_half(fp, radius, seen) if fp and radius else None
        hit = {"centre": bool(half), "pass": [str(v) for v in key]}
        if not half:
            hit["why"] = "no disk of a known body that fits the view" if not radius else \
                "the body is too big for the view, no frame looks at its centre, or a view centred on it would cut the frames"
            # north up where it is only when the frames are on the body's disk (a close-up): the body's surface
            # then holds still. Off the disk (rings, sky) Cassini rolled to keep the scene upright in the camera,
            # so the camera's own orientation is the steady one and north up would turn it frame to frame
            boxes = [(-x * fz / z - HALF, -y * fz / z - HALF, -x * fz / z + HALF, -y * fz / z + HALF)
                     for *_, x, y, fz in u["frames"] if fz] if found else [fp]
            # most of the pass's frames, each on its own (an arcing ring scan's footprint can clip the disk though
            # none of its frames is on it)
            on = sum(_on_disk(b, radius) for b in boxes) if radius else 0
            hit["north"] = bool(boxes) and on * 2 > len(boxes)
        # each still drawn on the pass's axes (pass_turn: the camera's own, turned the quarter that brings north
        # closest to the top), turned only by how far the camera rolled from them
        hit["turn"] = turn
        axes = view_axes(u) if found else mean_turn([frame_id])
        if axes is not None:
            hit["axes"] = axes   # the camera's own axes over the pass (mean_turn)
        places = [(fr[5], fr[6], fr[7]) for fr in u["frames"] if fr[7]] if found else [tuple(g[:3])]
        if not half and not hit.get("north") and axes is not None and body_in_view(target, cam, places):
            # a ring or spoke pass, or sky beside its body (the camera's own orientation is the steady one): each
            # still turned by a whole quarter only (square_turn: the pass's, so they face as its movie and mosaic
            # do, unless the camera rolled north past 45 degrees from the top); a sky pass that shows no body is
            # shown as it is
            hit["quarter"] = quarter_of(hit["turn"], axes)
        with _lock:
            _centre_views[key] = hit
    # the frame's own disk of the body (full resolution pixels), so centred knows whether the frame cuts it
    if hit["centre"]:
        hit = dict(hit, side=FRAME, radius=RADIUS.get(target, 0) / (g[2] * IFOV[cam]))
    else:
        hit = dict(hit, side=FRAME) if hit.get("north") else dict(hit)
        if hit.get("quarter") is not None:
            # turned by a whole quarter alone, so its roll stays as the camera had it. A frame that needs no turn (it
            # already has north toward the top) or has no turn of its own is shown as it is, as this frame only
            # ("frame": the page keeps asking for the pass's other stills)
            own = reel.north_angles([frame_id]).get(frame_id)
            turn = square_turn(own, hit["quarter"]) if own is not None else None
            if turn is None or frame_quarter(own, hit["quarter"]) == 0:
                hit = {k: v for k, v in hit.items() if k != "quarter"}
                hit.update(frame=True, why="this picture already has north toward the top" if turn is not None
                           else "SPICE has no turn for this picture")
            else:
                hit = dict(hit, side=FRAME, turn=turn)
    rolled = None
    if (hit.get("centre") or hit.get("north")) and hit.get("axes") is not None:
        # a frame the camera rolled more than ROLL_SQUARE from the pass's axes: its still square on its own, a whole
        # quarter (square_turn) from the camera's frame, not tilted by its roll (it no longer holds with the pass)
        own = reel.north_angles([frame_id]).get(frame_id)
        if own is not None and abs(wrapped(own - hit["axes"])) > ROLL_SQUARE:
            rolled = square_turn(own, quarter_of(hit["turn"], hit["axes"]))
    # a north-up pass's stills hold where the pass has the body (a centred pass's are centred on it, frame_server.centred)
    if found and not hit["centre"] and hit.get("north") and rolled is None:
        hold = hold_of(u, found[1], hit.get("turn", 0.0))
        if hold:
            hit = dict(hit, **hold)
    if rolled is not None:
        hit = dict(hit, turn=rolled, square=True)
    with _lock:
        if len(_centre_of) >= UNIT_OF_KEEP:
            _centre_of.clear()
        _centre_of[frame_id] = hit
    return dict(hit)


HOLD_SPREAD = 0.25   # of a frame: the most a pass's frames may point away from their average for its stills to hold
HOLD_RULE = "h1"     # names the held stills' cache folders (frame_server.centre_folder)


def hold_of(u, n, turn=0.0):
    """Auto center's hold for frame n of pass u, when its still cannot be centred (the body's centre off the frame, a
    close-up turned north up, or a disk the frame cuts): the body kept where it sits on average over the pass, so it
    holds still from picture to picture as SPICE places it, as the pass's movie holds it (Sam 2026-10-30: a Saturn
    stare's stills jumped with each pointing while Auto center was on). {"hold": (dx, dy), "at": (x, y)}: the view's
    middle moved from the frame's middle by (dx, dy), and where SPICE puts the frame's middle from the body's centre
    (both full resolution pixels of frame n), which centred checks against the picture's own placement; None for a
    pass whose frames point further apart than HOLD_SPREAD of a frame (a mosaic: its stills would be mostly black)
    or a frame SPICE has not placed. turn: the stills' orientation (pass_turn), the axes the hold is on."""
    frames = u["frames"]
    if not (0 <= n < len(frames)) or not frames[n][-1]:
        return None
    z = u["z"]
    placed = [fr for fr in frames if fr[7]]
    angles = reel.north_angles([fr[1] for fr in placed])

    def middle(fr):
        # where the frame's middle sits from the body's centre, on the stills' axes (turn short of north up),
        # reference pixels
        x, y, fz = fr[5], fr[6], fr[7]
        a = math.radians(angles.get(fr[1], 0.0) - turn)
        c, s, k = math.cos(a), math.sin(a), fz / z
        return np.array(((c * x + s * y) * k, (c * y - s * x) * k))
    pts = np.array([middle(fr) for fr in placed])
    m = pts.mean(0)
    if np.abs(pts - m).max() > HOLD_SPREAD * FRAME:
        return None
    me, k = middle(frames[n]), z / frames[n][7]
    return {"hold": [round(float(v), 1) for v in (m - me) * k], "at": [round(float(v), 1) for v in me * k]}


def _on_disk(fp, radius):
    """True when the box fp (a frame's footprint, reference pixels round the body's centre) takes in part of the
    body's disk."""
    x0, y0, x1, y1 = fp
    dx, dy = max(x0, 0, -x1), max(y0, 0, -y1)
    return dx * dx + dy * dy < radius * radius


# ---------- HDR: recovery maps of tiles, movie frames and mosaics (calibration.hdr_capture) ----------
# Each tile keeps its recovery map (<n>.hdr.webp beside <n>.png: per pixel of its highlights, log2 of how much brighter
# the pass's linear scale had it than the tile drawn), cut and sized as the tile is. A movie frame's or a mosaic's map is
# the maps of the tiles it draws, placed where it draws them (each filter's newest tile on top, the brightest of the
# filters); the picture itself is drawn as before. Kept as <picture>.hdr.webp beside a movie frame or mosaic picture.
# CASSINI_HDR=0: no maps.
HDR_ON = os.environ.get("CASSINI_HDR", "1") != "0"
_hdr_drawn = contextvars.ContextVar("hdr_drawn", default=None)   # movie_frame's tiles as _place draws them


def _keep_tile_map(sink, image, side, crop, base):
    """The tile's recovery map (sink's last: processed_frame placed it on image's canvas) cut and sized as _lit_crop cut
    the tile, written as base.hdr.webp (grey, lossless); nothing when there is none"""
    try:
        m = sink[-1] if sink else None
        if m is None or m.shape != image.shape[:2]:
            return
        lit = _lit_crop(np.dstack([m, m, m, image[..., 3]]), side)
        if lit is None:
            return
        cut = lit[0][..., 0]
        if cut.shape != crop.shape[:2]:
            cut = cv2.resize(cut, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_LINEAR)
        Image.fromarray(np.ascontiguousarray(cut), "L").save(base + ".hdr.webp", "WEBP", lossless=True, quality=80, method=4)
    except Exception as e:
        print(f"No HDR map kept for {base}: {e}")


def _map_part(path, w, h):
    """A tile's recovery map (path: the tile's picture) at w x h, or None when it has none"""
    mp = path[:-len(".png")] + ".hdr.webp"
    if not os.path.exists(mp):
        return None
    return np.asarray(Image.open(mp).convert("L").resize((w, h), Image.BILINEAR))


def hdr_map(placed, W, H):
    """A picture's recovery map from the tiles it drew, placed: [(filter, tile picture path, left, top, sw, sh)] in
    the order drawn, on its W x H canvas: within a filter the tile drawn last wins where it has any alpha, across
    filters the brightest. None when no tile has a map"""
    zero = calibration.HDR_ZERO
    by = {}
    found = False
    for f, path, left, top, sw, sh in placed:
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
        if not (x0 < x1 and y0 < y1):
            continue
        part = _part(path, sw, sh)
        m = _map_part(path, sw, sh)
        canvas = by.setdefault(f, np.full((H, W), zero, np.uint8))
        a = part[y0 - top:y1 - top, x0 - left:x1 - left, 3] > 0
        v = m[y0 - top:y1 - top, x0 - left:x1 - left] if m is not None else np.full(a.shape, zero, np.uint8)
        found = found or m is not None
        region = canvas[y0:y1, x0:x1]
        region[a] = v[a]
    if not found:
        return None
    return np.max(np.stack(list(by.values())), axis=0)


def _place(u, t, rect, k, W, H, cache, scale):
    """Tile t (made on the display scale) drawn where SPICE puts it in the view rect, on a W x H canvas (k canvas
    pixels per reference pixel)."""
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    frame = np.zeros((H, W, 4), np.uint8)
    x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
    if x0 < x1 and y0 < y1:
        part = _shade(_part(os.path.join(_tiles(u, cache, scale), f"{t['n']}.png"), sw, sh), t)
        frame[y0:y1, x0:x1] = part[y0 - top:y1 - top, x0 - left:x1 - left]
    drew = _hdr_drawn.get()
    if drew is not None:
        drew.append((t.get("filter"), os.path.join(_tiles(u, cache, scale), f"{t['n']}.png"), left, top, sw, sh))
    return frame


PARTIAL = 0.5   # of a whole frame: a frame that came down with less than this (tile "lost") is partial (partial)


def partial(t):
    """True when tile report t is a partial frame SPICE placed: under PARTIAL of it came down, its lines lost in
    downlink and not made up by a repeat or the fill (often a frame sent again, a _2 or higher suffix: N1662236009_2
    lost 1,022 of 1,024 lines). A movie holds the frame of its filter before it in its place (held_of), a colour set
    with it is not complete (movie_frame), and a mosaic draws it under its other tiles (_window, _over), where it
    shows only what nothing else covers. One rule, by the area that came down, not by the suffix."""
    return "offset" in t and 1.0 - t.get("lost", 0.0) < PARTIAL


OVER_EXPOSED = 0.5   # of a frame: a movie frame the camera saturated this much of is over-exposed (over_exposed) ...
OVER_LEAST = 0.05    # ... and so is one saturated this much of the frame, where that is OVER_EXPOSED of its lit part
OVER_STEP = 3.0      # (unfit) a frame saturated OVER_LEAST or more, and this many times as much as its filter's frames
#                      before and after it, is a long exposure among short ones
SATURATED_ALL = 0.95   # ... and one saturated this much of carries no picture (left out of mosaics, never shown in movies)
BLOWN = 0.5            # (unfit) a filter more than this share of whose frames in a movie are over-exposed or saturated all over
SATURATED_LIT = 0.9    # ... and in a mosaic, one saturated over this much of its lit part (and OVER_LEAST of the frame)
LIT_LEVEL = 16       # levels: the tile's pixels at least this bright are its lit part (its report's "lit", _tile_made)


def over_exposed(t):
    """True when tile report t is over-exposed: the camera saturated OVER_EXPOSED of the frame or more (its
    "saturated"), or OVER_EXPOSED of the frame's lit part ("lit": a ring arc or a planet over a third of a frame of
    sky, 011RI IMPACT003's clear frame) when that is OVER_LEAST of the frame or more. Its saturated part calibrates to
    the top of the camera's range over a long exposure, far under what was there, and draws as one flat field (the
    long frames of 201RI DRNGMOV001, 8.2 s after 2 s ones, ~75% of them saturated: the rings a grey slab, lifted 4x by
    exposure normalization, every other frame), white since saturated pixels are drawn white (#205)."""
    s = t.get("saturated", 0.0)
    return s >= OVER_EXPOSED or (s >= OVER_LEAST and s >= OVER_EXPOSED * t.get("lit", 1.0))


MOVIE_LOST = 0.03    # of a frame: a movie frame with more of it lost in downlink than this (its tile's "lost": lines no
#                      repeat or fill made up) is not shown, its filter's frame before it held (unfit). A mosaic keeps
#                      such a frame (its other tiles cover the gap), drawing only a partial one under the rest
EMPTY_SPREAD = 16    # levels: a frame whose top (EMPTY_TOP_PCT) is less than this over its floor shows nothing lit ...
EMPTY_FLOOR = 96     # ... unless its floor is this bright or more (a featureless disk or haze filling the frame)
EMPTY_TOP_PCT = 99.99


def empty(t):
    """True when tile report t shows nothing lit: its levels on the display scale ("floor" and "top", _tile_made)
    span under EMPTY_SPREAD, and it is no bright featureless field. The 2009 south pole movie's frames past the limb
    (099SA SPOLEDYN001 W: sky stretched to a grey square), the 2010 plume movie's blank GRN frame (141EN PLMHPHR001:
    a colour set built from it held for seven frames). A tile made before its report had the levels is never empty."""
    if "top" not in t or "offset" not in t:
        return False
    return t["top"] - t.get("floor", 0) < EMPTY_SPREAD and t.get("floor", 0) < EMPTY_FLOOR


MOVIE_HOLD_LOST = 0.25   # of a frame: a movie frame with more than this lost in downlink (and not made up) is held (unfit).
#                          Under it a frame whose lost lines are a strip along an edge plays, the strip left out; lines
#                          lost across the picture (lost_inside past MOVIE_LOST) still hold it. 286RI FNTHPLE001
#                          (2017-07-24, the F ring turning) lost 6-22% of each of its last twelve frames as a strip along
#                          one edge, and MOVIE_LOST held the movie on frame 5 for all twelve. A mosaic movie keeps
#                          MOVIE_LOST (patchy); a colour set with such a frame is drawn where all its frames have the
#                          picture (colour_picture, HELD_COVER)


def lost_inside(alpha):
    """The share of a tile's picture (alpha: its tile's alpha, > 0 where drawn) lost inside it: the holes within the
    hull of what is drawn. A strip lost along an edge (286RI FNTHPLE001's) leaves the hull, so it counts ~0; lines lost
    across the frame (265RF FMOVIE001 2017-04-02: 7-34% lost, every few lines, which drew the F ring as a comb) count."""
    drawn = (alpha > 0).astype(np.uint8)
    cnts, _ = cv2.findContours(drawn, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0.0
    hull = np.zeros_like(drawn)
    cv2.fillPoly(hull, [cv2.convexHull(np.vstack(cnts))], 1)
    return round(float((hull & (1 - drawn)).sum()) / max(1, int(hull.sum())), 4)


def lost_held(t):
    """True when tile report t is a movie frame unfit holds for its lost lines or for showing nothing lit (empty):
    lost past MOVIE_HOLD_LOST, or past MOVIE_LOST inside its picture (lost_inside: lines lost across it, not a strip
    along an edge; its "lost" when the report has none)."""
    lost = t.get("lost", 0.0)
    return "offset" in t and (lost > MOVIE_HOLD_LOST or t.get("lost_inside", lost) > MOVIE_LOST or empty(t))


def patchy(t):
    """True when tile report t is a movie frame with lines lost past MOVIE_LOST, or nothing lit (empty): a mosaic
    movie draws it only where its place has no other copy (rolling_layout), a movie holds the frame before it."""
    return "offset" in t and (t.get("lost", 0.0) > MOVIE_LOST or empty(t))


def _silhouette(t):
    """Tile report t as a mosaic draws it (layout): a tile the camera saturated over nearly all of what is lit in it
    (SATURATED_LIT of its "lit", and OVER_LEAST of the frame) is left out, as one saturated all over is (_tile_made):
    it holds no picture of the body, only its outline drawn white, and drawn in a mosaic that outline stood out in the
    sky as a second limb. Iapetus ISS_049IA_REGMAPTRL001: the CL1/CL2 frames N1568160488_2 and N1568160638_2, long
    exposures off the dark leading side's limb, saturated 99.5% of their lit part; the limb they drew white lay
    ~250 px left of where the mosaic's dark ground (drawn near black) seemed to end, and read as a misplaced tile.
    Applied when drawn, so reports already made keep working; a movie keeps its own rule (unfit)."""
    s = t.get("saturated", 0.0)
    if "offset" not in t or s < OVER_LEAST or s < SATURATED_LIT * t.get("lit", 1.0):
        return t
    out = {k: v for k, v in t.items() if k not in ("offset", "box", "native_offset", "spice_offset", "outline", "registered")}
    out["why"] = f"saturated over {s / max(t.get('lit', 1.0), 1e-6):.0%} of what is lit in it: left out of the mosaic"
    return out


BLANK_SHARE = 0.5    # a frame whose levels span (top over floor) less than this share of both its filter's nearest
#                      frames either side shows little of what they show (blank)
BLANK_CLIPPED = 0.01   # of a frame: a frame of the filter saturated over this much is no measure for blank_frame: its top is
#                        the camera's clip, not the scene (263RI HIPHASE001, 2017-03-04: short and long exposures in turn
#                        through each filter; the short ones, rings at levels 0-76 to 99, read as blank against the long
#                        ones' clipped 255, and were held along with the long ones, a whole filter pair at a time)


def _span(t):
    return t["top"] - t.get("floor", 0) if "top" in t and "offset" in t else None


def blank_frame(frames, n, tile_of):
    """True when frame n of a movie spans under BLANK_SHARE of the levels its filter's nearest frames on both sides
    span (_span: the tile's top over its floor): a grey square among frames of its filter that show the scene. The
    2010 plume movie (141EN PLMHPHR001): seven frames, a whole set among them, came down as flat grey squares (levels
    23-75, against 0-160 either side), and the set built from them was shown for seven frames. A pass that brightens
    or dims steadily has a brighter frame on one side, so its frames are never blank by this rule."""
    me = _span(tile_of(n))
    if me is None:
        return False
    f = frames[n][2]
    near = []
    for js in (range(n - 1, -1, -1), range(n + 1, len(frames))):
        j = next((j for j in js if frames[j][2] == f and _span(tile_of(j)) is not None
                  and tile_of(j).get("saturated", 0.0) < BLANK_CLIPPED), None)
        if j is None:
            return False
        near.append(_span(tile_of(j)))
    return all(me < BLANK_SHARE * v for v in near)


def unfit(frames, n, tile_of):
    """True when frame n of a movie (frames: the pass's, tile_of(j): tile j's report) is not shown, its filter's
    whole frame before it held in its place (held_of): a partial frame (partial), a frame that can't be calibrated
    among frames that can (an 8LSB frame, only its low 8 bits sent: the Phoebe 2004-06-12 movie's UV3 and IR3 frames
    flashed grey; calibrated False, the tile's), or an over-exposed frame (over_exposed) between frames of its filter
    that are not (a pass alternating short and long exposures; a run of over-exposed frames is what the camera saw,
    and plays), or a long exposure among short ones: saturated OVER_LEAST of the frame or more and OVER_STEP times as
    much as its filter's frames on either side (007RI HIPHASE001's clear frames, ~9% saturated after ones that are not:
    the B ring a white band, flashing), or a frame saturated all over (SATURATED_ALL), which shows nothing, or one
    with lines lost past MOVIE_HOLD_LOST or nothing lit (lost_held), or a blank among its filter's frames (blank_frame). One rule
    for the server's movies and the page's (steady table's "partial")."""
    t = tile_of(n)
    if "offset" not in t:
        return False
    if partial(t) or lost_held(t) or (t.get("calibrated") is False and calibration.step("calibrate")) or blank_frame(frames, n, tile_of):
        return True
    s = t.get("saturated", 0.0)
    if s < OVER_LEAST:
        return False
    if s >= SATURATED_ALL:
        return True   # (saturated all over: nothing of the picture, whatever is round it)
    f = frames[n][2]
    # a filter the pass over-exposed through: when most of its frames are over-exposed, saturated all over, blank or lit nowhere
    # (one saturated all over calibrates to one flat level), its
    # frames saturated OVER_LEAST or more are held too, as the rest of them are, so its least saturated one is not
    # left to play alone, half white (SPOLEDYN001 2009: clear frames 92-100% saturated round W1609834686_1, 39%,
    # which played twice, held in the 65% one's place, late in the dark south pole movie). A run in a pass whose
    # filter is mostly well exposed still plays (a bright limb coming in). Over-exposed here is saturated over
    # OVER_EXPOSED of the whole frame, not of its lit part: a limb coming into a dark frame is saturated over most of
    # its lit part from its first frames, yet shows the scene (293EN ENCSET001 2017-09-13, Enceladus setting behind
    # Saturn: clear frames 5-40% saturated, all of it the limb; 34 of 45 counted as blown held the movie on one frame)
    mine = [j for j in range(len(frames)) if frames[j][2] == f and "offset" in tile_of(j)]
    blown = sum(1 for j in mine if tile_of(j).get("saturated", 0.0) >= OVER_EXPOSED
                or lost_held(tile_of(j)) or blank_frame(frames, j, tile_of))
    if len(mine) >= 3 and blown > BLOWN * len(mine):
        return True
    # its filter's nearest frames either side that show a picture: one saturated all over is held itself, so it is no
    # run of over-exposed frames to play with (SPOLEDYN001 2009: a clear frame 92% saturated between two 99-100%
    # saturated ones played as a white slab; its filter's frames shown round it are dark)
    shows = lambda j: frames[j][2] == f and tile_of(j).get("saturated", 0.0) < SATURATED_ALL
    near = [j for j in (next((j for j in range(n - 1, -1, -1) if shows(j)), None),
                        next((j for j in range(n + 1, len(frames)) if shows(j)), None)) if j is not None]
    if over_exposed(t):
        return not any(over_exposed(tile_of(j)) for j in near)
    return bool(near) and all(s >= OVER_STEP * tile_of(j).get("saturated", 0.0) for j in near)


def held_of(filters, n, is_partial, whole):
    """The frame a movie shows in frame n's place (pure, ported to the page: steady-local.html heldOf): n, or when n
    is partial (is_partial(n): unfit's frames), the last frame before it of its filter (filters[j]) that is whole
    (whole(j): placed and not partial), as the camera windows hold a colour movie's last set; when its filter has
    none, the last whole frame before it of any filter (the Phoebe 2004-06-12 movie's 8LSB frames are each its
    filter's first). With no whole frame before it (a pass whose first frame is over-exposed: 010SA EUVFUV003,
    011RI IMPACT003 opened on a white frame), the first whole frame after it, of its filter, else of any; n when
    there is none, so a pass whose frames all came down partial keeps them. The movie keeps its frame count: only
    the picture is held."""
    if not is_partial(n):
        return n
    for j in range(n - 1, -1, -1):
        if filters[j] == filters[n] and whole(j):
            return j
    for j in range(n - 1, -1, -1):
        if whole(j):
            return j
    for j in range(n + 1, len(filters)):
        if filters[j] == filters[n] and whole(j):
            return j
    for j in range(n + 1, len(filters)):
        if whole(j):
            return j
    return n


HELD_COVER = 0.5   # of a movie frame's own place: a colour set covering less of it is not shown for it (movie_frame)


def held_cover(t, planes, rect, k):
    """The share of tile t's place in the view (its box where SPICE puts it, as _place draws it) where every plane
    of a colour set has the picture: 1.0 when the set covers all of it, 0.0 off it (movie_frame)."""
    H, W = planes[0].shape[:2]
    bx, by, bw, bh = t["box"]
    left, top = round((t["offset"][0] + bx - rect[0]) * k), round((t["offset"][1] + by - rect[1]) * k)
    x0, y0 = max(left, 0), max(top, 0)
    x1, y1 = min(left + max(1, round(bw * k)), W), min(top + max(1, round(bh * k)), H)
    if x0 >= x1 or y0 >= y1:
        return 0.0
    return float(np.logical_and.reduce([a[y0:y1, x0:x1, 3] > 0 for a in planes]).mean())


def colour_sets(frames):
    """The pass's frames grouped into filter sets, the camera windows' own (sets_passes, the one rule: reel.load_index's
    sets, which the page reads from the data): a run of frames, each taken within SET_GAP of the one before, through
    different filters; a clear or polarizer frame ends it, and a filter coming round again starts a new one (the next
    pointing of a mosaic, the next colour cycle). Each set is a list of (filter, frame index), in time order, with the
    set's frames that are tiles of the pass (a repeat exposure units leaves out is stacked into its tile). Frames
    the index does not have are grouped by the same rule among themselves."""
    try:
        idx, row = _row_of()
    except FileNotFoundError:   # no index (a synthetic pass)
        idx, row = None, {}
    qs = [row.get(fr[1]) for fr in frames]
    if not frames or any(q is None for q in qs) or "set" not in idx:   # (or an index made without its sets)
        return _own_sets(frames)
    set_of, by = idx["set"].to_numpy(), {}
    for j, (fr, q) in enumerate(zip(frames, qs)):
        if set_of[q] >= 0:
            by.setdefault(int(set_of[q]), []).append((fr[2], j))
    return [run for _, run in sorted(by.items(), key=lambda kv: kv[1][0][1]) if len(run) >= 2]


def _own_sets(frames):
    """colour_sets' rule applied to frames on their own (one camera, target and observation)."""
    at = sets_passes.runs([("", "", "", None if fr[2] == "CL1/CL2" or _polarizer(fr[2]) else fr[2], fr[3]) for fr in frames])
    return [[(frames[j][2], j) for j in run] for run in sorted(at, key=lambda r: r[0])]


COLOUR_STEPS = 2     # a movie plays in colour when it takes at least this many sets of its colour filters (plays_colour) ...
STEP_FRAMES = 4      # ... or one, and its grey filter fewer frames than this (one visit through many filters: 125TI
#                      CLOUD002's twelve frames, three CB3). Otherwise its grey filter plays: a Titan cloud watch takes
#                      CB3 every step and one RED, GRN, BL1 set part way (167TI CLOUD001), which froze the clouds from it on
STEP_RUN = 12        # frames: in a movie playing its grey filter, a run of other filters this long or shorter shows the
#                      grey filter's frame beside it (step_frame): one filter a step, not a strobe of looks (273TI
#                      LRMONITOR002's MT1 between CB3s, 054TI CLOUDMAP001's IR2/IR1)


def _pass_sets(u):
    """colour_sets of the whole pass, worked out once."""
    if "_sets" not in u:
        u["_sets"] = colour_sets(u["frames"])
    return u["_sets"]


def plays_colour(u, want, grey):
    """True when a movie of pass u with colour filters want plays in colour (movie_frame, colour on): it takes
    COLOUR_STEPS sets of them, or one and under STEP_FRAMES frames of its grey filter. A set is one of the camera
    windows' (colour_sets) holding every filter of want."""
    if not want:
        return False
    sets = sum(1 for run in _pass_sets(u) if set(want) <= {f for f, _ in run})
    return sets >= COLOUR_STEPS or (sets >= 1 and sum(fr[2] == grey for fr in u["frames"]) < STEP_FRAMES)


def set_of(u, n, want, not_shown, placed, covers=None):
    """{filter: frame} of the colour set frame n of pass u shows (pure but for the pass's sets: the page's sets come
    from it, _colour_by), or None: the newest set taken by then whose frames of want are all shown (not_shown: unfit)
    and placed, so a set updates only once every channel of the next one is in; before the first, the first such set
    (a film opens on colour, not on 2 to 43 grey frames as its filters come in: the 2000 Jupiter and 2004 Saturn
    approach movies). A set with a frame not shown leaves the one before it up. covers(got): whether a set takes in
    frame n's place; when the newest does not (the camera has moved on to the next pointing, whose set is still
    coming in), the next set does if it covers it: the 2009 south pole movie's frames at each new pointing showed
    grey filter after grey filter, and white slabs, until its set was in."""
    def whole(run):
        got = {f: j for f, j in run if f in want and not not_shown(j)}
        return got if len(got) == len(want) and all(placed(j) for j in got.values()) else None
    ok = covers or (lambda got: True)
    runs = _pass_sets(u)
    for run in reversed([r for r in runs if max(j for _, j in r) <= n]):
        got = whole(run)
        if got:
            if ok(got):
                return got
            break
    for run in runs:
        if max(j for _, j in run) > n:
            got = whole(run)
            if got:
                return got if ok(got) else None
    return None


HOLD_AGE = sets_passes.SET_GAP   # s: the furthest in time a picture of other frames stands in for a movie frame (shown_of)
HOLD_BANDS = ("MT1", "MT2", "MT3", "UV1", "UV2", "UV3")   # bands a colour set stands in for within HOLD_AGE (held_band)


def held_band(f):
    """Whether a frame through filter f is one a colour set taken near it stands in for (shown_of): a methane band, an
    ultraviolet one or a polarizer, whose own gray as the picture's brightness would not be the body's look (dark
    methane belts, a UV limb). Any other filter (clear, the colours, the continuum bands, IR) gives its own picture."""
    return f in HOLD_BANDS or any(b in HOLD_BANDS for b in f.split("/")) or _polarizer(f)


def set_shown(u, n, want, not_shown, placed, covers=None):
    """_set_shown's set, its exposures matched (matched_exposures)."""
    got, tint = _set_shown(u, n, want, not_shown, placed, covers)
    return (matched_exposures(u, got, not_shown, placed) if got else got), tint


def _frame_exposure(u, j):
    """Frame j of pass u's exposure in s (its label), or None; read once per pass."""
    kept = u.setdefault("_exposures", {})
    if j not in kept:
        try:
            kept[j] = _exposure(label_handler.label(u["frames"][j][0], as_png=True))
        except Exception:   # (no label: a synthetic pass, a frame missing from the archive)
            kept[j] = None
    return kept[j]


def matched_exposures(u, got, not_shown, placed):
    """Colour set got ({filter: frame}) with a frame exposed LONG_EXPOSURE times longer than the set's shortest
    swapped for its filter's frame nearest in time (within HOLD_AGE, shown and placed) exposed under that, when there
    is one. A pass alternating short and long exposures through each filter groups a long frame with short ones of the
    other filters: its saturated part (the clipped arc of the rings) was mixed against the short frames' unclipped one,
    and came out red where the others had no picture to match (263RI HIPHASE001 2017-03-04: a 2 s RED with 0.1 s GRN
    and 0.18 s BL1, the bright arc pure red and every frame tinted pink from it). got as it is when the exposures are
    not known or there is no such frame."""
    es = {f: _frame_exposure(u, j) for f, j in got.items()}
    if any(e is None or e <= 0 for e in es.values()):
        return got
    least = min(es.values())
    frames, out = u["frames"], dict(got)
    for f, j in got.items():
        if es[f] < LONG_EXPOSURE * least:
            continue
        t = frames[j][3]
        near = [i for i in range(len(frames)) if frames[i][2] == f and i != j and abs(frames[i][3] - t) <= HOLD_AGE
                and placed(i) and not not_shown(i)]
        near = [i for i in near if (_frame_exposure(u, i) or 0) > 0 and _frame_exposure(u, i) < LONG_EXPOSURE * least]
        if near:
            out[f] = min(near, key=lambda i: abs(frames[i][3] - t))
    return out


def _set_shown(u, n, want, not_shown, placed, covers=None):
    """(the colour set frame n of a movie playing in colour shows, or None; True when it shows it as the colour of
    frame n's own picture) (pure but for the pass's sets: movie_frame's and the page's, _colour_by). The set is
    set_of's. A frame of the set, or one taken within HOLD_AGE of it (the same moment: a cycle's other filters, which
    drawn on their own would strobe from look to look), is drawn as the set. A frame further from it plays its own
    moment in the set's colour (tinted: its brightness and detail, the set's hue; shown_of picks the picture, lum_of)
    (Sam 2026-11-06: frames were lost behind one colour picture, and the movie had fewer frames than it took).
    The 2012 Titan transit (165TI LRMONITOR001 WAC) played 25 of its 26 frames as one set taken 50 minutes into it, and
    the first Titan flyby (00ATI MOVIEA001) never showed the CB3 frames that see its surface through the haze."""
    got = set_of(u, n, want, not_shown, placed, covers)
    if not got or n in got.values():
        return got, False
    frames = u["frames"]
    t, ts = frames[n][3], [frames[j][3] for j in got.values()]
    age = t - max(ts) if t >= max(ts) else min(ts) - t
    if age <= HOLD_AGE:
        return got, False
    # further from it, a frame of a set still coming in (its channels within HOLD_AGE after it) shows that set: its own
    # moment in its own colors, not drawn through a set taken long before (165TI LRMONITOR001's last RED and GRN, 75
    # minutes after the set before, came out blown white and banded)
    for run in _pass_sets(u):
        if any(j == n for _, j in run):
            mine = {f: j for f, j in run if f in want and not not_shown(j)}
            if (len(mine) == len(want) and all(placed(j) for j in mine.values())
                    and max(frames[j][3] for j in mine.values()) - frames[n][3] <= HOLD_AGE
                    and (covers is None or covers(mine))):
                return mine, False
            break
    return got, True


def step_frame(filters, s, grey, whole, near, times=None):
    """The frame shown for frame s (held_of's) in a movie playing its grey filter (pure, ported to the page through
    the steady table's "step"): s when it is the grey filter's; else, in a run of at most STEP_RUN frames of other
    filters, the grey filter's last whole frame before the run (whole(j): placed, shown), else its first after it,
    that near(j) (its place takes in most of s's) and, given the frames' times, was taken within HOLD_AGE of s; s when
    there is none."""
    if filters[s] == grey:
        return s
    a, b = s, s
    while a > 0 and filters[a - 1] != grey:
        a -= 1
    while b + 1 < len(filters) and filters[b + 1] != grey:
        b += 1
    if b - a + 1 > STEP_RUN:
        return s
    before = (j for j in range(a - 1, -1, -1) if filters[j] == grey and whole(j))
    after = (j for j in range(b + 1, len(filters)) if filters[j] == grey and whole(j))
    for j in (next(before, None), next(after, None)):
        # (times: the frames' times; a gray frame taken over HOLD_AGE from s is not s's moment, s plays itself)
        if j is not None and near(j) and (times is None or abs(times[j] - times[s]) <= HOLD_AGE):
            return j
    return s


def box_cover(t, q):
    """The share of tile t's place (its box where SPICE puts it) that tile q's place covers: 0.0 off it."""
    def at(x):
        bx, by, bw, bh = x["box"]
        return x["offset"][0] + bx, x["offset"][1] + by, x["offset"][0] + bx + bw, x["offset"][1] + by + bh
    a, b = at(t), at(q)
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h) / max(1e-9, (a[2] - a[0]) * (a[3] - a[1]))


def set_cover(t, qs):
    """The share of tile t's place (its outline where SPICE puts it; its box without one) that every one of tiles
    qs's places covers at once, as a colour set is drawn (colour_picture: only where every filter has the picture;
    held_cover on the planes). Each filter's box over half of it was not enough: a frame turned in the view fills
    little of its box, so the 2008 north pole movie (082SA NPOLECAM002, which moved between its cycles) held its
    first cycle's set through the second, each box taking in 55% of the new place but the pictures less than half,
    and played grey filter after grey filter until the second cycle's own set was in."""
    def poly(x):
        if x.get("outline"):
            return np.asarray(x["outline"], np.float32)
        bx, by, bw, bh = x["box"]
        ox, oy = x["offset"]
        return np.asarray([[ox + bx, oy + by], [ox + bx + bw, oy + by], [ox + bx + bw, oy + by + bh],
                           [ox + bx, oy + by + bh]], np.float32)
    a = poly(t)
    full = abs(float(cv2.contourArea(a)))
    if full <= 0:
        return 0.0
    hull = cv2.convexHull(a)
    for q in qs:
        area, inter = cv2.intersectConvexConvex(hull, cv2.convexHull(poly(q)))
        if area <= 0 or inter is None:
            return 0.0
        hull = cv2.convexHull(inter.reshape(-1, 2).astype(np.float32))
    return abs(float(cv2.contourArea(hull))) / full


def holds(tile_of, not_shown):
    """whole(j) for held_of: frame j placed, shown (not not_shown) and not over-exposed. A frame held in another's place
    is never a white slab: the 2009 south pole movie's empty clear frames held the 88% saturated one before them."""
    return lambda j: "offset" in tile_of(j) and not not_shown(j) and not over_exposed(tile_of(j))


def lum_of(frames, s, grey, whole, near, reach=None):
    """The frame whose picture gives a tinted movie frame s its brightness and detail (shown_of): of the frames within
    HOLD_AGE of it that are whole (whole(j)), cover its place (near(j)) and are not of held_band's bands, the pass's
    gray filter's nearest in time, else any filter's nearest; s itself when it is not of those bands and none of the
    gray filter is near; None when s is of those bands and no such frame is near (it then plays on its own, in gray).
    So the movie keeps one look instead of strobing filter to filter (00ATI MOVIEA001: CB3's surface, CB1's smooth
    haze, IR3's bands), and a polarizer or UV frame shows its moment through the filter beside it (153HY HYPERION001:
    its P0, P60, P120 and UV3 frames flashed gray between colour ones)."""
    t, reach = frames[s][3], HOLD_AGE if reach is None else reach
    ok = [j for j in range(len(frames)) if abs(frames[j][3] - t) <= reach and not held_band(frames[j][2])
          and (j == s or (whole(j) and near(j)))]
    by_time = lambda js: min(js, key=lambda j: (abs(frames[j][3] - t), j != s)) if js else None
    mine = by_time([j for j in ok if frames[j][2] == grey])
    if mine is not None:
        return mine
    if not held_band(frames[s][2]):
        return s
    return by_time(ok)


def shown_of(u, p, n, not_shown, tile_of):
    """(the frame whose picture frame n of a movie shows, the colour set it shows or None, True when the set is drawn
    as the colour of that frame's picture), as movie_frame draws it with colour on: the set (set_shown) when the pass
    plays in colour (plays_colour); else the frame held_of holds, put through step_frame when the pass plays its grey
    filter."""
    frames, want = u["frames"], p.get("colour")
    placed = lambda j: "offset" in tile_of(j)
    colours = bool(want) and plays_colour(u, want, p["grey"])
    # in a pass playing in colour an over-exposed frame (a run of them too: the 2009 south pole movie's clear frames,
    # 86-92% saturated) is never shown, its colour set or the frame before it is
    hidden = (lambda j: not_shown(j) or over_exposed(tile_of(j))) if colours else not_shown
    whole = holds(tile_of, hidden)
    s = held_of([fr[2] for fr in frames], n, hidden, whole)
    if colours:
        covers = lambda got: set_cover(tile_of(n), [tile_of(j) for j in got.values()]) >= HELD_COVER
        got, tint = set_shown(u, n, want, not_shown, placed, covers)
        if got and not tint and not held_band(p["grey"]):
            # one look for the whole movie: a set's own frames, and those near it, are drawn from the pass's gray filter
            # beside them too (lum_of) in the set's colors, as the frames between sets are, so a Titan movie no longer
            # flips between the sets' plain haze and its CB3 frames' surface (00ATI MOVIEA001, 117TI CLOUD001, 147TI
            # EUVFUV001), and Epimetheus (259EP EPIMETHEU001) shows its sharp clear frame, not the blurred IR1 set.
            # Not from a gray frame over-exposed in part (TINT_SATURATED: the transit's clear frames on Saturn)
            j = lum_of(frames, s, p["grey"], whole, lambda j: box_cover(tile_of(s), tile_of(j)) >= HELD_COVER, LUM_REACH)
            if j is not None and frames[j][2] == p["grey"] and tile_of(j).get("saturated", 0.0) < TINT_SATURATED:
                return j, got, "near"   # (the set's own moment: its brightness taken whole, tinted_frame's near)
        if got and tint:
            # its own moment in the set's colour, its picture from lum_of (one look for the movie; a frame held_of
            # holds another in place of is tinted as that one is: 153HY's unfit P120 frames flashed gray)
            j = lum_of(frames, s, p["grey"], whole, lambda j: box_cover(tile_of(s), tile_of(j)) >= HELD_COVER)
            if j is not None:
                return j, got, True
            got = None   # (a held band with no other filter near: on its own, in gray, below)
        if got:
            return s, got, False
    if placed(s) and len({fr[2] for fr in frames}) > 1:
        s = step_frame([fr[2] for fr in frames], s, p["grey"], whole,
                       lambda j: box_cover(tile_of(s), tile_of(j)) >= HELD_COVER, [fr[3] for fr in frames])
    return s, None, False


def movie_frame(u, n, cache, trail=0, colour=True, out=OUT, centre=True, steady=0, exposure=0, sharpen=True, per_body=True):
    """Frame n of the pass played as a movie, RGBA out px on its longest side, and its report; (None, report)
    when SPICE could not place it. The frame is the pass's tile n (color_image.processed_frame: repeat exposures
    merged in I/F, calibrated, centred north up by SPICE, scaled to the pass's reference distance, on the pass's
    one display scale), drawn where SPICE puts it in movie_rect: so the picture keeps one brightness scale and one
    size for the whole pass, and the body holds still. colour: when the pass's plan has colour filters and the
    newest frame of each of them was taken within reel.SET_GAP of this one, the three are drawn as one colour
    picture (each where SPICE puts it), as the pass's mosaic does; otherwise the frame in grey. trail: up to that
    many earlier frames of the same filter drawn under it, fading with age (a rolling trail). In a pass that plays in
    colour (plays_colour) every frame shows the newest complete colour set, held until the next one is complete, and
    the frames before the first show the first (set_of); a pass that plays its grey filter shows that filter's frame
    for a short run of others (step_frame); a frame not fit to show (unfit: lines lost, nothing lit, over-exposed)
    shows the frame before it of its filter (held_of). centre: the body in the
    middle of the view (movie_rect). steady: image stabilization (Settings > Movie), every tile drawn at its
    stabilized place (steady_places, smoothed over that many frames) instead of SPICE's; 0: SPICE's places.
    exposure: exposure normalization (Settings > Movie), the whole picture drawn with frame n's exposure gain
    (exposure_gains, smoothed over that many frames); 0: as the pass's display scale draws it. sharpen: a filled
    pass's last step, detail(); False leaves it out (the plane a browser gains, mixes and sharpens itself,
    steady-local.html). per_body False: every other body where each filter saw it (_per_body_planes not applied), as
    exposure_chain measures the movie."""
    p = plan(u, cache)
    t = tile(u, n, cache, p["display_scale"])
    rep = {"movie": True, "n": n, "of": len(u["frames"]), "filter": t["filter"], "observation": u["key"][1],
           "pass": u["key"][3], "id": t["id"]}
    if "offset" not in t:
        rep["why"] = t.get("why", "not placed by SPICE")
        return None, rep
    frames, own = u["frames"], t
    tile_of = lambda j: own if j == n else tile(u, j, cache, p["display_scale"])
    held = {}

    def not_shown(j):
        if j not in held:
            held[j] = unfit(frames, j, tile_of)
        return held[j]
    whole = holds(tile_of, not_shown)
    # a partial frame (lines lost in downlink), an uncalibrated, over-exposed or empty one (unfit) shows the last whole
    # frame of its filter in its place; with colour on, the frame plays its colour set (set_of) or, in a pass playing
    # its grey filter, that filter's frame beside it (step_frame): shown_of
    got, tint = None, False
    if colour:
        s, got, tint = shown_of(u, p, n, not_shown, tile_of)
    else:
        s = held_of([fr[2] for fr in frames], n, not_shown, whole)
    if s != n:
        rep["held"] = frames[s][1]
        t = tile_of(s)
    if t.get("white"):
        # (a long exposure drawn on the white of the pass's long exposures, pass_scale's "long")
        rep["segment_white"] = round(t["white"], 6)
    # a feature track: every tile drawn at its steady place (track_places), so the feature holds still; the body
    # moves past it instead, so a track is not centred on the body
    track = track_places(u, cache, p) if u.get("track") else None
    # any other movie: stabilized, each tile where the pictures put it from the tile before, held to SPICE
    places = track or (steady_places(u, cache, p, steady) if steady else None)

    # one gain for every tile of the picture (a colour set's filters, the trail), so its colour stays
    gain = exposure_gains(u, cache, p, exposure, colour, centre, steady).get(n, 1.0) if exposure else 1.0
    gamma = p["display_scale"].get("gamma", 2.2)

    def at(q):
        if places and q.get("n") in places:
            q = dict(q, offset=places[q["n"]])
        if gain != 1.0:
            q = dict(q, gain=round(q.get("gain", 1.0) * gain, 3), gamma=q.get("gamma", gamma))
        return q
    spice, raw = t["offset"], t
    t = at(t)
    if track:
        rep["steady"] = "track"
    elif places:
        rep["steady"] = "stabilized"
        rep["stabilized"] = {"smooth": steady, "shift": [round(t["offset"][0] - spice[0], 2), round(t["offset"][1] - spice[1], 2)]}
    if exposure:
        rep["exposure"] = {"smooth": exposure, "gain": gain}
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    seen = pass_seen(u) if centre and not track else None
    fp = movie_footprint(u, cache, p)
    rect = movie_rect(fp, t, radius, centre and not track, seen)
    rep["centred"] = rect[0] == -rect[2] / 2 and rect[1] == -rect[3] / 2
    k = out / max(rect[2], rect[3])
    # a movie following the frame: the frame drawn as Cassini took it, filling the picture (follow_view)
    # a movie following the frame: the frame drawn as Cassini took it, filling the picture (follow_view); with a
    # rolling trail asked for, the window MOVIE_FIT frames across as before, so the frames before it show round it
    unturn = None
    if not track and not trail and follows(fp, rect):
        rect, k, turn = follow_view(u, s, t, out, _pic(u, cache, p["display_scale"], t))
        unturn = (turn, follow_middle(t, rect, k), out, out)
        rep["follow"] = {"turn": round(turn, 2)}
    W, H = max(1, math.ceil(rect[2] * k)), max(1, math.ceil(rect[3] * k))
    # only the frames this picture needs are made: the colour set's, the trail
    used, newest = None, {}
    # a pass that plays in colour (plays_colour): every frame shows the newest colour set taken by then (colour_sets,
    # the camera windows' sets, so the movie mixes the frames color.webp does) whose every channel is in, held until
    # the next set is complete, as the camera windows hold a colour movie's last set; a frame of another filter (CB2,
    # a methane band) keeps it up; the frames before the first set show the first (set_of)
    if got:
        want = p["colour"]
        own_gain = {}
        bases = {f: own if j == n else tile(u, j, cache, p["display_scale"]) for f, j in got.items()}
        to_white = one_white(list(bases.values()), p["display_scale"])
        for f, j in got.items():
            # (frame n's own tile as made: at() is applied once, below, so its gain is not taken twice)
            base = bases[f]
            if to_white.get(id(base)):
                base = dict(base, gain=round((base.get("gain") or 1.0) * to_white[id(base)], 4),
                            gamma=base.get("gamma", gamma))
            newest[f] = at(base)
            own_gain[f] = base.get("gain")
        used = want
    if used:
        # (drawn without the frame's exposure gain, which is applied to the colour picture made of them: on each
        # plane alone, _shade kept one band's clipped white while the others were dimmed under it, and a moon only
        # one band clipped on came out with a lime-green blotch, Rhea in GRN, 154RH MUTUALEVE002 at gain 0.5; and
        # colour_picture fills a clipped band from the others only where it still reads as clipped)
        # (a gain over 1 as before: nothing is kept white then)
        late = gain < 1.0
        planes = [_place(u, dict(newest[f], gain=own_gain[f]) if late else newest[f], rect, k, W, H, cache,
                         p["display_scale"]) for f in used]
        # another body in the set (a transit: Titan behind Rhea) moved against the target between the filters: each
        # filter's copy of it put where the shown frame has it (_per_body_planes), not three colored copies
        # (where the target is in each tile's picture: SPICE's place, or the pictures' where seen_places took them,
        # Dione 28 px off SPICE in 153DI MUTUALEVE002, whose copies otherwise went with Titan's)
        held = steady_held(u, cache, p) if steady and not track else {}
        raws = {f: held.get(j) or (own if j == n else tile(u, j, cache, p["display_scale"]))["offset"]
                for f, j in got.items()}
        planes, moved = _per_body_planes(u, [got[f] for f in used], [(newest[f]["offset"], raws[f]) for f in used],
                                         planes, rect, k, radius, s) if per_body else (planes, None)
        away = None
        if moved:
            away = moved.pop("_away", None)
            rep["per_body"] = moved
        # a colour filter the pass takes once (a cycle's lone MT1 and UV1, _set_colour's Titan stares) has no frame of
        # its own filter either side to take its cosmic rays out against (_around): the set's planes are cleaned as a
        # still composite's channels are (calibration._clean_spikes), or each hit is a bright dot through the mix
        if any(_around(u, got[f]) == [None, None] for f in used if f in got):
            planes = _despiked(planes, p["display_scale"].get("gamma", 2.2))
        # a colour set held from an earlier pointing (a track's last visit, a thousand px away, or a pass that moved
        # on across the body) shows little or nothing where this frame is: colour_picture draws only where every
        # filter has the picture. Under HELD_COVER of both frame n's own place and the frame shown for it covered,
        # the frame is drawn on its own instead. (Either place will do: the 2008 north pole movie's MT3 frames, held to
        # the first cycle's, are covered at their own place only; an unfit clear frame held to the one before, as in
        # the 2009 south pole movie, is covered at the held frame's place.)
        if max(held_cover(at(own), planes, rect, k), held_cover(t, planes, rect, k)) >= HELD_COVER:
            shown = None
            if tint and not moved:
                # each filter's plane moved onto the frame it tints, by its lit outline (_onto_frame): a set's filters a
                # minute apart are placed by their own pointings and can sit 20 px from each other and from the frame,
                # and their limbs then crossed the frame's disk as ghost arcs, blue on one side and orange on the other
                # (133TI CLOUD002, CB3 + MT1; Sam 11-08)
                shown = _place(u, t, rect, k, W, H, cache, p["display_scale"])
                planes = [_onto_frame(plane, shown) for plane in planes]
            rgba = colour_picture(u, p, used, planes, away)
            if late:
                rgba = _shade_rgb(rgba, gain, gamma)
            rep["color"] = used
            rep["ids"] = [newest[f]["id"] for f in used]
            if tint:
                # frame n's own picture in the set's colour (set_shown): its brightness and detail, the set's hue
                rgba = tinted_frame(rgba, shown if shown is not None else _place(u, t, rect, k, W, H, cache, p["display_scale"]),
                                    gamma, tint == "near")
                rep["tint"] = True
        else:
            used = None
    if not used:
        rgba = _place(u, t, rect, k, W, H, cache, p["display_scale"])
        # the rolling trail: earlier frames of this filter under it, older ones fainter
        if trail:
            # (behind the frame shown, held or not, and without partial frames)
            js = list(itertools.islice((j for j in range(s - 1, max(-1, s - 8 * trail), -1)
                                        if frames[j][2] == t["filter"] and not not_shown(j)), trail))
            older = [at(q) for q in (tile(u, j, cache, p["display_scale"]) for j in reversed(js)) if "offset" in q]
            acc = np.zeros((H, W, 4), np.float32)
            for age, q in zip(range(len(older), 0, -1), older):
                a = _place(u, q, rect, k, W, H, cache, p["display_scale"]).astype(np.float32)
                w = a[..., 3:] / 255 * (1 - age / (len(older) + 1))
                acc[..., :3] = acc[..., :3] * (1 - w) + a[..., :3] * w
                acc[..., 3:] = np.maximum(acc[..., 3:], w * 255)
            w = rgba[..., 3:].astype(np.float32) / 255
            acc[..., :3] = acc[..., :3] * (1 - w) + rgba[..., :3] * w
            acc[..., 3:] = np.maximum(acc[..., 3:], rgba[..., 3:])
            rgba = (acc + 0.5).astype(np.uint8)
            rep["trail"] = len(older)
    if unturn:
        drawn = (W, H)
        rgba = _unturn(rgba, *unturn)
        H, W = rgba.shape[:2]
    if sharpens(p["display_scale"]) and sharpen:
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * k)
    rep.update({"view": [round(v, 1) for v in rect], "width": W, "height": H})
    im = Image.fromarray(rgba, "RGBA")
    if unturn:
        im.info["unturn"] = (unturn, drawn)   # (its recovery map turned back the same way, _with_hdr_map)
    return im, rep


def _with_hdr_map(make):
    """movie_frame with its recovery map (hdr_map of the tiles _place drew) in the picture's info["hdr"]"""
    def made(*args, **kwargs):
        if not HDR_ON:
            return make(*args, **kwargs)
        drew = []
        token = _hdr_drawn.set(drew)
        try:
            im, rep = make(*args, **kwargs)
        finally:
            _hdr_drawn.reset(token)
        if im is not None:
            try:
                turn = im.info.pop("unturn", None)
                # (a movie following the frame: the map on the canvas the tiles were drawn on, turned back as the
                # picture was, follow_view)
                m = hdr_map(drew, *turn[1]) if turn else hdr_map(drew, im.width, im.height)
                if m is not None and turn:
                    m = _unturn(m, *turn[0])
                if m is not None:
                    im.info["hdr"] = m
            except Exception as e:
                print(f"No HDR map for the movie frame: {e}")
        return im, rep
    made.__doc__ = make.__doc__
    return made


def keep_picture_map(im, path):
    """A movie frame's or mosaic picture's recovery map (im.info["hdr"], sized to im) beside its picture at path, as
    <path less its extension>.hdr.webp (grey, lossless); nothing when it has none"""
    m = im.info.get("hdr")
    if m is None or not path.endswith(".webp"):
        return
    try:
        if m.shape != (im.height, im.width):
            m = cv2.resize(m, (im.width, im.height), interpolation=cv2.INTER_AREA)
        buf = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(m), "L").save(buf, "WEBP", lossless=True, quality=80, method=4)
        reel._cached(path[:-len(".webp")] + ".hdr.webp", buf.getvalue)
    except Exception as e:
        print(f"No HDR map kept for {path}: {e}")


movie_frame = _with_hdr_map(movie_frame)


# the same frame drawn the same way: named in the cache by folder, frame, trail, colour and centring (movie_webp)
movie_frame = _kept_for_next_size(movie_frame, lambda u, n, cache, trail=0, colour=True, out=OUT, centre=True, steady=0, exposure=0, sharpen=True, per_body=True:
                                  (folder(u, cache), n, trail, colour, out, centre, bool(u.get("track")), steady, exposure, sharpen, per_body)
                                  if out <= OUT else None)


# a pass's movie frames, renamed whenever the way they are drawn changes (movie-2: colour frames mixed as the mosaic is)
MOVIE_DIR = "movie-3"   # movie-3: views sized to the frames' own boxes (movie_footprint2) and following ones drawn as
                        # the frame (follow_view)
MOVIE_SIZES = (512, 1024)   # the sizes the windows play a movie at, smallest first (a smaller one is shrunk from them)


def steady_of(u, steady):
    """The stabilization smoothing a movie of pass u is drawn with: steady (Settings > Movie, frames) within
    0..STEADY_MOST, 0 for a feature track (always steady, track_places) and with Settings > Processing's alignment
    off (SPICE's places)."""
    if u.get("track") or not calibration.step("align"):
        return 0
    return max(0, min(STEADY_MOST, int(steady or 0)))


def exposure_of(exposure):
    """The exposure smoothing a movie is drawn with: exposure (Settings > Movie, frames) within 0..EXPOSURE_MOST."""
    return max(0, min(EXPOSURE_MOST, int(exposure or 0)))


def _exposure_ready(u, cache, rec, how):
    """True when the pass's brightness chain for this way of drawing it (how: colour, centre, steady) is in memory
    or in the cache."""
    return (rec is not None and ("exposure",) + tuple(how) in (rec.get("exposure") or {})) or \
        os.path.exists(os.path.join(folder(u, cache), _exposure_name(*how)))


def _steady_ready(u, cache, rec):
    """True when the pass's stabilization chain is in memory or in the cache."""
    return (rec is not None and rec.get("steady") is not None) or os.path.exists(os.path.join(folder(u, cache), STEADY_FILE))


_movie_making_now, _movie_making_lock = {}, threading.Lock()   # movie picture path -> [its lock, threads making or waiting]


@contextlib.contextmanager
def _making_movie(path):
    """One thread at a time makes the movie picture at path: another asking for it meanwhile waits for it and then
    finds it in the cache (reel._cached), instead of drawing the same frame again beside it. The Movie Editor's levels
    (export.measure, 3 threads) and a Pre-process (Segments, 4 threads) walk the same stretch from its start at once,
    and a frame not made yet (a Jupiter WAC color frame with Exposure normalization: 3 to 4 s) was drawn by both."""
    with _movie_making_lock:
        held = _movie_making_now.setdefault(path, [threading.Lock(), 0])
        held[1] += 1
    try:
        with held[0]:
            yield
    finally:
        with _movie_making_lock:
            held[1] -= 1
            if not held[1]:
                del _movie_making_now[path]


def movie_webp(frame_id, size, cache, trail=0, colour=True, wait=False, ahead=6, centre=True, steady=0, exposure=0, sharpen=True):
    """(WebP, report) of frame_id played as a movie of its pass (movie_frame), made once and kept in the cache;
    None when the frame is in no pass. A pass whose plan is not worked out yet (seconds: it measures the pass's
    scale) is started in the background and answers (None, report) unless wait, so the window shows the plain
    frame meanwhile. Then makes the next few tiles in the background. centre: the body in the middle (movie_rect).
    steady: image stabilization smoothed over that many frames (steady_places), 0 for SPICE's places; a pass whose
    stabilization is not worked out yet (every tile registered: seconds to a minute) answers as a new pass does.
    exposure: exposure normalization smoothed over that many frames (exposure_gains), 0 for none; the same.
    sharpen False: a filled pass's frame before detail() (movie_frame), named apart (_d0); the same picture as
    sharpen True for any other pass."""
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    steady, exposure = steady_of(u, steady), exposure_of(exposure)
    rec = _record(u, cache)
    if not wait and ((_footprint_kept(u, rec) is None and
                      not all(os.path.exists(os.path.join(folder(u, cache), f)) for f in (PLAN_FILE, _footprint_file(u))))
                     or (steady and not _steady_ready(u, cache, rec)) or (exposure and not _exposure_ready(u, cache, rec, (bool(colour), bool(centre), 0)))):
        # (footprint: a mosaic movie played as a movie, the Mosaic / Movie switch on Movie, needs the footprint its
        # rolling picture does without, or this answers "working out the pass" for ever)
        warm_movie(u, n, ahead, cache, steady=bool(steady), exposure=(bool(colour), bool(centre), 0) if exposure else None,
                   footprint=True)
        return None, {"why": "working out the pass", "observation": u["key"][1], "pass": u["key"][3],
                      **_progress(u, cache, rec)}
    # (a feature track's frames, at their steady places, are named apart from the frames it played before, and so
    # are a stabilized movie's, by its smoothing; a filled pass's frame before detail() by _d0)
    filled = not sharpen and sharpens(plan(u, cache)["display_scale"])
    path = os.path.join(folder(u, cache), MOVIE_DIR, str(size),
                        f"{n}_{trail}_{int(bool(colour))}{'_c2' if centre else ''}{'_k2' if u.get('track') else ''}"
                        f"{f'_s{steady}' if steady else ''}{f'_e{exposure}r{EXPOSURE_RULE}' if exposure else ''}{'_d0' if not sharpen and filled else ''}.webp")
    report, meta = {}, path[:-4] + "json"

    def make():
        # a strip (smaller than the sizes a window plays) of a frame already kept at one of them is that picture
        # shrunk (both are movie_frame at OUT, shrunk): the pass's tiles are not read again
        for big in MOVIE_SIZES:
            kept = os.path.join(folder(u, cache), MOVIE_DIR, str(big), os.path.basename(path))
            if size < MOVIE_SIZES[0] and os.path.exists(kept) and os.path.exists(kept[:-4] + "json"):
                im, rep = Image.open(kept), reel.report_of(kept[:-4] + "json")
                im.load()
                break
        else:
            with _asking():
                im, rep = movie_frame(u, n, cache, trail, colour, centre=centre, steady=steady, exposure=exposure, sharpen=sharpen)
        report.update(rep)
        reel._cached(meta, lambda: json.dumps(rep).encode())
        reel.keep_report(meta, rep)
        if im is None:
            raise LookupError(rep.get("why"))
        if max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        reel.save_webp(im, buf, quality=QUALITY, method=4)
        keep_picture_map(im, path)
        return buf.getvalue()

    try:
        with _making_movie(path):
            data = reel._cached(path, make)
        calibration.hdr_note_served(path, path[:-len(".webp")] + ".hdr.webp")
    except LookupError:
        return None, report
    finally:
        if ahead:
            warm_movie(u, n + 1, ahead, cache)
    if not report:
        report = reel.report_of(meta)
    return data, report


def _progress(u, cache, rec):
    """How far a pass being worked out is: {"made": tiles made (as far as memory knows; 0 while its plan is worked
    out), "of": its frames}, what the window says while it waits ("PREPARING MOVIE · 12 OF 36 FRAMES")."""
    rec = rec or _record(u, cache)
    if rec is None:
        return {"made": 0, "of": len(u["frames"])}
    with _lock:
        made = len(set(rec.get("tiles") or ()) | set(rec.get("made") or ()))
    return {"made": min(made, len(u["frames"])), "of": len(u["frames"])}


_movie_ahead = {}   # pass key -> (first, last) tile a movie wants made ahead; MOVIE_WORKERS threads per pass make them
MOVIE_WORKERS = int(os.environ.get("CASSINI_MOVIE_WORKERS", "2"))
_movie_background = threading.Semaphore(MOVIE_WORKERS)   # movie frames made ahead, beside the mosaics' one at a time


def warm_movie(u, n, ahead, cache, steady=False, exposure=None, footprint=False):
    """A movie is at frame n of the pass: work out its plan and make tiles n .. n+ahead in the background, from
    where the movie is rather than from the pass's start, MOVIE_WORKERS at once (a fast movie at high playback
    speed needs several frames a second). steady: the pass's stabilization chain too (steady_chain); exposure: (colour, centre, steady) of its brightness chain (exposure_chain) to work out too.
    The pass's movie footprint (movie_footprint) is worked out too, except for a mosaic movie's rolling picture,
    which does without it; footprint True: a mosaic movie's too (movie_webp: the pass played as a movie)."""
    mode = calibration.mode()
    key, last = (u["key"], mode), min(n + ahead, len(u["frames"]) - 1)
    rolling = u.get("kind", "movie" if u.get("movie") else None) == "mosaic_movie" and not footprint
    # nothing to make (the plan, footprint and those tiles are in memory): no workers
    rec = _record(u, cache)
    if rec is not None and (_footprint_kept(u, rec) is not None or rolling) \
            and _all_made(u, cache, rec["plan"], n, last, look=True) and not (steady and not _steady_ready(u, cache, rec)) \
            and not (exposure and not _exposure_ready(u, cache, rec, exposure)):
        return
    with _lock:
        running = key in _movie_ahead
        _movie_ahead[key] = (n, last)
        if running:
            return

    taking = set()

    def run():
        try:
            with _movie_background, calibration.in_mode(mode):
                p = plan(u, cache)
                if not rolling:
                    movie_footprint(u, cache, p)
                if (steady and not _steady_ready(u, cache, _record(u, cache))) or \
                        (exposure and not _exposure_ready(u, cache, _record(u, cache), exposure)):
                    # a chain draws every tile of the pass, one after another under the pass's lock: on a cold pass
                    # the workers make them first, side by side, from the frame asked for on (the same tiles, made
                    # sooner: 67 tiles of 021TI REGMAPNA001 took 67 s one at a time before its first frame)
                    every = list(range(n, len(u["frames"]))) + list(range(0, n))
                    while True:
                        with _lock:
                            j = next((j for j in every if j not in taking), None)
                            if j is None:
                                break
                            taking.add(j)
                        if not _has_tile(u, j, cache, p):
                            _yield()
                            tile(u, j, cache, p["display_scale"])
                # (asked for by name, the chains are worked out for any pass: a mosaic movie played as a steady
                # movie waits on them as any movie does)
                if steady:
                    steady_chain(u, cache, p)
                if exposure:
                    exposure_chain(u, cache, p, *exposure)
                while True:
                    with _lock:
                        first, last = _movie_ahead.get(key, (0, -1))
                    todo = [j for j in range(first, last + 1) if j not in taking and not _has_tile(u, j, cache, p)]
                    with _lock:
                        todo = [j for j in todo if j not in taking]
                        if not todo:
                            break
                        taking.add(todo[0])
                    _yield()
                    tile(u, todo[0], cache, p["display_scale"])
        except Exception as e:
            print(f"movie {key} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                workers[0] -= 1
                if not workers[0]:
                    _movie_ahead.pop(key, None)

    workers = [MOVIE_WORKERS]
    for _ in range(MOVIE_WORKERS):
        threading.Thread(target=run, daemon=True).start()


def slots(u):
    """The place of each frame of pass u (places), with the camera's drift over a long mosaic movie taken out:
    places closer than half the pass's step (the median jump from one place to the next in one filter) are one
    slot. The Jupiter approach's 2x2s drift over nine laps by more than mosaic.min_step, so the classifier gives
    their last laps places of their own (8 for 4 tiles), and without this a lap over the drifted places would run
    on into the next (lap_of) and a drifted tile would stay up beside its own older copy (rolling_layout). None
    for a frame with no place."""
    if "slots" in u:
        return u["slots"]
    u["slots"] = _slot_of(u, places(u))
    return u["slots"]


def _slot_of(u, where):
    """(slots) the slot of each frame of pass u, its places being where."""
    at, last, steps = {}, {}, []
    for fr, i in zip(u["frames"], where):
        x, y, z = fr[5:8]
        if i is None or not z or not u.get("z"):
            continue
        p = (-x * z / u["z"], -y * z / u["z"])
        at.setdefault(i, []).append(p)
        if fr[2] in last and last[fr[2]][0] != i:
            steps.append(max(abs(p[0] - last[fr[2]][1][0]), abs(p[1] - last[fr[2]][1][1])))
        last[fr[2]] = (i, p)
    near = 0.5 * float(np.median(steps)) if steps else 0.0
    centre = {i: np.mean(v, 0) for i, v in at.items()}
    parent = {i: i for i in centre}

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    if near > mosaic.min_step * FRAME:
        for a in sorted(centre):
            for b in sorted(centre):
                if b > a and np.abs(centre[a] - centre[b]).max() < near and root(a) != root(b):
                    parent[max(root(a), root(b))] = min(root(a), root(b))
    return [root(i) if i in parent else i for i in where]


def lap_of(u):
    """The lap each frame of pass u is in: how many times the camera has come back to a slot in one filter by that
    frame (a run of frames at one slot counts once), the most over its filters; 1 for a pass that never comes back."""
    if "lap_of" in u:
        return u["lap_of"]
    runs, lap, out = {}, 1, []
    for fr, i in zip(u["frames"], slots(u) if u["frames"] else []):
        if i is not None:
            seq = runs.setdefault(fr[2], [])
            if not seq or seq[-1] != i:
                seq.append(i)
                lap = max(lap, seq.count(i))
        out.append(lap)
    u["lap_of"] = out
    return out


def lap_ends(u):
    """The frames (indices into u["frames"]) that finish a whole lap of a mosaic movie: the last frame before the
    camera comes back to a slot it has already taken in this lap (lap_of), or the pass's last frame, of a lap that
    took every slot in every filter the pass's laps usually take (the median over its laps: a lap that started or
    stopped short, or missed a filter's tile, is not whole). At one of them every tile is new, so the rolling
    picture there (rolling_layout) is a whole new mosaic (Settings > Movie > Mosaic movie frames: Whole mosaics),
    rather than new tiles over the last lap's, which Jupiter has turned a sixth of a turn away from. When no lap
    is whole, the pass's last frame. [] for a pass that is not a mosaic movie."""
    if u.get("kind") != "mosaic_movie" or not u["frames"]:
        return []
    lap = lap_of(u)
    ends = [j for j in range(len(lap) - 1) if lap[j + 1] > lap[j]] + [len(lap) - 1]
    took = {n: {} for n in set(lap)}
    for fr, i, n in zip(u["frames"], slots(u), lap):
        if i is not None:
            took[n].setdefault(fr[2], set()).add(i)
    filters = {f for t in took.values() for f in t}
    need = {f: float(np.median([len(t.get(f, ())) for t in took.values()])) for f in filters}
    whole = [j for j in ends if all(len(took[lap[j]].get(f, ())) >= need[f] for f in filters)]
    return whole or ends[-1:]


def lap_end(frame_id):
    """True when frame_id finishes a lap of a mosaic movie (lap_ends), False for another frame of one, None when
    it is in no mosaic movie."""
    found = unit_of(frame_id)
    if not found or found[0].get("kind") != "mosaic_movie":
        return None
    u, n = found
    return u["frames"][n][1] == frame_id and n in lap_ends(u)


def pass_info(frame_id, cache):
    """The pass frame_id is in, for the movie's filmstrip: its observation, which frame this is and every frame
    of it ([id, seconds since 1970, filter]), and how the server judged it; None when it is in no pass."""
    found = unit_of(frame_id)
    if not found:
        return None
    u, n = found
    ts = [fr[3] for fr in u["frames"]]
    gaps = np.diff(ts) if len(ts) > 1 else []
    return {"observation": u["key"][1], "target": u["key"][0], "camera": u["key"][2], "pass": u["key"][3], "n": n,
            "movie": bool(u["movie"]), "mosaic": bool(u["mosaic"]),
            "cadence": round(float(np.median(gaps)), 1) if len(gaps) else None,
            "frames": [[fr[1], fr[3], fr[2]] for fr in u["frames"]]}


def places(u):
    """The place (pointing) index of each frame of the pass: u["place"] from the classifier when it has one,
    otherwise worked out here the same way, frames closer than mosaic.min_step of a frame (at the pass's
    reference distance) being one place."""
    if u.get("place"):
        return u["place"]
    out, seen = [], []
    for *_, x, y, z in u["frames"]:
        if not z:
            out.append(out[-1] if out else 0)
            continue
        pt = (-x * z / u["z"], -y * z / u["z"])
        for i, q in enumerate(seen):
            if max(abs(pt[0] - q[0]), abs(pt[1] - q[1])) < mosaic.min_step * FRAME:
                out.append(i)
                break
        else:
            seen.append(pt)
            out.append(len(seen) - 1)
    return out


FADE_MAX = 120       # most frames a mosaic movie's older tiles fade over (Settings > Movie > Older tiles fade over)
FADE_PERSIST = 35    # how bright a faded tile stays, per cent (Settings > Movie > Faded tiles keep)


def fade_style(fade=0, persist=FADE_PERSIST):
    """A mosaic movie's fade as (frames, per cent), clamped; (0, 0) when off, so every name made without one stays
    as it was."""
    fade = max(0, min(FADE_MAX, int(fade or 0)))
    return (fade, max(0, min(100, int(persist)))) if fade else (0, 0)


def _fade_weight(age, fade):
    """How bright a tile age frames older than the newest drawn stays when older tiles fade over fade[0] frames
    down to fade[1] per cent: 1 for the newest, falling evenly to that floor and staying there."""
    floor = fade[1] / 100
    return 1.0 if age <= 0 else max(floor, 1 - (1 - floor) * age / fade[0])


# ---------- a mosaic movie's laps on one level ----------
# Each lap's copy of a place replaces the copy before it at its own brightness (its exposure, the light on it), so
# a single panel flashed darker or brighter than the mosaic round it, then back, lap after lap (SPOLEDYN001: 20 such
# swings). Each copy is brought to the level of the copy it replaces, one broad gain over the ground both see, so
# the laps change only where the scene does. A step bigger than LAP_BELIEVE is another scene (a limb come into
# view), not an exposure: that copy is drawn as it came, and the copies after it are brought to it.
LAP_SIDE = 128           # px: the side of a frame the two copies are measured at
LAP_LIT = 0.1            # of the brighter copy's bright end: the pixels measured (the body, not the sky's noise)
LAP_MIN = 400            # lit pixels both copies share, at LAP_SIDE, for a match; fewer, and the copy stays as it is
LAP_BELIEVE = 3.2        # the largest step (linear) from one copy to the next taken for an exposure (either way):
                         # SPOLEDYN001's short and long exposures of one place differ 2.6-2.8 times
LAP_GAIN = (0.25, 4.0)   # the furthest a copy's gain goes, over every lap
LAP_CELLS = 3            # the shared ground is also measured in LAP_CELLS x LAP_CELLS parts ...
LAP_EVEN = 0.5           # ... and a step is an exposure only when the parts agree: the spread (std) of their log steps
                         # under LAP_EVEN x the step's own log. An exposure scales the whole frame alike (SPOLEDYN001's
                         # 2.6-2.8x steps: parts within 0.01 log, 0.18 at worst); a step that differs part to part is
                         # the scene's own (Cassini closing in on the 2017-04-26 north pole movie, 271SA NPOLMOV001: the
                         # night side's column measured 0.7x a lap, its parts 0.23-0.86x, and its tiles were drawn at
                         # half brightness by lap 3, dark blocks in the mosaic)
LAP_FREE = 0.12         # log: a step smaller than this (about 12% either way) is the scene's own change, kept as it is.
                         # Taken out lap after lap, the slow brightening of the 2013 hexagon movie's places (2-5% a lap,
                         # more at some places than others) left them up to twice as bright as each other by its end
LAP_RULE = "g3s"         # in the pictures' names: these gains, the base drawn under the picture, and whole colour sets (set_laps)


def _lap_prev(u):
    """For each frame of a mosaic movie, the frame before it at its slot in its filter (the copy it replaces), or
    None."""
    if "_lap_prev" in u:
        return u["_lap_prev"]
    where, last, out = slots(u), {}, []
    for j, fr in enumerate(u["frames"]):
        key = (where[j], fr[2]) if where[j] is not None else None
        out.append(last.get(key) if key else None)
        if key:
            last[key] = j
    u["_lap_prev"] = out
    return out


def _lap_step(u, p, cache, a, b):
    """The broad gain that brings copy b of a place to copy a's level (tile reports), on linear brightness over
    the lit ground both cover; 1.0 when they share too little lit ground; None when the step is a change of scene
    (past LAP_BELIEVE)."""
    memo = u.setdefault("_lap_step", {})
    key = (_tiles(u, cache, p["display_scale"]), a["n"], b["n"])
    if key in memo:
        return memo[key]
    k = LAP_SIDE / FRAME
    boxes = []
    for t in (a, b):
        bx, by, bw, bh = t["box"]
        boxes.append((round((t["offset"][0] + bx) * k), round((t["offset"][1] + by) * k), max(1, round(bw * k)), max(1, round(bh * k))))
    x0, y0 = max(q[0] for q in boxes), max(q[1] for q in boxes)
    x1, y1 = min(q[0] + q[2] for q in boxes), min(q[1] + q[3] for q in boxes)
    g = 1.0
    pics = [_pic(u, cache, p["display_scale"], t) for t in (a, b)]
    if not all(os.path.exists(x) for x in pics):
        return g   # (a layout worked out without the pictures: nothing to measure)
    if x1 > x0 and y1 > y0:
        gamma = p["display_scale"].get("gamma", 2.2)
        cut = []
        for pic, (left, top, sw, sh) in zip(pics, boxes):
            part = _part(pic, sw, sh)[y0 - top:y1 - top, x0 - left:x1 - left]
            cut.append((calibration.decode(part[..., 0].astype(np.float32) / 255, gamma), part[..., 3] > 250))
        (la, ma), (lb, mb) = cut
        both = ma & mb
        if both.sum() >= LAP_MIN:
            top = max(float(np.percentile(la[both], 99)), float(np.percentile(lb[both], 99)))
            lit = both & (np.maximum(la, lb) > LAP_LIT * top)
            if lit.sum() >= LAP_MIN and lb[lit].mean() > 0:
                step = float(la[lit].mean() / lb[lit].mean())
                g = step if 1 / LAP_BELIEVE <= step <= LAP_BELIEVE else None
                if g is not None and not _lap_even(la, lb, lit, step):
                    g = 1.0   # (the scene's own change, kept as it is)
    memo[key] = g
    return g


def _lap_even(la, lb, lit, step):
    """(_lap_step) Whether a step between two copies is alike over their shared lit ground, as an exposure's is: the
    ground cut in LAP_CELLS x LAP_CELLS parts, the spread of the parts' log steps under LAP_EVEN x |log step|. True
    when fewer than three parts have lit ground enough to say (LAP_MIN / LAP_CELLS^2 pixels each)."""
    H, W = lit.shape
    logs = []
    for i in range(LAP_CELLS):
        for j in range(LAP_CELLS):
            s = (slice(i * H // LAP_CELLS, (i + 1) * H // LAP_CELLS), slice(j * W // LAP_CELLS, (j + 1) * W // LAP_CELLS))
            m = lit[s]
            if m.sum() >= LAP_MIN / LAP_CELLS ** 2:
                a, b = float(la[s][m].mean()), float(lb[s][m].mean())
                if a > 0 and b > 0:
                    logs.append(math.log(a / b))
    if len(logs) < 3:
        return True
    return float(np.std(logs)) < LAP_EVEN * abs(math.log(step))


def _lap_lead(u):
    """For each frame of a mosaic movie, the frame whose lap step its copy takes (lap_gain): the first frame of its
    filter at its slot in its lap (lap_of) takes the step of the first frame of the lap at that slot, whatever its
    filter, so every filter of a place moves by one gain and the colour stays as the filters gave it; a later frame
    of the same filter there (a second exposure at one place) takes its own step to the copy before it, as before.
    The frame itself when it leads, or has no slot."""
    if "_lap_lead" in u:
        return u["_lap_lead"]
    where, lap, first, out = slots(u), lap_of(u), {}, []
    for j, fr in enumerate(u["frames"]):
        if where[j] is None:
            out.append(j)
            continue
        here = first.setdefault((where[j], lap[j]), {})
        out.append(here.setdefault("lead", j) if fr[2] not in here else j)
        here.setdefault(fr[2], j)
    u["_lap_lead"] = out
    return out


def lap_gain(u, p, cache, j, report, made_only=False, skipped=None):
    """The gain tile j of a mosaic movie is drawn at: its place's copies, from the first, each brought to the one
    before it (_lap_step), within LAP_GAIN; a copy of another scene starts again at 1. The step is one per place and
    lap (_lap_lead: measured on the lap's first tile there), not one per filter: chained per filter, each colour
    drifted on its own (a place's RED copy of the 2012 north pole map movie's last lap stepped down 12% while its
    GRN and BL1 did not: the place turned blue-green). A step under LAP_FREE is the scene's own and kept. report(i): tile i's
    report, or None when it is not made (made_only), which then goes in skipped and ends the chain there: the
    picture is not the frame's own yet (its name says which gains it drew)."""
    prev, lead = _lap_prev(u), _lap_lead(u)

    def placed(i):
        # the newest copy at or before i (back through the copies of its filter at its slot) that is placed; None
        # when there is none, or one is not made yet (skipped)
        while i is not None:
            t = report(i)
            if t is None:
                if skipped is not None and i not in skipped:
                    skipped.append(i)
                return None
            if "offset" in t:
                return i
            i = prev[i]
        return None
    links, cur = [], j
    while True:
        b = placed(lead[cur])
        if b is None:
            break
        if lead[b] != b:
            # (the lap's lead there is not placed: the copy before it, which takes its own lap's step)
            cur = b
            continue
        a = placed(prev[b])
        if a is None:
            break
        links.append((a, b))
        cur = a
    g = 1.0
    for a, b in links[::-1]:
        step = _lap_step(u, p, cache, report(a), report(b))
        if step is not None and abs(math.log(step)) < LAP_FREE:
            continue   # (the scene's own slow change, kept)
        g = 1.0 if step is None else float(np.clip(g * step, *LAP_GAIN))
    return round(g, 4)


def rolling_base(u, p, tiles, used):
    """The tiles (their n) a mosaic movie's picture draws in its luminance base, or none when the filters used cover
    every place it shows: the pass's base tiles (lum_frames) and, at a slot no base tile has reached yet, a tile
    already there (of the filters drawn, else of the base's, else of any: the most taken so far, the newest), so a
    place shown in one filter stays when the picture changes filters (a pass whose gray filter starts a lap after
    its other filters, or after its polarized frames)."""
    frames, where, allowed = lum_frames(u, p), slots(u), set(_luminance(p)["filters"])
    base = [t for t in tiles if t["n"] in frames]
    have = {where[t["n"]] for t in base if where[t["n"]] is not None}
    # (ties: the filter taken first, as the picture's filter is chosen before a gray tile is placed)
    taken = collections.Counter(t["filter"] for t in tiles)
    first = {f: -i for i, f in enumerate(dict.fromkeys(t["filter"] for t in tiles))}
    rank = lambda t: (t["filter"] in used, t["filter"] in allowed, taken[t["filter"]], first[t["filter"]], t["n"])
    fill = {}
    for t in tiles:
        key = where[t["n"]] if where[t["n"]] is not None else ("frame", t["n"])
        if t["n"] not in frames and key not in have and (key not in fill or rank(t) > rank(fill[key])):
            fill[key] = t
    base += fill.values()
    return {t["n"] for t in base} if lum_base(u, p, tiles, used, base) else set()


def _drawable(report):
    """(set_laps) whether tile j is a copy a colour set at its place can be made of: placed, not partial, no lines
    lost past MOVIE_LOST and something lit (patchy); a tile not made yet (report(j) None) is taken as one, so the
    picture drawn while it is made (made_only, named apart) waits for nothing."""
    def ok(j):
        t = report(j) if report is not None else None
        return t is None or ("offset" in t and not partial(t) and not patchy(t))
    return ok


def _whole_sets(u, upto, colour, report=None):
    """{slot: (lap, {filter: frame}, the frame that completed it)} of the newest lap at each slot of a mosaic movie
    that has taken a copy of every colour filter there that can be drawn (_drawable) by frame upto, and in order of
    frames the slots as each first completes ({slot: frame}): set_laps' and colour_start's one scan."""
    where, lap, ok = slots(u), lap_of(u), _drawable(report)
    want = set(colour)
    took, best, first = {}, {}, {}
    for j in range(upto + 1):
        f = u["frames"][j][2]
        if f in want and where[j] is not None and ok(j):
            got = took.setdefault((where[j], lap[j]), {})
            got[f] = j
            if len(got) == len(want) and (where[j] not in best or lap[j] >= best[where[j]][0]):
                best[where[j]] = (lap[j], dict(got), j)
                first.setdefault(where[j], j)
    return best, first


def set_laps(u, n, colour, report=None):
    """For a colour mosaic movie at frame n: {(slot, filter): the newest of its frames there that the picture draws}
    for each colour filter at each slot where a lap has taken all of them by then, the frame of that filter in the
    newest such lap (lap_of). A lap's first colour copy at a place used to go up at once over the last lap's other
    two: the place drew one filter from this lap and two from the last, each filter's mosaic of the pass laid with
    its own newest copy on top, so where two places overlap one filter showed one and another the other (the 2013
    hexagon movie, 193SA NPOLMOV001: whole panels green at a RED frame, magenta, and grey steps; 175SA NPOLMAP001:
    salmon and purple blocks). Only copies that can be drawn count (report: tile j's report, _drawable): a lap whose
    copy of one filter SPICE could not place, or that came down partial, leaves the lap before it up whole, rather than
    its other two filters over that filter's older copy. {} for a pass that is not in colour."""
    if not colour or len(colour) < 2:
        return {}
    best, _ = _whole_sets(u, n, colour, report)
    return {(slot, f): j for slot, (_, got, _) in best.items() for f, j in got.items()}


def colour_start(u, colour, report=None):
    """The frame a colour mosaic movie's picture starts at: the first by which every slot its first lap takes in a
    colour filter, and that its first two laps complete, has a whole colour set (_whole_sets). Its frames before then show the
    picture there (rolling_layout), so the film opens on colour rather than on grey panels filling in one filter at a
    time (2000 Jupiter, C23RI RMOV001; 2004 Saturn, 00ASA 2X2MOVIEA001; the 2015 equator map's blown grey lead-in,
    221SA EQUAMAP001). 0 for a pass that is not in colour, or whose first lap's slots never complete."""
    if not colour or len(colour) < 2 or not u["frames"]:
        return 0
    where, lap = slots(u), lap_of(u)
    # (looked for over its first two laps: a slot the second lap does not complete either is not waited for, and the
    # pass's later tiles are not made for it)
    upto = max(j for j in range(len(lap)) if lap[j] <= 2)
    best, first = _whole_sets(u, upto, colour, report)
    lap1 = {where[j] for j, fr in enumerate(u["frames"]) if lap[j] == 1 and where[j] is not None and fr[2] in colour}
    need = [first[slot] for slot in lap1 if slot in first]
    return max(need) if need else 0


CLIP_UNDER = 0.05   # of a frame: (clipped_under) a mosaic movie's tile the camera saturated over this much, and OVER_STEP
                    # times as much as the median of the picture's other tiles of its filter, goes under them


def clipped_under(tiles):
    """(rolling_layout) The tiles (n) of a mosaic movie's picture drawn under the others: saturated CLIP_UNDER of the
    frame or more, and OVER_STEP times the median of the picture's other tiles of its filter. Its saturated part is
    drawn white in its band, while the other bands of its place did not saturate there, and the color mix turned it
    a green or magenta blotch: the 2017-04-26 north pole movie's pointings at 03:53 and 05:22 (271SA_NPOLMOV001:
    VIO 16-33%, GRN 11-29%, CB3 7-21%, RED 4-15% saturated, the others under 1%). Under, its neighbours' frames show
    wherever they reach. A long exposure taken again in a colour set (long_repeats) goes under the same way."""
    out, by = set(), {}
    for t in tiles:
        if "offset" in t:
            by.setdefault(t["filter"], []).append(t)
    for mine in by.values():
        if len(mine) < MIN_PLACES:
            continue
        for t in mine:
            s = t.get("saturated", 0.0)
            if s < CLIP_UNDER:
                continue
            others = [o.get("saturated", 0.0) for o in mine if o["n"] != t["n"]]
            if s >= OVER_STEP * float(np.median(others)):
                out.add(t["n"])
    return out


def clipped_pointings(u, tiles):
    """(clipped_under) The tiles of pass u that go under: those clipped_under picks and every tile of the same pointing
    (slot and lap), so the pointing's filters stay together."""
    low = clipped_under(tiles)
    if low:
        where, lap = slots(u), lap_of(u)
        at = {(where[j], lap[j]) for j in low if where[j] is not None}
        low |= {t["n"] for t in tiles if where[t["n"]] is not None and (where[t["n"]], lap[t["n"]]) in at}
    return low


def rolling_layout(u, n, cache, laps=1, made_only=False, skipped=None, fade=(0, 0)):
    """What a mosaic movie (a raster repeated over the same places: kind "mosaic_movie") shows at frame n, in the
    form of layout(): every place's newest tile of each filter taken by then, so the mosaic never empties when a
    new lap begins and each tile replaces its own earlier copy (laps=1, a time-lapse); laps=N keeps the N newest
    copies of each place, older under newer (a rolling mosaic). Drawn by so_far through filter_mosaic and
    mosaic.compose like the pass's mosaic, on its scale and in its view: the colour filters where all three
    cover, over the luminance base (lum_base) everywhere a tile is, so the picture never shrinks when a colour set
    completes (rolling_base: the tiles marked "base"). Each copy is drawn at its lap gain (lap_gain: brought to the copy it replaces). The tiles drawn
    carry "drawn" (the colour's or the base's), which the name counts. made_only: only tile n is made here, the
    other places show the tiles already made (a window playing fast never waits on the tiles it missed;
    tiles_ahead makes them); skipped (a list) gets the tiles left out for that, so the caller knows the picture
    is not yet the frame's own. fade (fade_style): older tiles fade (Rolling) rather than stay as bright as the
    newest (Time-lapse): each drawn tile gets a "fade" field (0-1, _fade_weight of its age in frames behind the
    newest drawn), which _faded applies to the composed picture, and the picture's name says so."""
    p = plan(u, cache)
    where = slots(u)
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _lock:
        kept = dict(rec["tiles"]) if rec is not None else {}
    there = rec["tiles_dir"] if rec is not None else _tiles(u, cache, p["display_scale"])

    def report(j):
        t = kept.get(j)
        if t is None:
            if made_only and j != n and not os.path.exists(os.path.join(there, f"{j}.json")):
                return None
            t = kept[j] = tile(u, j, cache, p["display_scale"])
        return t
    # a colour pass opens on its first whole colour picture (colour_start): the frames before it show it
    n = max(n, colour_start(u, p["colour"], report)) if p["colour"] else n
    # a colour pass's colour filters at a place show the copies of its newest whole set (set_laps): a lap's first
    # colour copy waits for the others, so the three filters at a place, and which place lies over which, are the
    # same lap's
    held = set_laps(u, n, p["colour"], report)
    # ... and each place's set lies over or under another's as a whole, by the frame that completed it, so where two
    # places overlap all three filters show the same place (by frame alone, a set taken a filter at a time across the
    # places, every place's RED then every place's GRN, could lay one place's RED over the other's and its GRN under)
    rank = {}
    for (slot, _), j in held.items():
        rank[slot] = max(rank.get(slot, -1), j)
    rank = {j: rank[slot] for (slot, _), j in held.items()}
    # each place's newest copies that are there to draw: a copy not made yet (made_only) or one SPICE could not
    # place leaves the copy before it up, so a place never drops out of the mosaic and comes back
    keep, seen, spare = [], {}, {}
    for j in range(n, -1, -1):
        # (a frame the classifier gave no place stays up on its own, under the newer ones, rather than taking the
        # place of every other such frame)
        key = (where[j] if where[j] is not None else ("frame", j), u["frames"][j][2])
        if seen.get(key, 0) >= laps:
            continue
        if key in held and j > held[key]:
            continue
        t = report(j)
        if t is None:
            if skipped is not None:
                skipped.append(j)
            continue
        if "offset" not in t:
            continue
        if partial(t) or patchy(t):
            # a partial copy (most of it lost in downlink), or one with lines lost or nothing lit (patchy), holds the
            # place's whole copy before it up instead, and is drawn (a partial one under the rest, _window) only where
            # its place has no whole copy
            spare.setdefault(key, t)
            continue
        seen[key] = seen.get(key, 0) + 1
        keep.append(t)
    keep += [t for key, t in spare.items() if not seen.get(key)]
    # a copy the camera saturated much more than the picture's other tiles of its filter goes under them (clipped_under)
    # (every filter of that pointing alike: one band under and the others over put the pole's eye in two places, a
    # blue spot at 05:32 on the 2017-04-26 north pole movie)
    low = clipped_pointings(u, keep)
    keep = [dict(t, under=True) if t["n"] in low else t for t in keep]
    # (in the order they are drawn, so a fade's brightness map, _faded and the page's, lays them alike)
    tiles = under_first(sorted(keep, key=lambda t: (rank.get(t["n"], t["n"]), t["n"])))
    count = {}
    for t in tiles:
        count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not count:
        return None
    rect = view_rect(p, tiles)
    colour = p["colour"]
    used = colour if colour and all(count.get(f) for f in colour) else [p["grey"] if count.get(p["grey"]) else max(count, key=count.get)]
    base = rolling_base(u, p, tiles, used)
    gamma = p["display_scale"].get("gamma", 2.2)
    # copies of the tile dicts, since the pass's record keeps the originals
    out = []
    for t in tiles:
        g = lap_gain(u, p, cache, t["n"], report, made_only, skipped)
        t = dict(t, gain=g, gamma=gamma, base=t["n"] in base) if g != 1.0 else dict(t, base=t["n"] in base)
        if t["filter"] in used or t["base"]:
            t["drawn"] = True
        out.append(t)
    tiles = out
    drawn = [t for t in tiles if t.get("drawn")]
    ids = hashlib.sha1((LAP_RULE + ":" + ",".join((f"{t['n']}x{t['gain']}" if "gain" in t else str(t["n"])) + ("u" if t["n"] in low else "")
                                                  for t in drawn)).encode()).hexdigest()[:12]
    if not fade[0]:
        return p, tiles, rect, count, used, f"lap-{laps}-{ids}"
    # ages from the newest tile drawn, so frames of a filter the picture does not draw share its picture
    newest = max(t["n"] for t in drawn)
    tiles = [dict(t, fade=_fade_weight(newest - t["n"], fade)) for t in tiles]
    return p, tiles, rect, count, used, f"lap-{laps}-f{fade[0]}p{fade[1]}-{ids}"


FADE_SCALE = 4   # the fade's brightness map is worked out at this fraction of the picture's size (it is smooth)


def _faded(u, made, cache):
    """The post step (_make_mosaic) of a mosaic movie whose older tiles fade: the composed picture's colour
    multiplied by each place's fade, a map drawn from the tiles' own alpha oldest first (newer over older, as
    compose draws them, soft at their feathered edges) at 1/FADE_SCALE of the picture's size. Done after compose,
    so the filter mosaics stay the time-lapse's own (grown a tile a frame, _roll, and shared with it) and the
    seams are solved on the tiles as they are."""
    import cv2
    p, tiles, rect, _, used, _ = made
    there = _tiles(u, cache, p["display_scale"])

    def post(im):
        W, H = im.size
        w, h = max(1, W // FADE_SCALE), max(1, H // FADE_SCALE)
        light = np.ones((h, w), np.float32)
        for t in tiles:
            if not t.get("drawn") or "offset" not in t:
                continue
            part = _fade_part(t, rect, w, h, there)
            if part is None:
                continue
            (a0, b0, a1, b1), a = part
            a = a.astype(np.float32) / 255
            light[b0:b1, a0:a1] = light[b0:b1, a0:a1] * (1 - a) + t.get("fade", 1.0) * a
        light = cv2.resize(light, (W, H), interpolation=cv2.INTER_LINEAR)
        rgba = np.asarray(im.convert("RGBA")).astype(np.float32)
        rgba[..., :3] *= light[..., None]
        return Image.fromarray((rgba + 0.5).clip(0, 255).astype(np.uint8), "RGBA")
    return post


def _fade_part(t, rect, w, h, there):
    """Where tile t lies on a fade's brightness map (w x h, the view rect) and its alpha there (uint8), or None
    when it is off the map: ((a0, b0, a1, b1), alpha)."""
    k = w / rect[2]
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    a0, b0, a1, b1 = max(left, 0), max(top, 0), min(left + sw, w), min(top + sh, h)
    if a1 <= a0 or b1 <= b0:
        return None
    return (a0, b0, a1, b1), _part(os.path.join(there, f"{t['n']}.png"), sw, sh)[b0 - top:b1 - top, a0 - left:a1 - left, 3]


def fade_table(frame_id, cache, laps=1, W=0, H=0):
    """What a browser needs to fade a mosaic movie's older tiles by itself (steady-local.html, cassiniFadeLocal),
    on the time-lapse picture the server already has (fade 0, W x H px as made at OUT), for any fade and persistence:
    every frame's drawn tiles and the filters it draws (rolling_layout at laps), and each tile's place and alpha on
    the fade's brightness map (_fade_part, the map 1/FADE_SCALE of the picture; zlib, base64), so _faded's post step is worked out
    in the page. None when the frame is in no mosaic movie; {"working": true} while some of its tiles are not made
    (the page asks the server for the faded pictures meanwhile)."""
    import base64
    import zlib
    found = unit_of(frame_id)
    if not found or found[1] < 0 or found[0].get("kind") != "mosaic_movie":
        return None
    u = found[0]
    if not W or not H:
        return {"local": False}
    p = plan(u, cache)
    there = _tiles(u, cache, p["display_scale"])
    w, h = max(1, W // FADE_SCALE), max(1, H // FADE_SCALE)
    frames, parts, rect = [], {}, None
    for j in range(len(u["frames"])):
        skipped = []
        made = rolling_layout(u, j, cache, laps, made_only=True, skipped=skipped)
        if skipped:
            tiles_ahead(u, j, cache)
            return {"working": True}
        if not made:
            frames.append(None)
            continue
        _, tiles, rect, _, used, _ = made
        drawn = [t for t in tiles if t.get("drawn") and "offset" in t]
        frames.append({"n": [t["n"] for t in drawn], "newest": max([t["n"] for t in drawn] or [j])})
        for t in drawn:
            if str(t["n"]) not in parts:
                part = _fade_part(t, rect, w, h, there)
                parts[str(t["n"])] = None if part is None else {
                    "at": list(part[0]), "alpha": base64.b64encode(zlib.compress(np.ascontiguousarray(part[1]).tobytes(), 6)).decode()}
    return {"local": True, "laps": laps, "W": W, "H": H, "w": w, "h": h, "frames": frames, "parts": parts,
            "ids": [fr[1] for fr in u["frames"]], "fade_max": FADE_MAX}


def _rolling_picture(u, n, size, cache, laps, slots, fmt, out, made_only, read=True, skipped=None, fade=(0, 0)):
    """(WebP, report) of the pass's mosaic movie at frame n, made once and kept; None before any tile is placed.
    One frame's picture is made once at a time (a window's request and the one made ahead wait for each other).
    read=False (made ahead): True when the picture is in the cache already, without reading it. skipped: as
    rolling_layout's. fade: older tiles fade (fade_style), applied after compose (_faded)."""
    made = rolling_layout(u, n, cache, laps, made_only=made_only, skipped=skipped, fade=fade)
    if not made:
        return None
    post = _faded(u, made, cache) if fade[0] else None
    full = size == "full"
    path = os.path.join(drawn(u, cache), "rolling-level", f"full{out}" if full else str(size), f"{made[5]}.{fmt}")
    if os.path.exists(path):
        return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out, post) if read else True
    with _lock:
        lock = _making.setdefault(path, threading.Lock())
    token = _rolling.set(laps == 1)
    try:
        with lock:
            return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out, post)
    finally:
        _rolling.reset(token)
        with _lock:
            _making.pop(path, None)


_roll_ahead = {}   # (pass, look) -> [the frame a window is at, size, out]: the mosaic movie pictures to make ahead
ROLL_AHEAD = 10    # frames of a mosaic movie made ahead of the window playing it
ROLL_WORKERS = int(os.environ.get("CASSINI_ROLL_WORKERS", "2"))   # ... this many at once (a color picture's mix is ~1 s)


def _picture_made(rec, size, out, n, skipped, fade=(0, 0)):
    """Frame n's mosaic movie picture is made: drawn with every tile it shows (none skipped as not made yet), it is
    the frame's picture for good, and the pass's record keeps that it is made (rolling_ahead)."""
    if rec is not None and not skipped:
        with _lock:
            rec["rolled"].setdefault((size, out, fade), set()).add(n)


def rolling_ahead(u, n, size, cache, slots=None, out=OUT, fade=(0, 0)):
    """A window plays the mosaic movie at frame n: make the pictures of frames n+1 .. n+ROLL_AHEAD (their tiles
    first) in the background, in order, each grown from one before it (_roll), so the window's next requests
    are answered from the cache. ROLL_WORKERS threads per pass, each taking the next frame not taken (a picture
    waits for the tiles before it, which the other thread may be making); a later call moves them on. Waits
    while a window waits for a mosaic (_yield). fade: the window's (fade_style), so they are its pictures."""
    mode = calibration.mode()
    key = (u["key"], mode, fade)
    rec = _record(u, cache)
    with _lock:
        # every picture ahead made already (the pass's record keeps which are): no workers
        known = rec["rolled"].get((size, out, fade), ()) if rec is not None else ()
        if known and all(j in known for j in range(n + 1, min(n + ROLL_AHEAD, len(u["frames"]) - 1) + 1)):
            return
        running = key in _roll_ahead
        taken = _roll_ahead[key][3] if running else [-1]
        _roll_ahead[key] = [n, size, out, taken, ROLL_WORKERS if not running else _roll_ahead[key][4]]
        if running:
            return

    def run():
        try:
            with calibration.in_mode(mode):
                p = plan(u, cache)
                kept = _kept_tiles(u, cache, p["display_scale"])
                while True:
                    with _lock:
                        at, sz, o, taken = _roll_ahead[key][:4]
                        made = kept["rolled"].get((sz, o, fade), ()) if kept is not None else ()
                        j = max(at, taken[0]) + 1
                        while j in made:   # (made already: nothing to do)
                            j += 1
                        taken[0] = j
                    if j > min(at + ROLL_AHEAD, len(u["frames"]) - 1):
                        return
                    for i in range(at + 1, j + 1):
                        _yield()
                        tile(u, i, cache, p["display_scale"])
                    _yield()
                    # one made already is not read again
                    skipped = []
                    if _rolling_picture(u, j, sz, cache, 1, slots, "webp", o, made_only=True, read=False, skipped=skipped,
                                        fade=fade):
                        _picture_made(kept, sz, o, j, skipped, fade)
        except Exception as e:
            print(f"mosaic movie ahead {u['key']} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                _roll_ahead[key][4] -= 1
                if not _roll_ahead[key][4]:
                    _roll_ahead.pop(key, None)

    for _ in range(ROLL_WORKERS):
        threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()


def rolling_webp(frame_id, size, cache, laps=1, slots=None, fmt="webp", out=OUT, wait=False, fade=(0, 0)):
    """(WebP, report) of frame_id's pass played as a mosaic movie (rolling_layout), made once and kept; None when
    the frame is in no pass, (None, report) while the pass is being worked out (unless wait). fade: older tiles
    fade (fade_style: frames, per cent; Rolling) instead of staying as bright as the newest (Time-lapse)."""
    fade = fade_style(*fade)
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    if not wait and not os.path.exists(os.path.join(folder(u, cache), PLAN_FILE)):
        warm_movie(u, n, 6, cache)
        return None, {"why": "working out the pass", "observation": u["key"][1], "pass": u["key"][3]}
    skipped = []
    with _asking():
        res = _rolling_picture(u, n, size, cache, laps, slots, fmt, out, made_only=not wait, skipped=skipped, fade=fade)
        if res is None:
            return None, {"why": "no tile placed yet"}
    if laps == 1 and fmt == "webp":
        _picture_made(_record(u, cache), size, out, n, skipped, fade)
    # the tiles ahead, by the pass's one background thread (tiles_ahead, as a pass mosaic's), and the pictures of
    # the next frames, so a playing window finds them made (rolling_ahead)
    tiles_ahead(u, n + 1, cache)
    if laps == 1 and size != "full" and fmt == "webp":
        rolling_ahead(u, n, size, cache, slots, out, fade)
    if res:
        res[1].update({"rolling": True, "keep": laps, "n": n, "fade": list(fade)})   # laps: the pass's own, from _make_mosaic
        if skipped:
            # drawn without tiles not made yet: the frame's picture for now, not for good (the server says so)
            res[1]["partial"] = len(skipped)
    return res


def _rims(mask):
    """The first and last set pixel of each row of mask (once when they are one pixel), as cv2.findNonZero gives
    points, or None when nothing is set. Every set pixel's convex hull is these points' hull, so minAreaRect finds
    the same rectangle from them, without sorting the million points of a tile (190 ms to 8 ms)."""
    rows = np.flatnonzero(mask.any(1))
    if not len(rows):
        return None
    sub = mask[rows]
    left, right = sub.argmax(1), mask.shape[1] - 1 - sub[:, ::-1].argmax(1)
    xs, ys = np.stack([left, right], 1).ravel(), np.repeat(rows, 2)
    keep = np.ones(len(xs), bool)
    keep[1::2] = right != left
    return np.stack([xs[keep], ys[keep]], 1).astype(np.int32).reshape(-1, 1, 2)


def _corners(t, alpha):
    """The four corners of the frame in a tile's picture (its alpha): the smallest rotated rectangle around it, so
    a frame turned north up keeps its slant, in reference pixels from the body's centre."""
    import cv2
    pts = _rims(alpha > 0)
    corners = cv2.boxPoints(cv2.minAreaRect(pts)) if pts is not None else np.zeros((4, 2))
    bx, by = t["box"][:2]
    return [[float(t["offset"][0] + bx + x), float(t["offset"][1] + by + y)] for x, y in corners]


def outline(u, t, cache):
    """Tile t's outline (_corners): kept in its report when the tile is made; for a tile made before that,
    measured once from tiles/<n>.png and kept beside it."""
    if "outline" in t:
        return t["outline"]
    base = os.path.join(_tiles(u, cache, plan(u, cache)["display_scale"]), str(t["n"]))
    with _lock:
        kept = _outlines.get(base)
    if kept is None:
        make = lambda: json.dumps(_corners(t, np.asarray(Image.open(base + ".png"))[..., 3])).encode()
        kept = json.loads(reel._cached(base + ".outline.json", make))
        with _lock:
            if len(_outlines) >= UNIT_OF_KEEP:
                _outlines.clear()
            _outlines[base] = kept
    return kept


_outlines = {}   # tile (its path, less .png) -> its outline, for tiles made before outlines were in their reports


def tile_map(frame_id, cache):
    """Where each frame sits in the mosaic shown for frame_id (the same layout as mosaic_webp, so the same
    tiles and view), for the camera windows' drill-down and Cassini Studio's tile tuning, the picture's manifest:
    {observation, target, pass, filters (the colour set or the gray filter drawn), layers {color: the colour
    filters when the picture has colour, else null; luminance: the luminance base's filters with a tile so far},
    pointings: [{n, t, ids {filter: id} (the filters drawn), luminance {filter: id} (frames drawn in the gray base
    only), set (every colour filter is there, so the pointing shows in colour), also {filter: id} (frames taken
    there that the picture does not draw), tiles, poly [[x, y] x4], center [x, y]}]} with x, y as fractions (0-1)
    of the picture. A pointing is the drawn tiles of different filters at one place (within SAME_PLACE of a frame)
    taken one after another; its outline is its newest tile's, which is the one on top. Kept beside the pass's
    mosaics (MAPS_DIR/<layout name>.json) once every tile in it is made. None when frame_id is not in a mosaic pass or
    nothing is placed yet."""
    found = unit_of(frame_id)
    if not found or not found[0]["mosaic"] or found[1] < 0:
        return None
    u, n = found
    made = layout(u, n, cache)
    if not made:
        return None
    key = (folder(u, cache), made[5])
    with _lock:
        if key in _maps:
            return _maps[key]
    kept = os.path.join(key[0], MAPS_DIR, f"{made[5]}.json")
    if os.path.exists(kept):
        with open(kept) as fh:
            found = json.load(fh)
        with _lock:
            _maps[key] = found
        return found
    p, tiles, rect, count, used, _ = made
    frames = lum_frames(u, p) | lum_fills(u, p, tiles)
    colour = used if len(used) > 1 else None
    x0, y0, w, h = rect
    frac = lambda x, y: [round((x - x0) / w, 5), round((y - y0) / h, 5)]
    pointings, complete = [], True
    rec = _kept_tiles(u, cache, p["display_scale"])
    there = rec["tiles_dir"] if rec is not None else _tiles(u, cache, p["display_scale"])
    also = []
    for t in tiles:
        if "offset" not in t:
            continue
        if t["filter"] not in used and t["n"] not in frames:
            also.append(t)
            continue
        # (a tile's report is written after its picture: a tile whose report is kept in memory has its picture)
        if not (rec is not None and t["n"] in rec["tiles"]) and not os.path.exists(os.path.join(there, f"{t['n']}.png")):
            complete = False   # still being written: this map is not kept
            continue
        last = pointings[-1] if pointings else None
        if last and t["filter"] not in last["ids"] and t["filter"] not in last["luminance"] and \
                t["t"] - last["t1"] <= REPEAT_POINTING and \
                math.hypot(t["offset"][0] - last["at"][0], t["offset"][1] - last["at"][1]) <= SAME_PLACE * FRAME:
            pass
        else:
            last = {"ids": {}, "luminance": {}, "also": {}, "tiles": []}
            pointings.append(last)
        last["ids" if t["filter"] in used else "luminance"][t["filter"]] = t["id"]
        last["tiles"].append(t["n"])
        last["t1"], last["at"] = t["t"], t["offset"]
        last.setdefault("t", t["t"])
        last["poly"] = [frac(x, y) for x, y in outline(u, t, cache)]
        last["center"] = frac(*t["offset"])
    # the frames not drawn, each with the pointing at its place nearest in time
    for t in also:
        near = [(abs(q["t1"] - t["t"]), i) for i, q in enumerate(pointings)
                if math.hypot(t["offset"][0] - q["at"][0], t["offset"][1] - q["at"][1]) <= SAME_PLACE * FRAME]
        if near:
            pointings[min(near)[1]]["also"].setdefault(t["filter"], t["id"])
    out = []
    for q in pointings:
        q.pop("t1"); q.pop("at")
        q["set"] = bool(colour) and all(f in q["ids"] for f in colour)
        if not (max(c[0] for c in q["poly"]) <= 0 or min(c[0] for c in q["poly"]) >= 1 or
                max(c[1] for c in q["poly"]) <= 0 or min(c[1] for c in q["poly"]) >= 1):   # in the view
            out.append(dict(q, n=len(out) + 1))   # numbered as shown, so "n of N" holds
    found = {"observation": u["key"][1], "target": u["key"][0], "pass": u["key"][3], "filters": used,
             "layers": {"color": colour, "luminance": sorted({t["filter"] for t in tiles if "offset" in t and t["n"] in frames},
                                                              key=_luminance(p)["filters"].index)},
             "fixed": p["fixed"], "pointings": out}
    if complete:
        reel._cached(kept, lambda: json.dumps(found).encode())
    with _lock:
        if complete:
            _maps[key] = found
        while len(_maps) > MAPS_KEEP:
            _maps.pop(next(iter(_maps)))
    return found


MAPS_DIR = "maps-1"   # the kept manifests (under the pass's versioned folder), renamed whenever tile_map's answer changes
_maps = {}   # (pass folder, layout name) -> its tile map: a mosaic's map is asked for on every hover of a new picture
MAPS_KEEP = 512   # a few passes' every mosaic (a map is ~100 bytes a pointing), so a pass played again maps none again


POINT_MAX = 2048   # longest side of a pointing opened from its mosaic (its tiles are at the pass's reference distance)
POINTINGS_DIR = "pointings-3"   # the kept pictures of opened pointings (under the pass's versioned folder), renamed
#                                 whenever pointing_picture's answer changes


def pointing_of(mapped, ids):
    """The pointing of the tile map mapped (tile_map) that holds the frames ids (drawn there, or in its gray base), as
    the camera windows' older links name a pointing; None when no one pointing holds them all."""
    for q in mapped["pointings"]:
        if set(ids) <= set(q["ids"].values()) | set(q.get("luminance", {}).values()):
            return q
    return None


def pointing_picture(frame_id, n, cache, size="full", fmt="webp", slots=None, channel=None):
    """(picture, report) of pointing n (as tile_map numbers them) of the mosaic shown for frame_id, opened from it:
    the tiles the mosaic draws there, on a canvas of their own at the tiles' full size (up to POINT_MAX), each given
    the seam correction the mosaic gave it (_seam_of, fitted against its filter's mosaic) and composed through
    mosaic.compose, then mixed (colour_picture) and given the pass's local contrast (detail) as so_far does: the
    mosaic's own picture of that spot, larger. A pointing the colour set covers is in colour; elsewhere it is the gray
    the mosaic draws there (the luminance base, or the one filter drawn), before the gray's tint toward the colour it
    borders (match_grey). channel 0-2: one colour filter's plane, gray, as in that filter's mosaic (before the mix).
    None when the frame is not in a mosaic pass or there is no pointing n. Kept in the cache. The report's box is where
    the picture lies in the mosaic's picture (x, y, w, h as fractions of it), so the two can be laid on one another."""
    found = unit_of(frame_id)
    if not found or not found[0]["mosaic"] or found[1] < 0:
        return None
    u, i = found
    made, mapped = layout(u, i, cache), tile_map(frame_id, cache)
    q = next((q for q in mapped["pointings"] if q["n"] == n), None) if made and mapped else None
    if q is None:
        return None
    p, tiles, rect, count, used, name = made
    by_id = {t["id"]: t for t in tiles if "offset" in t}
    colour = q["set"] and len(used) > 1
    if colour:
        layers = [(by_id[q["ids"][f]], f) for f in used]
    else:
        # the gray the mosaic draws at a place its colour set does not cover: the luminance base's newest tile there
        # (so_far draws the base when lum_base says so), else the filter drawn
        mine = []
        if lum_base(u, p, tiles, used):
            frames, f = lum_frames(u, p), LUM
            mine = [by_id[v] for v in list(q["ids"].values()) + list(q.get("luminance", {}).values()) if v in by_id]
            mine = sorted((t for t in mine if t["n"] in frames), key=lambda t: t["n"])
        if not mine:
            # no base, or a place whose frames the base leaves to the grey filter's nearby: its own drawn filter, gray
            f, mine = None, [by_id[q["ids"][g]] for g in used if g in q["ids"]]
        if not mine:
            return None
        layers = [(mine[-1], f)]
    # a gray place in a colour mosaic: the gray takes the tint over_grey gives it toward the colour it borders
    tint = None
    if not colour and len(used) > 1 and layers[0][1] == LUM and channel is None:
        ref = max(used, key=lambda g: count[g])
        tint = grey_gain(colour_picture(u, p, used, [filter_mosaic(u, p, g, tiles, rect, cache, ref) for g in used]),
                         filter_mosaic(u, p, LUM, tiles, rect, cache), p["k"], p["display_scale"]["gamma"])
    if channel is not None and not 0 <= channel < len(layers):
        return None
    ids = [t["id"] for t, _ in layers]
    cut = "" if channel is None else f"_c{channel}"
    path = os.path.join(folder(u, cache), POINTINGS_DIR, name, f"{n}-{'_'.join(ids)}{cut}-{size}.{fmt}")

    def make():
        with slots or contextlib.nullcontext():
            rgba = _pointing(u, p, tiles, rect, count, used, layers, cache, channel, tint)[0]
        im = Image.fromarray(rgba, "RGBA") if channel is None else \
            Image.fromarray(np.ascontiguousarray(np.dstack([rgba[..., 0], rgba[..., 3]])), "LA")
        if size != "full" and max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "png":
            im.save(buf, "PNG", compress_level=6)
        else:
            reel.save_webp(im, buf, quality=QUALITY, method=4)
        return buf.getvalue()

    bx, by, bw, bh = pointing_box(layers)
    box = [round((bx - rect[0]) / rect[2], 5), round((by - rect[1]) / rect[3], 5), round(bw / rect[2], 5), round(bh / rect[3], 5)]
    return reel._cached(path, make), {"observation": u["key"][1], "pointing": n, "of": len(mapped["pointings"]), "ids": ids,
                                      "filters": [t["filter"] for t, _ in layers], "color": colour, "box": box}


def pointing_box(layers):
    """The canvas of an opened pointing: its tiles' boxes together (x0, y0, w, h, reference pixels from the body's centre)."""
    x0 = min(t["offset"][0] + t["box"][0] for t, _ in layers)
    y0 = min(t["offset"][1] + t["box"][1] for t, _ in layers)
    x1 = max(t["offset"][0] + t["box"][0] + t["box"][2] for t, _ in layers)
    y1 = max(t["offset"][1] + t["box"][1] + t["box"][3] for t, _ in layers)
    return x0, y0, x1 - x0, y1 - y0


def _pointing(u, p, tiles, rect, count, used, layers, cache, channel=None, tint=None):
    """pointing_picture's (RGBA, (x, y, k)): layers [(tile, LUM or None)], one per colour filter (red, green, blue) or
    one gray (tint: grey_gain's gain for it); x, y where its top left corner sits (reference pixels from the body's
    centre), k its pixels per them."""
    ref = max(used, key=lambda f: count[f])
    own = pointing_box(layers)
    x0, y0 = own[:2]
    k = min(1.0, POINT_MAX / max(own[2], own[3]))
    planes = []
    for t, f in layers:
        # the tile at its own size where it sits (_window on this canvas), corrected as the mosaic corrected it
        window, _ = _window(u, dict(p, k=k), [t], own, cache)
        gain, offset = _seam_of(u, p, tiles, rect, ref, t, cache, f)
        planes.append(_compose(window, k, corrections=(np.full((1, 3), gain), np.full((1, 3), offset))))
    if channel is not None:
        rgba = planes[channel]
    elif len(planes) > 1:
        rgba = colour_picture(u, p, used, planes)
    elif tint is not None:
        rgba = np.dstack([(tinted(planes[0], tint, p["display_scale"]["gamma"]) + 0.5).astype(np.uint8), planes[0][..., 3]])
    else:
        rgba = planes[0]
    if sharpens(p["display_scale"]):
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * k)
    # (not cut to its picture: the tiles are cut to theirs, and the canvas is where pointing_box says it is)
    return np.ascontiguousarray(rgba), (x0, y0, k)


def _seam_of(u, p, tiles, rect, ref, t, cache, f=None):
    """(gain, offset) the mosaic's compose gave tile t, as it shows in its filter's mosaic (f = LUM: in the
    luminance base, its band's gain included): fitted between the tile and that mosaic where the tile is whole
    (neighbours blend in near its edges, so the fit is trimmed); (1, 0) when too little of it is in the view."""
    window, shown = _window(u, p, [t], rect, cache)
    if not shown:
        return 1.0, 0.0
    mos = filter_mosaic(u, p, f or t["filter"], tiles, rect, cache, None if f else ref)
    tile_px = window[0][0]
    keep = (tile_px[..., 3] == 255) & (mos[..., 3] == 255)
    a, b = tile_px[..., 0][keep].astype(np.float32), mos[..., 0][keep].astype(np.float32)
    lit = (a > 3) & (a < 252) & (b > 3) & (b < 252)
    if lit.sum() < 500:
        return 1.0, 0.0
    a, b = a[lit], b[lit]
    lo, hi = np.percentile(a, [5, 95])
    if hi - lo < 4:
        return 1.0, float(np.median(b - a))
    blo, bhi = np.percentile(b, [5, 95])
    gain = (bhi - blo) / (hi - lo)
    return float(gain), float(blo - gain * lo)


REPEAT_POINTING = 600   # s: a filter's tiles at one place are one pointing when taken within this of each other


def mosaic_webp(frame_id, size, cache, slots=None, ahead=3, fmt="webp", out=OUT, force=False, tune=None):
    """(WebP, report) of the mosaic so far at frame_id when its pass is a mosaic (or force: the person asked for
    the pass as a mosaic, whatever _judge says); otherwise None. Then makes the next few tiles and the mosaics
    with them in the background, so the next frames' mosaics are ready when the window asks for them. Never
    waits for tiles beyond the first: past the tiles made so far it answers with their mosaic (report "behind":
    how many frames short of frame_id it is). size
    "full" = out px on the longest side (the full view's picture, never warmed ahead); fmt "png" for a PNG
    instead. tune: the person's changes to its tiles (parse_tune), the tuned mosaic (tuned_layout) instead of
    the pass's own; never made ahead."""
    found = unit_of(frame_id)
    if not found or not (found[0]["mosaic"] or force) or found[1] < 0:
        return None
    u, n = found
    if tune and (tune[0] or tune[1]):
        with _asking():
            made = layout(u, n, cache)
            made = tuned_layout(made, tile_map(frame_id, cache), *tune) if made else None
            return _mosaic_at(u, n, size, cache, slots, fmt, out, made=made) if made else None
    # the mosaic of the tiles made so far, when the clock has run past them (playing faster than a frame is
    # processed): the window gets a picture at once, a little behind, and catches up as the tiles behind it
    # (tiles_ahead) are made, instead of waiting for every tile up to n
    m = _made_through(u, n, cache)
    tiles_ahead(u, m + 1, cache)
    if m < n:
        if m < 0:
            return None
        n, ahead = m, 0
    with _asking():
        laid = layout(u, n, cache)
        if size == "full":
            made = _mosaic_at(u, n, size, cache, slots, fmt, out, made=laid)
        else:
            made = _mosaic_at(u, n, size, cache, slots, made=laid)
    if made:
        made = made[0], {**made[1], "behind": found[1] - n}
        # its tile map too, once the mosaic is made, so the window's first hover finds it ready (tiles made before
        # outlines were kept in their reports are measured once here); a map worked out already needs no work
        with _lock:
            mapped = (folder(u, cache), laid[5]) in _maps
        if not mapped:
            _map_later(u, n, cache)
    if made and ahead and size != "full":
        warm(u, n + ahead, cache, size, slots, start=n + 1, force=force)
    return made


_map_wanted, _map_running = {}, set()   # pass folder -> the last tile whose mosaic's map is wanted; passes mapping


def _map_later(u, n, cache):
    """Works out the tile maps of the pass's mosaics up to tile n in the background, in order and once each (the
    pass's record keeps how far it has got), one worker per pass, so the window's first hover finds its map ready
    and a pass played fast starts one thread, not one per mosaic waiting its turn."""
    rec, key = _record(u, cache), folder(u, cache)
    with _lock:
        if rec is not None and rec.get("mapped", -1) >= n:
            return   # (mapped already, then dropped from _maps: a hover works it out)
        _map_wanted[key] = max(n, _map_wanted.get(key, -1))
        if key in _map_running:
            return
        _map_running.add(key)

    def run():
        try:
            while True:
                _yield()
                rec = _record(u, cache)
                with _lock:
                    upto = _map_wanted.pop(key, None)
                    if upto is None:   # (under the lock that a later ask takes: it starts a worker of its own)
                        _map_running.discard(key)
                        return
                    first = rec.get("mapped", -1) + 1 if rec is not None else upto
                for j in range(first, upto + 1):
                    _yield()
                    try:
                        tile_map(u["frames"][j][1], cache)
                    except Exception:   # a tile not made yet: the window's own request works it out
                        pass
                    if rec is not None:
                        with _lock:
                            rec["mapped"] = max(rec.get("mapped", -1), j)
        except BaseException:
            with _lock:
                _map_running.discard(key)
            raise

    threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()


_made = {}   # (pass, look) -> the last tile of the pass up to which every tile is made (or -1)


def _made_through(u, n, cache):
    """The last tile j <= n of the pass with tiles 0..j all made (their reports in the cache), -1 for none.
    Tile 0 is made here when nothing is (with the plan, seconds), so a pass's first mosaic does not wait for
    the background."""
    key = (u["key"], calibration.mode())
    with _lock:
        j = _made.get(key, -1)
    if j < 0:
        with _asking():
            tile(u, 0, cache)
    p = plan(u, cache)
    while j < n and _has_tile(u, j + 1, cache, p):
        j += 1
    with _lock:
        _made[key] = max(_made.get(key, -1), j)
    return min(j, n)


_asked = [0]   # mosaics a window is waiting for right now: work made ahead waits while there are any


@contextlib.contextmanager
def _asking():
    with _lock:
        _asked[0] += 1
    try:
        yield
    finally:
        with _lock:
            _asked[0] -= 1


def _yield():
    """Background work waits here, between one tile or mosaic and the next, while a window waits for a
    mosaic, so the mosaic asked for goes first (one compose at a time, reel._mosaic_lock) instead of after
    the ones being made ahead of it."""
    while _asked[0]:
        time.sleep(0.02)


def _mosaic_path(u, made, size, cache, fmt="webp", out=OUT):
    """Where the mosaic of layout made is kept in the cache (named after what it is made of)."""
    return os.path.join(drawn(u, cache), f"full{out}" if size == "full" else str(size), f"{made[5]}.{fmt}")


def _mosaic_made(u, n, size, cache):
    """Whether the pass's mosaic at tile n is made at size (or holds nothing yet): nothing for warm to make."""
    made = layout(u, n, cache)
    if not made:
        return True
    path = _mosaic_path(u, made, size, cache)
    return path in _blank or os.path.exists(path)


def _mosaic_at(u, n, size, cache, slots=None, fmt="webp", out=OUT, made=None):
    """(WebP, report) of the pass's mosaic with tiles 0..n at size, made once (kept in the cache under the name
    of what it is made of, so frames that add nothing to it share it; a request that comes while it is being
    made waits for it); None before any tile is placed. made: its layout when already worked out (a tuned one)."""
    made = made or layout(u, n, cache)
    if not made:
        return None
    path = _mosaic_path(u, made, size, cache, fmt, out)
    if not os.path.exists(path):
        with _lock:
            lock = _making.setdefault(path, threading.Lock())
        with lock:
            try:
                return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out)
            finally:
                with _lock:
                    _making.pop(path, None)
    return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out)


BLANK_LEVEL = 2   # a mosaic whose 99th percentile over its tiles is at most this many levels holds nothing yet
_blank = set()    # mosaics found blank (paths): asked again, they are blank again


def blank(im):
    """Whether a mosaic picture (RGBA) shows nothing above black over the tiles placed: a pass's first tiles of
    sky at its own noise level (Saturn's Shadow's outer E ring), drawn black. The window keeps showing its frame
    (the single picture, processed on its own scale) until a tile with something in it is placed."""
    a = np.asarray(im)
    covered = a[..., 3] > 0
    return not covered.any() or float(np.percentile(a[..., :3].max(axis=2)[covered], 99)) <= BLANK_LEVEL


def _make_mosaic(u, n, size, path, cache, slots, made, fmt="webp", out=OUT, post=None):
    """(picture, report) of the mosaic so_far draws from made, kept at path; None before anything is above black.
    post: a step applied to so_far's picture before it is kept (a mosaic movie's fade, _faded)."""
    report, full, meta = {}, size == "full", path[:-len(fmt)] + "json"
    if path in _blank:
        return None

    def make():
        with slots or contextlib.nullcontext():
            im, rep = so_far(u, n, cache, made, out if full else OUT)
        if im is None:
            raise LookupError("no tile placed yet")
        if blank(im):
            with _lock:
                _blank.add(path)
            raise LookupError("nothing above black yet")
        report.update(rep)
        if post:
            hdr = im.info.get("hdr")
            im = post(im)
            if hdr is not None and "hdr" not in im.info:
                im.info["hdr"] = hdr
        if not full and max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "png":
            im.save(buf, "PNG", compress_level=6)
        else:
            reel.save_webp(im, buf, quality=QUALITY, method=4)
            keep_picture_map(im, path)
        reel._cached(meta, lambda: json.dumps(rep).encode())
        reel.keep_report(meta, rep)
        return buf.getvalue()

    try:
        data = reel._cached(path, make)
    except LookupError:
        return None
    if path.endswith(".webp"):
        calibration.hdr_note_served(path, path[:-len(".webp")] + ".hdr.webp")
    if not report:
        report = reel.report_of(meta)
    return data, report


def warm(u, upto, cache, size=None, slots=None, start=0, force=False):
    """Makes the pass's plan and its tiles up to upto in the background, and with a size the mosaics at tiles
    start..upto. One thread per pass and size: a later call while it runs moves its end on. Background work
    runs one pass at a time (_background). force: a pass _judge does not call a mosaic, asked for as one."""
    if not (u["mosaic"] or force):
        return
    mode = calibration.mode()
    key = (u["key"], size, mode)
    upto = min(upto, len(u["frames"]) - 1)
    with _lock:
        running = key in _warming
    # nothing to make (the tiles up to upto in memory, and their mosaics in the cache): no thread
    if not running:
        rec = _record(u, cache)
        if rec is not None and _all_made(u, cache, rec["plan"], 0, upto) and \
                (not size or all(_mosaic_made(u, j, size, cache) for j in range(start, upto + 1))):
            return
    with _lock:
        _upto[key] = max(_upto.get(key, -1), upto)
        _from[key] = max(_from.get(key, 0), start)
        if key in _warming:
            return
        _warming.add(key)

    def run():
        try:
            with _background, calibration.in_mode(mode):
                p = plan(u, cache)
                done = -1
                while True:
                    with _lock:
                        last, first = _upto[key], _from[key]
                        if last <= done:   # nothing more asked: finished (a later call starts a new thread)
                            _warming.discard(key)
                            _upto.pop(key, None)
                            _from.pop(key, None)
                            return
                    for j in range(done + 1, last + 1):
                        _yield()
                        tile(u, j, cache, p["display_scale"])
                    if size:
                        for j in range(max(first, done + 1), last + 1):
                            _yield()
                            # a window that has asked for a later frame meanwhile (a burst) has passed this one;
                            # one made already is not read again
                            if j >= _from[key] and not _mosaic_made(u, j, size, cache):
                                _mosaic_at(u, j, size, cache, slots)
                    done = last
        except Exception as e:
            print(f"observation mosaic {u['key']} failed: {type(e).__name__}: {e}", flush=True)
            with _lock:
                _warming.discard(key)
                _upto.pop(key, None)
                _from.pop(key, None)

    threading.Thread(target=run, daemon=True).start()


_ahead_passes = collections.deque(maxlen=2)   # (pass, mode) windows were in last (a NAC and a WAC window)
_ahead_running = set()   # (pass, mode) a thread is making tiles ahead for


def tiles_ahead(u, n, cache):
    """Makes the pass's tiles from the first one not made to its end in the background (n: the frame the window
    is at, kept for the callers), one thread per pass, so a playing window's
    mosaic finds its tiles made (processing a frame is the slow part of a cold mosaic) instead of waiting for
    each. Stops once windows have moved on to two other passes. Waits between tiles while a window waits for a
    mosaic (_yield), so the pass's lock goes to the request first instead of to the next tile ahead."""
    mode = calibration.mode()
    me = (u["key"], mode)
    with _lock:
        # the pass asked for in one mode only (Settings > Processing switched): the thread of its mode before stops
        for was in [a for a in _ahead_passes if a[0] == u["key"]]:
            _ahead_passes.remove(was)
        _ahead_passes.append(me)
        if me in _ahead_running:
            return
    # every tile of the pass made and in memory: nothing to make, no thread
    rec = _record(u, cache)
    if rec is not None and _all_made(u, cache, rec["plan"], 0, len(u["frames"]) - 1):
        return
    with _lock:
        if me in _ahead_running:
            return
        _ahead_running.add(me)

    def run():
        try:
            with calibration.in_mode(mode):
                p = plan(u, cache)
                # from the first tile not made: a window's mosaic is the tiles made so far in a row (mosaic_webp)
                with _lock:
                    first = _made.get((u["key"], mode), -1) + 1
                for j in range(first, len(u["frames"])):
                    _yield()
                    if me not in _ahead_passes:
                        return
                    tile(u, j, cache, p["display_scale"])
        except Exception as e:
            print(f"observation tiles {u['key']} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                _ahead_running.discard(me)

    threading.Thread(target=run, daemon=True).start()


def warm_frame(frame_id, cache, ahead=4):
    """A frame was asked for: when it is in a mosaic pass, start making that pass's tiles from it on."""
    found = unit_of(frame_id)
    if found and found[0]["mosaic"]:
        tiles_ahead(found[0], max(found[1], 0), cache)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frame", help="a frame of the pass, e.g. W1537023863_1")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--all", action="store_true", help="also make the mosaic at every tile (1024 px)")
    args = ap.parse_args()
    u, _ = unit_of(args.frame)
    print(u["key"], len(u["frames"]), "tiles", "mosaic" if u["mosaic"] else "not a mosaic", "whole body" if u["whole"] else "")
    t0 = time.time()
    p = plan(u, args.cache)
    print("plan", {k: v for k, v in p.items() if k != "display_scale"}, f"{time.time() - t0:.1f} s", flush=True)
    if args.all:
        for fr in u["frames"]:
            t0 = time.time()
            made = mosaic_webp(fr[1], 1024, args.cache, ahead=0)
            print(fr[1], fr[2], made and made[1]["mosaic"], f"{time.time() - t0:.2f} s", flush=True)


if __name__ == "__main__":
    main()
