# Processing level bar: evidence

Page only; served from the 2017 cache built on main e755fd89 (Mini preview 8943), the page put in front by a proxy.

- `moon_1999_four_levels.jpg`: NAC, Moon flyby 1999-08-18 02:10:45 UTC, at Raw, Processed, Color and Full.
- `enceladus_2017_full_raw_processed_color.jpg`: NAC in full view, Enceladus south pole 2017-08-01 11:31:30 UTC
  (ISS_286EN_SPOLE001_CIRS), stepped Full (the 18-tile colour mosaic) > Raw (the frame as sent) > Processed > Color > Full.
- `enceladus_2017_before.jpg`: the same moment on main: no bar, the mosaic only.

Test: `node web/test_processing_levels.cjs http://127.0.0.1:PORT OUT 2017-08-01T11:31:30` (15 checks pass at the Moon
moment, every level's picture made from the route it should be; the Settings default moves every window).
