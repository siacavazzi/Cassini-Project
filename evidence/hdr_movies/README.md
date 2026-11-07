# HDR movies and mosaics: recovery maps for tiles, movie frames and mosaic pictures

The stills of #361 keep a recovery map. This does the same for the pictures a pass makes:

- **Tiles.** `calibration.display` draws a tile on the pass's one scale. When a caller asks (`load_channels` on a pass's
  scale, one frame) and `hdr_capture` is open, it also keeps the tile's map. `obs_mosaic._tile_made` opens the capture,
  and `color_image.processed_frame` places the map like the tile (#361). The map is cut like the tile (`_lit_crop`) and
  written as `<n>.hdr.webp` beside `<n>.png`. What the camera saturated is marked 8x white in the map.
- **Movie frames.** `movie_frame` records each tile `_place` draws: the color set's planes, the trail and the tinted
  frame. Its map is those tiles' maps, placed the same way (`hdr_map`). Within a filter the tile drawn last wins
  wherever it has alpha. Across filters the brightest wins. The map is kept as `<frame>.hdr.webp` beside the frame's
  WebP (`keep_picture_map`).
- **Mosaics and mosaic movies.** `so_far` places the maps of the tiles each drawn filter uses, and of its luminance
  base, where `_over` places the tiles (`_mosaic_map`), with the tiles drawn under the picture placed first. The
  pictures themselves are not drawn again.
- `calibration.hdr_note_served` records which cached picture a maker just served, along with its map, so the frame
  server and the film export can find its HDR version.

Blends, seam gains, exposure gains and detail() change the SDR picture but are not applied to the map. The map is a
ratio, so it still fits where those steps only scale the picture. At soft tile seams the map takes the newest tile's
value.

## Parity (the real prebuild, twice)

`parity2.sh` runs `prebuild.py mosaics` and `movies` with `--only movie-ids.txt`, which covers three passes:
ISS_003EN_PLUME001_PRIME (Enceladus plume movie, 26 frames), ISS_007RI_HIPHASE001_VIMS (ring movie, 19) and
ISS_028RI_HIPHASE001_VIMS (the 2006 backlit Saturn mosaic, 78 tiles). It runs once with `CASSINI_HDR=0` and once with
`=1`. Comparing the two caches (`../hdr_stills/compare.py`):

    files without HDR: 966, the same bytes with HDR on: 966; new files: 414 (all maps)

| new files | count | mean KB |
|---|---|---|
| tile maps (`.hdr.webp`; measured as PNG in the run, 92 KB; lossless WebP of the same maps 38 KB) | 123 | 38 |
| movie frame maps | 187 | 9.3 |
| mosaic picture maps | 104 | 13.7 |

That is about 7.7 MB on a 191 MB cache, or 4%. Time: mosaics 460 s to 499 s, movies 160 s to 181 s (one thread).

## Pictures

`*_SDR.webp` is the cache's picture (unchanged). `*_HDR.avif` is made from it and its map by `hdr_still.make_avif`
(#362). `*_headroom.jpg` is the SDR picture in gray with the map's highlights in amber. `sheet.jpg` shows all three.

- `plume_movie_frame`: Enceladus' lit crescent, up to 3.2 stops above white
- `rings_movie_frame`: the ring movie's bright limb
- `shadow_mosaic`: the backlit Saturn mosaic, with the rings, the glare and the E ring arc (4% of the picture)
