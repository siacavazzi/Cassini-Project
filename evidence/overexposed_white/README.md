# Frames overexposed on purpose: white from what the camera did not saturate (taste call 24, option B)

2026-11-17, pipeline audit thread. Sam's choice of three shown on ten frames (`taste_24_expectedmax_1..10.jpg` and
`taste_24_notes.md` in the project files): B, at most 4 times brighter, only where the label forecasts over 100% of
full well and under about 5% of the frame really saturated.

## Before and after, from this branch's code

`overexposed_NN_<frame>.jpg`: each frame as a still (`color_image.load_aligned`), with the rule off
(`calibration.OVEREXPOSED_GAIN = 1`, which is main's white) and on. `overexposed.jsonl` has the numbers;
`audit_c24_evidence.py` makes them.

| file | frame | label forecast | saturated | rule | mean brightness (of 255) |
|---|---|---|---|---|---|
| 01 | Enceladus plume, N1864087239_1 | 909% | 0.017% | applies | 18.5 to 3.3 (the gray veil over the sky goes; the plume is plain) |
| 02 | Enceladus plume, N1880394659_5 | 1,018% | 0.020% | applies | 20.6 to 5.3 |
| 03 | Enceladus plume and E ring glow, N1872024820_1 | 699% | 0.007% | applies | 21.9 to 3.4 |
| 04 | plume close-up, N1704334379_1 | 596% | 0.001% | applies | 16.0 to 30.0 |
| 05 | Enceladus in Saturn's shadow, N1604174645_2 | 126,922% | 0.009% | applies | 17.9 to 33.6 |
| 06 | the same, wide-angle, W1604171130_1 | 69,230% | 0.002% | applies | 1.0 to 1.9 |
| 07 | rings at equinox, N1629351499_1 | 197% | 0.022% | applies | 53.3 to 88.9 |
| 08 | high-phase ring glow, N1534037684_1 | 17,663% | 1.9% | applies | 11.3 to 13.0 |
| 09 | rings, N1486897692_1 | 317% | 60.5% | does not apply (5% and over) | identical |
| 10 | ring arc, N1845333748_1 | 3,282% | 31.3% | does not apply | identical |

On the three plume frames with the crescent in view the mean goes down although the plume gets brighter: with the
white set by the blown-out crescent the sky sat in the tone curve's toe as a gray veil, and on the lower white it is
dark, as in the taste sheets.

## Image benchmark (d929b47d against main 02598865, all 53 items)

`bench_report.md`: 52 identical, 1 changed. The one is `plume-bloom-still` (Enceladus PLUME002, N1831473782_1, the CCD
bloom frame), named as the target: 3.0% of its pixels move more than 8 levels, 47 at most; the night side lit by
Saturn and the plume come up, the bloom and the sky stay as they were (`bench_plume-bloom-still.jpg`). Verdict
NEEDS EYES, which is the harness's word for a target that changed as meant.
