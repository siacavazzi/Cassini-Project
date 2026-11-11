# How the pictures are made: page evidence

Screenshots of `web/cassini-os/how/` (headless Chromium, 1280 px wide).

- `whole_page.jpg`: the whole page, scaled down.
- `flow.jpg`: the opening flow (raw frames + SPICE -> color, body location -> mosaic), Jupiter 29 Dec 2000, playing through its 9 pointings.
- `pointing_steps.gif`: the pointing diagram's five steps with the Rhea preset (16 Jan 2005, real numbers from the geometry cache).
- `pointing_jupiter.jpg`: the Jupiter preset, its center off the sensor.
- `pointing_step5.jpg`: step 5, the shortcut the code takes (`bootleg_autonav.project`).

Every picture on the page was fetched from a frame server at this branch by `web/cassini-os/how/make_images.py`
(archive PNGs, `/frames/processed` with and without one `off=` step, `/frames/color.webp` with `off=align`,
`colors=raw` and `off=calibrate`, `/frames/mosaic/<ID>.webp`); `pictures.json` keeps the server's own report headers
and the geometry cache's numbers. Picture cache versions are unchanged.
