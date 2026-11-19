# Evidence: defects the benchmark checks found on main 701fd40f

These are the image benchmark's own pictures, built in an isolated root on the MacBook at 3 slots: base 701fd40f, candidate 04aede6c. The full report is in bench_report.md.

| sheet | what it shows | check |
|---|---|---|
| titan127_p60.jpg | 127TI CLOUD001 frames 5-7 on main: the P60 frame flashes gray in a colour movie | odd_frame 40.9 |
| titan127_p60_fix.jpg | the same frames on the fix: frame 6 shows frame 5's picture | odd_frame 0.9 (fixed) |
| titan127_grn.jpg | frame 46, a lone GRN haze frame between CB3 surface frames: main, then the fix holding frame 45 | |
| composites.jpg | storm (CB2/MT2/BL1) and hexagon (RED/UV3): gray on main, colour on the fix, the flat channel placed by SPICE | gray_colour fixed |
| moon_titan04.jpg | moon99 (HAL/GRN/BL1): exactly gray on main, true colour on the fix; titan04 (collateral, a taste call): balanced to Titan's tint on main, true colour on the fix | gray_colour fixed |
| methone_held.jpg | collateral: methone-movie frame 11, a polarized MT2 frame drawn gray on main, now the colour picture before it | |
| enceladus_daphnis_held.jpg | collateral: enceladus15-movie frame 11 (UV1) and daphnis17-movie frame 24 (P60/UV3), gray on main, now the colour picture before them | |

The lone-frame rule holds a picture only from a frame taken within HOLD_REACH (1 hour) of the held one; 127TI's held frames are 32 and 36 minutes away.
