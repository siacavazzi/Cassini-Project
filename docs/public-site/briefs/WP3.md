# WP3 · Publisher to R2 and to a local mirror

Read `_common.md` first.

**Goal.** Copy every picture and table the public page can ask for into R2 under its canonical key, and nothing else;
the same into a local folder (the mirror) for every test before real R2.

**Owns.** New `web/frames/publish.py`, new `web/frames/test_publish.py`.

**Read first.** `web/public/` (all of it: keys.py is yours to import), `web/frames/resolve.py` (a stub until WP1
merges: use a test double that maps the sampler cache's files for the routes you test), `prebuild.py`'s item lists,
`frame_server.picture_versions()`, `slices.py`.

**Do.**
- Enumerate every allowed URL per family from the index and prebuild's lists, at the built sizes and parameter values
  `policy.json` allows (frames, archive, composites, processed, pass pictures, thumbnails, full view).
- For each: `resolve()`; `keys.canonical()` with tags from `keys.family_tags(picture_versions())`; upload the file with
  `Content-Type` and its report as metadata per `headers.json` storage (whole, trimmed, or sidecar); a `negative` answer
  becomes a marker object. Upload WP2's tables and shards under the table family. Archive frames per D6.
- Upload last a manifest (`manifest.schema.json`) and print its key: WP8 switches the Worker to it.
- Parallel, resumable, skips unchanged objects (md5 against ETag), goes year by year. `--to-dir` writes the mirror with
  the same keys (metadata in a `<key>.meta.json` beside each object). `published.json` counts objects and bytes per
  family and year and lists anything missing, with a reason.
- Credentials from the environment only (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`).
- Run `python web/public/measure_headers.py` on a harness log first and report whether any route needs a sidecar.

**Don't.** Upload tiles, intermediates or anything the policy refuses; make the bucket public; put a version in code.

**Tests.** `test_publish.py` on the sampler slice into a mirror: every enumerated URL is published or listed missing,
the mirror's bytes equal the server's for 1,000 sampled URLs, metadata round-trips, a second run uploads nothing.

**Done when.** A clean run of the sampler slice to the mirror, with object counts and bytes per year (this sizes R2).
