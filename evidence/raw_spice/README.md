# Raw with SPICE: evidence

- `plume_raw_placed_processed.jpg`: N1880382131_1 (Enceladus plume, 2017-08-01): the frame route's raw picture, the new
  raw placed by SPICE (`/frames/processed/<ID>?off=all&center=1`), and the processed picture. The placed one keeps the
  raw's own codes (sky 24, plume peak 48 to 51 of 255; the raw 24 and 48) and sits where the processed one does.
- `enceladus_2017_raw_placed_steps.jpg`: NAC in full view at 2017-08-01 11:31:30 UTC: Raw (placed by SPICE), Auto
  center off (the frame as taken), Auto center on again, Color, Full (the 18-tile colour mosaic).

Built with this branch's `prebuild.items("rawplaced")` for the 24 frames of ISS_286EN_SPOLE001_CIRS into a scratch
cache, served by a local frame server at this branch; every other picture came from the Mini preview of the 2017 cache.
Timing: 0.16 to 0.22 s a frame (three sizes), about 33 KB a frame.
