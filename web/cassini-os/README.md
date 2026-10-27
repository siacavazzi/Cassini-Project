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

## Ambient mode

The non-interactive Cassini OS, for a screen nobody touches: a wallpaper, a screen saver, a TV, a 24/7 stream
(`src/ambient.html`). `?ambient=1` opens in it, Go > Ambient Mode (A) starts it, Escape or the Leave button that shows
when the pointer moves ends it. No menus, windows or dock: the 3D view fills the screen, centered on Cassini, and
slowly turns to look past it at the most interesting thing around it. One rule picks it: each body scores by how big
it looks from Cassini, plus a bonus when Cassini photographs it next (more the sooner; the look-ahead grows with the
speed) and a smaller one when it was just photographed. So a Saturn filling the sky wins, and a picture of Enceladus
coming up turns the view to Enceladus as Cassini closes in. A new subject has to win for a few seconds and each one
holds at least half a minute. Framing keeps Cassini and its subject both in the picture: the camera stands off the line
from Cassini to the subject by the subject's apparent radius plus a spacing (Spacing, 22° by default, kept inside the
screen), and looks halfway between the spacecraft and the subject's near edge. A small moon is seen past Cassini; a big
planet close by is seen from beside the spacecraft, or from between the two looking back at Cassini with the limb
alongside. The camera circles slowly around that line (Camera drift). Framing > Past Cassini keeps the earlier view
over the spacecraft's shoulder. The narrow-angle and wide-angle pictures stay on as two
frameless panels in the bottom corners. They are the camera windows themselves, restyled, so every picture comes
through the same pipeline as in Cassini OS, with every processing switch; through a quiet stretch each panel keeps its
last picture, and the caption counts down to the next one.

Modes (Settings > Ambient, or `?ambient=<mode>`): `live`, real time ten years behind today (the clock is today's date
and time minus ten years, checked every few seconds, so a stream started now reaches the Grand Finale on its 10th
anniversary, 15 Sep 2027); `60`, `600` and `3600`, a minute, ten minutes or an hour a second; `pictures`, every
picture (movie mode, a few seconds each, the quiet hours skipped); `highlights`, the highlight reel over and over.
Pictures are large when they are rare and smaller when they come fast (Picture size, live and fast; the speeds between
are in between). While it runs the page never pauses in the background, sound starts without a click where the browser
allows it (a kiosk or stream browser started with `--autoplay-policy=no-user-gesture-required`), the 3D view is drawn
at most 30 times a second (Frame rate), and the caption and panels move a few pixels every minute against screen
burn-in. The camera cones stay on (orbits and the trail go), fainter, fading in and out and turning smoothly from one
pointing to the next; the sound turns calm (softer, slower chimes with more echo, a quiet bed under them, no flyby
pulse), each with its own switch in Settings > Ambient. A thin timeline along the top shows the imaging sessions of
the last stretch and the coming one as short dashes (a day at live, about four minutes of playback at the faster
speeds), with the next three bodies to be photographed named and how long until then. Cutscenes still play when the clock crosses them; after one, or at the end of the reel or the mission, it
carries on by itself.

## Pre-processing a stretch

Drag across the timeline's lanes to highlight a stretch (a click still moves the clock there, and dragging the row
of dates still pans), or press `I` and `O` at its ends; drag a highlighted edge to move it. A row comes up in the
Cassini Replay window, right above the timeline, with the stretch's times and frames and **NAC / WAC / Both** (the
same choice as Export Movie's Cameras; with one camera the stretch is made and played for it alone, the other
camera's window stepping aside while it plays). **Pre-process** asks the frame
server to make every picture the camera windows will show in the stretch ahead of time (`POST /prebuild`, made by the
pre-build tool's own makers in `web/frames/prebuild.py`: processed and centered single frames, color composites,
mosaic and movie passes, at the windows' sizes and in the page's look and movie style). The row and a line along the
foot of the timeline show how far it is; when it is done the stretch plays in movie mode at the row's **Frame rate**
(`movie.fps`, the same as Settings > Playback), every picture waiting in the cache. **Play** works before
pre-processing too (movie mode then waits for each picture), **Save movie…** opens Export Movie for the stretch (a
video file to download), and × or Escape clears the highlight. When movie mode spends most of its time waiting, a
quiet note suggests pre-processing, with a button that highlights the next 300 frames. Settings > Playback:
`segment.autoplay`, `segment.hint`, and `movie.completeFrames` (Complete color pictures only, on: a color set is one step, its finished color picture) and `playback.completeMosaics` (Complete mosaics only, off: a mosaic pass shows once finished, at its last frame, in every playback). One stretch is made at a time, at full speed: it gives way only to the
server's own picture requests (the camera windows' pictures go first), never to other jobs on the machine, and the
row stays up while it is made, even when the rest of the interface fades. While it is being made, and once it is made, the highlight is kept: a drag elsewhere leaves it be (× lets it go), its ends drag outward to add to it (the part already made stays made and only the new ends are made), and they drag inward only once it is done. It also carries on with the tab in the background or another window in front (the rest of the page pauses, Settings > Playback > Pause in the background): the tab title shows how far it is, and a stretch finished meanwhile plays when you come back.

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

## Zoom lens

Move the pointer onto any picture (camera windows, body windows, full view) and a lens comes up showing
the area under the pointer magnified; it follows the pointer and the scroll wheel over it changes the magnification.
It draws from the frame server's full resolution picture (`size=full`, asked for once the lens is up), so it shows
detail the window's 512 or 1024 px picture does not have. On a phone, press and hold on a picture. Settings > Zoom
lens holds the magnification, size, delay, shape and position (`src/loupe.html`; any `<img data-loupe>` gets it too).

## Dock

Along the bottom of the screen, as on the Mac (`src/dock.html`): Cassini and each body on stage now (the same list as
the main window's body picker; a click on a body opens its body view, below, flies the view there and brings that
body's windows forward; a blue dot marks the body in view, a grey dot one with windows open, a ring the body whose view
is open), then every planet Cassini photographed that is not on stage, then Moments, Highlights, Gallery and Settings (a click opens the window,
brings it forward, or tucks it away). A minimized window shrinks into the dock as a tile showing its last picture,
including the main window, and a click brings it back. Settings > Interface: Dock on or off (off brings back the
menu-bar tray), Dock position (bottom, left, right), icon size and magnification. On a phone the dock is a strip under
the replay controls that scrolls sideways.

Huygens is not in the row: once it has left Cassini (and while the viewer has it on stage) it waits in All bodies, under
Spacecraft.

The icons that are not a body's surface map are rendered pictures in `icons/` (256 px WebP): Cassini from NASA's model,
Huygens from ESA's descent module as it stood on Titan (`models/huygens_dm.glb.b64.txt`, from the Huygens landing
work), Saturn from its map with its rings passing in front of the globe (it takes a wider place in the dock), All bodies as seven of Saturn's moons from their maps, and Moments, Highlights, Settings and the two cameras lit as the
planets are. A minimized camera window shows its camera's icon in the corner of its picture.
`node web/cassini-os/icons/make_icons.cjs [name ...]` renders them again from `icons/make_icons.html` (Playwright; set
`THREE_DIR` to an unpacked three@0.128.0 where jsDelivr is out of reach; Saturn's icon needs
`data/textures/rings/saturn_rings.png`).

## Body view

A click on a body in the dock switches from Cassini's mission to that body's (`src/bodymode.html`). The timeline then
shows only that body's pictures, over its whole history from its first picture to its last (the months not loaded
from `data/targets/<body>.json`, the loaded ones from the catalog itself), with only its moments marked; Moments lists
only the moments about it; and the narrow-angle and wide-angle windows show only its pictures ("Titan · NAC"). A window
in the top right corner holds the body's picture counts, previous and next session, "Skip the gaps" (playback jumps
from one of the body's imaging sessions to the next instead of playing through the days or months between; Settings >
Body view sets how long a gap has to be), the list of its sessions (one per observation, with its NAC and WAC counts
and color sets) to jump to, "Whole history" to show it all on the timeline again, and every other body Cassini
photographed. The camera windows never go blank or shrink in a body's view: each keeps its last picture of the body
across jumps to other months until the next one arrives (a window with nothing yet shows the body's next picture),
pictures keep a square (a mosaic is letterboxed), and the picture after a jump dissolves in over the one before.
Every planet Cassini photographed a lot (1,000 pictures or more) stays in the dock wherever the mission is (Jupiter
while at Saturn, Saturn in the cruise); the dock's All bodies folder holds every body photographed, in groups
(planets and the Sun, Saturn's moons, Jupiter's moons, Earth's Moon, others), each with its surface map or else its
sharpest real picture. Picking a body that is not on stage now goes to its Moment nearest to now, or its busiest
session. Click Cassini in the dock, or close the body window, to go back. `?body=TITAN` opens a link in Titan's view.
On a phone the body window is a bar over the replay controls; tap its name for the sessions.

The list of bodies and their sessions comes from `web/replay/build_data.py` (`data/targets.json` and
`data/targets/<body>.json`, made with the rest of the whole-mission data). `window.cassiniBodyMode` (name, enter, exit,
index, sessions) is the way in for other parts of the page.

## Shareable links

The address bar always holds the moment on screen (`src/link.html`), so a copied link opens on it again:
`?t=2005-02-16T23:27:00&view=enceladus&speed=3600&play=0&cam=1.836,0.4572,-0.6478`. `t` is the mission time
(UTC, to the second) and follows playback; `view` is `follow` (Cassini, looking where its camera points), `cassini`
(Cassini, free camera) or a body; `cam` is where the free camera sits around it; `speed` is mission seconds per
second; `play=0` opens paused and `movie=1` in movie mode. `ambient=1` (or a mode) opens in ambient mode. Other
parameters (`?frames=`, `?tex=`, `?finale`) are kept.
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


## Cassini Studio

Editing saved pictures and films (`src/studio.html`): Edit on a gallery item, E for the picture in front, Studio in the
dock, or Go > Cassini Studio…. It works on the finished picture the pipeline made (or the export's film), like a photo
app: Adjust (exposure, contrast, black and white levels, midtones, saturation, warmth and tint for color balance,
sharpness, Auto levels, a histogram), Crop (Free, Original, Square, 4:5, 3:2, 16:9, 9:16; turn left/right, flip,
straighten), Filters (Vivid, Mono, Noir, Warm, Cool, Sepia, at a strength), and for a film its start and end. One WebGL
pass draws the edit for the preview, the saved JPEG and every frame of a film (recorded in the browser at its own
speed: MP4 where the browser records MP4, WebM in Firefox). Compare (hold, or \) shows the original; undo and redo.
Save to Gallery keeps the original and adds the edit beside it with its recipe (`edit`, a short string such as
`ct:30,sa:60,cr:0_0_0.7_0.7`) and the original's id, so editing it again starts from the original with every slider
where it was; Share… is the gallery's share menu, and a shared link to an edited picture carries `&edit=` so the page
that opens it applies the same edit to the picture the frame server makes. Settings > Studio: picture quality, film
quality (Mbit/s) and largest film size.

## Phone layout

On a screen under 600 px wide, or a touch screen under 500 px tall (Settings > Interface > Phone layout: Automatic,
Always or Never; `?phone=1` forces it), the windows dock instead of floating (`src/phone.html`). Upright: the NAC
and WAC pictures side by side under the menu bar, the 3D view in the middle, the replay controls along the bottom
(the speed slider on its own row; zoom shows the body picker), and Moments as a sheet over the view, opened from the list
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

Orbits, trails and outlines are drawn as smooth lines (`src/smoothlines.html`): WebGL's own lines are one pixel wide
and the graphics card's multisampling hardly smooths them, so each line gets a mesh of thin quads whose pixels are lit
by how much of them the line covers. Settings > Performance > Smooth lines switches back to the plain lines (pixel
for pixel what the page drew before); Settings > View > Line width sets their width in screen pixels (1 by default,
as thin as the plain lines).

To measure: `node bench/fps.js URL OUT [WIDTH HEIGHT DPR SECS]` (needs `npm i playwright-core`; `CHANNEL=chrome`
on a Mac for the real GPU) reports the uncapped frame rate, the CPU time of each step of the render loop and the GPU.

## Playback speed

The speed slider sits next to play in the replay window (`src/head-quiet.html`): a log scale from real time to a
month of mission a second that lands on round speeds (`window.cassiniSpeed` in `src/settings.html`, shared with
Settings > Playback > Starting speed, 10 min/s by default, and the clock read-out). The arrow keys step from one round
speed to the next. It sets the clock through `setSpeed`, as a `?speed=` link does, and follows whatever set the speed
last. When a burst or a picture still being made slows the clock, the rate it really runs at shows under the speed
("now 3.2 min/s").

Past Settings > Playback > Load pictures up to (`playback.picturesUpTo`, 1 day/s by default, all the way right =
any speed), no frame server keeps up, so while playing faster than that the camera windows hold their last picture,
dimmed, and ask for nothing, and the clock runs at the full speed (no burst slowdown). The slider's track is dimmer
past that point. Pausing, scrubbing, movie mode or a slower speed bring the pictures back at once.

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
Movie mode lives in `src/movie.html` (style and script); the build splices it into the page. It is only a rule for the clock: it skips the time between pictures and steps from one to the next at `movie.fps`, and the camera windows show each picture as usual.

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
