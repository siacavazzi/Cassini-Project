# Cassini OS

The mission replay dressed as a small desktop OS: a menu bar, windows you can move, minimize into the
menu-bar tray or zoom, and a Camera window that shows the real frame Cassini took at each moment.

| Page | What it is |
| --- | --- |
| `index.html` | Smoked Mac OS X style panels, the camera feed as the main window, the interface fades when the pointer rests (the camera picture stays), window layout remembered per browser. Narrow-angle and wide-angle frames each have their own camera window; frames that make a filter set are shown as a colour composite with their channels underneath. |
| `replay/` | Link to the plain replay viewer (`web/replay`), so one server shows both. |

## Movie mode

The film button next to the moment arrows (or `M`, or Go > Movie mode) plays the camera frames one after another,
in time order, at 2 to 24 frames per second, starting from the frame the camera last took. Every frame plays,
whatever the target, camera or filter. The mission clock jumps from frame to frame, so the stretches without
pictures drop out (a "skipped" tag says how long) and the 3D view moves with the film. Space pauses, the arrow keys
step, scrubbing the timeline carries the film on from the new time, and Escape (or the window's close button or the
main play button) leaves. Frames are fetched ahead of the play head; a frame that has not arrived holds the film
rather than being skipped.

## Timeline

The Cassini Replay window is mostly timeline. Its head holds the controls in one small cluster on the left (previous
moment, play/pause, next moment, movie mode, sound), the clock in the middle, and the timeline's zoom on the right.
The view follows the clock, turning the page when now runs off the right edge, until you move it yourself: the
mouse wheel or a two-finger swipe over the timeline scrolls through time, as far as the mission goes, and dragging
the top edge (the row of dates) does the same; a pinch, or ⌘/Ctrl with the wheel, zooms at the pointer. The view
then stays where you left it while playback carries on, and the "back to now" button at the top right lights up;
click it to center the current moment and follow it again. Jumping to a moment or clicking in the timeline (which
moves the clock there) follows again too. The slider zooms from the whole mission (left) to ten minutes (right),
around now while following, otherwise around the middle of the view; − and + halve and double the span.

## Window sizes and full view

Every window resizes from its bottom-right corner, from a thumbnail up to the whole screen; a picture window keeps
its picture square (a mosaic keeps its own shape, letterboxed) and stops growing at the bottom of the screen. Once a
picture is shown wider than 600 px the window asks the frame server for the 1024 px picture instead of the 512 px
one. The zoom button switches between the standard large size and the size you chose. Windows that show pictures
(the camera windows, per-body windows, Play a Body, Movie) also have a full-view button at the right of the title
bar: the window fills the screen under the menu bar, its picture as big as it fits. Double-click a picture or press
`F` for the same, `Esc` to come back. Sizes are remembered with the rest of the layout.

## Dock

Along the bottom of the screen, as on the Mac (`src/dock.html`): Cassini and each body on stage now (the same list as
the main window's body picker; a click flies the view there and brings that body's windows forward, a blue dot marks
the body in view, a grey dot one with windows open), then Moments, Highlights, Gallery and Settings (a click opens the window,
brings it forward, or tucks it away). A minimized window shrinks into the dock as a tile showing its last picture,
including the main window, and a click brings it back. Settings > Interface: Dock on or off (off brings back the
menu-bar tray), Dock position (bottom, left, right), icon size and magnification. On a phone the dock is a strip under
the replay controls that scrolls sideways.

## Shareable links

The address bar always holds the moment on screen (`src/link.html`), so a copied link opens on it again:
`?t=2005-02-16T23:27:00&view=enceladus&speed=3600&play=0&cam=1.836,0.4572,-0.6478`. `t` is the mission time
(UTC, to the second) and follows playback; `view` is `follow` (Cassini, looking where its camera points), `cassini`
(Cassini, free camera) or a body; `cam` is where the free camera sits around it; `speed` is mission seconds per
second; `play=0` opens paused and `movie=1` in movie mode. Other parameters (`?frames=`, `?tex=`, `?finale`) are kept.
The page rewrites the URL with `history.replaceState` at most twice a second, so the back button is unaffected, and
a link's view is for that visit only (it does not change the Follow camera setting). Go > Copy Link to This Moment
(⇧⌘C) copies it.

## Gallery

The viewer's own library of saved pictures and films (`src/gallery.html`, Gallery in the dock or Go > Gallery…). The ＋ in
a picture window's title bar (or G) adds the picture on screen, full view has Add to Gallery beside its save button, and a
finished movie export has Add to Gallery beside Download. Everything stays on this device, in the browser's IndexedDB
(database `cassini-gallery`); no server keeps anything. Each item is its recipe (the moment, as share-link parameters
`t`, `view`, `cam`, `play=0`, plus the `/frames/...` address or the export options that make it through the pipeline)
and, unless Settings > Gallery > Keep a copy of each file is off, the file itself (full-resolution JPEG, or the MP4).
An item without its file (the browser cleared storage, or the setting is off) is made again by the server when opened.
Export Library writes one `.zip` of the pictures (JPEG) and films (MP4); with Include metadata
(Settings > Gallery > Export with metadata) it adds gallery.json and thumbs/, and Import reads that back.

Open an item to see it large, go to its moment, download it, remove it (with Undo) or share it. A shared link carries
the recipe, never the picture: `?t=…&view=…&play=0&pic=/frames/color.webp?ids=…` (or `film=from=…&until=…`) opens the
moment and shows the picture over it, made by the frame server. Share also offers the device's share sheet with the
file itself (phones), Copy picture, Reddit, X, Bluesky, Facebook, a text message and email. Link previews on social sites
need the frame server reachable from the internet.

## Phone layout

On a screen under 600 px wide, or a touch screen under 500 px tall (Settings > Interface > Phone layout: Automatic,
Always or Never; `?phone=1` forces it), the windows dock instead of floating (`src/phone.html`). Upright: the NAC
and WAC pictures side by side under the menu bar, the 3D view in the middle, the replay controls along the bottom
(zoom shows speeds and the body picker), and Moments as a sheet over the view, opened from the list
button next to the moment arrows. Sideways: the two pictures down the left edge and the controls beside them. Tap a
picture for full screen, tap again to come back. Settings > Interface > Camera pictures on a phone (50 to 100 %) sets
how big the docked pictures are.

## Frame rate

The 3D view is drawn at a share of the screen's pixel density (`src/perf.html`, Settings > Performance). With
Automatic quality on, that share drops when the frame rate falls under the target (55 fps by default, so a 60 Hz screen that keeps missing frames steps down) and climbs
back when there is room; 3D resolution (30 to 100 %) is the most it may use. While nothing moves (paused, nobody
touching the view) the view is not redrawn, except once a second. Frosted windows off removes the blur behind
windows, which the browser redoes every frame. Show frame rate puts a read-out in the bottom right corner. The HUD
glow is drawn on the GPU in the HUD's own canvas, and surface maps are decoded off the main thread.

To measure: `node bench/fps.js URL OUT [WIDTH HEIGHT DPR SECS]` (needs `npm i playwright-core`; `CHANNEL=chrome`
on a Mac for the real GPU) reports the uncapped frame rate, the CPU time of each step of the render loop and the GPU.

## Imaging bursts

In normal playback each camera window shows at most a set number of new pictures a second (5 by default). When
Cassini takes a burst of frames faster than that at the chosen speed, the clock slows down so every picture gets its
turn, then returns to full speed once the burst is over; the status line reads "imaging burst, slowed to …" while
it does. Change it with the slider under View > Bursts (0 to 24, 0 = no limit), or in the Settings window (Playback > Maximum images per second,
`playback.maxImageRate`, 0 = no limit) when the page has one. Movie mode keeps its own clock. A burst never slows the clock below a
share of the chosen speed (Playback > Bursts slow playback to no less than, `playback.burstFloor`, 25 % by default),
so a faster speed always plays faster: during the Saturn tour, where Cassini images almost all the time, 1 day/s used to
crawl at about 2 min/s.

## Launch

Playing the mission from the very start of the data (the Launch moment does that, or `?t=1997-10-15T08:43` and
Play), or opening `?launch`, plays a short opening (`src/launch.html`, about 25 seconds; Escape or Skip ends it, as in
every cutscene). The data begins where the Centaur upper stage let Cassini go, 42 min 40 s after liftoff, in low Earth
orbit: the screen fades to black, then up on Cassini on its own with Earth falling away beneath it, the clock reading
its real distance and speed from Earth, and the captions name the plan ahead (borrow speed from Venus twice, Earth and
Jupiter, then Saturn). Then the interface comes back and the mission plays on from there.

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
Movie mode lives in `src/movie.html` (style, window and script); the build splices it into the page.

`src/strip.py` strips the document wrapper for publishing as a claude.ai artifact.

## Mosaics

When Cassini steps the camera across a body a tile at a time, the camera window shows each new tile drawn over
the tiles before it. The frame server decides (`/frames/mosaic/<ID>.webp`, rule in `mosaic.panels`): same camera,
observation and filter (or colour set), the body moved at least 15% of a frame since the last tile, the tiles
overlap, at most 30 min apart and within 10% of the same distance. Stares, movies and filter cycles at one spot
stay single frames. It needs the geometry cache (`CASSINI_GEOMETRY_CACHE`, see `bootleg_autonav.py`); without it
nothing is a mosaic. The window shows its frame straight away and swaps in the mosaic (made by the pipeline like a
body reel picture: stacked, calibrated, aligned, centred north up by SPICE) when it arrives.
`window.cassiniMosaics = false` turns it off.

Most mosaics go further (`web/frames/obs_mosaic.py`): when the frame is in a mosaic pass (one camera, target and
observation, split at a 30 min pause or a 40% change in distance; three or more pointings, footprint under 16
frames), the route sends the pass's mosaic so far: every tile up to that frame, every filter, each tile scaled to
one km per pixel for the pass, placed by SPICE (no overlap needed), drawn like the mosaic benchmark
(`mosaic_benchmark.py`: one display scale for the pass, calibrated compose with none pinned), in false colour when
it cycles three or more colour filters. Where the body fills the frames (Titan's maps) the scale goes from the
darkest to the brightest of the body and the local contrast is raised, so surface detail shows. The view is the
pass's whole footprint (up to 8 frames, or a whole body; bigger ones get a 4 frame window that follows the newest
tile in steps), so it grows in place; the window takes its shape and keeps it up between tiles. Asking for a frame of
a pass starts making its tiles (about half a second each), so the mosaic is usually ready as the camera reaches
it; `python web/frames/obs_mosaic.py <frame id> --cache DIR --all` makes a pass ahead of time.

## Colour sets

The camera windows find filter sets in the catalog (`findSets` in `src/head-quiet.html`): a run of frames from
one camera on one target, in one observation, each within 5 minutes of the one before, through different colour
filters. Clear and polarizer frames end a run, and a filter coming round again starts a new one. Channels are
placed by each filter's effective wavelength from `filter_calibration.csv` (build.py writes the table into the page):

- RED, GRN and a blue (BL1, else BL2 or VIO): **true colour**
- any other three or more filters: **false colour**, longest wavelength as red, the middle one as green, the shortest as blue
- two filters: **two-filter colour**, longer as red, shorter as blue, green from both

Once a set's channels are all taken the window asks the frame server for `/frames/color.webp?ids=R,G,B`, which
calibrates the frames onto one brightness scale, aligns them and caches the result like the frames.

Design rule (Sam, 2026-10-19): the interface should be as unobtrusive as possible; the OS stays because
there is a lot to configure, and the camera feed is the main feature.
