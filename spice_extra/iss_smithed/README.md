# JPL's corrected pointing carried over within each observation

The mission kernels hold two kinds of camera pointing. For about 97,000 frames (22%), JPL's imaging team
measured the pointing on the picture itself and wrote it as one CK segment per image (the C-smithed
`*_ISS.bc` kernels, `cosp_1000/data/ck`). Every other frame has only the spacecraft's reconstructed
attitude (`*ra.bc` and the like), typically 3 to 15 NAC pixels off (p90 20 to 44 px).

The pipeline took the best pointing SPICE had for each frame, so 5,533 observations switched between the
two from one frame to the next (138,340 raw frames among corrected ones): Titan's 133TI CLOUD002 cloud
movie jumped 24 to 54 px between frames 40 s apart, and the 2005-04-13 ring movie ISS_006RI_LPHRLFMOV001
27 px every time a raw frame came up (Sam, 2026-11-16: a sequence must never switch pointing source).

`make_smith_neighbours_ck.py` carries the observation's correction to its other frames, as
`spice_extra/usgs_titan/make_neighbours_ck.py` does for USGS's Titan pointing:

    E = C_iss(t0) C_raw(t0)^T      at each C-smithed frame t0 of the observation
    C_new(t) = E(t) C_raw(t)

- Only from C-smithed frames of the same pointing (a new pointing wherever the attitude turns 0.1 deg or more
  from one frame to the next), or of a pointing the observation comes back to (within 0.15 deg): the attitude
  error changes with the attitude, so a mosaic tile's correction does not fit the next tile.
- On each side of t, the C-smithed frame nearest it stands for the median of the 5 corrections nearest that
  frame. The two sides are faded with their time distance (whole to 10 min, then gone over ~3 h) and blended by
  where t falls between them, so the correction is smooth through a movie's gaps.
- Only where JPL's own corrections agree: their median distance from that median is at most 5 NAC px
  (30 urad) or 2.5 WAC px (150 urad). JPL navigated each image on its own. On the WAC ring mosaics, one
  pointing's corrections scatter by tens of pixels, and sometimes hundreds (ISS_260RI_HIPHASEFA001: 2 to 76 px,
  one 482 px). There, no carried value beats raw: carrying them drew those mosaics' tiles out of line. Such
  frames keep their raw pointing, and the mosaic's joint solve places them.

So 54,070 frames are carried over. 1,408 observations still hold a raw frame in a pointing with a corrected one
(26,635 frames, where JPL's own corrections disagree), down from 4,590 (84,954 frames).

| file | what |
|---|---|
| `ISS_smithed_neighbours_ck.bc` | CK of Cassini's attitude (-82000, J2000), one type 3 segment per frame (a second round its mid-exposure time), segment id = frame id |
| `ISS_smithed_neighbours_ck.lis` | the frames it covers (54,070) |
| `ISS_smithed_frames.lis` | the frames JPL's own C-smithed CKs cover (98,692) |
| `make_smith_neighbours_ck.py` | makes all three |
| `check_mixed.py` | lists observations with a raw frame in the same pointing as a corrected one |

Frames the USGS Titan kernels cover are left out (USGS's own correction wins; its carry-over,
`usgs_titan/neighbours.lis`, now reaches every frame of its observations, as this one does).
`bootleg_autonav.load_kernels` loads the CK after a year's kernels and before USGS's; `CASSINI_ISS_NEIGHBOURS=0`
leaves it out. Geometry cache answers for these frames are tagged with the CK's name and a hash of its content, and are
worked out again when the tag no longer matches:

    CASSINI_KERNELS=... python bootleg_autonav.py geometry     (then: bodies, for the same frames)

Remake it after the mission kernels or the index change:

    CASSINI_KERNELS=... CASSINI_KEEP_SPICE_CACHE=1 python spice_extra/usgs_titan/make_neighbours_ck.py
    CASSINI_KERNELS=... CASSINI_KEEP_SPICE_CACHE=1 python spice_extra/iss_smithed/make_smith_neighbours_ck.py spice_extra/iss_smithed/ISS_smithed_neighbours_ck.bc
    CASSINI_KERNELS=... python spice_extra/iss_smithed/check_mixed.py      # 1,408 observations
