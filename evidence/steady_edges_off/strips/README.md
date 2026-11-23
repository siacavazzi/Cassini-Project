Frame strips, judged by Fable 5.2 (PASS: no visible hop the base lacks).

- ringmovie04 / saturn09-movie3 / titan15-movie3 / titan08-movie2 / approach04: main 6452dc6d | 618 before the one-source rule (99d6e0f9) | 618 with it (19ab250f). The 7 px hop at ringmovie04 frames 31-32 without the rule is gone with it; titan15's 4 px step at 2-3 and approach04's picture change at 26-27 are on main too.
- *-final.jpg: main 4a44695e | 618 final c4f966d8. titan08-movie2 shows no visible step; approach04 frames 25-28 the same as main.

Bench c4f966d8 vs 4a44695e (image_bench/): FAIL by rule on three flags, each explained:
- ringclose124-movie moved 12 px as a whole: its 5 frames are one sequence on SPICE's smoothed path (pictures matched 2 of 5; main mixed picture and SPICE places). Fable: same, nothing cut off.
- approach04-movie odd_frame 20.3 -> 27.6 at frame 27: a different picture type that stands out on main as well; Fable: same as main.
- rz-titan08-movie2 jitter 1.6 -> 3.3 p90 (largest 3.6 px): Fable sees no step in either row.
