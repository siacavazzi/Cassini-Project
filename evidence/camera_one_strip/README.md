# One strip under a camera picture

Before is #466 + #467 merged (990775be). After is this branch. Both were shot at the same moment, with frames from the channel-frames preview cache (Mini 8990), in Playwright at 1600x1000.

- `window-color-before-after.jpg`: NAC window on the Saturn approach movie, 2004-02-16 13:27:49. Before, there were two thumbnail rows (filter frames and picture strip) and five status lines. After, there is one row, the red, green and blue channels are marked along the frames' bottom edges, the strip's last row covers time, and the caption covers the picture.
- `full-color-before-after.jpg`: the same window in full view. The Replay window's own transport and speed (play, the moment arrows, the speed slider and the time warp) sit in the strip's last row. They move there and back rather than being copied. The ‹ › arrows and the ← → keys step one picture.
- `window-mosaic-before-after.jpg` and `full-mosaic-before-after.jpg`: the false color mosaic movie, 2005-02-06 13:01:08.
- Video, `one-strip.mp4` in the project files: full view, play and pause, three picture steps, a double click on a red-channel frame that opens it on its own, As taken and back, then Esc twice.
- `phone-full-after.jpg`: on a phone (iPhone 13 emulation) in full view, the controls wrap onto rows of their own above the count.

Checks: `node web/test_one_strip.cjs BASE` passes 22 of 22 checks at both moments (11 each, including one arrow press in movie mode being one step). `node web/test_channel_frames.cjs BASE` still opens 23 frames with 0 failures, because the filter row's frames still open when the strip is off.
