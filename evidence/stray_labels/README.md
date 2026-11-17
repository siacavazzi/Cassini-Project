# Audit S5: archive housekeeping (2026-11-16)

## Stray label copies
`label_handler.frame_labels` run over the archive's own listing (cassini_lut8.zip, `data_source.listdir`):

| folder | labels listed | frames' own labels | stray copies skipped |
|---|---|---|---|
| wac_data | 124,739 | 124,723 | 16 |
| nac_data | 318,743 | 318,454 | 289 |
| total | 443,482 | **443,177** | 305 |

443,177 is exactly the number of rows in `Image_index.csv`. Every one of the 305 copies (`<frame> (1).LBL`) is byte for byte identical to its twin's label, and every one has a twin. No archive file is changed.

## N1855753770_1
Fetched from NASA (PDS COISS_2108, MD5 verified, `orig12.py fetch-frames`) into `orig12/comparison/` on the Mini's T7, as an addition. NASA's own product is the same as the archive's: its IMG holds **256 x 256** pixels (VICAR NL=256, NS=256) under a PDS label that says `INSTRUMENT_MODE_ID = "FULL"`, `LINES = 1024`. So a re-fetch cannot fix it. The archive's copy is correct, and the mismatch is in NASA's data. PR #476's `resize_image` change (draw any picture stored smaller than 1024 at the frame grid) is the right handling, and it is the only such frame of the 443,177.
