# Frames centred on the body they show

Sam 2026-11-12: N1455663489_1 (2004-02-17 04:14 on the page, ISS_C42OT_SATELLORB002, NAC CL1/CL2) looked unprocessed.
Its archive target is Enceladus, a one pixel dot; Auto center centred the dot, so Saturn stayed cut at the frame's edge.

- `before_satellorb.png`: the three SATELLORB002 frames on main 5f655bc, raw and with Auto center.
- `ba_satellorb002.png`: Auto center stills before (main) and after (this branch).
- `ba_satellorb002_movie.png`: the same pass in movie view; before, five one-frame passes on five moons; after, one Saturn pass.
- `sheetA.png`, `sheetB.png`: one frame of every affected group (observation family, body, camera) plus six storm watch frames, before and after.
- `shown.tsv`: all 717 affected frames (time, frame, camera, observation, archive target, body shown, filters).

Made with two frame servers on the M5 (main 5f655bc on 8984, this branch on 8983), the full SPICE kernels and the
geometry cache with its bodies table (private copies), and web/frames' processed and movie routes with center=1.
