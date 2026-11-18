# Where each file in media/ came from

Every picture and film here is an output of the repo's own pipeline (Cassini OS frame server), not a re-render.

| File | Source |
| --- | --- |
| saturn.mp4, saturn.jpg | **Sam's own export, awaiting re-export once 2004 is rebuilt on main.** Saturn true color, NAC CL1/GRN, 2004-02-06 to 2004-03-29 (Sam's GIF `cassini-2004-01-28-0115-saturn.gif`, code version not recorded; caption bar cropped, re-encoded H.264 at 15 fps). Frames 18 (mottled color) and 117 (horizontal streaks) left out. |
| rhea.mp4, rhea.jpg | **Sam's own export, awaiting re-export once 2006 is rebuilt on main.** Rhea movie, NAC CL1/CL2, 2006-01-27 21:22–21:56 UTC (Sam's GIF `cassini-2006-01-27-2119-rhea.gif`, code version not recorded; caption cropped). No bad frames found. |
| plume.mp4, plume.jpg | `/export` on the 2017 cache, server at main e755fd89: from=2017-06-18T00:43:00 until=2017-06-18T16:00:00 cams=N fps=auto size=1024 caption=0 (ISS_279EN_PLUME001_PIE, 288 pictures). One frame per picture taken at the middle of its hold (from `/export/plan.json`), 640 px, 15 fps. The last two pictures (N1876495358_1, N1876495398_1: flat grey sky squares) left out. Remake after the plume-steadiness fix (claude/plume-jump) merges: the moon still wanders here. |
| dive.mp4, dive.jpg | `/export` on the 2017 cache, server at main e755fd89, 2017-04-26 07:49–08:50, cams=W, fps=auto, size=1024, caption=0; ISS_271SA_HIRESWACS001_PIE, 214 pictures; re-encoded at 8 fps, 640 px |
| farewell.webp | `/frames/mosaic/W1884011258_5.webp` (ISS_293SA_FAREWELL001_PRIME), 2017 cache, server at main e755fd89, as served |
| daphnis.webp | `/frames/movie/N1863265328_1.webp?size=1024` (ISS_257DA_DAPHNIS001_PIE), 2017 cache, server at main e755fd89, as served |
| app-dive.webp, share.jpg | Screenshot of Cassini OS (2017 cache preview, main e755fd89), `?t=2017-04-26T08:05:00&view=follow&play=0`, 1600x960 |
| app-daphnis.webp | Screenshot of Cassini OS (2017 cache preview, main e755fd89), 2017-01-16 11:47:09, both camera windows |
