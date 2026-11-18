# Saturn arrival cutscene: review and polish

The cutscene (`?soi`, `web/cassini-os/src/soi.html`) played in headless Chromium (Metal GPU) at 1280x720 and as an
iPhone 13, before on main e755fd89 and after on this branch (stacked on the shared cutscene fixes, PR 585). Each run
logged the camera every frame (view direction, up, distance to Cassini, where Cassini is on screen), recorded the
page's own sound, and some runs scripted input (drags, wheel, two-finger pinch, every shortcut key, Skip, Escape).
Videos with sound are in the project folder, not in the repo: `soi-arrival-before-desktop.mp4`,
`soi-arrival-after-desktop.mp4`, `soi-arrival-before-phone.mp4`, `soi-arrival-after-phone.mp4`,
`soi-arrival-roll-before-left-after-right.mp4`.

| | before | after |
|---|---|---|
| Length, first frame to the cover coming down | 56.1 s | 55.9 s |
| Largest camera step in one frame with the picture showing (cuts aside) | 28.8 degrees at 17.8 s | 0.25 degrees |
| Fastest the view turns during the roll onto the shot list | 26 degrees/s, bunched in 3.5 s | 12 degrees/s, over 6 s |
| Drag during the fade to black, the flyby or the move in | turns the view up to 155 degrees, Cassini leaves the shot | held still (look.lock) until two minutes before ignition |
| Wheel during the first 17 s | nothing, then a jump from 40 m to 130 m | nothing, and no jump |
| Phone: Cassini on screen during the flyby | off the right edge from 8 to 11 s | always in frame (never past 75% of the way to the edge) |
| Phone: note and readout | printed over each other | note at the top, readout clear |
| Shortest time a burn line is up | 3.4 s (five lines) | 5.5 s (four lines; the steering line is dropped) |
| "Engine off" line | 3.6 s | 4.8 s |
| Sound before ignition | silent for 23 s | soft bed that grows to the ignition, one note at the ring plane |

- `roll_before_top_after_bottom.jpg`: 13.5 to 20.7 s, a frame every 0.8 s. Before, the horizon stays level and then
  swings round in three seconds (with the one-frame jump in it); after, the roll starts earlier and runs evenly.
- `phone_flyby_before_left_after_right.jpg`: phone, 8 to 11 s. Before, Cassini has left the frame.
- `phone_text_before_left_after_right.jpg`: phone, the note and the readout.
- `after_every_4s.jpg`: the whole cutscene after, a frame every 4 s.

Cause of the jump: the parked camera's orientation and the shot list's are nearly opposite, and three.js's slerp picks
the shorter arc each frame; the shorter arc changed sides as Cassini moved, at a blend of 8%, which is 29 degrees.
