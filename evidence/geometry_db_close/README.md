# Geometry cache connections closed with their thread

Two frame servers on the Mac Mini, side by side, same environment and geometry cache (`geometry-usgs.sqlite`), fed the
same 200 `/frames/mosaic/<id>.json` requests (first frame of each 2008 observation), counting the server's open
`.sqlite` and `.sqlite-wal` handles with `lsof` every 25 requests (`before.txt`, `after.txt`, `open_handles.png`).

- before (regression-2017, 8c121d5): 0 → 41 handles within 200 requests, and they stay open: request threads have
  ended, their connections wait for the cycle collector.
- after (this PR): 0 throughout (one blip of 3 while requests were in flight).

In production, before: the 8952 preview had 116 `.sqlite` + 91 `-wal` handles open on 2026-11-11 after a day up, hit
its 256-file limit, and answered 404 to every request (page, data, pictures) until it was restarted. The 8955
preview had 61 after six hours.

`python web/frames/test_geometry_db_close.py`: 400 short threads leave 99 files open before, 0 after.
