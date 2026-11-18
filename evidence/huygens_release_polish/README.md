# Huygens release cutscene: review and polish

Recorded from the page itself (Chromium, the page's own screencast and its own sound), played through the release at
1 min/s like a viewer. The clock in the corner is seconds into the cutscene.

The videos are in the project library, not in the repo: `huygens_release_before_after_desktop.mp4` (main on the left,
62 s, and this branch on the right, 48 s, from the same start; the sound is this branch's), `huygens_release_after_desktop.mp4`,
`huygens_release_before_phone.mp4` and `huygens_release_after_phone.mp4` (a 390 x 844 touch viewport). Stills here:

| File | What it shows |
| --- | --- |
| `after_desktop_stills.jpg`, `after_phone_stills.jpg` | stills through the new version |
| `skip_before.jpg`, `skip_after.jpg` | Skip at 20 s: just before, then 0.1, 0.4, 0.9, 1.6 and 3 s after |
| `stay_before_after.jpg` | what "Stay with Huygens" leaves on screen (main left, this branch right; the tour tip on the left is the test browser's first visit) |

Measured on main, per frame (camera direction, distances, where the two craft are on screen):

- the view turned 20 to 26 degrees a second from 19 to 28 s and kept turning until 50 s; Cassini's attitude record has it
  turning 0.79 degrees a second from the instant of the release for about 310 s (axis 0.91 along the probe's), and the
  camera rode Cassini's body. On this branch the view turns 0.5 degrees a second through that stretch and at most 6
  degrees a second in the fly-over (8 on the phone)
- one-frame jumps with the picture up: 6.4 degrees at 0.0 s (main), none on this branch
- a drag during the opening fade opened the picture 103 degrees off (main); 0 on this branch
- sound: digital silence from 15 to 28 s and two chords 0.2 s apart at the release (main); a bed about 10 dB under the
  chords from start to end and one chord at the release (this branch)
