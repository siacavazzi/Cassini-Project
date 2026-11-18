# Automatic light denoise (taste call 15)

Stills and color composites end in `sharpen.adaptive_sharpen`, which measures each picture's grain (the spread left
in its smoothest places, in display levels). A picture whose grain is over `DENOISE_FROM` (1.8) is blended with an
edge-keeping 5 x 5 average of its brightness (range 2.5 grains). The share rises to `DENOISE_MAX` (0.7) at
`DENOISE_FULL` (5). Stars, spikes, saturated pixels and the canvas edge are left alone. A picture at or under 1.8
comes out byte-identical to before.

Each sheet shows one picture under the four options of taste call 15 (A off, B gentle 2.5/6/0.5, C 1.8/5/0.7 =
this PR, D 1.5/4/0.9), as 2x crops, rendered through the repo pipeline (`frame_server.composite`, full SPICE kernels,
12-bit originals) with `render.py`:

    DN=off|FROM,FULL,MAX python render.py <checkout> <out dir> <frame id> ...
    python tsheet.py <name> <frame id> x0,y0,x1,y1 <sheet.jpg>      (reads out/tA..tD, run from the out folder's parent)

- `taste_15_plume290-a_1.jpg`: Enceladus plume, 290EN, grain 2.0 (C share 0.05)
- `taste_15_plume290-b_2.jpg`: Enceladus plume, 290EN, grain 2.7 (C share 0.2)
- `taste_15_plume264_3.jpg`: Enceladus plume, 264EN, grain 4.5 (C share 0.58)
- `taste_15_fring-haze_4.jpg`: F ring strands in haze, grain 5.9 (C share 0.7)
- `taste_15_ring-texture_5.jpg`: fine ring texture, grain 3.0: the structure is unchanged under every option
