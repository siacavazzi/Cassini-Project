# Cassini OS

The mission replay dressed as a small desktop OS: a menu bar, windows you can move, minimize into the
menu-bar tray or zoom, and a Camera window that shows the real frame Cassini took at each moment.

| Page | What it is |
| --- | --- |
| `index.html` | Smoked Mac OS X style panels, the camera feed as the main window, the interface fades when the pointer rests (the camera picture stays), window layout remembered per browser. |
| `replay/` | Link to the plain replay viewer (`web/replay`), so one server shows both. |

## Run it

The page reads the replay data through the `data` link (`data -> ../replay/data`), and the camera frames
from the frame server that serves them. Build the replay data once, then serve this folder with
`web/frames/frame_server.py`:

```
python web/replay/build_data.py --data <export dir> --years 1997-2017 --attitude <attitude dir> --huygens <huygens replay dir>
CASSINI_DATA=/Volumes/LaCie/cassiniprojectJAN05.zip python web/frames/frame_server.py --site web/cassini-os --host 0.0.0.0
```

Run the server from the repo folder so it finds the zip index (`zip_index/`). Then open
`http://<machine>:8765/` (Cassini OS) or `/replay/` (plain viewer).

The Cassini model (`web/replay/data/models/cassini.glb.b64.txt`, NASA 3D Resources "Cassini-Huygens",
Draco-decoded) and the planet textures are committed; everything else under `web/replay/data` is generated.

## Change it

The page is generated: edit the head in `src/` (styles, markup, window manager, camera feed), then rebuild the page
from the current replay viewer:

```
python web/cassini-os/src/build.py
```

`src/build.py` takes the viewer's script from `web/replay/index.html` and patches in the hooks the heads use
(colours and fonts from CSS variables, a separate HUD canvas for the glowing orbits, NASA's model). If the
viewer changes a line a patch depends on, the build stops with an assertion naming that line.
`src/strip.py` strips the document wrapper for publishing as a claude.ai artifact.

Design rule (Sam, 2026-10-19): the interface should be as unobtrusive as possible; the OS stays because
there is a lot to configure, and the camera feed is the main feature.
