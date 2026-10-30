"""Checks of natural color emulation (colors=eye, calibration.eye_mix): a false color set comes out in its body's own
color where its bands are at their typical shares, methane bands give no color, a body without a measure is gray,
a set reaching both sides of the visible leans the way its bands do, and true color sets are drawn as Natural color
draws them. Run: python web/test_color_eye.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402  (puts the repo on the path)
import calibration as cal  # noqa: E402


def hue(rgb):
    """linear rgb -> its share of each channel"""
    rgb = np.asarray(rgb, float)
    return rgb / rgb.sum()


def typical(target, camera, bands):
    return np.array([cal.body_level(target, b, camera, sure=False) for b in bands])


# filters' wavelengths from filter_calibration.csv, either wheel
assert abs(cal.band_wavelength("W", "CB2") - 752.3) < 0.1 and abs(cal.band_wavelength("N", "BL1") - 456.8) < 0.1
assert abs(cal.band_wavelength("N", "IR3") - 925.9) < 0.1 and abs(cal.band_wavelength("W", "VIO") - 419.7) < 0.1

# Saturn's methane stare (WAC MT3 + CB2 + MT2): drawn from CB2 alone, in Saturn's color, at its typical brightness
m = cal.eye_mix("W", ["MT3", "CB2", "MT2"], "SATURN")
assert np.all(m[:, [0, 2]] == 0)
out = m @ typical("SATURN", "W", ["MT3", "CB2", "MT2"])
assert np.allclose(hue(out), hue(cal.eye_tint("SATURN")), atol=1e-4)
assert abs(out.mean() / typical("SATURN", "W", ["CB2"]).mean() - 1) < 0.01
# a cloud twice as bright in CB2 is twice as bright, same color; MT3 and MT2 change nothing
v = typical("SATURN", "W", ["MT3", "CB2", "MT2"]) * [1, 2, 1]
assert np.allclose(m @ v, 2 * out, rtol=1e-5)
assert np.allclose(m @ (v * [5, 1, 0.2]), m @ v)

# Titan's two-filter CB3 + MT1 (channels: longer, mean, shorter): orange, from CB3, the green column empty
m = cal.eye_mix("N", ["CB3", "MT1"], "TITAN")
assert m.shape == (3, 3) and np.all(m[:, 1:] == 0)
assert np.allclose(hue(m[:, 0]), hue(cal.eye_tint("TITAN")), atol=1e-4)

# a body with no measure in a band (Phoebe): gray where the set's bands read alike, and the set's own slope where
# they don't: brighter in IR3 than UV3 leans red, the other way blue
m = cal.eye_mix("N", ["IR3", "GRN", "UV3"], "PHOEBE")
assert np.allclose(hue(m @ [0.3, 0.3, 0.3]), [1 / 3] * 3, atol=1e-4)
red, blue = m @ [0.4, 0.3, 0.2], m @ [0.2, 0.3, 0.4]
assert red[0] > red[1] > red[2] and blue[2] > blue[1] > blue[0]

# Iapetus' dark side against its typical (both sides): redder in IR3 than in UV3 comes out redder than the body
t = typical("IAPETUS", "N", ["IR3", "GRN", "UV3"])
m = cal.eye_mix("N", ["IR3", "GRN", "UV3"], "IAPETUS")
body, dark = m @ t, m @ (t * [0.5, 0.3, 0.15])
assert np.allclose(hue(body), hue(cal.eye_tint("IAPETUS")), atol=1e-4) and dark[0] / dark[2] > 1.5 * body[0] / body[2]
# the measured colors: Saturn and Titan warm, the icy moons near gray, a body without one gray
assert cal.eye_tint("SATURN")[2] < 0.8 and abs(cal.eye_tint("DIONE")[2] - 1) < 0.15 and cal.eye_tint("PHOEBE") == [1.0] * 3

# in the eye style true color sets keep their natural matrix; false color sets get eye_mix, not the false balance
with cal.coloring("eye"):
    assert cal.style() == "eye"
    assert np.allclose(cal.color_mix("N", ["RED", "GRN", "BL1"], "SATURN"), cal.natural_mix("N", ["RED", "GRN", "BL1"]))
    got = cal.color_mix("W", ["MT3", "CB2", "MT2"], "SATURN")
    assert not isinstance(got, cal.FalseMix) and np.allclose(got, cal.eye_mix("W", ["MT3", "CB2", "MT2"], "SATURN"))
    # tone draws it like a true color set: a typical Saturn pixel cream, from CB2 alone
    lvl = typical("SATURN", "W", ["MT3", "CB2", "MT2"])
    chans = [np.full((8, 8), v, np.float32) for v in lvl]
    px = [int(c[0, 0, 0]) for c in cal.tone(chans, 0.0, got)]
    assert px[0] > px[1] > px[2], px
with cal.coloring("natural"):
    assert cal.style() == "balanced" and isinstance(cal.color_mix("W", ["MT3", "CB2", "MT2"], "SATURN"), cal.FalseMix)
print("ok")
