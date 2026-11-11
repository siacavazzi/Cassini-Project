# WP5 · Camera windows, lens and save menu

Read `_common.md` first.

**Goal.** With the public switch on, the camera windows ask only for what is published.

**Owns.** `src/head-quiet.html`, `src/steady-local.html`, `src/loupe.html` (`src/` is `web/cassini-os/src/`), and the
harness sessions `web/public/harness/sessions/s1.mjs` to `s4.mjs` and `s8.mjs`. Port 8912.

**Read first.** In head-quiet.html: `FRAMES`, `frameUrl`, `colorUrl`, `movieUrl`, `rollingUrl`, `savesFor` and the save
menu, the `warm=1` look-ahead, `mosaicOf`, the drill-down into pointings and channels. In steady-local.html: `want`,
`apply`, `planeUrl`. In loupe.html: `fullUrl`, `nativeFor`. Settings helpers `cassiniLook`, `cassiniMovieStyle`,
`cassiniHdr` (settings.html, WP6's file: read only).

**Do, behind `window.cassiniPublic` (WP6 sets it; read it as false when absent):**
- Ask canonical URLs only: build them, or check them, with `keys.mjs` (`canonical(...).refused` must be null). No `x=1`,
  no laps, fade or persist on plain movie frames, no `format=png`, no `hdr`.
- Never ask for `exposure=` or `steady=` variants of a pass the table says the page evens: wait for the steady table.
- The lens and full view use the published pictures (D3): `size=full` on a mosaic (the Worker falls back to 1024),
  1024 elsewhere; no `/full.json`, no native crops.
- Save menu: PNG encoded in the page from the picture loaded; the archive frame from R2; science TIFF and label as OPUS
  links (D6).
- A colour picture's channel is cut from the composite in the page (D5), with a test against the server's channel
  within WebP q95 noise.
- A pointing opens as its frame or colour picture (D9), not `/p/<n>.webp`.
- Find and stop the misses the policy cannot see: run S1 to S4 and S8 against the sampler cache with
  `--mode before`, then look at `miss` in the log once WP3's mirror exists (an uncentred movie frame is not prebuilt).

**Don't.** Change anything with the switch off. Keep the separate NAC and WAC windows, mosaics and colour composites.

**Tests.** Harness sessions S1 to S4 and S8 with zero refused and zero misses on the mirror; the channel-cut test; the
existing page tests still pass.

**Evidence.** Before and after harness counts, and recordings of S1 and S3.
