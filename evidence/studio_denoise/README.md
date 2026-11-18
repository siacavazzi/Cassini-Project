# Studio denoise slider

A Denoise slider in Cassini Studio's Detail group, above Sharpness, off by default (0). It is part of the same single
WebGL pass as every other slider: an edge-keeping (bilateral) average of the 5 x 5 pixels around each pixel, before
the light and color steps. The slider is squared into the filter's range sigma (0.12 at 100), so the gentle end has
fine control. With Sharpness also on, sharpening works on the denoised picture. The movie export's Python copy of the
studio look (web/frames/studio_look.py) does the same, so a film's frames match the studio preview.

- `plume_279EN_denoise_steps.jpg`: ISS_279EN_PLUME001_PIE (2017-06-18), N1876443795_1, 2x crop around Enceladus,
  exposure +2 EV and white 60% to show the grain; then Denoise 25, 50, 75, 100, and 50 with Sharpness 30.
  All drawn by the page's own WebGL renderer (cassiniStudio.apply), full resolution.
- `plume_279EN_late_denoise_steps.jpg`: the same for N1876486995_1, later in the pass.
- `studio_denoise_off.jpg`, `studio_denoise_60.jpg`: the Studio window with the new slider.

WebGL vs the Python film copy on these frames: 99th percentile difference 1 level of 255 (JPEG rounding).

Scripts: `shoot.py` (WebGL renders), `sheet.py` (crops, WebGL vs Python), `ui.py` + `proxy.py` (window screenshots;
the page's static data came from the 2017 preview, no frame was drawn by it).
