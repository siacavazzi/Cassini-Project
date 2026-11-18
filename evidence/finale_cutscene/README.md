# Grand Finale cutscene: review fixes

Before (main) and after (this change), from real-time plays of the cutscene in headless Chrome on the M5's GPU against
the complete 2017 cache, at 1440 by 900 and at phone size (390 by 844). Times are seconds from the cutscene's start.
Videos are in the project folder, not in the repo.

| File | What it shows |
| --- | --- |
| `recap_100s_desktop.jpg` | The recap at 100 s. main: the view has stopped moving (it drops from 1.4 to 0.14 degrees a second in one frame at 94 s) and Saturn is small. After: Saturn fills four fifths of the width, set high so the rings clear the captions, and keeps receding and turning. |
| `what_it_found_desktop.jpg` | The "What it found" card on a desktop, the same framing. |
| `what_it_found_phone.jpg` | The same card on a phone. main: the rings run off both sides and the list is printed over them. After: the view stands back until the rings fit the screen's width. |
| `descent_phone.jpg` | The descent on a phone. main: the readout is wider than the screen and printed over the note. After: two lines above the note. |
| `burn_up_75s_desktop.jpg` | The close view of the burn-up. main: the shade under the captions ends in an edge halfway up. After: it fades out gradually. |
| `drag_close_in.jpg` | A drag of 1,600 px sideways while close in on the burn-up. main: the camera is under the cloud tops (5,400 km inside Saturn) and the fireball is gone. After: it stays above the horizon of the spot Cassini went in at. |
| `skip_60ms.jpg` | 60 ms after Skip during the descent. main: the mission view with the cutscene's readout still over it. After: black (the cut to black is the shared change this one is stacked on). |
| `after_keys.jpg` | The page after every key was pressed during the descent and the cutscene skipped. main: a camera window covers the screen, Highlights and Export are open. After: as it was (the key gate is the shared change). |

## Measured

| | main | after |
| --- | --- | --- |
| Whole cutscene, desktop | 297.6 s | 230.3 s |
| Whole cutscene, phone | 407.5 s | 251.2 s |
| Recap over Saturn | 62 s | 55.5 s |
| Credits roll, desktop / phone | 165 s / 275 s | 104 s / 125 s |
| Silence under the credits | 146 s at digital zero | none: a held tone at about -40 dB with a chord every 10 s |
| Largest camera jump with the picture showing | none (all three jumps are under the black cover) | the same |
| Camera turn rate in the recap | 1.4 deg/s, then 0.14 deg/s from one frame to the next at 94 s | rises to 2.3 deg/s and eases to 0.37 deg/s, never zero |
| Drag sideways while close in | camera 54.8 thousand km from Saturn's center (inside it) | 65.3 thousand km (above the clouds) |
| ArrowUp six times in the credits | not tested on main | roll moves 766 to 526 px, holds 1.5 s later, rolls again 5.5 s later |
| "Watch again" on the last card | no such button | restarts under black; the interface never shows |
