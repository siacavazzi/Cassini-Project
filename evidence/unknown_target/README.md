# Frames whose archive target SPICE cannot name

33,773 frames (SKY 28,196, UNK 4,336, NONE 825, DARKSKY 188, stars) had no geometry row, so were never grouped into
passes. Filled with the seen rule into a private copy of the geometry cache (`bootleg_autonav.py geometry` then
`bodies`, about a minute of work on the MacBook): 7,460 frames see a body or Saturn's rings. Only the frames of
(archive target, observation, camera) groups that agree as a whole, and are not a star-tracking observation (target
code ST: a stellar occultation, the camera following a star across the rings), are placed and relabelled
(`_place_seen`): 3,415 frames in 624 groups (Saturn 3,139, then Iapetus, Enceladus, Dione...), 678 passes
(392 movies, 26 mosaics, 260 single pictures): `passes.json`. The other 30,358 frames the rule looked at keep an
unplaced row, as before: never centred on a body nor grouped with it.

`unknown_target_seen.jpg` (made before the star-tracking and placing rules): left, what the window shows today (the
frame alone, processed); right, the pass it plays with the rule (movie or mosaic route, last frame). The 044RI and
008RI 0PHASE ring movies play well. 098ST URBETCRU001 (a star occultation) became a thin streak of a mosaic there;
star-tracking observations now keep their star and stay unplaced. 036ST is one too, now unchanged from today.

103RI TDIFN45HP001's movie shows dark ragged patches on its dim rings. Not this rule: the frame's own still
(W1613182176_1) is byte-identical on main and this branch, patches included (`103RI_still_main_vs_pr.jpg`: main
centred, main uncentred, branch centred, branch uncentred), and the movie's black deepens them; main's dim-ring
sky handling, passed to the sky-smooth-limb work. `103RI_frames.jpg`: the movie's mid frames beside the frames alone.

`spot_checks.txt`: a group whose frames see different bodies, and 098ST, through the target row, cached_target,
shown_targets and units.
