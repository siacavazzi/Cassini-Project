# Huygens data: findings (2026-10-18)

Everything is in `/Users/sam/Development/huygens-data`. Raw downloads total **1.6 GB** under `raw/`, and my outputs total about 0.5 MB under `derived/`. Every downloaded file is listed with its size in `derived/manifest.tsv` (16,722 files). Nothing has been converted to replay formats yet.

```
raw/spice/        NAIF kernels (22 MB)
raw/psa/DTWG/     ESA PSA HP-SSA-DTWG-6-TRAJECTORY-V2.0, full volume (65 MB)   <- use this
raw/pds/hpdtwg_0001/  PDS Atmospheres DTWG V1.0, full volume (65 MB)         <- superseded, kept for comparison
raw/psa/DISR/HP-SSA-DISR-2-3-EDR-RDR-V1.3/   DISR subset (1.4 GB of a 15.4 GB volume)
derived/imager_index.csv   one row per imager frame (608), parsed from labels
derived/sample_png/        decoded sample frames + contact sheet
scripts/                   index_labels.py, decode_tab.py, spk_coverage.py
```

## 1. Trajectory

### SPICE (cruise and approach, up to entry interface)

| File | Size | Source | Notes |
|---|---|---|---|
| `spk/050214R_SCPSE_04336_05015.bsp` | 16.5 MB | https://naif.jpl.nasa.gov/pub/naif/CASSINI/kernels/spk/ | **Primary.** Reconstructed (R). Contains -150, -82, Sun/planet barycenters, Earth/Moon, Saturn 699, and satellites 601–609. |
| `spk/041210AP_OPK_04329_08189.bsp` | 6.1 MB | same | Predicted orbiter + probe kernel (-150, -82 only). Backup and comparison only. |
| `lsk/naif0012.tls` | 5 KB | NAIF CASSINI/kernels/lsk | |
| `pck/pck00011.tpc` | 131 KB | NAIF generic_kernels/pck | Titan radius 2575 km. Gives the same lon/lat as the DTWG's CPCK14JAN2010 at entry, to 4 decimal places. |
| `fk/cas_v43.tf` | 197 KB | NAIF CASSINI/kernels/fk | Cassini frames kernel. It has no Huygens probe frame. |

NAIF has no `hp-*` PDS volume and no HUYGENS directory. In NAIF, -150 is named `CASP` (the Cassini probe).

**spkcov for -150** (one type 1 segment, center 6 = Saturn barycenter, frame J2000 in both files):
- 050214R_SCPSE: **2004-11-23T23:58:56 → 2005-01-14T09:05:53 UTC**. This starts before the 2004-12-25 separation, so the segment before that date is the probe still mated to Cassini.
- 041210AP_OPK: 2004-12-25T02:00:00 → 2005-01-14T09:05:56 UTC.
- Titan (606) in the SCPSE file: 2004-12-01T11:58:56 → 2005-01-15T12:58:56.

Both SPKs **stop at entry interface (about 1270 km)**. Nothing in NAIF covers the descent.

### DTWG (entry and descent to landing)

Source: **https://archives.esac.esa.int/psa/ftp/CASSINI-HUYGENS/DTWG/HP-SSA-DTWG-6-TRAJECTORY-V2.0/** (published 2011-02-03, producer B. Kazeminejad, ESTEC). The PDS Atmospheres copy is V1.0 (2007): https://atmos.nmsu.edu/PDS/data/hpdtwg_0001/. **Use V2.0.** V1.0's landing latitude is 0.32° off, at -10.251°, and its altitudes differ from V2.0 by up to 0.15 km.

All tables are fixed-width ASCII. Columns 1–3 are the same everywhere: `ET_EPOCH` (TDB s past J2000), `ELAPSED_TIME` (s from T0, the start of the parachute sequence, 2005-01-14T09:10:21 UTC), and UTC ISO time. Altitudes are above a **2575 km reference sphere**. Longitudes are **west**.

| File (`DATA/`) | Rows | UTC range | Step | Columns after time |
|---|---|---|---|---|
| `HUY_DTWG_ENTRY.TAB` | 1,344 | 09:05:52.522 → 09:28:15.815 | 1 s | REF_ALT km, WEST_LON, LAT, AOA (not computed, all 0), ENTRY_INERTIAL_VEL (m/s), 1σ errors for alt/lon/lat |
| `HUY_DTWG_ENTRY_EME2000_POS/VEL.TAB` | 1,344 each | entry | 1 s | Titan-centred EME2000 x, y, z (km) and vx, vy, vz |
| `HUY_DTWG_ENTRY_AERO.TAB`, `_MASS.TAB` | 937 each | entry | – | aerodynamics, mass |
| `HUY_DTWG_DESCENT_POS.TAB` | 8,753 | 09:12:18.999 → **11:38:10.769 (landing)** | 1 s | PRESSURE mbar, REF_ALT km, WEST_LON, LAT, plus 1σ errors |
| `HUY_DTWG_DESCENT_VEL.TAB` | 8,753 | descent | 1 s | velocities relative to the 2575 km sphere |

- Landing: **10.5730°S, 192.3346°W (167.665°E)**, altitude 0, at 2005-01-14T11:38:10.769 UTC.
- The DESCENT label gives START_TIME 09:10:20.999, but the first row is at 09:12:18.999. Between 09:12 and 09:28 the entry and descent tables overlap.
- `GEOMETRY/` has the kernels the DTWG used: CPCK14JAN2010.TPC, LSK naif0007, the event file EVENT_FILE_DTWG5.DAT, and the probe aero databases. `EXTRAS/BSP_FILE/` has SAT199.BSP and 050214_PE_DE405.BSP. `DOCUMENT/` has the Kazeminejad PhD thesis and the EAICD.

**SPK → DTWG handoff.** Compared at the same epoch (09:05:52.522 UTC):
- The SPK puts the probe at 1270.0 km, 185.523°W, 8.818°S.
- DTWG V2 entry row 0 gives 1247.7 km, 185.419°W, 8.925°S.
- In Titan-centred J2000 the two positions are **24.4 km apart**. At 6.03 km/s that is about 3.7 s along-track.

The SPK is the pre-entry navigation solution and the DTWG is the post-flight reconstruction, so the replay will need a short blend or a time shift at 09:05:52.

### DISR attitude and position (bonus)

`raw/psa/DISR/.../EXTRAS/PROBE_ATTITUDE/HUYGENS_DESCENT_PARAMETERS/HUYGENS_DESCENT_PARAMETERS.TXT` has about 4,450 rows at a 2 s step from T0 to landing. Its columns are mission time (s), rotation number, altitude (km, consistent with the DTWG), Sun azimuth and zenith distance, **east** longitude, north latitude, tilt, and tilt Δt. This is the easiest source for probe spin and attitude per image.

## 2. DISR images

Source: **https://archives.esac.esa.int/psa/ftp/CASSINI-HUYGENS/DISR/HP-SSA-DISR-2-3-EDR-RDR-V1.3/** (errata dated 2019-11-28). The same V1.3 volume is at https://atmos.nmsu.edu/PDS/data/hpdisr_0001/, but NMSU served about 0.25 MB/s against 3.8 MB/s from PSA. I started on NMSU, stopped, and took everything from PSA.

The volume is 15.4 GB in total, too big for the disk. I downloaded these parts (1.44 GB, 16,577 files, 0 failures):

| Directory | Size | What it is |
|---|---|---|
| `DATA/IMAGER/{TABLE,TIFF,XDR}_FORMAT` | 381 MB | **EDR**: 608 products, each in 3 formats with a label (.LBL per TAB/TIF/XDR) |
| `BROWSE/PNG` | 133 MB | 604 browse PNGs (16-bit, upsampled 2×, clipped) with labels |
| `EXTRAS/PROCESSED_IMAGES` | 263 MB | **Calibrated / processed** (Karkoschka, 13 Nov 2005): 3 sets × 606 frames × (PGM + TIF) |
| `EXTRAS/IMAGE_ELEMENTS` | 587 MB | raw decompressed images (1,212 PGM/TAB), improved flat fields (1,212), dark current (272), sqrt tables (606), on-board flat fields per camera, DCT coefficients |
| `EXTRAS/MOSAICS` | 51 MB | 9 contour mosaics (PGM), high/medium-altitude mosaics, and an altitude series of mosaic PNGs (1, 2, 3, 4, 5, 10, 15, 20, 30, 40, 50, 60 km) |
| `DATA/TIME`, `DESCENT_CYCLES`, `HOUSEKEEPING`, `SUN_SENSOR`, `SLI_STRIP`, `DERIVED_DATA_PRODUCTS` | about 20 MB | DDB↔DISR clock tables, per-cycle summaries, housekeeping, sun sensor, radiometry DDPs |
| `INDEX/`, `CATALOG/`, root files | about 1 MB | |

Not downloaded (about 14 GB): `EXTRAS/DISR_IN-FLIGHT_DATA` (5.2 GB), `IDL_PROGRAMS` (3.5 GB), `DISR_XDR_DATA` (2.8 GB), `DISR3_CALIBRATION_DATA` (1.0 GB), `MOVIES` (0.9 GB), calibration docs (0.4 GB), and the spectrometer, photometer and lamp data. Any of these can be fetched later with `scripts/` and the PSA URL.

### Frame count. There are 608 frames, not about 3,500.

About 3,500 is roughly how many images DISR took. Only Channel B reached the ground, because Cassini's Channel A receiver was not configured. That left **608 imager products**:

| Camera | Frames | Size (cols × rows) | First → last (UTC, 2005-01-14) |
|---|---|---|---|
| SLI (side-looking, 45–96° from nadir) | 214 | 128 × 256 | 09:12:44 → 12:45:24 |
| MRI (medium res, 16–45°) | 184 | 176 × 256 | 09:12:47 → 12:46:15 |
| HRI (high res, 6–21°) | 204 | 160 × 256 | 09:12:47 → 12:45:48 |
| UHH / LHH (half-frames) | 6 | 160 × 128 | 11:37:11 → 11:37:23, plus 2 with a bogus time |

- **376 frames during descent** (143 km → 0) and **232 on the surface** (11:40:29 → 12:46). There are 68 imaging cycles in all.
- Images 1068 and 1089 (UHH) carry a placeholder time of 19:10:21.000, which is mission time 36000 s. Treat their time as unknown.
- Exposure runs from 0 to 50 ms. The DN range is 0 to 519,168, where 519,168 means saturated and 0 means a missing 16×16 packet.
- The processed sets have 606 frames, two fewer than the EDR.

### Per-frame label fields (all 608 have them; parsed into `derived/imager_index.csv`)

- `START_TIME`, `STOP_TIME` (UTC), `SPACECRAFT_CLOCK_START_COUNT` (DDB mission time in s since T0), `SEQUENCE_NUMBER`, `IMAGE_ID` (camera), `PRODUCT_TYPE` = EDR
- `EXPOSURE_DURATION` (ms), `EXPOSURE_TYPE`
- `PREDICTED_ALTITUDE` (real-time), `SPACECRAFT_ALTITUDE_START/END` (km, from the June 2011 DTWG reconstruction)
- `AZIMUTH_START/END` (CCW from the Sun, seen from nadir), `AZIMUTH_NORTH_START/END` (CW from North), `EW_TILT_ANGLE_START/END` (positive means the parachute is to the east), `SPIN_RATE` (rpm, positive is CCW). Azimuth and tilt come from Karkoschka's March 2013 analysis.
- Instrument temperatures (11 points), `LAMP_STATE`, and an embedded copy of the original XDR header (cols, rows, cycle_num, dataset type, compression ratio, pixel min/max/mean)
- File names encode the sequence number, mission time and altitude: `IMAGE_0300_04397_S_027_KM` is image 300 at T0+4397 s and 27 km. `_0000_M` means on the surface.
- The browse PNG labels use a `HUYGENS:` prefix on the altitude, azimuth and tilt keys. The EDR TAB labels mostly don't. My indexer handles both.

### Formats and decoding

- **TABLE_FORMAT** (`.TAB`): ASCII. Records 1–3 are header lines, then 256 rows of `ROW` followed by N DN integers (I8). The on-disk records are *not* padded to RECORD_BYTES, so read them as lines. The label notes that the image is inverted up/down relative to the descent attitude. `scripts/decode_tab.py` decodes these. The DN min/max of image 2 match its label exactly (3364 / 196529).
- **TIFF_FORMAT**: 16-bit (`I;16`) TIFF in native orientation, so PIL opens it directly.
- **XDR_FORMAT**: the original IDL XDR files (not decoded; the TAB and TIFF hold the same data).
- **PROCESSED_IMAGES**: 32-bit PGM plus TIF, three levels.
  - `UNSMOOTHED`: compressor, sqrt and flat field reversed, dark subtracted.
  - `DISRSOFT_G`: adds artifact cleanup. 30 rejects are in `TIFF/Junk/`.
  - `DISRSOFT_E`: adds PSF deconvolution and compression-artifact removal.
  - **G or E images are the ones to show.** The raw EDR still has the on-board flat-field honeycomb, as surface frame 767 shows.
  - PGM names look like `V_00300DCS_011316_6380`, which is sequence 300 at mission time 01:13:16.6380, so they join to the EDR by sequence number.

Samples are in `derived/sample_png/`: `contact_sheet.png` has EDR frames 2 (SLI, 143 km), 300 (HRI, 27 km, drainage channels visible), 359 (SLI, 21 km) and 767 (on the surface). `G_V_00300...png` is the processed version of frame 300.

## 3. What failed or needs attention

- NAIF has no Huygens PDS volume (`hp-*`) and no descent SPK. The descent comes only from the DTWG tables.
- There is a 24 km discontinuity between the NAIF SPK and the DTWG at entry; see §1.
- The NMSU (PDS Atmospheres) mirror is slow, about 0.25 MB/s. Use PSA.
- Two UHH frames have bogus timestamps (see above).
- **Disk:** about 10 GB is free on the internal disk now (14 GB when I started; I used 1.6 GB). The rest of the DISR volume (about 14 GB) would not fit.
- I did not touch the Cassini-Project checkout or the LaCie. The scripts were run with the existing Cassini-Project venv.
- Label `ROWS = 10000` in most DTWG labels is a placeholder; real row counts are in the table above.
