"""Mean and peak level (dB) of a recorded cutscene's sound, by section of screen time.
    python3 levels.py OUT   (OUT.webm and OUT.json from audio.cjs)  [a-b ...]
"""
import json
import re
import subprocess
import sys

out = sys.argv[1]
off = json.load(open(out + ".json"))["offset"]
segs = sys.argv[2:] or ["0-4", "4-14", "14-34", "34-45", "45-62", "62-73", "73-88", "88-97"]
for seg in segs:
    a, b = map(float, seg.split("-"))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(off + a), "-t", str(b - a), "-i", out + ".webm", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (\S+) dB", r), re.search(r"max_volume: (\S+) dB", r)
    print(f"  {seg:>8}  mean {m[0][1] if m[0] else '?':>6} dB  peak {m[1][1] if m[1] else '?':>6} dB")
