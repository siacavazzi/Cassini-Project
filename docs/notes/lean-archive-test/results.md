# Lean archive format test: 12-bit Cassini ISS frames

Date: 2026-10-18. Run on Sam's Mac (PDS is blocked from the cloud).

## Summary

- **Size:** the new format (8-bit PNG of the camera's own 12→8 bit square-root LUT codes, plus gzipped line prefixes) averages **300 KB per full-frame NAC image**. That is about the same as the current stretched dataset PNGs (287 KB, so new/old = 1.04×), 0.37× a lossless 16-bit PNG (812 KB) and 0.14× the raw PDS IMG (2,128 KB).
- **Scale is kept:** decoding is `DN = LUT[code]`, which needs no per-frame stretch, so every frame calibrates to I/F. The old PNGs could not be rescaled correctly for any of these 39 frames (see the calibration.py bug below).
- **Quantisation cost is real at gain 29:** at gain 29 e⁻/DN the camera's 8-bit table has steps of about 2–3σ of photon noise. Error / (shot + read noise) has a worst case of **2.0**, a median per-frame 99th percentile of **1.65**, and an RMS of **0.83**. In practice this raises the total noise by about 30% (√(1+0.83²)). It is exactly the loss the camera itself applied to every TABLE frame. 72% of all 12-bit frames are gain 29. Gain 95 and 215 frames will be worse in σ terms (by about ×1.8 and ×2.7); gain 12 frames will be better (×0.64).
- **Projection for the 200,308 12-bit frames in COISS_2xxx:** about 233 GB of raw downloads, which shrink to about **33 GB** in the new format (16-bit PNG: about 88 GB; old PNG equivalent: about 31 GB). At the throughput I measured, the download takes **1.2–1.7 days single-stream**, or about 0.5 days at the best 4-way parallel rate.
- **Bug found in `Cassini-Project/calibration.py` (origin/main), not fixed since the repo is read-only for this task:** `recover_span()` always accepts span 252, because the ±1e-6 tie handling makes the 252 level set cover all 255 values. As a result, 24 of 39 12-bit frames here "calibrate" from the old PNGs with **I/F 5–19× too low** (old/true median ratio 0.052–0.176). Details are in `old_calibration_check.txt`.

## Sequence chosen

`ISS_123RI_PHOTDARK002_PRIME`, NAC, COISS_2060, 2010-002 (09:43–12:18 UTC), target SATURN (mostly the unlit side of the rings, plus the limb).
That gives 13 RED/GRN/BL1 triplets: **39 frames, all 12BIT, all FULL 1024×1024, LOSSLESS, gain 29 e⁻/DN**. Exposures are 4.6–32 s, and the bias is 17–20 DN.
I picked it by parsing the volume `index.tab` files for 2060/2070/2080/2090 (`scripts/idx.py`). The frame list is in `sequence.json`.
The batch contains no TABLE frames. The TABLE path in `encode.py` (store the raw codes) is implemented but was not exercised.

## Download speed (pds-rings.seti.org; OPUS API also responded, HTTP 200 in 0.37 s)

| Test | Bytes | Seconds | Rate |
|---|---|---|---|
| 39 IMG + 39 LBL, sequential curl | 83.1 MB | 52.4 | 1.59 MB/s overall (1.99 MB/s per IMG) |
| 16 IMGs, 1 / 4 / 8 / 16 parallel | 34.0 MB | 7.7 / 5.8 / 16.4 / 16.0 | 4.45 / 5.87 / 2.07 / 2.13 MB/s |
| cumindex.tab (1.25 GB, one stream, one resume) | 1250 MB | 578 | 2.2 MB/s sustained |
| volume index.tab files (12 MB) | | | about 11 MB/s |

The throughput is noisy and the server seems to throttle above about 4 connections. Plan for about 2 MB/s sustained, or 4–6 MB/s with 4 connections on a good run.
(Python urllib gets 403 without a User-Agent header, so set one.)

## Sizes (39 frames)

| Format | Total | Per frame | vs IMG |
|---|---|---|---|
| Raw IMG | 83.0 MB | 2,128 KB | 1.000 |
| LBL | 0.14 MB | 3.7 KB | |
| Current dataset PNG (per-frame stretch, from cassiniprojectJAN05.zip) | 11.2 MB | 287 KB | 0.135 |
| **New 8-bit LUT PNG** | 11.6 MB | 296 KB | 0.139 |
| **+ prefix.gz** (24 B × 1024 lines) | 0.16 MB | 4.1 KB | 0.002 |
| (prefix as npz instead) | 0.19 MB | 4.8 KB | |
| 16-bit PNG of raw DN (lossless) | 31.7 MB | 812 KB | 0.381 |

Per frame, new/old ranges from 0.62 to 2.27. New is larger where the old stretch had crushed the image into a few levels, and smaller where the old stretch spread a small range over all 255 levels. Per-frame numbers are in `metrics.json`. A chart is in `evidence/sizes.png`.

## Quality (new PNG decoded via LUT vs raw DN)

Noise is σ = √(max(DN−bias,1)/g) with g = 29, excluding pixels at or below bias. "+read" also adds a read noise of 0.75 DN (median of 21 frames). I measured it from pixel-to-pixel differences in sky.

| Metric | err / shot noise | err / (shot + read) |
|---|---|---|
| max over all pixels | 5.39 | 2.01 |
| 99th percentile (median frame) | 2.37 | 1.65 |
| 99th percentile (worst frame) | 4.03 | 1.95 |
| RMS (mean over frames) | 1.15 | 0.83 |

Shot-noise-only ratio by signal level (99th pct median / max): 1–10 DN above bias 3.38 / 4.23; 10–100 DN 2.32 / 2.87; 100–1000 DN 1.43 / 1.60; 1000+ DN 1.30 / 1.34.
The large shot-only figures near bias come from ignoring read noise, which dominates there. The largest absolute error is 15 DN, which is half a LUT step near 4000 DN.
Every new PNG and 16-bit PNG round-trips bit-exactly (asserted in `encode.py`).

## Evidence (`evidence/`)

- `triplet_NN_<first frame>.png`: on the left, the dataset PNGs merged as RGB, each with its own stretch. On the right, the new format calibrated to I/F with calibration.py's math (LUT → bias → shutter-corrected exposure → gain → filter factor → sun distance) and one shared white point, sky black point and gamma 2.2, as in `load_channels`. The old composites have a yellow cast, and their blue/green ratio varies from 0.30 to 0.82 from triplet to triplet. In the new composites that ratio is stable at 0.50–0.77, and the rings come out neutral (`evidence_notes.json`).
- `dark_NN_<frame>_y?x?.png`: the darkest structured 256×256 crop, with the same strong stretch on both sides. In the 4095-DN-span frames (triplets 00 and 12) the old PNG flattens the sky and faint ring to near black in 16-DN steps. The new format keeps the faint signal, and even the 2 Hz banding that the prefix side file is meant to remove. In most crops the new format has more distinct levels (counts are in `evidence_notes.json`).
- `sizes.png`: bar chart of the mean size per frame by format.

## Projection (COISS_2xxx cumulative index, 407,303 frames)

12-bit frames: FULL 86,755, SUM2 79,098, SUM4 34,455, for **200,308** in total. (Image_index.csv also covers the cruise volumes, which is where the ~210k figure comes from.) The gain mix is 29: 145,127; 95: 26,769; 12: 23,976; 215: 4,436.
I used IMG sizes of 2,127,944 / 540,768 / 140,968 bytes and scaled the new format's size per pixel from this batch.

| | Size |
|---|---|
| Raw IMG + LBL to download | about 233 GB |
| New format (8-bit LUT PNG + prefix) | **about 33 GB** |
| Same frames as the old stretched PNG | about 31 GB |
| 16-bit lossless PNG | about 88 GB |

The download takes 1.7 days at 1.6 MB/s, 1.2 days at 2.2 MB/s, or 0.5 days at 5.9 MB/s.
Caveat: this is one ring sequence. Scenes with lots of empty sky compress better, and noisy or busy scenes compress worse, so treat ±30% as the uncertainty.

## calibration.py bug detail

`recover_span` builds the allowed level set as the union of `floor(x+0.5±1e-6)`. For span 252, x = k·254/252 lands exactly on .5 often enough that the union covers all of 0..254, so any PNG passes at 252. The only guard is "levels ≥ 0.75·(span+1)", which lets through any frame with at least 190 levels. Of the 39 frames, the 3 with all 255 levels never reach 252 and correctly return None. 12 more fail the 0.75 guard. The other 24 return span 252 and get a DN scale that is 6–16× too small (true spans are 1,441–4,095 DN).

## Files

- `scripts/`: `idx.py` (index parsing), `encode.py` (IMG reader, encoder, metrics), `evidence.py`, `partest.py`, and a copy of `calibration.py` + `filter_calibration.csv` from Cassini-Project origin/main. I did not modify the repo or check out a different branch.
- `img/`: 39 IMG + LBL (79 MB, kept because they are under 5 GB). `old_png/`: dataset PNGs. `new/`: the new format (`.png` + `.prefix.gz`; the `.prefix.npz` copies are only for the size comparison). `new16/`: 16-bit PNGs.
- `metrics.json`, `evidence_notes.json`, `old_calibration_check.txt`, `projection_counts.txt`, `summary.txt`, `download_log*.txt`.
- `idx/cumindex.tab` (1.25 GB), the full COISS_2xxx index with DATA_CONVERSION_TYPE and gain for every frame. It is useful for choosing what to download; delete it if you need the space.

Reproduce with:
`~/Development/Cassini-Project/.venv/bin/python -I scripts/encode.py . && ~/Development/Cassini-Project/.venv/bin/python -I scripts/evidence.py .`
