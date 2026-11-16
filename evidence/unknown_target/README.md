# Frames whose archive target SPICE cannot name

33,773 frames (SKY 28,196, UNK 4,336, NONE 825, DARKSKY 188, stars) had no geometry row, so were never grouped into
passes. With the seen rule filled into a private copy of the geometry cache (`bootleg_autonav.py geometry` then
`bodies`, about a minute on the MacBook): 7,460 frames see a body or Saturn's rings; 4,830 of them are in groups
(archive target, observation, camera) that agree as a whole and are relabelled (Saturn 4,521, Iapetus 80, Enceladus
50, Dione 49, Tethys 27, Jupiter 26, Rhea 23, Mimas 23, Titan 17, Hyperion 14), in 814 groups and 1,051 passes
(461 movies, 91 mosaics, 499 single pictures): `passes.json`.

`unknown_target_seen.jpg`: left, what the window shows today (the frame alone, processed); right, the pass it now
plays (movie or mosaic route, last frame). 044RI and 008RI ring movies and 036ST play well. Two problems are open:
103RI TDIFN45HP001's movie frame smears in bands, and 098ST URBETCRU001 (a UVIS star occultation tracking a star
across the rings) becomes a thin streak of a mosaic.
