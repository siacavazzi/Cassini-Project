# HDR stills: a recovery map beside every composite and processed frame

`calibration.tone` draws the 8-bit picture as before. With `calibration.hdr_capture()` open (the frame server opens it
for every composite and processed frame unless `CASSINI_HDR=0`), it also keeps a recovery map: per pixel of the
highlights, log2 of how much brighter the linear picture was than the picture drawn (`calibration.recovery_map`).
The frame server writes it as a grey lossless WebP in `hdr-r1/` beside the picture's size folders
(`frame_server.keep_hdr`), moved, turned and cut like the picture when it is centred. The SDR picture is the same bytes
either way. `web/frames/hdr_still.py` makes a PQ AVIF or PNG from a cached picture and its map, with no pipeline run.

## Parity (the real prebuild, twice)

`parity.sh` runs `prebuild.py composites` and `processed` with `--only` 80 frames (2006-09-15 09:15-09:50,
ISS_028RI_HIPHASE001_VIMS, and 2013-06-26 01:20-02:30, ISS_193SA_NPOLMOV001_VIMS), with `CASSINI_HDR=0` and `=1`.
`compare.py parity-0 parity-1`:

    files without HDR: 542, the same bytes with HDR on: 542; new files: 90, of them maps: 90
    map KB: mean 16.0, median 6.5, max 91.1

Every WebP (270) and report (270) is identical. Time: composites 17 s -> 18 s, processed 51 s -> 54 s (one thread).

## Pictures

- `shadow_SDR.webp`, `hexagon_SDR.webp`, `hexagon_RED_frame_SDR.webp`: the cache's pictures (unchanged)
- `*_HDR.avif`: made from those and their maps by `hdr_still.py` (10-bit PQ, Rec.2020)
- `shadow_map.webp`: a map (84% of it 0 stops; up to 3 stops over the saturated glare)

The shadow AVIF made from the cache matches the one made from the pipeline's linear data directly (the study's
capture) to 0.012 PQ in the highlights (about 1 to 2% of their brightness: the cache picture is sharpened and WebP).
