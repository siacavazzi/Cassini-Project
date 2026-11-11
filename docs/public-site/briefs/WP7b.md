# WP7b · Movie Editor, films, Gallery and Studio

Read `_common.md` first.

**Goal.** Making and sharing a movie never touches an origin.

**Owns.** `src/movieedit.html`, `src/export.html`, `src/segment.html`, `src/gallery.html`, `src/studio.html`, and the
harness sessions `web/public/harness/sessions/s5.mjs` to `s7.mjs`. Port 8914.

**Read first.** Those files; `window.cassiniPlanLocal` as WP7a's brief defines it (stub it until WP7a merges);
`docs/compute-on-viewer.md` rows 6, 7b and 7c (films made in the page, colour smoothing, film stabilization already
ported).

**Do, behind `window.cassiniPublic`:**
- movieedit.html takes its plan from `cassiniPlanLocal.plan` and its levels from `.levels` over the pictures it loads,
  starts no Pre-process (segment.html's make off), and previews through `cassiniSteadyLocal` as the windows do.
- export.html makes films only in the page, up to 1024 px a camera: no `POST /export`, no `PUT .../sound.wav`, no
  `/export/<job>`; a clear note in browsers without WebCodecs.
- gallery.html makes a shared film in the viewer's browser through export.html's make-here path, with a progress note
  (D7), and asks full sizes only where published.
- studio.html hides tile tuning (`tune=`, `hide=`); looks, filters and crop unchanged.
- Script the steps S5 to S7 now log as skipped (change the look, make a 1024 px film and download it; open a shared
  film link and a shared Studio edit in a fresh browser; change a mosaic's looks and export).

**Tests.** Harness S5, S6 and S7 with zero refused and zero misses on the mirror, and no skipped step; update the
existing export-here and movie-levels page tests.
