# WP1 · Cache-only resolver and `--public` mode

Read `_common.md` first.

**Goal.** One function that names the cache file a request gets, without making anything, and a server mode that only
ever does that.

**Owns.** `web/frames/frame_server.py`, `web/frames/resolve.py` (WP0 wrote its signature and `Answer`), read-only naming
helpers added to `web/frames/obs_mosaic.py` and `web/frames/reel.py`, new `web/frames/test_resolve.py`. Port 8910.

**Read first.** In `frame_server.py`: `get()`, `size_of`, `webp`, `color_webp`, `processed_webp`, `centre_of`,
`centre_folder`, `color_folder`, `processed_folder`, `thumb_key`, `thumb_webp`, `send_picture`, `not_centred`. In
`obs_mosaic.py`: `mosaic_webp`, `_mosaic_path`, `_mosaic_made`, `movie_webp`, `rolling_webp`, `_rolling_picture`,
`kind_of`, `pass_info`, `steady_table`, `fade_table`, `tile_map`. `web/frames/resolve.py`; `web/public/policy.json`.

**Do.**
- Split each maker's "which file" from "make it" with helpers that reuse the maker's own naming code. No copied naming
  rules: the maker calls the helper.
- Fill `resolve(path, query, cache) -> Answer`: `file` (the cached path, mime and the X-* headers the server would send,
  read from the report kept beside the picture), `negative` (Auto center's 404 with X-Center, from `centre_view` /
  `view_shown`, as `centre_of` decides it) or `none`. It never makes a picture, never starts `warm_frame`,
  `tiles_ahead`, `warm_movie`, `rolling_ahead`, `_map_later` or a startup warmer, and never waits on a slot.
- `--public`: GET only; every request first through `keys.py canonical()` (refused: 404, counted), then through
  `resolve()` for `r2` routes. Table routes answer from the same functions WP2 calls, but only from what is kept
  (never `{"working": true}`; a miss is 404). `version.json` and `slices.json` as today; `/health` answers `ok public`.
  No POST or PUT. None of the warmers start at startup.

**Don't.** Change a picture, a cache name or a version string; reformat or move code in `obs_mosaic.py`.

**Tests.** `test_resolve.py`: for sampled URLs of every `r2` route on a rehearsal cache (the sampler cache on the T7,
read-only), the normal server makes the picture, `resolve()` names that same file, and `--public` sends the same bytes
and headers. Refused URLs answer 404. The thread count stays flat over 1,000 requests.

**Evidence.** A harness session's request log against `--public` beside the normal server's
(`node web/public/harness/zero_origin.mjs --site http://127.0.0.1:8910 --sessions S1,S3 --out ...`), and screenshots
showing the same pictures.

**Done when.** The tests pass and S1 plays the sampler slice against `--public` with no picture missing.
