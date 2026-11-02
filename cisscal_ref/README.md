# CISSCAL IDL source + test frames (scratch branch, never merge)

- `../cisscal_idl/`: CISSCAL **4.1** (readme dated 7/7/2019), unchanged, from
  https://pds-rings.seti.org/holdings/volumes/COISS_0xxx/COISS_0011/extras/cisscal.tar.gz
  (same files as the latest COISS_0011 calibration volume). The calib/ support data
  (darkcurrent, slope, dustring, offset, correction, ...) is not included; it is on
  the USGS mirror. None of the three steps below reads calib/ files.
- `docs/iss_data_user_guide_180916.pdf`: ISS Data User's Guide (CISSCAL is Section 4.4).
- `raw/`: 4 raw EDRs (.IMG + .LBL) from COISS_2017; `frames.txt` has the key label values.
  - N1511812952_1, N1511812985_1: 2005-331, Enceladus, TABLE (8-bit LUT), lossless, AB ON, 220 ms, gain 29
  - N1513700682_1: Enceladus, 12BIT, lossless, AB ON, 1.5 s, gain 29, dark sky
  - N1510252949_1: Iapetus, 12BIT, lossless, AB ON, FULL, 32 s, gain 12

**No GDL reference outputs.** Homebrew and conda-forge have no GNU Data Language
package for macOS arm64. GDL's own GitHub weekly-release has a macOS arm64 dmg, but the
Mac Mini's agent safety check refused to run a downloaded binary.

## Where the steps are

Pipeline order (`cassimg__radiomcalib.pro`): TwelveBit (LUT) → BitWeightCorrect →
**DeBias** → **TwoHz** → SubtractDark → **BrightDark** (A-B pairs) → Linearise → flats ...

| Step | File | Notes |
|---|---|---|
| Bias | `cassimg__debias.pro` | BSM (label `BIAS_STRIP_MEAN`, de-LUT'd for TABLE) or OC: linear fit (`linfit`) to the per-line overclock average; zero pixels stay 0 |
| 2 Hz | `cassimg__twohz.pro` | overclock method (OC minus its linear fit) or image-mean method (mask via `AutoStarLevel` sigmas=4, `pixrange` 9, per-line median of cols 12..NS-5), then mirror-pad 100, SavGol(15 NAC / 10 WAC, order 4) minus 4x `smooth` slow part; split at `LineBreak()`; FULL mode only; skipped for TABLE with gain state < 3 |
| A-B pairs | `cassimg__brightdark.pro` | AB ON and FULL only; threshold `abpp threshold` (default 30); replace bright/dark pair with mean of left/right neighbours |
| helpers | `cassimg__define.pro` | `Overclocks` (l.46), `OverclockAvg` (l.59), `Missing` (l.98), `LineBreak` (l.180) |
| helpers | `cassimg__readvic.pro` (overclock prefix bytes, l.243), `cisscal_delut.pro` (8→12-bit LUT inverse) |
| options | `cisscal_readoptfile.pro`, `cisscal_default_options.txt` | bias type BSM / OC / IM. **IM = BIAS_STRIP_MEAN bias + image-mean 2 Hz**; OC = overclock bias + overclock 2 Hz |
