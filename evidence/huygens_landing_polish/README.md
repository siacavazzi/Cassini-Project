# Huygens landing cutscene: review and polish

Before is `main` e755fd89, after is this branch (on top of the shared cutscene fixes, `claude/cutscene-shared-fixes`).
Both were played in headless Chromium on the M5 MacBook (Metal) against the same replay data, on a hand-stepped clock
at 30 frames a second, with the camera logged every frame; the sound was recorded from a second, real-time run of each.
The videos are in the project's shared folder, not here:

- `huygens_landing_before_desktop_sound.mp4`, `huygens_landing_after_desktop_sound.mp4` (1280 x 720, with sound)
- `huygens_landing_before_phone.mp4`, `huygens_landing_after_phone.mp4` (390 x 844)
- `huygens_landing_touchdown_before_left_after_right.mp4` (the last seconds of the descent, side by side)

## What the camera log says

| | before | after |
|---|---|---|
| Length (screen seconds, plus 1.6 s of fade in) | 112.0 | 97.3 |
| Largest turn of the view in one frame, picture showing | 23.4° (0:33.6), 18.0° (1:01.6) | 0.9° |
| Fastest second of turning | 36°/s (parachute pull-back) | 22°/s |
| Fastest change of distance | 64 m to 22 m in 0.6 s (0:19.5) | 64 m to 22 m in 3 s |
| Probe on screen in the last 8 s of the descent | half off the top edge | centered |
| Closing shot | 39.5 s of Cassini on Titan's night side | 15 s, then the probe on Titan under the card |
| "Stay with Huygens" | clock runs on at 10 min/s | paused, the view does not move |
| Dragging up after touchdown | camera under the ground | stops 35 cm above it |

## Stills

- `approach_before_after.jpg`: 4 s before touchdown.
- `last_card_before_after.jpg`: the closing card.
- `cassini_epilogue_before_after.jpg`: Cassini as the link ends (the camera is now on the Sun's side of it).
- `drag_up_after_touchdown_before_after.jpg`: the view after dragging upward as far as it goes, on the ground.
- `phone_before_after.jpg`: 390 x 844, the parachute and Cassini listening.

## Sound

Mean level by section (dB, from the recorded runs; the chords peak at about -18 dB in both):

| section | before | after |
|---|---|---|
| entry | -36.7 | -37.8 |
| parachutes | -41.4 | -38.1 |
| Cassini listening | -40.7 | -36.4 (carrier tone) |
| descent to the ground | -43.2 | -38.6 |
| touchdown | -36.7 | -34.9 |
| epilogue | -40.2 | -34.1 until the link ends, then -37.7 |

Before, the rumble started at a third of its level in vacuum, held for 9 s after the heating was over and cut off as
the parachutes opened; between chords there was silence. After, a soft bed sits under the whole of it, the rumble
follows the air, and Cassini's shots carry the probe's carrier as a faint tone that stops at the end of the link.

## How it was made

`step.cjs` plays `?huygens-landing` on a stepped clock, logs the camera every frame and (with `REC=1`) writes the
video; `analyze.py` reads the log; `input.cjs` runs the input checks (drags, wheel, keys, clicks, two fingers, Skip and
Escape at several moments, the three endings, a replay); `audio.cjs` records the page's sound in real time and
`levels.py` measures it. `proxy.py` serves one built `index.html` on a local port and passes everything else to a
running preview, read only. Set `PLAYWRIGHT` to a `playwright-core` folder if it is not on the module path.
