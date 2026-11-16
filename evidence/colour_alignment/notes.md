# Taste call 6: gray color sets that now come out in color

Each sheet: left = today's main (drawn gray because the channels could not be lined up), right = the same set with the full-depth calibration branch plus the direction-aware matcher (branch claude/colour-alignment-recovery). Both drawn by the site's own picture path (color_image.processed_frame), north up, on black.

- titan-crescent_1.jpg: Titan crescent, CB3+MT1. Recovered by full-depth calibration alone (phase correlation near SPICE).
- saturn-limb_2.jpg: Saturn's limb on black sky, CB2+MT2. Recovered by full-depth calibration (limb outline match).
- phoebe_3.jpg: Phoebe, GRN+IR1+UV3. Recovered by full-depth calibration (phase correlation on all channels).
- rhea_4.jpg: Rhea, GRN+IR1+UV3. Recovered by full-depth calibration (one channel by phase near SPICE, one at SPICE's offset).
- saturn-rgb_5.jpg: Saturn, BL1+GRN+RED. Recovered by full-depth calibration (phase near SPICE).
- titan-limb-borderline_6.jpg: BORDERLINE. Titan CB3+MT1 placed by a limb outline match 87 px from as taken. The haze at the top edge shows a gray-brown band: is that real haze color or a misplaced channel?
- saturn-ring-line_7.jpg: Saturn cloud tops crossed by one thin ring line, CB2+MT2+MT3. Direction-aware match: pinned across the line, SPICE's place along it (the clouds are featureless that way). The line fades toward the right in color. NOTE: after review this set stays gray (the third-by-third guard: the line does not line up in every third).
- rings-over-disk_8.jpg: rings over Saturn's disk, CB2+MT2. Direction-aware match on the ring edges.
- rings-gap_9.jpg: ring gaps in front of Saturn, CB2+MT2+MT3. Both other channels pinned across the ring edges.
- ring-arc-stars_10.jpg: faint ring arc on star sky. Arc lined up; stars may show small color dots along the arc's direction.
- titan-blank-closeup_11.jpg: Titan close-up wholly on the disk (SPICE), CB3+MT1, a 3-level spread and nothing else: drawn in the haze's own even color instead of gray.
- saturn-ring-edge-weak_12.jpg: Saturn cloud tops with a ring edge, CB2+MT2: the weakest ridge the matcher accepted (edges agree 0.52). NOTE: after review this set stays gray (third-by-third guard).
- wac-limb-borderline_13.jpg: BORDERLINE. WAC Saturn limb, BL1+GRN+RED: a parallel ridge stood fairly close (0.58 against 0.36).

## Review checks (head after 8119d049)

- check_overlay_*.jpg: red = reference, cyan = the other channel, whole frame plus the middle at full size, for the five sets review called uncertain.
- check_hard_*.jpg: the site's picture of the same sets under the hardest studio look (black 60, contrast 100, saturation 100, white at the picture's 99th percentile). The three faint-band Saturn sets (N1775449422_1, N1775455941_1, N1740713147_1) show no fringe; they wash to even yellow-white. They stay in color.
- check_N1481722996_crops.png: full-resolution red/cyan crops at left, middle and right along the two shadow lines. A one-sided cyan edge runs along the lines. The edge matches (whole frame, each third, and the fine detail alone) all put the channels within 0.5 px across the lines, so the edge is the line's own shape differing between the filters, not a shift. It stays in color, flagged for Sam's eye.
- W1704429349_1 (WAC limb) is now gray: the limb is curved, and its thirds do not agree within 1 px.
