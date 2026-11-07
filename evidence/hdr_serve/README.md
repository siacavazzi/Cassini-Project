# HDR movie frames, mosaics, saves and films (viewer and export side of #363)

The test server is this branch on 127.0.0.1:8930, using a copy of #363's parity cache (three passes built with maps)
and Chrome 157 headless.

- **Routes.** `hdr=1` on `/frames/movie/<ID>.webp` (movie frames and `mode=rolling` mosaic movies) and on
  `/frames/mosaic/<ID>.webp` returns an AVIF. It is made from the picture the maker just served
  (`calibration.hdr_served`) and the map kept beside it (`hdr_avif_served`, kept as `<picture>.hdr-avif-v1.avif`).
  - `movie/N1487333777_1.webp?size=1024&color=1&hdr=1` returns `image/avif` with `X-HDR: 1`.
  - `movie/W1493791136_1.webp?size=512&hdr=1` returns `image/avif`.
  - `mosaic/W1537005244_1.webp?size=1024&hdr=1` returns `image/avif`.
  - The same addresses without `hdr` return `image/webp`, unchanged.
- **Save.** The save menu's "This picture in HDR" (`hdr=1&download=1`) returns the AVIF as
  `Cassini_<ID>_movie_HDR.avif`.
- **Page.** `run.py` opened 2005-02-17T12:05 (Enceladus plume movie):
  - On an emulated HDR screen, 30 of 76 movie and mosaic requests asked for `hdr=1` and 14 came back as AVIF. The
    rest were the first requests for frames made on demand (Even exposure 8, not in the cache), answered with WebP
    while the one AVIF slot was busy.
  - On an SDR screen, none of the requests asked for `hdr=1`.
  - Saved in `requests.json`.
- **Film export.** `export.py 2005-02-17T11:49 2005-02-17T12:15 --cams N --hdr` produced `plume_HDR10.mp4`: HEVC Main10,
  `hvc1`, BT.2020 with PQ, HDR10 metadata, 112 frames. A frame at 3 s peaks at 1,074 nits on the crescent's limb, and
  its 99.9th percentile is 410 nits. `plume_SDR.mp4` is the same film without `--hdr`. In the page, Export's new HDR
  box adds `hdr=1` and has the server make the film.
- **Curve.** One curve for every picture (`hdr_still.MID`, not each picture's own median), so a movie's frames and a
  film keep one brightness from picture to picture.
