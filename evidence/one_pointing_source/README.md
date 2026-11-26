One pointing source per sequence (follow-up to #618) and the regression round's pointing items.

- image_bench/: bench 8dfd9d70 vs main 53c9279e, NEEDS EYES with notes (notes name each changed item's cause and Fable's verdict).
- strips/: base-vs-candidate frame strips Fable judged (main row on top). *-final.jpg are on the final head; the others on 91702854/dee9c7d4 (Janus 2010, Enceladus 2013, Pallene, saturn16-uv2, rx-saturn14).
- taste_36/: still framing A (centred) vs B (as taken), taste call 36, with notes.

Fable 5.2: PASS on taste 36 (after deciding per picture; Titan 125TI stays centred), PASS on the still orientation, PASS on final strips (saturn16-uv2, skathi11, rx-saturn05 SAME). One item visibly worse: the 2010 Janus pass (m-janus10-pass) hop between colour sets 11 -> 20 px; a known failure (jitter 31 on main), its unmatched frame now placed with its own set's pictures.

Review round (11-24): m-janus10-pass fixed at 8dfd9d70 — an unmatched frame of a colour set takes the median of its set's placed frames (strips/m-janus10-pass-fixed.jpg shows the intermediate ca6432eb, still teal; m-janus10-pass-final.jpg the final). Fable: SAME as main in colour and position; rx-saturn14 no visible fringe. from_pictures no longer extrapolates past the span of the steps it uses.

After merging main 387019fa (#623), 11-26: image_bench_623/ is a targeted bench (25 items: 622's targets and the five items it shares with #623) of 412b12cc vs 387019fa. It reads FAIL only because six fixed items outside the targeted list were not built. Every built item is noted or a target. strips623/ holds Fable's strips of the five shared items, all SAME as main. On the way, Fable caught saturn16-uv2 hopping 5-7 px against #623's steadier main, and 412b12cc fixed it: links across filters are weighed down only off the rings (a ring pass shows the same ringlets in every filter). Jitter is now 1.67, the same as main. The chain's agreement check also leaves those links out (588513a6), and they are not dropped for disagreeing (9ede65a7).
