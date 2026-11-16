# JPL's corrected pointing carried over within each observation

The mission kernels hold two kinds of camera pointing. For about 97,000 frames (22%), JPL's imaging team
measured the pointing on the picture itself and wrote it as one CK segment per image (the C-smithed
`*_ISS.bc` kernels, `cosp_1000/data/ck`). Every other frame has only the spacecraft's reconstructed
attitude (`*ra.bc` and the like), typically 3 to 15 NAC pixels off (p90 20 to 44 px).

The pipeline took the best pointing SPICE had for each frame, so 5,533 observations switched between the
two from one frame to the next (138,340 raw frames among corrected ones): Titan's 133TI CLOUD002 cloud
movie jumped 24 to 54 px between frames 40 s apart, and the 2005-04-13 ring movie ISS_006RI_LPHRLFMOV001
27 px every time a raw frame came up (Sam, 2026-11-16: a sequence must never switch pointing source).

`make_smith_neighbours_ck.py` gives every other frame of an observation with any C-smithed frame that
observation's correction, as `spice_extra/usgs_titan/make_neighbours_ck.py` does for USGS's Titan pointing:

    E = C_iss(t0) C_raw(t0)^T      at each C-smithed frame t0 of the observation
    C_new(t) = E(t) C_raw(t)       E interpolated (slerp) between the two C-smithed frames either side of t,
                                   the nearest one's outside them

| file | what |
|---|---|
| `ISS_smithed_neighbours_ck.bc` | CK of Cassini's attitude (-82000, J2000), one type 3 segment per frame (a second round its mid-exposure time), segment id = frame id |
| `ISS_smithed_neighbours_ck.lis` | the frames it covers (135,749) |
| `make_smith_neighbours_ck.py` | makes both |
| `check_mixed.py` | lists observations that still mix corrected and raw pointing: 5,533 before, 0 after |

Frames the USGS Titan kernels cover are left out (USGS's own correction wins; its carry-over,
`usgs_titan/neighbours.lis`, now reaches every frame of its observations, as this one does).
`bootleg_autonav.load_kernels` loads the CK after a year's kernels and before USGS's; `CASSINI_ISS_NEIGHBOURS=0`
leaves it out. Geometry cache answers for these frames are kept with the tag `iss-neighbours-2026-11` and worked
out again once when it is missing:

    CASSINI_KERNELS=... python bootleg_autonav.py geometry     (then: bodies, for the same frames)

Remake it after the mission kernels or the index change:

    CASSINI_KERNELS=... CASSINI_KEEP_SPICE_CACHE=1 python spice_extra/usgs_titan/make_neighbours_ck.py
    CASSINI_KERNELS=... CASSINI_KEEP_SPICE_CACHE=1 python spice_extra/iss_smithed/make_smith_neighbours_ck.py spice_extra/iss_smithed/ISS_smithed_neighbours_ck.bc
    CASSINI_KERNELS=... python spice_extra/iss_smithed/check_mixed.py      # 0 observations
