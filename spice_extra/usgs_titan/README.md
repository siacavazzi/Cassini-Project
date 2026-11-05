# USGS bundle-adjusted pointing for Titan

Weller, L., Karkoschka, E., et al. (2026), *Geodetically improved images and mosaics of Titan via rigorous
photogrammetric control of Cassini Imaging Science Subsystem data*, USGS data release,
doi:[10.5066/P14FAEKS](https://doi.org/10.5066/P14FAEKS)
(ScienceBase item `68a5107ad4be02198e361c35`; image list from child item `68b85fd3d4be0247d962606e`).
USGS data, public domain.

A control network of 6,896 NAC images of Titan (938 nm), 92,831 tie points, tied to Cassini RADAR. The bundle
adjustment solved Cassini's attitude and position for each image; tie point residuals are about 1.1 px (2 sigma).

| file | what | MD5 |
|---|---|---|
| `Titan_CISS_2024_ck.bc` | CK, Cassini attitude (`CASSINI_SC_COORD`, -82000) relative to J2000, one type 3 segment per image | `ad9474145c1ce21b15423b731b60ca98` |
| `Titan_CISS_2024_spk.bsp` | SPK, Cassini (-82) relative to Titan (606) in J2000, one segment per image | `bd3fc9726ef3d88617280f1b3e5ae5d0` |
| `images.lis` | the 6,896 frame ids (`root_updated_CISS_Titan_FFCombined7_Thin_PixReg_SubReg_Ground_V4.lis`) | `444d7d1eb03762e25ff04f77c0c1ae68` |
| `Titan_neighbours_ck.bc` | ours: the USGS correction carried over to 7,328 other Titan frames of the same passes (`make_neighbours_ck.py`) | `0d717443dc8e90fb97f960e6d1dfa3b3` |
| `neighbours.lis` | the frames `Titan_neighbours_ck.bc` covers | |
| `concurrent.lis` | 44 WAC frames of Titan whose mid-exposure time falls inside a segment (shuttered with a NAC frame of the list); ours, not USGS's | |

Each CK segment is 6 ms around its image's mid-exposure time, so loading these after a year's kernels
(`bootleg_autonav.load_kernels`) changes the pointing of these frames and of the 44 WAC frames taken at the same
moment (`concurrent.lis`, which take the corrected spacecraft attitude), and nothing else.
USGS controlled only the 938 nm (CL1,CB3) frames. The other filters of a pass are shot seconds to minutes away at
the same pointing, and left on the mission pointing they would sit a median 8 px (up to 165 px) from their CB3
neighbours, enough to break colour sets. `make_neighbours_ck.py` gives each Titan frame within 10 minutes of a USGS
frame of its observation that frame's attitude error rotation (E = C_usgs C_mission^T at the USGS frame, applied to
the mission attitude at the frame's own time), and writes the result as one more CK, loaded before USGS's.

`CASSINI_USGS_TITAN=0` leaves all of them out. After adding or changing them, refill the geometry cache for these frames:

    python bootleg_autonav.py geometry --usgs-titan
