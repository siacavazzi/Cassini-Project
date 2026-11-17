"""Even exposure gives a held picture one gain (obs_mosaic.held_gains). A colour movie holds each colour set until the
next is complete, so frames in a row show the same picture and the brightness chain repeats (exposure_chain's "1.000 x").
evened_gains spreads each step between two pictures over the frames either side, so a held picture brightened towards
the next step and dropped after it: 149HE HELENCLOS001's gains ran 1.015, 1.02, 1.025, 1.03, 1.04, then 0.97
(2026-11-16). Each run of the same picture now takes the mean of what evened_gains wants for its frames. The flashes
and the smoothing are still counted in frames: a picture shown once among held ones is still brought to them, and a
pass that holds nothing is evened to the same gains as before.
Run: python web/test_exposure_held.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import math  # noqa: E402
import obs_mosaic as om  # noqa: E402

runs = lambda L: [[k for k in range(len(L)) if L[k] == v and all(L[m] == v for m in range(min(k, j), max(k, j) + 1))]
                  for j, v in enumerate(L)]

# a staircase, as Helene's: each picture held five or six frames, brighter each time
stairs = [0.0] * 5 + [0.27] * 6 + [0.49] * 1 + [0.50] * 6 + [0.58] * 2 + [0.59] * 5 + [0.64] * 2 + [0.66] * 4 + [0.69]
was, now = om.evened_gains(stairs, 8), om.held_gains(stairs, 8)
assert len(now) == len(stairs)
for k, same in enumerate(runs(stairs)):
    assert len({now[m] for m in same}) == 1, (k, [now[m] for m in same])          # one gain for the picture
assert len(set(was[:5])) > 1 and was[4] > was[0] and was[5] < was[4]              # (what it was: a ramp, then a drop)
# the gain is the mean of what the frames were given (to the rounding)
for same in runs(stairs)[::5]:
    want = math.exp(sum(math.log(was[m]) for m in same) / len(same))
    assert abs(now[same[0]] - want) < 0.006, (now[same[0]], want)

# a picture shown once among held ones (a colour set's own frame between the held frames, brighter): brought to them
blink = ([0.0] * 3 + [0.6]) * 8 + [0.0] * 3      # (ending on held frames: a stretch's last frame is never taken for a flash)
got = om.held_gains(blink, 8)
assert all(abs(g - 1.0) < 0.02 for g, v in zip(got, blink) if v == 0.0), got
assert all(abs(g - math.exp(-0.6)) < 0.02 for g, v in zip(got, blink) if v == 0.6), got

# nothing held: the same gains as before
plain = [0.01 * ((7 * k) % 13) + 0.002 * k for k in range(40)]
assert len(set(plain)) == len(plain) and om.held_gains(plain, 8) == om.evened_gains(plain, 8)
assert om.held_gains([0.3], 8) == om.evened_gains([0.3], 8) and om.EXPOSURE_RULE == 10
print("ok")
