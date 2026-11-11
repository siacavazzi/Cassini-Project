# WP6 · The public switch, settings and small modules

Read `_common.md` first.

**Goal.** One build-time switch that turns the site into its public form.

**Owns.** `src/settings.html`, `src/about.html`, `src/link.html`, `src/loading.html`, `src/flag.html`, `src/reel.html`,
`src/highlights.html`, `src/dock.html`, `src/bodymode.html`, `src/coverage.html`, `src/build.py`, `src/site.json`, new `web/test_public_switch.cjs`, and the
harness session `web/public/harness/sessions/s9.mjs`. Port 8913.

**Read first.** `policy.json` `page_settings`; settings.html (every `D({...})`, `cassiniLook`, `cassiniOff`,
`cassiniMovieStyle`, `cassiniHdr`); build.py; about.html's version line; loading.html's jumplog.

**Do.**
- `"public": true` and `"frames": "<frames host>"` in `site.json`, set at build time by `build.py --public --frames URL`;
  the page reads them as `window.cassiniPublic` and the frames host (head-quiet's `FRAMES` keeps `?frames=` first).
- With it on, hide and force what `policy.json` `page_settings` lists: the 18 processing toggles, Balanced color, raw
  and false Filter colors, Auto center (D4), HDR highlights and glow (D8, forced off), Mosaic movies keep above 1,
  Mosaic passes: Always mosaic, Pre-process, the flag button and /flags links, the reel window (D2), Studio tile tuning.
  Steady movies on this computer is forced on.
- `version.json` and `slices.json` come from the frames host (the Worker answers them from the manifest); the usage
  beacon posts to the frames host's `/usage`; the page posts no jumplog.
- The static build includes `data/coverage/` (build_coverage.py) for "Seen so far" and "Pictures of a place", and the
  explainer page's `how/` folder from #414 (merge #414 in before you start if it has merged; it also edits about.html).
- `build.py` inlines WP7a's `src/plan-local.js` and `src/levels-local.js` as it does steady-local.html, so they reach the
  page. Add them as soon as WP7a's PR exists (an empty file is fine until then).
- You also own `src/bodymode.html` and `src/coverage.html` (they ask the frames host for `size=256` and `size=128`
  frames): fix any miss S1 or S9 finds there.
- Decide, with numbers, whether three.js and the two fonts move onto Pages (the harness's `cdn` count) and say so in the PR.

**Tests.** `web/test_public_switch.cjs` (every hidden setting hidden, every forced value forced, nothing changes with
the switch off) and harness S9 with zero refused requests.
