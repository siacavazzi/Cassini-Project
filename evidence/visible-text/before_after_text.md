# Visible text rewrite: before and after

166 passages changed. Each row is one string as it appears on screen.


## web/cassini-os/src/settings.html

| Before | After |
|---|---|
| Each step the pictures go through, in the order they run. With everything on you see the mission's pictures processed; turn a step off to see what it does. A picture with a step off is made the first time it is asked for (a few seconds); with everything on it comes from the cache at once. | Each step of picture processing, in the order the steps run. With every step on, you see the mission's pictures fully processed. Turn a step off to see what it does. A picture with a step off is made the first time you ask for it, which takes a few seconds. With every step on, it comes from the cache at once. |
| Menus and windows fade out when the pointer rests, so the view has the screen to itself. | Menus and windows fade out when you stop moving the pointer, so you see only the view. |
| How long the pointer has to rest before the interface fades. | How long the pointer has to stay still before the interface fades. |
| A frame shown on its own goes through the pipeline like a color picture's channels: repeat exposures stacked, calibrated, lost lines filled, on the same display stretch. Off shows the frame as it is in the archive. | A frame shown on its own is processed the same way as the channels of a color picture: repeat exposures are stacked, the frame is calibrated, lost lines are filled, and it is shown on the same display stretch. Off shows the frame as it is in the archive. |
| How much of the pipeline the camera windows show, also set for each window on the bar under its picture. Raw: each frame as Cassini sent it, nothing done to it (with Auto center, only moved and turned into place by SPICE). Processed: each frame on its own, repeat exposures stacked, calibrated, cleaned and on the display stretch. Color: a filter set's frames put together as one color picture, but no mosaics or movies. Full: everything, with mosaics and steadied movies. | How much processing the camera windows show. You can also set it for each window on the bar under its picture. Raw: each frame as Cassini sent it, with nothing done to it (with Auto center on, SPICE only moves and turns it into place). Processed: each frame on its own, with repeat exposures stacked, calibrated, cleaned and on the display stretch. Color: the frames of a filter set are combined into one color picture, but there are no mosaics or movies. Full: everything, including mosaics and steadied movies. |
| Frames Cassini took again of the same thing, with the same filter and exposure, are averaged into one picture, which cuts the noise (a plain stack). Off shows each frame alone. | When Cassini took the same picture more than once, with the same filter and exposure, the frames are averaged into one picture to reduce the noise (a plain stack). Off shows each frame alone. |
| In mosaics, mosaic movies and the body reels, an exposure bracket (short exposures for the bright parts, long ones for the faint) is merged into one picture that has the range of both. Off merges only identical exposures, like the plain stack. Needs Stack repeat exposures. | In mosaics, mosaic movies and the body reels, Cassini sometimes took short exposures for the bright parts and long exposures for the faint parts (an exposure bracket). These are merged into one picture with the range of both. Off merges only identical exposures, like the plain stack. Needs Stack repeat exposures. |
| Lines a frame lost on its way to Earth are filled from the lines round them, so they don't show as black stripes or throw off the stretch. Off leaves them black. | Some lines of a frame were lost on the way to Earth. They are filled in from the lines around them, so they don't show as black stripes or spoil the brightness stretch. Off leaves them black. |
| Every frame is turned into reflectance (I/F: bias, exposure, gain, filter and distance from the Sun taken out) and drawn on one display scale, so filters and mosaic tiles match and colors are true. Off shows each frame on the archive's own stretch, as it came down. | Every frame is converted to reflectance (I/F), which removes the effects of bias, exposure, gain, filter and distance from the Sun. All frames are then drawn on one display scale, so filters and mosaic tiles match and colors are true. Off shows each frame on the archive's own stretch, as it was received. |
| Takes out the faint horizontal bands ("2 Hz noise") the camera's electronics added while each picture was read out, line by line from the extra pixels the camera read past the end of every line, as the camera team's calibration (CISSCAL) does. Most visible in dark sky and faint pictures. Full-size frames only. Off leaves the bands in. Needs Calibrate. | Removes the faint horizontal bands ("2 Hz noise") that the camera's electronics added while each picture was read out. The camera read a few extra pixels past the end of every line, and the bands are measured from these pixels, line by line, as the camera team's calibration (CISSCAL) does. Most visible in dark sky and faint pictures. Full-size frames only. Off leaves the bands in. Needs Calibrate. |
| Measures the 2 Hz bands from the picture's own dark sky (the median of each line with stars and bodies masked out, CISSCAL's "image mean" method) instead of from the few extra pixels past each line, which catch only part of them. Takes the bands out far more completely, and also on the 8-bit and lossy frames CISSCAL skips. Used where at least 9 lines in 10 have some clear sky; a frame filled by a moon or Saturn keeps the extra-pixel method. Off uses the extra pixels only, as CISSCAL does by default. Needs 2 Hz noise. | Measures the 2 Hz bands from the picture's own dark sky: the median of each line, with stars and bodies masked out (CISSCAL's "image mean" method). The few extra pixels past each line show only part of the bands, so this removes the bands far more completely. It also works on the 8-bit and lossy frames that CISSCAL skips. It is used where at least 9 lines in 10 have some clear sky. When a moon or Saturn fills the frame, the extra pixels are used instead. Off uses only the extra pixels, as CISSCAL does by default. Needs 2 Hz noise. |
| The archive keeps a dark sky as only a handful of brightness steps, so once the bands are measured from the sky each line still sits a fraction of a step above or below the next and the bands show again when the sky is stretched. Where the bands were measured from the sky, its one-step speckle is evened out over a few pixels; stars, cosmic rays and edges, several steps brighter, are left as they were. Off shows the sky's steps as they came down. Needs Bands from the sky. | In the archive, a dark sky has only a handful of brightness steps. Even after the bands are measured from the sky, each line can sit a fraction of a step above or below the next, and the bands show again when the sky is stretched. Where the bands were measured from the sky, this evens out the one-step speckle over a few pixels. Stars, cosmic rays and edges are several steps brighter, so they are left as they were. Off shows the sky's steps as they were received. Needs Bands from the sky. |
| Takes out the charge the camera's detector gathers without any light, which grows with the exposure and with how long each line waits to be read out, with the camera team's own dark model. Most visible on long exposures: night sides, rings, Titan's surface. Off leaves them in. Needs Calibrate. | Removes the charge that builds up in the camera's detector without any light, using the camera team's own dark model. This charge grows with the exposure and with how long each line waits to be read out. Most visible on long exposures: night sides, rings, Titan's surface. Off leaves it in. Needs Calibrate. |
| The camera team's dark model is right on average but not in detail: on long star fields and the dark sky round a moon it leaves a faint glow round the picture's edges and fine vertical stripes, which the display stretch lifts into a grey, striped sky. Where a picture has enough dark sky, what the model leaves there is measured and taken out too: the stripes column by column, the glow near the edges only (a plume or a faint ring in the middle stays). Lit pictures are left alone. Off uses the model as it is, as the camera team's calibration (CISSCAL) does. Needs Dark current. | The camera team's dark model is right on average but not in detail. On long star fields, and in the dark sky around a moon, it leaves a faint glow around the picture's edges and fine vertical stripes. The display stretch then makes the sky look gray and striped. Where a picture has enough dark sky, this measures what the model left behind and removes it too: the stripes column by column, and the glow only near the edges (a plume or a faint ring in the middle stays). Lit pictures are left alone. Off uses the model as it is, as the camera team's calibration (CISSCAL) does. Needs Dark current. |
| In anti-blooming mode the detector leaves pairs of pixels, one too bright sitting on one too dark, scattered over the picture. As the camera team's calibration (CISSCAL) does, each pair more than 30 DN off its neighbors is replaced by the mean of the pixels either side of it. Full-size frames with anti-blooming on only. Off leaves them in. Needs Calibrate. | In anti-blooming mode, the detector leaves pairs of pixels scattered over the picture: one too bright, sitting on one too dark. As in the camera team's calibration (CISSCAL), each pair that differs from its neighbors by more than 30 DN is replaced by the mean of the pixels on either side. Full-size frames with anti-blooming on only. Off leaves them in. Needs Calibrate. |
| Takes out what the camera itself adds to every picture, with the mission's own calibration maps: the dust rings (shadows of dust on the narrow-angle camera's optics, more of them as the mission went on), the fine mottle that appeared in late 2003, the darker corners and the faint column pattern of the detector. Off leaves them in. Needs Calibrate. | Removes what the camera itself adds to every picture, using the mission's own calibration maps: the dust rings (shadows of dust on the narrow-angle camera's optics, more of them as the mission went on), the fine mottle that appeared in late 2003, the darker corners and the faint column pattern of the detector. Off leaves them in. Needs Calibrate. |
| The detector pixels that went hot or dead over the mission (the camera team's lists, and the far more the archive's own frames show, month by month) are filled in from the pixels round them, so they don't show as dots that stay put while the stars and the moon move in a movie. A star that lands exactly on one is filled in too. Off leaves them in. Needs Calibrate. | Over the mission, some detector pixels went hot or dead. The camera team listed some of them, and the archive's own frames show many more, month by month. These pixels are filled in from the pixels around them, so they don't show as dots that stay put while the stars and the moon move in a movie. A star that lands exactly on one is filled in too. Off leaves them in. Needs Calibrate. |
| The wide-angle camera's lens bends the picture a little towards its corners, up to 3 pixels, and each of its filters focuses at a slightly different length, so the same scene is up to a pixel bigger in one filter than another. As the camera team's calibration (CISSCAL) does, every wide-angle frame is redrawn onto one straight grid at one focal length for every filter, so mosaic tiles meet without kinks and a color set's channels are the same size. The narrow-angle camera needs none. Off shows each frame as the lens drew it. Needs Calibrate. | The wide-angle camera's lens bends the picture a little toward its corners, by up to 3 pixels. Each of its filters also focuses at a slightly different length, so the same scene is up to a pixel bigger in one filter than in another. As in the camera team's calibration (CISSCAL), every wide-angle frame is redrawn onto one straight grid, at the same focal length for every filter. Mosaic tiles then meet without kinks, and the channels of a color set are the same size. The narrow-angle camera needs no correction. Off shows each frame as it came through the lens. Needs Calibrate. |
| A color set's channels, taken seconds or minutes apart, are moved onto one another, and a mosaic's filters onto each other's tiles. Off lays them over one another as the camera pointed, so moving bodies show colored fringes. | The channels of a color set were taken seconds or minutes apart. They are moved onto one another, and in a mosaic each filter's tiles are moved onto the other filters' tiles. Off lays them over one another as the camera pointed, so moving bodies show colored fringes. |
| Evens out the brightness where mosaic tiles overlap, smoothly across each tile, as the planetary mosaic tools do (a gentle brightness field per tile, solved together so no tile's step shows at a seam). Works with Blend mosaic seams on; off blends the tiles as they are. | Evens out the brightness where mosaic tiles overlap, smoothly across each tile, as planetary mosaic software does. Each tile gets a gentle brightness correction, and all the tiles are solved together so no step in brightness shows at a seam. Works with Blend mosaic seams on. Off blends the tiles as they are. |
| A mosaic's panels are taken minutes apart, and the moon turns and Cassini moves in between, so the same crater sits 8 to 18 pixels apart in neighboring panels and doubles or steps at their seam. On, each panel's surface is redrawn as it was at the middle of the pass, from SPICE's shape, spin and Cassini's position; the limb, the sky and the rings stay where they are. Off shows each panel as it was taken. | The panels of a mosaic were taken minutes apart, and in between the moon turned and Cassini moved. So the same crater can sit 8 to 18 pixels apart in neighboring panels, and it shows twice, or with a step, at their seam. On redraws each panel's surface as it was at the middle of the pass, using the body's shape and spin from SPICE and Cassini's position. The limb, the sky and the rings stay where they are. Off shows each panel as it was taken. |
| SPICE places each mosaic panel from where Cassini was said to point, 3 to 5 pixels off and differently for each panel. On, each panel is matched to the panels taken before it where they overlap (by what the pictures show) and moved by the few pixels it is off (12 at most), all its filters together. Panels with nothing to match on stay where SPICE puts them. Needs Align. | SPICE places each mosaic panel from the recorded pointing, which is 3 to 5 pixels off, by a different amount for each panel. On matches each panel to the earlier panels where they overlap, by what the pictures show, and moves it by the few pixels it is off (12 at most), with all its filters together. Panels with nothing to match stay where SPICE puts them. Needs Align. |
| A gentler color stretch: black sits just above the sky's noise so grain and scan lines stay dark, white sits at the bright part of the body but never stretches dim pictures far, bright edges roll off instead of clipping, and mosaic tiles are evened out without changing the mosaic's overall level. Off shows the earlier stretch. | A gentler color stretch. Black is set just above the sky's noise, so grain and scan lines stay dark. White is set at the bright part of the body, but dim pictures are never stretched far. Bright edges roll off instead of clipping, and mosaic tiles are evened out without changing the mosaic's overall level. Off shows the earlier stretch. |
| Natural color turns red, green and blue filter sets into the colors an eye would see, shows sets taken through a methane filter as Natural color (emulated) does, and balances other false color sets (ultraviolet, infrared) so the planet comes out gray and only its differences between filters show as color. Where a set took more than three filters, the three nearest red, green and blue are used. Natural color (emulated) shows false color sets too as an eye would have seen them: the body in its own color (Saturn and Jupiter cream, Titan orange, the icy moons gray), with what the filters show as its brightness and, where they reach both sides of the visible, as its shades. Methane bands give no color. It is worked out on this computer, in movie passes for now (with Steady movies on this computer); still pictures and mosaics keep Natural color. False color balances every false color set, methane ones too, as Natural color did before November 2026: the cloud heights a methane filter sees show as color. Raw filters draws each filter straight as a channel. Needs Balanced color. | Natural color turns red, green and blue filter sets into the colors an eye would see. It shows sets taken through a methane filter the way Natural color (emulated) does. Other false color sets (ultraviolet, infrared) are balanced so the planet comes out gray, and only the differences between filters show as color. Where a set has more than three filters, the three nearest to red, green and blue are used. Natural color (emulated) also shows false color sets as an eye would have seen them: the body is drawn in its own color (Saturn and Jupiter cream, Titan orange, the icy moons gray). What the filters show becomes its brightness and, where the filters reach both sides of the visible range, its shades. Methane bands give no color. Your computer works this out, for now only in movie passes (with Steady movies on this computer); still pictures and mosaics keep Natural color. False color balances every false color set, including methane sets, as Natural color did before November 2026, so the cloud heights seen through a methane filter show as color. Raw filters draws each filter directly as a channel. Needs Balanced color. |
| Every picture is turned a whole quarter (0, 90, 180 or 270 degrees, so it stays square) to bring north toward the top, by SPICE, the same for the whole pass. A moon or a planet whose whole disk fits goes in the middle, even where a picture caught only its edge, at one size for the whole pass, so the body holds still from picture to picture. Sky pictures with no body in them stay as the camera took them. Each camera window's settings button (the slider icon in its title bar) can turn it on or off for that window. | Using SPICE, every picture is turned by a whole quarter turn (0, 90, 180 or 270 degrees, so it stays square) to bring north toward the top, the same way for the whole pass. If a moon's or planet's whole disk fits in the picture, the body is placed in the middle at one size for the whole pass, even when a picture shows only its edge, so it holds still from picture to picture. Sky pictures with no body in them stay as the camera took them. You can turn it on or off for one window with that window's settings button (the slider icon in its title bar). |
| What shows where a picture's frame does not reach, as when Auto center keeps a body in the middle that the camera caught at its edge. Black by default. | The color shown where a picture's frame does not reach. This happens, for example, when the camera caught a body at its edge and Auto center moves the body to the middle. Black by default. |
| On a screen that shows HDR (an iPhone, a recent Mac, an HDR monitor), color pictures and processed frames come as HDR pictures: the bright parts the usual picture rolls off at white (a lit ring, a bright limb, glare the camera saturated) shine brighter than white, with their detail, while the rest looks as before. Other screens, and pictures not made in HDR yet, show the usual picture. Off always shows the usual picture. | On a screen that can show HDR (an iPhone, a recent Mac, an HDR monitor), color pictures and processed frames are shown as HDR pictures. The brightest parts, which the usual picture flattens to white (a lit ring, a bright limb, glare that saturated the camera), shine brighter than white and keep their detail. The rest looks as before. Other screens, and pictures not yet made in HDR, show the usual picture. Off always shows the usual picture. |
| SPICE places each frame of a movie pass from where Cassini was said to point, and that is a few pixels off, differently from frame to frame, so a moon or Jupiter's clouds can wobble. On, each frame is matched to the frame before it by what the pictures show (the pipeline's own alignment, with SPICE's place as the starting guess), and held to SPICE over a longer stretch so the body stays where it is. Feature tracks (a cloud followed across Saturn) are always steadied. Off shows every frame where SPICE puts it. | SPICE places each frame of a movie pass from the recorded pointing. That is a few pixels off, by a different amount in each frame, so a moon or Jupiter's clouds can wobble. On matches each frame to the frame before it by what the pictures show, with the pipeline's own alignment, starting from the SPICE position. Over a longer stretch the frames are held to SPICE, so the body stays where it is. Feature tracks (a cloud followed across Saturn) are always steadied. Off shows every frame where SPICE puts it. |
| How long the pictures are believed over SPICE (with Image stabilization on). Low takes out only the frame-to-frame wobble and follows SPICE closely; high also holds slow drifts still, trusting the frame-to-frame matching over that many frames. | Over how many frames the picture matching is trusted more than SPICE (with Image stabilization on). Low removes only the wobble between frames and follows SPICE closely. High also holds slow drifts still, trusting the matching over that many frames. |
| Image stabilization and exposure normalization worked out by this computer, at any smoothing: it moves and brightens the frame the server already has, instead of the server drawing every frame again for each setting. True-color frames and a trail too; false-color sets, feature tracks and passes whose view follows the frames are still drawn by the server, and exports are always made by the server. Off asks the server to draw every frame again for each setting, which is slower and is not offered when many people are watching. | Your computer does the Image stabilization and Even exposure, at any smoothing. It moves and brightens the frames the server has already made, so the server does not have to draw every frame again for each setting. This also covers true-color frames and trails. The server still draws false-color sets, feature tracks and passes whose view follows the frames, and it always makes exports. Off asks the server to draw every frame again for each setting, which is slower and is not offered when many people are watching. |
| A movie pass is drawn on one brightness scale, so a frame whose exposure the calibration did not fully even out, or one lit by stray light, flashes or jumps in brightness. On, each picture's brightness is measured against the picture before it, a frame or two far brighter or darker than their neighbours are brought to their level, and other jumps are spread over several frames, one gain for the whole picture so a color picture keeps its color. Slow changes stay, and every frame keeps its data, only scaled. Off shows every frame as the pass's scale draws it. | A movie pass is drawn on one brightness scale. So when the calibration did not fully even out a frame's exposure, or stray light lit a frame, that frame flashes or jumps in brightness. On measures each picture's brightness against the picture before it. A frame or two that are far brighter or darker than their neighbors are brought to their level, and other jumps are spread over several frames. Each picture gets one gain for the whole picture, so a color picture keeps its color. Slow changes stay, and every frame keeps its data, only scaled. Off shows every frame on the pass's brightness scale. |
| How many frames a flash or jump in brightness is evened over (with Even exposure on). Low keeps quick real changes; high evens the movie out more. The same as each camera window's Even exposure slider. | Over how many frames a flash or jump in brightness is evened out (with Even exposure on). Low keeps quick real changes; high evens the movie out more. The same as each camera window's Even exposure slider. |
| A run of color pictures mostly shares one set of filters, but now and then Cassini swapped one filter for another (a blue filter in place of a continuum one), and that picture comes out in other colors: peach and blue among green. On, every color picture's colors are moved toward the palette of the pictures round it in the same camera window (the most common one, so the odd one out never sets it), worked out by this computer. Only the balance between the colors moves: each pixel keeps its brightness (that is Even exposure's), and a run of one palette is left almost as it is. | In a run of color pictures, most use the same set of filters. Now and then Cassini swapped one filter for another (a blue filter in place of a continuum one), and that picture comes out in other colors: peach and blue among green. On moves every color picture's colors toward the most common palette of the pictures around it in the same camera window, so the odd one out never sets the palette. Your computer works this out. Only the balance between the colors changes: each pixel keeps its brightness (Even exposure handles brightness), and a run with one palette is left almost as it is. |
| How far an odd picture's colors are moved toward its neighbours' palette (with Color smoothing on). 100% matches them; lower keeps more of the picture's own colors. | How far an odd picture's colors are moved toward its neighbors' palette (with Color smoothing on). 100% matches them; lower keeps more of the picture's own colors. |
| How a pass of pictures plays: Auto builds the passes that step across a body as mosaics, rolls the ones that go round the same places again and again as mosaic movies, and plays movies and stares as frames. The others force one way for every pass. A camera window's settings button changes it for the pass it is showing. | How a pass of pictures plays. Auto shows passes that step across a body as mosaics, passes that cover the same places again and again as mosaic movies, and movies and stares as single frames. The other choices use one way for every pass. A camera window's settings button changes it for the pass that window is showing. |
| While a mosaic or a mosaic movie builds, a faint line goes round the tile Cassini just took. It moves with each new tile and fades when none follows. On screen only: saved pictures and films never have it. | While a mosaic or a mosaic movie builds, a faint line goes around the tile Cassini just took. It moves with each new tile and fades when no new tile comes. On screen only: saved pictures and films never have it. |
| The moment Cassini OS opens on. At random, each visit lands on one of the famous moments in this list, at its own speed. A shared link still opens on its own moment. | The moment Cassini OS opens on. With the random choice, each visit opens on one of the famous moments in this list, at that moment's speed. A shared link still opens on the moment it links to. |
| When the picture cache holds only some years (a test build of one year), the timeline, Moments and Highlights keep to them. Off shows the whole mission, and pictures outside them are made as they are asked for. | When pictures are built for only some years (for example, a test build of one year), the timeline, Moments and Highlights show only those years. Off shows the whole mission, and pictures outside those years are made when they are needed. |
| Outline on each body where Cassini's last pictures landed: every frame's field of view from the pointing data, laid on the surface and turning with it, the newest in warm white and older ones fading. Narrow-angle frames are the small blue squares, wide-angle the large grey-blue ones. | Outlines on each body where Cassini's last pictures landed: every frame's field of view from the pointing data, laid on the surface and turning with it. The newest is warm white and older ones fade. Narrow-angle frames are the small blue squares, wide-angle frames the large gray-blue ones. |
| With Picture footprints on, the newest footprints show the pictures themselves, laid on the body where the camera saw them: the frame server's processed frame (as in the camera windows, not centered), stretched over the footprint ray by ray, so each part of the picture sits where it looked. Newest on top; older ones fade. | With Picture footprints on, the newest footprints show the pictures themselves, laid on the body where the camera saw them. Each is the frame server's processed frame (as in the camera windows, not centered), stretched over the footprint ray by ray, so each part of the picture sits on the place it shows. Newest on top; older ones fade. |
| Map size for Saturn and the moons. 4k is sharper and slower to load; Off keeps the plain painted look. A ?tex= link still wins. | Map size for Saturn and the moons. 4k is sharper and slower to load; Off keeps the plain painted look. A ?tex= link still takes priority. |
| The real night sky (<button class='credit' data-about='star-sky'>NASA's Deep Star Maps</button>: Hipparcos, Tycho-2 and Gaia stars and the Milky Way), placed where Cassini saw it. Auto picks 8k on a desktop and 4k on a phone; 8k is the sharpest and takes the most memory (11 MB to load), 2k is the lightest but soft. Off keeps the old painted dots. A ?sky= link still wins. | The real night sky (<button class='credit' data-about='star-sky'>NASA's Deep Star Maps</button>: Hipparcos, Tycho-2 and Gaia stars and the Milky Way), placed where Cassini saw it. Auto picks 8k on a desktop and 4k on a phone. 8k is the sharpest and takes the most memory (11 MB to load); 2k is the lightest but soft. Off keeps the old painted dots. A ?sky= link still takes priority. |
| When a pass plays as a movie in a camera or body window (a stare, a ring or storm movie), every frame is centered by SPICE, north toward the top, on one brightness scale and one size for the whole pass, so the body holds still and the picture does not pump. Off shows each frame as it is. | When a pass plays as a movie in a camera or body window (a stare, a ring or storm movie), SPICE centers every frame, with north toward the top, on one brightness scale and at one size for the whole pass. The body holds still and the brightness does not pulse. Off shows each frame as it is. |
| For the Movie Editor and saved movies: Auto center puts each picture's body where SPICE says it is, and on a small moon in the narrow-angle camera that can be off by a good part of the moon, differently from picture to picture, so the movie wobbles. On, this computer matches each picture of the movie to the one before it by what the two show (the pipeline's own alignment) and takes the wobble out, keeping slow motion over this many pictures. Higher holds the body stiller; the Movie Editor's Framing sets it for each movie. | For the Movie Editor and saved movies. Auto center puts each picture's body where SPICE says it is. For a small moon in the narrow-angle camera, that can be off by a good part of the moon's size, by a different amount in each picture, so the movie wobbles. On, your computer matches each picture to the one before it by what the two show (with the pipeline's own alignment) and removes the wobble, keeping slow motion over this many pictures. Higher holds the body stiller. The Movie Editor's Framing slider sets it for each movie. |
| With Additional stabilization Off, a movie of a small body (under a tenth of the frame across, as Atlas or Pan in the narrow-angle camera, where SPICE's few pixels of error are a good part of the body) is steadied anyway, over 12 pictures. The Movie Editor's Framing slider still sets it for each movie, Off included. | With Additional stabilization off, a movie of a small body is steadied anyway, over 12 pictures. A small body is under a tenth of the frame across, as Atlas or Pan in the narrow-angle camera, where SPICE's few pixels of error are a good part of the body. The Movie Editor's Framing slider still sets it for each movie, including Off. |
| In a mosaic movie, each tile dims as the camera moves on, so the mosaic shows where the camera is now and where it was a moment ago: the newest tile is full brightness and a tile this many frames older has faded down to the level below. Off is a time-lapse: every place's newest tile stays at full brightness until the camera comes back to it. | In a mosaic movie, each tile dims as the camera moves on, so the mosaic shows where the camera is now and where it was a moment ago. The newest tile is at full brightness, and a tile this many frames older has faded down to the level below. Off is a time-lapse: every place's newest tile stays at full brightness until the camera comes back to it. |

## web/cassini-os/src/head-quiet.html

| Before | After |
|---|---|
| With only one of the two camera windows open, the other camera's pictures are not loaded or processed, the timeline shows the open camera's frames only, and playback and movie mode go by its pictures alone. | When only one of the two camera windows is open, the other camera's pictures are not loaded or processed. The timeline shows only the open camera's frames, and playback and movie mode follow only its pictures. |
| When Cassini takes a burst of pictures, the timeline slows down so each camera window shows at most this many new pictures a second. Only frames that change the picture count: a color set counts once, at its last filter. 0 = no limit. | When Cassini takes a burst of pictures, the timeline slows down so each camera window shows at most this many new pictures a second. Only frames that change the picture count; a color set counts once, at its last filter. 0 = no limit. |
| However many pictures a burst has, the timeline keeps at least this share of the chosen speed, so a faster speed always plays faster (skipping pictures in long bursts). 100 % = never slow down. | However many pictures a burst has, the timeline plays at no less than this share of the chosen speed, so a faster speed always plays faster (long bursts skip some pictures). 100 % = never slow down. |
| When the frame server cannot make pictures as fast as the timeline passes them (a mosaic movie nobody has watched yet), the timeline slows down in proportion so each camera window stays within this many frames of the clock. 0 = never slow down. | Sometimes the frame server cannot make pictures as fast as the timeline reaches them, for example in a mosaic movie that nobody has watched yet. Then the timeline slows down in proportion, so each camera window stays within this many frames of the clock. 0 = never slow down. |
| Faster than this, the camera windows stop loading pictures (no frame server keeps up) and the timeline plays at the full speed; they show the picture of the moment again as soon as you slow down, pause or scrub. | Above this speed, the camera windows stop loading pictures, because no frame server can keep up, and the timeline plays at full speed. The windows show the current picture again as soon as you slow down, pause or scrub. |
| label: "Pictures a window may fall behind" | label: "Most pictures a window can lag" |
| ${v}% toward the pictures round it | ${v}% toward the pictures around it |
| "Hold this window on the whole mosaic of the pass this frame is in (Esc goes back)" | "Show the whole mosaic of this frame's pass in this window (Esc goes back)" |
| "Jump to the moment this pass's last tile is taken: the whole mosaic, before the next picture" | "Jump to the moment the last tile of this pass is taken, to see the whole mosaic before the next picture" |
| Seen from above the rings, the Sun up. Distances from Saturn on a square-root scale. | Seen from above the rings, with the Sun toward the top. Distances from Saturn are on a square-root scale. |
| Positions from Cassini's SPICE kernels (J2000). LCD lanes: narrow-angle (NAC) and wide-angle (WAC) frames colored by filter; RGB marks frames that belong to a red, green and blue set. | Positions come from Cassini's SPICE kernels (J2000). The timeline lanes show narrow-angle (NAC) and wide-angle (WAC) frames, colored by filter. RGB marks frames that belong to a red, green and blue set. |

## web/cassini-os/src/movieedit.html

| Before | After |
|---|---|
| <li id="mlmake">Making the pictures ahead</li> | <li id="mlmake">Making the pictures in advance</li> |
| title="Open the editor now; the pictures keep being made ahead" | title="Open the editor now; the pictures are still made in advance" |
| title="Play's frame rate (the movie mode frame rate, Settings > Playback)" | title="Frame rate for Play (the movie mode frame rate in Settings > Playback)" |
| title="Take the look off what Apply to says" | title="Remove the look from the frames chosen under Apply to" |
| title="Each mosaic once it is whole: a mosaic pass at its last tile, a mosaic movie once a lap, every tile new" | title="Each mosaic once it is complete: a mosaic pass at its last tile, and a mosaic movie once per lap, when every tile is new" |
| title="No mosaics: every frame of a mosaic or a ring strip on its own, as a still pass shows" | title="No mosaics: every frame of a mosaic or a ring strip is shown on its own, as in a still pass" |
| title="Take the crop off, put every nudged frame back and Additional stabilization as Settings has it" | title="Remove the crop, put every moved frame back, and set Additional stabilization back to its value in Settings" |
| aria-label="Additional stabilization: the pictures the matching is believed over" | aria-label="Additional stabilization: how many pictures the matching is trusted over" |
| title="For when SPICE's centering wobbles (a small moon in the NAC): each picture is matched to the one before it by what the two show, and the wobble taken out. Higher holds the body stiller, lower keeps more of its slow motion. Worked out on this computer." | title="Use this when SPICE's centering wobbles (for a small moon in the NAC). Each picture is matched to the one before it by what the two show, and the wobble is removed. Higher holds the body stiller; lower keeps more of its slow motion. Your computer works this out." |
| title="Stop making the pictures ahead (what is made stays made)" | title="Stop making the pictures in advance (pictures already made are kept)" |
| Off. For when SPICE's centering wobbles, as on a small moon in the NAC: slide it up to steady the movie by what the pictures show. | Off. Use it when SPICE's centering wobbles, as on a small moon in the NAC: slide it up to steady the movie by what the pictures show. |
| `Making pictures ahead · ${ | `Making pictures in advance · ${ |
| `Making the pictures ahead · ${of}${left}` | `Making the pictures in advance · ${of}${left}` |
| mk.textContent = !j ? "Making the pictures ahead" | mk.textContent = !j ? "Making the pictures in advance" |
| pictures made ahead${j.took | pictures made in advance${j.took |
| (j.error \|\| "Could not make the pictures ahead") | (j.error \|\| "Could not make the pictures in advance") |

## web/cassini-os/src/segment.html

| Before | After |
|---|---|
| Movie mode is waiting for pictures to be made. Highlight a stretch of the timeline and press Edit: its pictures are made ahead while it opens. | Movie mode is waiting for pictures to be made. Highlight a stretch of the timeline and press Edit, and its pictures are made in advance while the editor opens. |
| label: "Make ahead up to" | label: "Make in advance up to" |
| The most frames of a stretch opened in the Movie Editor that are made ahead while it opens (a busy day near Saturn has about 1,500). A long stretch takes a while: the editor shows how long is left, can open before it is done, and what is made stays made. A public site may set its own limit. | The most frames of a stretch that are made in advance while it opens in the Movie Editor (a busy day near Saturn has about 1,500). A long stretch takes a while. The editor shows how long is left and can open before it is done, and pictures already made are kept. A public site may set its own limit. |
| label: "Suggest making a stretch ahead when movie mode waits" | label: "Suggest making a stretch in advance when movie mode waits" |
| "The frame server cannot make that ahead." | "The frame server cannot make that stretch in advance." |
| `No frame server at ${FRAMES} that makes pictures ahead.` | `No frame server at ${FRAMES} that makes pictures in advance.` |
| % made ahead · ${TITLE} | % made in advance · ${TITLE} |
| the stretch in the Movie Editor keeps being made ahead` | the pictures for the Movie Editor are still being made` |

## web/cassini-os/src/activity.html

| Before | After |
|---|---|
| A thin strip along the top of the timeline and a line in the menu bar: sending data to Earth, radio signal through the rings, radar, rolling, or pointed at a body. Worked out from the recorded pointing. | A thin strip along the top of the timeline and a line in the menu bar show what Cassini is doing: sending data to Earth, sending a radio signal through the rings, using its radar, rolling, or pointing at a body. Worked out from the recorded pointing. |
| Earth is too far away to be on stage at Saturn. While Cassini's dish points at it, Earth gets its marker and tag like any other body, so you can see where the beam is going. | Earth is too far away to see from Saturn. While Cassini's dish points at Earth, Earth gets a marker and a label like any other body, so you can see where the beam is going. |
| "The dish is on Earth with the rings in between: the radio signal crosses them, and how it fades maps the rings (a radio occultation)." | "The dish points at Earth, with the rings in between. The radio signal crosses the rings, and the way it fades maps them (a radio occultation)." |
| `The dish is on Earth with ${B} in between: the radio signal passes through its atmosphere until it is cut off (a radio occultation).` | `The dish points at Earth, with ${B} in between. The radio signal passes through its atmosphere until it is cut off (a radio occultation).` |

## web/cassini-os/src/ambient.html

| Before | After |
|---|---|
| Live runs in real time, ten years behind today. The faster modes catch more pictures; Every picture skips the quiet hours; Highlights plays the highlight reel over and over. | Live runs in real time, ten years behind today. The faster modes show more pictures. Every picture skips the quiet hours. Highlights plays the highlight reel over and over. |
| The same when pictures come fast (1 h/s, every picture, highlights); the speeds between are in between. | The same, when pictures come fast (1 h/s, Every picture, Highlights). Speeds in between get sizes in between. |
| Cassini and its subject: the camera stands off to the side so the spacecraft and the body it looks at (its near edge, for a big one) are both in the picture; close to a big body that puts the camera between them, looking back at Cassini with the body's edge beside it. Past Cassini: the earlier view over the spacecraft's shoulder, at the subject. | Cassini and its subject: the camera stands off to the side, so the spacecraft and the body it is looking at (the body's near edge, for a big one) are both in the picture. Close to a big body, this puts the camera between them, looking back at Cassini with the body's edge beside it. Past Cassini: the earlier view over the spacecraft's shoulder, toward the subject. |
| How far apart Cassini and its subject's near edge sit on screen, Cassini and its subject framing. Kept inside the screen. | With Cassini and its subject framing, how far apart Cassini and the near edge of its subject are on screen. Both stay inside the screen. |
| A thin line along the top: the pictures of the last stretch and the ones coming, with the next few bodies named. | A thin line along the top showing the pictures from the last stretch and the ones coming next, with the names of the next few bodies. |
| Softer, slower chimes with more echo, a quiet bed under them and no flyby pulse. Off plays the sound as in Cassini OS. | Softer, slower chimes with more echo, a quiet background tone under them, and no flyby pulse. Off plays the sound as in Cassini OS. |

## web/cassini-os/src/away.html

| Before | After |
|---|---|
| While the tab is hidden or the browser is minimized, everything stops: the clock, the 3D view, picture requests and sound. It carries on where it stopped when you come back. | While the tab is hidden or the browser is minimized, everything stops: the clock, the 3D view, picture requests and sound. When you come back, it picks up where it stopped. |

## web/cassini-os/src/bodywin.html

| Before | After |
|---|---|
| Off: one narrow-angle and one wide-angle window. On: each target Cassini images gets its own narrow-angle and wide-angle windows instead, up to the number below for each camera. | Off: one narrow-angle and one wide-angle window. On: each body that Cassini takes pictures of gets its own narrow-angle and wide-angle windows instead, up to the number below for each camera. |
| The most body windows each camera has up at once: the target it has just imaged, and the ones before it. A newer target takes an older window's place. | The most body windows open at once for each camera: one for the body the camera just took pictures of, and others for the bodies before it. A window for a newer body replaces an older one. |
| label: "Body windows before they make way" | label: "Body windows kept open" |
| Up to this many body windows stay up however long their cameras go quiet. With more, the least relevant close first. | Up to this many body windows stay open, however long their cameras take no pictures. When there are more, the least relevant ones close first. |
| Seconds of playback a single frame stays up when the screen is busy, shortened as more windows crowd in. Color pictures and mosaics stay longer (the two settings below). | How many seconds of playback a single frame stays open when the screen is busy. The time gets shorter as more windows open. Color pictures and mosaics stay longer (the two settings below). |

## web/cassini-os/src/export.html

| Before | After |
|---|---|
| Pictures stay on screen for their real gap to the next one, sped up: bursts flip fast, quiet spells linger (1/30 to 1/2 s each). | Each picture stays on screen for its real time gap to the next one, sped up. Pictures in a burst go by quickly, and pictures before a quiet spell stay longer (1/30 to 1/2 s each). |
| Pixels per camera in an exported film; 1024 is a full Cassini frame. Up to 2048, mosaics are drawn up to that size, each only as big as its pass has detail for. | Pixels per camera in an exported film; 1024 is a full Cassini frame. Up to 2048, mosaics are drawn up to that size, but each only as big as its pass has detail for. |
| Picture size Full: a mosaic or mosaic movie keeps every pixel its frames took (up to 4096 px a side) instead of fitting 1024. Extra work on the frame server, made only when asked for: pre-process the stretch first. | Picture size Full: a mosaic or mosaic movie keeps every pixel of its frames (up to 4096 px a side) instead of fitting into 1024. This is extra work for the frame server, so it is made only when you ask for it: pre-process the stretch first. |
| Exported films carry the picture sounds, set as in Settings > Sound. | Exported films include the picture sounds, as set in Settings > Sound. |
| The film as HDR video (HEVC, HDR10): the bright parts the usual film rolls off at white (lit rings, bright limbs, glare) shine brighter than white on an HDR screen (an iPhone, a recent Mac or TV). Made by the frame server; plays as the usual film's brightness on other screens only where the player tone maps it, so keep it off for films meant for anywhere. | The film as HDR video (HEVC, HDR10). On an HDR screen (an iPhone, a recent Mac or TV), the brightest parts, which the usual film flattens to white (lit rings, bright limbs, glare), shine brighter than white. The frame server makes it. On other screens it looks as bright as the usual film only where the player tone maps it, so keep it off for films meant to play anywhere. |
| The film is put together and encoded by this browser from the pictures the frame server already has (and the movie steps worked out here), so making it costs the server nothing but the pictures. Off, or at sizes above 1024, Mosaics at full resolution or in a browser that cannot encode video, the frame server makes it. | This browser puts the film together and encodes it, from the pictures the frame server already has and the movie steps worked out here. The server only has to provide the pictures. When this is off, at sizes above 1024, with Mosaics at full resolution, or in a browser that cannot encode video, the frame server makes the film. |
| "The server refused the export." | "The server did not accept the export." |

## web/cassini-os/src/flag.html

| Before | After |
|---|---|
| "This frame server can't save flags yet (it needs restarting on the new version)" | "This frame server can't save flags yet (it needs to be restarted with the new version)" |
| A flag in each picture window's title bar (or R) saves the picture as shown, with its frames and the mission time, to the frame server's flagged-pictures folder, so odd pictures can be looked into later. | A flag button in each picture window's title bar (or the R key) saves the picture as shown, with its frames and the mission time, to a folder of flagged pictures on the frame server, so odd pictures can be checked later. |

## web/cassini-os/src/gallery.html

| Before | After |
|---|---|
| title="Also put in how each item was made and its thumbnail (gallery.json), so Import can bring the whole gallery back" | title="Also include how each item was made, and its thumbnail (gallery.json), so Import can restore the whole gallery" |
| Export Library also writes how each item was made and its thumbnail (gallery.json), so Import can bring the gallery back. Off: just the pictures and films. | Export Library also saves how each item was made, and its thumbnail (gallery.json), so Import can restore the gallery. Off: just the pictures and films. |
| A downloaded or shared picture gets a small card in its corner: Cassini's orbit at that moment, the line to what the camera looked at, the date and the distance. The same box is in a picture's save menu and by the gallery's Download. | A downloaded or shared picture gets a small card in its corner: Cassini's orbit at that moment, a line to what the camera looked at, the date and the distance. The same checkbox is in a picture's save menu and next to the gallery's Download. |
| "The gallery is full: this browser gave it no more room" | "The gallery is full: this browser has no more storage space for it" |
| "This browser keeps no storage for the gallery here" | "This browser has no storage for the gallery on this site" |
| "This browser would not copy the picture" | "This browser could not copy the picture" |
| "That zip has only pictures: export with Include metadata to make one Import can read" | "That zip has only pictures. Export with Include metadata to make a zip that Import can read" |

## web/cassini-os/src/loupe.html

| Before | After |
|---|---|
| Move the pointer onto a picture and a lens shows the area under it magnified, from the picture's full resolution version. It follows the pointer; the scroll wheel over it changes the magnification. On a phone, press and hold on a picture. | Move the pointer onto a picture, and a lens shows the area under it magnified, from the full-resolution picture. The lens follows the pointer, and the scroll wheel over it changes the magnification. On a phone, press and hold on a picture. |
| A mosaic is shown smaller than its frames were taken. When the lens magnifies past the picture's pixels, it loads the part under it at the frames' own resolution, a moment after the pointer stops. | A mosaic is shown at a smaller scale than its frames were taken at. When the lens magnifies past the picture's pixels, it loads the part under it at the frames' own resolution, a moment after the pointer stops. |
| In full view a mosaic is shown big enough to look at its seams, so the lens stays away there. The magnifying glass in the picture's top right corner turns it on and off, the same as this switch. | In full view, a mosaic is shown big enough to look at its seams, so the lens is off there. The magnifying glass in the picture's top right corner turns it on and off, the same as this switch. |

## web/cassini-os/src/sound.html

| Before | After |
|---|---|
| A chime for each picture that arrives, after the Huygens descent movie. Browsers start it at your first click or key press. The speaker by the play button, the one in the menu bar, or S mutes it. | A chime plays for each picture that arrives, inspired by the Huygens descent movie. Browsers start the sound at your first click or key press. To mute it, use the speaker by the play button, the one in the menu bar, or the S key. |
| Pitch from the filter (blue high, red and infrared low) and the target's size; the narrow-angle camera rings an octave above the wide-angle one. | The pitch comes from the filter (blue high, red and infrared low) and the target's size. The narrow-angle camera plays an octave above the wide-angle one. |
| When a color picture is complete, its channels' notes together. | When a color picture is complete, its channels' notes play together. |
| Two quiet tones: one rises and wavers while Cassini turns, the other rises as it nears its target. | Two quiet tones: one rises and wavers while Cassini turns, and the other rises as Cassini nears its target. |
| The closer Cassini is to its target (for its size), the bigger the music: louder, brighter chimes, a swelling chord and a quickening pulse. | The closer Cassini is to its target (relative to the target's size), the bigger the music: louder, brighter chimes, a swelling chord and a quickening pulse. |

## web/cassini-os/src/reel.html

| Before | After |
|---|---|
| "channels not aligned, drawn grey" | "channels not aligned, drawn gray" |

## web/cassini-os/src/studio.html

| Before | After |
|---|---|
| Reset the mosaic brings back the frame server's own.` | Reset the mosaic restores the frame server's version.` |
| "This browser has no WebGL, which the studio draws with." | "Studio needs WebGL, and this browser does not have it." |
| "this browser records no film format" | "this browser cannot record any film format" |

## web/cassini-os/src/tutorial.html

| Before | After |
|---|---|
| only its pictures, its moments and its imaging sessions. Cassini brings you back.` | only its pictures, its moments and its imaging sessions. ${p ? "Tap" : "Click"} Cassini to come back.` |

## web/cassini-os/src/moments.html

| Before | After |
|---|---|
| title="Finds, transits and closest views the searches turned up that nobody has picked yet" | title="Finds, transits and closest views from the automatic searches that nobody has picked yet" |
| the finds and transits nobody has picked yet ( | the finds and transits that nobody has picked yet ( |

## web/cassini-os/src/coverage.html

| Before | After |
|---|---|
| `This site's table of what Cassini had photographed was built for ${span}. Outside those years the moons are drawn as the whole map.` | `This site's record of what Cassini had photographed covers only ${span}. Outside those years, the moons are drawn with their whole map.` |

## web/cassini-os/src/huygens-landing.html

| Before | After |
|---|---|
| UTC · Huygens starts talking to Cassini. Its camera takes pictures as it turns. | UTC · Huygens starts sending data to Cassini. Its camera takes pictures as the probe turns. |
| `At 111 km the main chute lets go. | `At 111 km the main chute is released. |
| `Earth heard it too. At 10:25 UTC the Green Bank telescope caught Huygens's faint carrier, ${lt} minutes after it left.` | `Radio telescopes on Earth picked it up too. At 10:25 UTC the Green Bank telescope detected Huygens's faint carrier signal, ${lt} minutes after it left the probe.` |
| `Under the haze its camera maps the ground it falls toward. Each outline is where one picture fell | `Below the haze, its camera maps the ground beneath it. Each outline shows the area of one picture |
| `Huygens keeps talking from the ground: ${DATA.surface_k} K, i | `Huygens keeps sending data from the ground: ${DATA.surface_k} K, with i |
| UTC · The landing site sinks below Titan's edge as Cassini sees it, and the link | UTC · Seen from Cassini, the landing site sinks below Titan's edge, and the link |
| Only half came home: Cassini never listened on one of the two channels, so ${P.received} of ${P.planned} pictures arrived. | Only half came home: Cassini never recorded one of the two radio channels, so only ${P.received} of ${P.planned} pictures arrived. |

## web/cassini-os/src/huygens-release.html

| Before | After |
|---|---|
| until its thrusters wake and steady it.` | until its thrusters switch on and steady it.` |
| Huygens sleeps now. A timer wakes it about five hours befo | Huygens is switched off now. A timer turns it on about five hours befo |

## web/cassini-os/src/finale.html

| Before | After |
|---|---|
| Its mass spectrometer tasted Saturn's air directly, the first and only time | Its mass spectrometer sampled Saturn's air directly, the first and only time |

## web/cassini-os/src/launch.html

| Before | After |
|---|---|
| ten minutes later a dish near Canberra, Australia, hears its first signal.` | ten minutes later an antenna near Canberra, Australia, picks up its first signal.` |
| Too heavy to fly straight there, it plans to borrow speed from the planets on the way.` | It is too heavy to fly straight there, so it will borrow speed from the planets on the way.` |

## web/cassini-os/src/soi.html

| Before | After |
|---|---|
| minutes before the burn that has to catch it.` | minutes before the engine burn that must put it into orbit.` |
| <b>In orbit</b>Saturn has caught it. | <b>In orbit</b>Saturn's gravity has captured it. |

## web/cassini-os/src/loading-facts.json

| Before | After |
|---|---|
| It spent nearly seven years getting there, slingshotting past Venus twice, then Earth, then Jupiter, to pick up speed. | It spent nearly seven years getting there, flying past Venus twice, then Earth, then Jupiter, to pick up speed from each. |
| To get captured, it fired its main engine for 96 minutes on arrival in July 2004. | To be captured by Saturn's gravity, it fired its main engine for 96 minutes when it arrived in July 2004. |
| Cassini caught it in the act in 2005. | Cassini discovered these jets in 2005. |
| Cassini found new moons hiding in and near the rings, | Cassini found new moons in and near the rings, |
| Cassini kept sending science during its final plunge, | Cassini kept sending science data during its final plunge, |

## web/cassini-os/how/index.html

| Before | After |
|---|---|
| This is a frame as the pipeline starts from it: | This is a frame as the pipeline receives it: |
| the repeats are stacked to beat down noise and cosmic-ray hits. | the repeats are stacked to reduce noise and cosmic-ray hits. |
| Three kinds do the heavy lifting here: | Three kinds matter most here: |
| watch the Great Red Spot ride Jupiter's ten-hour day; | watch the Great Red Spot turn with Jupiter's ten-hour day; |
| Where a picture goes comes from SPICE and the picture itself, not by hand. | Each picture is placed using SPICE and the picture itself, never by hand. |

## web/cassini-os/how/page.js

| Before | After |
|---|---|
| Methane gas soaks up light at this color, | Methane gas absorbs light at this color, |
| It sees the main visible cloud deck. | It shows the main visible cloud deck. |
|  · the PNG copy the pipeline starts from |  · the PNG copy that the pipeline starts from |

## web/cassini-os/how/spice.js

| Before | After |
|---|---|
| This drawing could not load its data. | The data for this drawing could not be loaded. |

## web/coming-soon/index.html

| Before | After |
|---|---|
| a few bad frames were left out, as the app's Movie Editor does. | a few bad frames were left out with the app's Movie Editor. |
| The tiny moon Daphnis raising waves in the edge of the gap it clears through the A ring. | The tiny moon Daphnis raises waves along the edge of the gap that it clears in the A ring. |
| while the wide-angle camera window plays the pictures it took on the way in. | while the wide-angle camera window plays the pictures that the camera took on the way in. |
| so brightness means what it should. | so each pixel's brightness matches the scene. |
| the archive the mission team delivered. | the archive where the mission team delivered its data. |

## web/replay/index.html

| Before | After |
|---|---|
| Positions from Cassini's SPICE kernels (J2000, sub-pixel accurate). Timeline bars are camera frames per time slice. | Positions come from Cassini's SPICE kernels (J2000, accurate to under a pixel). Each timeline bar counts the camera frames in a slice of time. |

## web/cassini-os/src/finale.html

| Before | After |
|---|---|
| Its fuel nearly gone, it was sent in on purpose, so it could never fall onto the moons it found might hold life. | Its fuel nearly gone, it was sent in on purpose. Cassini had found that some of Saturn's moons might hold life, and it must never fall onto one of them. |

## web/cassini-os/src/huygens-landing.html

| Before | After |
|---|---|
| After twenty days asleep, Huygens hits Titan's air | After twenty days switched off, Huygens hits Titan's air |
| and the instruments meet Titan's air. | and the instruments are open to Titan's air. |
