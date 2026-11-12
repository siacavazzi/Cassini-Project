# How the pictures are made, round 2: evidence

Screenshots of `web/cassini-os/how/` at this branch (headless Chromium, 1280 px wide), one per reworked section:
`flow.jpg` (source frames turned north up), `source.jpg` (camera photos, filter wheels, filter card),
`raw.jpg`, `calibrate.jpg` (choosable examples), `spice.gif` (the three kernel drawings animating),
`pointing.jpg` (real Dione frame, textured globe, numbered steps), `centering.gif` (nine Enceladus frames as taken
and placed), `color.jpg` (Titan, with Saturn and Jupiter as choices), `mosaic.jpg`.

Pictures come from a frame server through `make_images.py`; `pointing.json` from `make_pointing.py` (the pipeline's
`bootleg_autonav.find_target` plus SPICE); `spice.json` from `make_spice_demo.py` (SPK and PCK). Camera and pallet
photos: NASA/JPL (ISS calibration report, PDS) and NASA/KSC (KSC-97PC1027); location illustration NASA/JPL-Caltech.
Filter purposes from `iss-na-camera-description` (PDS), slot order from the report's Figure 4.2.1-1.
