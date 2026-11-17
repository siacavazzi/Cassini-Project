#!/usr/bin/env python3
"""plan_frames.py: how many frames the mission's passes' plans read (obs_mosaic.plan: every frame of a filter, or
SCALE_FRAMES spread over it), and how many of those lie past the first frames the in-memory hand-over holds
(stacking.HANDED_MB at 6 MB a 1,024 px frame: 21). Run from the repo root with the pipeline's environment."""
import math, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "web", "frames"))
import prebuild, obs_mosaic, stacking
room = stacking.HANDED_MB * 2 ** 20 // (6 * 2 ** 20)
tot = collections = None
rows = {}
for kind, passes in (("movie", prebuild.movie_passes()), ("mosaic and mosaic movie", prebuild.mosaic_passes())):
    frames = read = past = 0
    for u in passes:
        count = {}
        for fr in u["frames"]:
            count[fr[2]] = count.get(fr[2], 0) + 1
        picks = sum(len(range(0, c, max(1, math.ceil(c / obs_mosaic.SCALE_FRAMES)))) for c in count.values())
        frames += len(u["frames"]); read += picks; past += max(0, picks - room)
    rows[kind] = (len(passes), frames, read, past)
    print(f"{kind}: {len(passes)} passes, {frames} frames; their plans read {read}; {past} of those past the first {room} of their pass")
print(f"all: {sum(r[1] for r in rows.values())} frames, plans read {sum(r[2] for r in rows.values())}, past the room {sum(r[3] for r in rows.values())}")
