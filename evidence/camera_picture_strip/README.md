# Camera picture strip (PR #466)

Before (main 2bdee523) and after, same moment, frames from the sampler cache (Mini preview 8989), Playwright at 1600x1000 (phone: iPhone 13 emulation, 390 px wide).

- `pho-before-after.jpg`: Phoebe flyby 2004-06-11 20:04:39, camera windows. No strip under ordinary pictures before.
- `jup-before-after.jpg`: Jupiter approach movie 2000-12-11 16:30, camera windows. Seven fixed 44 px thumbnails before; now the width is filled.
- `body-before-after.jpg`: Phoebe body window (per-body windows on).
- `full-before-after.jpg`: NAC in full view on the Jupiter movie.
- `phone-before-after.jpg`: phone layout, docked and full view. The strip is hidden in the docked camera windows (like the channels and caption) and shows in full view (5 thumbnails at 390 px).
- Scrub video (click, drag, wheel, bar): camstrip-scrub.webm in the project files (17 MB, not committed).

Scripted check (ev/act.cjs on the M5): click, drag 2.5 thumbnails, three wheel notches and a bar click each land on the expected picture at both moments.
