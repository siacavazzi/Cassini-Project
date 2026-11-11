# WP2 · Tables phase and full-view pictures

Read `_common.md` first.

**Goal.** Every per-frame JSON the page asks for exists as a file in the shape `tables.schema.json` gives, and the
full-view pictures of decision D3 exist.

**Owns.** `web/frames/prebuild.py`, new `web/frames/tables.py`, new `web/frames/test_prebuild_tables.py`.

**Read first.** `web/public/tables.schema.json`, `keys.json` (tables), `policy.json` (routes with store `table`). In
`obs_mosaic.py`: `unit_of`, `units`, `kind_of`, `pass_info`, `steady_table`, `fade_table`, `tile_map`, `layout`,
`MAPS_DIR`. In `prebuild.py`: `items`, `all_passes`, `mosaic_passes`, `movie_passes`, `make_pass`.

**Do.**
- `tables.py` calls those functions for each pass and writes, under `<out>/table/pass/<pass id>/`: `info.json`
  (pass_info without `n`), `kind.json`, `steady/c1k0.json` and `c1k1.json` for every movie pass (plus `c0k0`, `c0k1`
  where Auto center leaves the pass as it is), `fade/l1_<W>x<H>.json` for each mosaic movie at the W x H of its 1024 and
  512 rolling pictures, and `maps/<layout>.json` for every layout a frame's tile map names. Then the alias shards
  `<out>/table/alias/<shard>.json`. No new logic: a part is exactly what the route answers today. Validate every file
  against its `$defs` entry.
- A `tables` phase and a `fullview` phase in `prebuild.py`: fullview makes each mosaic pass's mosaic at its last frame
  at `size=full` (2048 px, `obs_mosaic.mosaic_webp(..., out=min(CANVAS, FULL_MAX))`, exactly as the route does). Both
  are incremental phases on a finished cache, so the full cache build is not held for them.
- The publisher reads tables from this output; agree the folder with WP3 through the lead if it is not `<cache>/public-tables`.

**Don't.** Edit `obs_mosaic.py` (ask WP1 for a helper) or change any maker.

**Tests.** `test_prebuild_tables.py` on sample passes of the sampler cache: each part equals the live route's JSON once
keys are sorted (info with `n` added back), every frame of a pass is in its shard, every part validates.

**Done when.** Both phases run on the sampler slice in under an hour on both Macs, and a coverage report lists no pass
without its tables.
