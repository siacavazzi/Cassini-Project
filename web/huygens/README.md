> **Raw inputs.** Each script takes `--root <dir>` and reads from `<dir>/raw/`. The raw data is not in this repo.
> - `build_huygens_track.py`, `verify_huygens_track.py` and `make_evidence.py` need the NAIF kernels `raw/spice/lsk/naif0012.tls`, `raw/spice/pck/pck00011.tpc` and `raw/spice/spk/050214R_SCPSE_04336_05015.bsp`. They also read the DTWG tables `HUY_DTWG_ENTRY.TAB`, `HUY_DTWG_DESCENT_POS.TAB` and `HUY_DTWG_ENTRY_EME2000_VEL.TAB` from `raw/psa/DTWG/HP-SSA-DTWG-6-TRAJECTORY-V2.0/DATA/`.
> - `export_huygens_catalog.py` needs `naif0012.tls` and the same DTWG tables. It also reads the DISR archive `raw/psa/DISR/HP-SSA-DISR-2-3-EDR-RDR-V1.3/`: the processed sets `DISRSOFT_E_IMAGES_13NOV2005` and `DISRSOFT_G_IMAGES_13NOV2005`, and the EDR TIFFs in `DATA/IMAGER/TIFF_FORMAT/`.
> - `make_evidence.py` also reads the EDR TIFFs. `pgm.py` is a helper the other scripts import.
>
> In this repo, the commands below are `web/huygens/<script>.py --root <data dir>`.

# Huygens replay data

These files use the formats of the Cassini mission replay (`web/README.md` on `claude/project-thread-xzkleb`). All positions are J2000, with the origin at the solar system barycentre, in km. All times are TDB seconds past J2000. To regenerate everything:

```
P=/Users/sam/Development/Cassini-Project/.venv/bin/python
$P tools/build_huygens_track.py --root .     # tracks + manifest_huygens.json
$P tools/export_huygens_catalog.py --root .  # huygens_descent.json, catalog, images
$P tools/verify_huygens_track.py --root .    # verify_huygens.json
$P tools/make_evidence.py --root .           # evidence/
```

| File | What it is |
|---|---|
| `tracks/huygens/2004.bin` | 173 samples (7.6 KB), from separation at 2004-12-25T02:00:00 UTC to 2005-01-01T00:00 UTC |
| `tracks/huygens/2005.bin` | 586 samples (25.8 KB), from 2005-01-01T00:00 UTC to 2005-01-15T00:00 UTC. The two years share their boundary sample. |
| `manifest_huygens.json` | The `HUYGENS` body entry (naif_id -150, chunks with year/file/count/bytes/coverage_et), plus sources, event ETs, landing site and the handover numbers |
| `huygens_descent.json` | Column arrays at 2 s, 4,570 rows from entry interface to landing: `et, utc, alt_km, lat_deg, lon_w_deg, pressure_hpa`, plus `landing_site`. Pressure is null before 09:12:19, because the entry table has none. |
| `catalog/huygens.json` | One entry per DISR frame (608), sorted by time: `id, et, utc, cam, phase, alt_km, lat_deg, lon_w_deg, az_sun_deg, az_north_deg, tilt_deg, exposure_ms, mean_dn_ms, w, h, file, file_enh, src, flags` |
| `images/huygens/<id>.png` | 608 8-bit PNGs at native size, with a shared stretch (below) |
| `images/huygens_enh/<id>.png` | The same frames stretched one by one, for legibility |
| `images/huygens/stretch.json` | The stretch limits that were used |
| `verify_huygens.json` | Full verification output |
| `mosaics/<s>m.png`, `mosaics/mosaics.json` | Karkoschka's landing-site mosaics at 60, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2 and 1 m/pixel, 1250x1600, north up, landing site at the same pixel in each, brightness matched between scales (`build_mosaics.py`) |
| `huygens_color.json`, `images/huygens_color/<id>.png`, `mosaics/color/<s>m.png` | Colour from the spectrometers against altitude (1 km steps), the 608 frames tinted with the colour at their altitude, and the mosaics tinted with the near-surface colour (`descent_color.py`) |
| `catalog/huygens_projection.json` | Per usable descent frame: nadir point, ground footprint outline (m east/north of the landing site) and its correlation with the mosaic, plus the camera model (`project_frames.py`) |

## How the track is built

1. **Coast** (separation to entry interface minus 10 min): the NAIF reconstructed SPK `050214R_SCPSE_04336_05015.bsp`, body -150.
2. **Blend** (the last 10 min before entry interface at 09:05:52.522 UTC): the SPK plus a cubic Hermite fade of the SPK-to-DTWG offset.
   - The fade goes from zero at the start of the blend to the full position offset (24.40 km) and velocity offset (2.8 m/s) at entry interface.
   - Position and velocity are continuous at both ends, and the track equals the DTWG exactly at entry interface.
   - The fade adds at most 0.4 m/s² (6·Δp/T²). The largest acceleration in the blend is 0.57 m/s², against 0.61 m/s² for the raw SPK alone (Titan's gravity).
3. **Entry**: DTWG V2.0 `HUY_DTWG_ENTRY` until the first descent row (09:12:18.999 UTC).
   - From there it fades into `HUY_DTWG_DESCENT_POS` over 60 s.
   - The two tables differ by 58 m at that point (median 0.60 km, max 1.16 km over their 957 s overlap). The descent table is the one used after the fade.
4. **Descent**: `HUY_DTWG_DESCENT_POS` until landing at 11:38:10.769 UTC.
5. **Surface**: the landing point (10.5730225°S, 192.3346498°W, on the 2575 km sphere) is held fixed in IAU_TITAN and rotates with Titan until 2005-01-15T00:00 UTC.

The DTWG rows give planetocentric latitude, **west** longitude, and altitude above a **2575 km sphere** in IAU_TITAN. Converting them with `latrec(2575+alt, -lon_w, lat)`, then `pxform IAU_TITAN→J2000` (pck00011) and adding Titan's SPK position, reproduces the DTWG's own `HUY_DTWG_ENTRY_EME2000_POS` table to under 1 m. Using the DTWG's own CPCK14JAN2010 instead gives the same result.

**Sampling.** Samples are adaptive, as in `export_tracks.py`: an interval is bisected until the Hermite error is within tolerance at its midpoint and quarter points.
- Coast: 5 µrad seen from Cassini, between a floor of 10 m and a cap of 50 km.
- Entry, descent and surface: 10 m. In the DTWG span the error is checked against **every source row** inside each interval.

## Verification (`tools/verify_huygens_track.py`)

| Check | n | max | median | p99 |
|---|---|---|---|---|
| Coast vs SPK -150, km | 3000 | 0.288 | 0.0001 | 0.0017 |
| Coast error / tolerance budget | 3000 | 0.81 | 0.001 | 0.03 |
| Coast vs SPK, µrad from Cassini (range > 2000 km) | 2412 | 4.05 | 0.004 | 0.075 |
| Blend vs blended source, km | 601 | 0.013 | 0.000 | 0.013 |
| Every DTWG row (stitched) vs track, m | 9139 | 9.83 | 0.70 | 7.10 |
| Descent table: position, m | 8693 | 9.83 | 0.71 | 7.03 |
| Descent table: altitude, m | 8693 | 9.69 | 0.38 | 5.56 |
| Entry table (before stitch): position, m | 386 | 8.51 | 0.52 | 8.14 |
| Surface vs landed point, m | 2500 | 9.49 | 0.017 | 0.071 |
| tracks.js (Node) vs Python Hermite, m | 8 | 0.0 | 0.0 | 0.0 |

The coast maximum of 0.288 km occurs while Cassini is far away, so it is still within the angular budget (0.81 of it). Near separation the probe is metres from Cassini, so the 10 m floor applies.

**Handover continuity at entry interface:**
- The raw stitch jumps 24.40 km, which gives a 17.1 km/s spike in finite-difference speed.
- The exported track matches the DTWG at entry interface to 0.0 m.
- Across entry interface (±1 ms, after removing the motion itself) the position step is 0.0001 m and the velocity step is 0.0009 m/s.
- The largest 1 s step in the window is 6.73 km, which is the probe's speed (6.03 km/s). The raw stitch's largest step is 26.1 km.

The landed point reads back as 10.57302°S, 192.33465°W at random surface times. Label altitudes in the catalog match the DTWG interpolated at each frame time to within 0.7 m (median 0.3 m).

## Catalog notes

- **et and utc:** `et` is the mid-exposure time. `utc` has millisecond precision.
- **Phase:** a frame is `phase: "surface"` if it was taken after 11:38:10.769 UTC.
- **Altitude:** `alt_km` is the label's `SPACECRAFT_ALTITUDE_START` (the DTWG 2011 reconstruction).
- **Position:** `lat_deg` and `lon_w_deg` are the DTWG descent table interpolated at `et`. On the surface they are the landing site.
- **Azimuths and tilt:**
  - `az_sun_deg` is measured CCW from the Sun, seen from nadir.
  - `az_north_deg` is measured CW from North.
  - `tilt_deg` is the east-west tilt; positive means the parachute is east of the probe.
  - All three come from Karkoschka's 2013 analysis, as given in the labels.
- **Counts:**
  - SLI: 130 descent + 84 surface
  - MRI: 117 + 67
  - HRI: 125 + 79
  - UHH/LHH half-frames: 4 + 2
- **Flags:**
  - `bad_time` (2: DISR_1068 and DISR_1089): the label time is a placeholder, 19:10:21. `et` and `utc` are null and the frames sort last. They are surface frames. They have no processed version, so their images are the raw EDR stretched on their own (`edr_fallback`).
  - `zero_exposure` (11): 3 MRI/SLI/HRI triplets at 09:23:46, 09:43:12 and 09:53:18, which are manual dark frames, plus the 2 bad_time frames.
  - `saturated` (57, mostly HRI on the surface): more than half the pixels are at the frame's maximum, because of the surface lamp. The image is mostly flat white or black.
  - `half_frame` (6): UHH/LHH.
  - `per_frame_stretch` (11): the frames that could not use the shared stretch.

## Image stretch

Source images come from Karkoschka's processed set **E** (`DISRSOFT_E_IMAGES_13NOV2005`): flat-fielded, dark-subtracted, decompressed, PSF-deconvolved, and oriented like the descent attitude. That is, they are flipped up/down relative to the raw EDR TIFF. All 606 frames that exist in set E were used, so set G was never needed. Native sizes are SLI 128×256, MRI 176×256, HRI 160×256, and half-frames 160×128.

Set E values are raw DN × 8 at the frame's auto-exposure time. Pillow rescales 16-bit PGMs to their own maxval, so `tools/pgm.py` reads the raw values instead.

**`images/huygens/` (shared stretch).**
- Each pixel is converted to DN/ms = E/8 ÷ exposure ms.
- It is then mapped linearly to 0–255 between the 0.5 and 99.5 percentiles pooled over all non-saturated frames of the same **camera and phase**. Half-frames use the HRI limits.
- The limits in DN/ms are:
  - SLI: 21.0–326.8 descent, 13.8–70.3 surface
  - MRI: 19.9–306.4 descent, 44.0–2000 surface
  - HRI: 46.8–335.3 descent, 58.4–2000 surface
- Descent and surface have separate limits, because the surface frames are lit by the probe's lamp.
- Brightness differences between frames of one camera and phase are therefore real. Scene brightness falls about 10× from 140 km to the ground, so low-altitude frames come out dark and low-contrast. The surface features differ by only a few percent.
- `mean_dn_ms` in the catalog gives the same brightness as a number.
- The 11 dark or fallback frames are stretched on their own, because they have no exposure to normalise by.

**`images/huygens_enh/` (per-frame stretch).** Each frame is stretched between its own 0.5 and 99.5 percentiles. Use these for display. To keep the real brightness trend, modulate them with `mean_dn_ms`. `evidence/frames_raw_vs_processed.png` shows the two sets side by side.

## Seeing the frames as one surface

Single DISR frames are hard to read: each covers a thin wedge of ground, the low-altitude ones are dark, and haze washes out the high ones. The imagers share one passband (660 to 1000 nm), so there is no colour to recover.

`build_mosaics.py` takes the twelve mosaics Erich Karkoschka assembled from all the frames (archive `EXTRAS/MOSAICS/MOSIACS_PNG`) and matches their brightness, so the replay can zoom smoothly from 60 m to 1 m per pixel. Each source file was scaled to 16 bits on its own; gains and offsets are fitted from each scale to the next coarser one over their overlap.

`project_frames.py` places every frame on that map. Its camera model is the instrument catalog's (rows run in nadir angle, columns in azimuth). Row direction, column direction and an azimuth offset of +4 deg were fitted against the mosaic: projected HRI/MRI frames at 6 to 14 km correlate with it at a median r = 0.80, and every other convention scores 0.54 or less. Frame by frame (`fit_r`), MRI frames at 1 to 14 km match at r 0.75 to 0.85 and HRI at 6 to 14 km at 0.47. Below 5 km an HRI frame covers only a few hundred metres, less than the uncertainty of the probe's position, so those footprints are approximate. Painting the frames themselves into a map with this geometry was tried and gives a radial patchwork, because the label attitude is not precise enough to line up frames taken at different altitudes, so the mosaic stays the surface and the frames are shown as footprints on it.

### Colour

`descent_color.py` gives the frames the colour the probe's spectrometers measured. The downward-looking visible spectrometer (DLVS, 477 to 977 nm) and the violet photometer (DLV, mean over 350 to 480 nm) cover the eye's range. Below 477 nm, where the spectrometer stops, a straight line is fitted that meets the spectrometer at 477 nm and matches the photometer's mean; about three quarters of the blue (Z) signal comes from that fill, so blue is the least certain channel. Each spectrum goes through the CIE 1931 colour matching functions to sRGB with a D65 white and no adaptation (the Sun is near D65), and only its hue and saturation are applied: brightness still comes from the frame. The probe's lamp lit the ground below about 700 m, so frames below that and on the surface use the 0.7 to 2 km colour. The result is a tan from 140 km down to about 3 km, turning orange-brown near the ground as less haze lies between the probe and the surface.

```
python web/huygens/descent_color.py --spec <dir with DLVS_DDP.TAB and DLV_DDP.TAB> --replay <replay>
python web/huygens/build_mosaics.py --src <DISR>/EXTRAS/MOSAICS/MOSIACS_PNG --out <replay>
python web/huygens/project_frames.py --replay <replay> --movie descent_mosaic.mp4 [--color <replay>/huygens_color.json]
```

## Evidence (`../evidence/`)

- `handover_before_after.png`: altitude, speed and offset around entry interface, comparing the raw stitch (24 km jump, 17 km/s speed spike) with the blended track
- `trajectory_overview.png`: probe and Cassini around Titan, from separation to landing and over the last 6 h; plus the descent profile with every frame's time, marked by camera
- `frames_raw_vs_processed.png`: six HRI frames from 140 km to 1.5 km, showing raw EDR, the shared stretch and the per-frame stretch
- `descent_movie.mp4` (597 frames, 10 fps, 59.7 s, 720×660) and `descent_movie.gif` (360 px wide): every descent frame, then the surface frames, from the `_enh` set, with UTC, altitude, camera and id overlaid. Dark and bad-time frames are left out.
- `contact_sheet.jpg` (shared stretch) and `contact_sheet_enh.jpg`: all 608 exported frames in time order
