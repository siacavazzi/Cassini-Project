# Full level against Processed (level bar, PRs 575/576)

Sam 11-19, 2017 build, F ring movie at 2017-05-14 07:16: the Full level looked worse than Processed, with a gray black
and vertical streaks.

- `fring_levels.jpg`: Raw | Processed | Full as the window showed them, and the plain calibrated frame
  (science_frame, no cleanup) on the movie's display scale. The streaks are in the plain frame: faint scattered ring
  light the movie's black (under the frame's sky) lifts and the stills' sky floor clips.
- `full_vs_processed_2017.jpg`: Raw | Processed | Full for an F ring movie, an aurora stare, an Enceladus plume, Titan
  and the rings' dark side (12-bit viewer cache).
- `bench_report.md`: the image benchmark, this branch against claude/bench-checks: 54 identical; the new checks report
  fring274-movie and ringmovie04-movie (2004) as known failures (`full_black` 54 and 61 points).

2017 survey (Mini viewer, every frame of the 513 movie passes, 512 px): 2,388 of 12,291 frames judged lose more than 20
points of black sky at Full, in 88 of 456 passes (F ring FMOVIE, AURSTARE/AURNSTARE, Enceladus PLUME001 first).
