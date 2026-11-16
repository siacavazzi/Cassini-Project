# Polarizer-only observations in true colour

Sam (2026-11-16): 2004-06-17 20:22 Saturn, both camera windows black and white though several filters were taken.
The NAC took every frame through a visible polarizer (P0, P60, P120) with BL2, GRN, CB1 or CB2; every polarizer
frame was left out of colour. The WAC took only CB2 and MT2 through IR polarizers (no visible band; gray is right).

- `gray_passes_survey.csv`: every pass of the finished cache (f9ab1b4), why it is gray (survey.py runs the repo's
  own `_filters`, `colour_sets`, `plays_colour` on each; report.py groups them). 1,540 passes with 2+ filters are
  gray; this change takes the "colour only through visible polarizers" group.
- `polarized_A_2004-06-17.jpg`, `polarized_A_2005-12-07.jpg`: before (main 1a35acb4) and after, the mosaic route
  (`/frames/mosaic/<id>.webp?size=1024`, finished) on private MacBook servers.
- Factors: `web/frames/polarized_share.py` (BL2 0.332, CB1 0.349 medians of 7 and 15 pairs; GRN 0.350 from the tint check, 0.355 on the icy moons).
  CISSCAL's pol_correction.tab has GRN and CB1 (3.43, 3.26) but no BL2, so it cannot balance a BL2/GRN/CB1 set.
- `tint_check.txt` (`tint.py`): 8 observations taking all three both ways; corrected polarized vs plain colour within 1% (2% for 218IC; 047TI an outlier with a mismatched plain GRN frame).
