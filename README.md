# Cassini final plunge: real science data (2017-09-15, day 258)

Small time series cut from NASA's Planetary Data System (PPI node) for the last hour of Cassini's data,
for the Grand Finale cutscene. Times are UTC spacecraft event time (signals reached Earth about 83 minutes later;
the DSN heard the carrier end at 11:55:46 UTC).

| File | Instrument | PDS dataset | Last sample (UTC, SCET) |
|---|---|---|---|
| finale_inms.json | INMS, closed-source neutral mode, count rate per mass | CO-S-INMS-3-L1A-U-V2.0 | 2017-09-15T10:31:54.351 (altitude 1,363 km) |
| finale_mag.json | MAG fluxgate, full resolution, KRTP | CO-E_SW_J_S-MAG-3-RDR-FULL-RES-V2.0 | 2017-09-15T10:31:44.755 |
| finale_rpws.json | RPWS key parameters, 60 s spectra | CO-V_E_J_S_SS-RPWS-4-SUMM-KEY60S-V1.0 | 2017-09-15T10:31:30 (start of the last 60 s average) |

The exact source file URLs are in each JSON's `source`.

Each file is `{"source", "dataset", "time", "last_sample", "window", "bins", "series": {name: [[utc, value], ...]}, "units"}`.

## How it was reduced (`reduce.py`)
- Window: the 60 minutes up to each instrument's last sample.
- INMS: hourly L1A CSVs for 09h and 10h. Detector-1 count rate (`c1rate`) for masses 2 (H2), 3, 4 (He), 15, 16 (CH4), 17, 18 (H2O), 28, 44,
  plus detector-2 (`c2rate`, `*_det2`) for masses 2, 4, 16, 18, 28. These are averaged into 400 equal bins of about 9 s, and empty bins are dropped (about 296 remain).
  `altitude_km` is the file's `alt_t`. These are **raw count rates, not densities**. Detector 1 saturates in the last minute (its H2 rate drops to 0 from about 10:31:15),
  while detector 2 keeps rising, so use `*_det2` for the end. There is no clean constant ratio between the two detectors.
- MAG: about 32 samples/s, with |B| computed from Br, Btheta and Bphi. Averaged into 400 bins of about 9 s, plus |B| at 1 s for the last 120 s.
- RPWS: native 60 s rows with quality flag 0. Band powers are the spectral density integrated over frequency (total, <1 kHz, 1–100 kHz, >100 kHz, and the magnetic total),
  plus a log10 electric spectrogram (61 times × 73 frequencies).

## Not included
- INMS densities. The Grand Finale density products (Waite et al. 2018) are not in PDS as a plunge time series, so these are count rates only.
- The MAG 1 s average dataset stops at orbit 292 (day 255), so full resolution was used instead.
