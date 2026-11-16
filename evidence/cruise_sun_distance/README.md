# Sun distance of the bodies passed in cruise (pipeline audit, item S3)

Measured 2026-11-16 on main 5d600b52 with the full SPICE kernels.

| file | what |
|---|---|
| `sun_distance_vs_spice.txt` | every frame before 2004, by year and target: the Sun distance `calibration.sun_distance` used, Cassini's own from SPICE, the target's from SPICE where the kernels have it, and the I/F factor (used over true, squared) |
| `audit_sun_distance.py` | makes that table (reads the audit's `labels.sqlite`, every label of the archive) |
| `cruise_stills_before_after.jpg` | the Moon, Venus and Masursky as stills (`color_image.load_aligned`) before and after, with the lit I/F of each |
| `sun.jsonl`, `audit_sun_render.py` | seven stills rendered both ways: Sun distance, lit I/F, and how many pixels of the picture differ |

## Result

| body | frames | distance used | true (SPICE) | I/F was |
|---|---|---|---|---|
| the Moon, 1999-08-18 | 56 | 4.953 AU | 1.012 AU | 24.0 times too high |
| Venus, 1999-06-24 | 24 | 4.951 AU | 0.725 AU | 46.7 times too high |
| asteroid Masursky, 2000-01-23 | 106 | 4.969 AU | 2.617 AU (Cassini's own; the kernels have no ephemeris for it, and it was 1.6 million km away) | 3.6 times too high |
| Jupiter, Io, Europa, Ganymede, Callisto, Himalia, Saturn | 27,000 | | | right (ratio 1.00 to 1.03) |

With its own distance Venus's cloud deck in CB2 (N1308947802_1) reads I/F 0.78; it read 36. The Moon's lit side in
GRN reads 0.03 to 0.04; it read 0.76 to 1.0.

A picture is scaled to its own white, so the pictures do not change: of seven stills rendered both ways four are
identical and three differ by one level on 1 to 11 pixels (rounding). What changes is the I/F itself, which the
science TIFF download gives.

Sky, star and dark frames without a body (SKY, NONE, SPICA, FOMALHAUT, UNK) still take the planet's distance; an
I/F means nothing for them.

Earth photographed from Saturn (13 frames filed under EARTH: 9 of 2013, ISS_195RI_HIPHASEC001, and 4 of 2017,
ISS_269RI_HIPHASEFB001) keeps Saturn's distance, as before. The rule rests on the frame's own label, not on the
year: all 13 carry `TARGET_DESC = "Saturn-Rings"`, the planners' statement of what the picture is of, and a frame
named for another body but described as Saturn's is lit at Saturn's distance. Every frame of the Moon, Venus and
Masursky has `TARGET_DESC = "UNK"`, and no frame before 2003 has a Saturn description.
