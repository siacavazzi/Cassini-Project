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

# a stacked pair has its own wavelength (WAC IR2 + IR1, 826 nm), so Titan's CB3 + IR2/IR1 has an eye mix
assert abs(cal.band_wavelength("W", "IR2/IR1") - 826.3) < 0.1 and cal.eye_mix("W", ["CB3", "IR2/IR1"], "TITAN") is not None

# Saturn's methane stare (WAC MT3 + CB2 + MT2): its color from CB2 alone, Saturn's, at its typical brightness
bands = ["MT3", "CB2", "MT2"]
m = cal.eye_mix("W", bands, "SATURN")
out = m @ typical("SATURN", "W", bands)
assert np.allclose(hue(out), hue(cal.eye_tint("SATURN")), atol=1e-4)
assert abs(out.mean() / typical("SATURN", "W", ["CB2"]).mean() - 1) < 0.01
# the methane bands stay in the brightness (METHANE_DETAIL of a band's share), never in the color: a cloud brighter
# in MT3 (high) is brighter, one darker in it darker, both Saturn's color
v = typical("SATURN", "W", bands)
high, low = m @ (v * [2, 1, 1]), m @ (v * [0.5, 1, 1])
assert high.sum() > out.sum() > low.sum()
assert np.allclose(hue(high), hue(out), atol=1e-4) and np.allclose(hue(low), hue(out), atol=1e-4)
w = cal.METHANE_DETAIL
assert abs(high.sum() / out.sum() - (1 + w / (1 + 2 * w))) < 1e-4
# the NAC's MT3 + MT2 + BL1 (set 37, which flattened to one cream): the methane bands' belts show as brightness
bands = ["MT3", "MT2", "BL1"]
m = cal.eye_mix("N", bands, "SATURN")
v = typical("SATURN", "N", bands)
assert (m @ (v * [1.5, 1.5, 1])).sum() > 1.2 * (m @ v).sum()

# twice a band's share (METHANE_DETAIL): set 37's storm and c32's belts stood out too little and the planet read pale;
# Titan's CB3 + MT2 + MT1 holds its surface window (SURFACE_WINDOW), where more methane haze would wash out the dark
# terrain, so its methane bands keep METHANE_DETAIL_WINDOW
assert cal.METHANE_DETAIL > 1 and cal.METHANE_DETAIL_WINDOW < 1
bands = ["CB3", "MT2", "MT1"]
m = cal.eye_mix("N", bands, "TITAN")
v = typical("TITAN", "N", bands)
w = cal.METHANE_DETAIL_WINDOW
assert abs((m @ (v * [2, 1, 1])).sum() / (m @ v).sum() - (1 + 1 / (1 + 2 * w))) < 1e-3

# Titan's two-filter CB3 + MT1 (channels: longer, mean, shorter): orange, its color from CB3, the green column empty
m = cal.eye_mix("N", ["CB3", "MT1"], "TITAN")
assert m.shape == (3, 3) and np.all(m[:, 1] == 0)
assert np.allclose(hue(m[:, 0]), hue(cal.eye_tint("TITAN")), atol=1e-4)
assert np.allclose(hue(m @ [0.2, 0, 0.05]), hue(cal.eye_tint("TITAN")), atol=1e-4)   # MT1: brightness, no color

# a body with no measure in a band (Phoebe): gray, whatever its bands read (their ratios to nothing are no color)
m = cal.eye_mix("N", ["IR3", "GRN", "UV3"], "PHOEBE")
for v in ([0.3, 0.3, 0.3], [0.4, 0.3, 0.2], [0.2, 0.3, 0.4]):
    assert np.allclose(hue(m @ v), [1 / 3] * 3, atol=1e-4)
assert (m @ [0.4, 0.4, 0.4]).sum() > (m @ [0.3, 0.3, 0.3]).sum()

# Iapetus, whose measure is unsure (two-toned: its spread is past BODY_SPREAD), in one color, its own, with its
# bands' brightness: the hot pink of set 35 (IR3 + GRN + UV3, ISS_214IA_IAPETUS091) is gone
assert cal.body_level("IAPETUS", "GRN", "N") is None
t = typical("IAPETUS", "N", ["IR3", "GRN", "UV3"])
m = cal.eye_mix("N", ["IR3", "GRN", "UV3"], "IAPETUS")
body, dark = m @ t, m @ (t * [0.5, 0.3, 0.15])
assert np.allclose(hue(body), hue(cal.eye_tint("IAPETUS")), atol=1e-4) and np.allclose(hue(dark), hue(body), atol=1e-4)
assert dark.sum() < body.sum()
# a body measured surely leans the way its bands do (Saturn's storm set, CB3 + MT2 + GRN: its color from CB3 and GRN)
bands = ["CB3", "MT2", "GRN"]
assert all(cal.body_level("SATURN", b, "N") for b in bands)
t = typical("SATURN", "N", bands)
m = cal.eye_mix("N", bands, "SATURN")
body, red = m @ t, m @ (t * [1.3, 1, 0.8])
assert np.allclose(hue(body), hue(cal.eye_tint("SATURN")), atol=1e-4) and red[0] / red[2] > 1.05 * body[0] / body[2]

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
# Natural color (the default) draws a set with a methane band as the eye style does (fix plan group C: Saturn
# teal, Jupiter green, Titan salmon); other false color sets keep the false color balance; Titan's surface window
# pair (CB3 + MT1) keeps its own drawing
with cal.coloring("natural"):
    assert cal.style() == "balanced"
    for cam, bands, target in (("W", ["MT3", "CB2", "MT2"], "SATURN"), ("N", ["MT3", "MT2", "BL1"], "JUPITER"),
                               ("N", ["CB3", "MT2", "MT1"], "TITAN"), ("W", ["CB2", "MT2"], "SATURN")):
        got = cal.color_mix(cam, bands, target)
        assert not isinstance(got, cal.FalseMix) and np.allclose(got, cal.eye_mix(cam, bands, target)), bands
    assert isinstance(cal.color_mix("N", ["IR3", "GRN", "UV3"], "ENCELADUS", own=True), cal.FalseMix)
    assert np.allclose(cal.color_mix("N", ["CB3", "MT1"], "TITAN"), cal.pair_mix("N", ["CB3", "MT1"], "TITAN"))
    assert np.allclose(cal.color_mix("N", ["RED", "GRN", "BL1"], "SATURN"), cal.natural_mix("N", ["RED", "GRN", "BL1"]))
# False color (Settings > Filter colors) balances methane sets as Natural color did before, in its own cache
with cal.coloring("false"):
    assert cal.style() == "false" and cal.false_balanced()
    assert isinstance(cal.color_mix("W", ["MT3", "CB2", "MT2"], "SATURN"), cal.FalseMix)
    assert np.allclose(cal.color_mix("N", ["RED", "GRN", "BL1"], "SATURN"), cal.natural_mix("N", ["RED", "GRN", "BL1"]))
with cal.coloring("raw"):
    assert cal.color_mix("W", ["MT3", "CB2", "MT2"], "SATURN") is None

# a false color set of more than three filters draws the three nearest red, green and blue, methane bands last
import sets_passes  # noqa: E402
nm = lambda fs: [cal.band_wavelength("N", f) for f in fs]
pick = lambda fs: [fs[j] for j in sets_passes.nearest_visible(fs, nm(fs))]
assert pick(["IR3", "GRN", "UV3", "UV1"]) == ["IR3", "GRN", "UV3"]          # Pandora: GRN over UV1
assert pick(["MT3", "CB2", "CB1", "MT2", "BL1", "UV1"]) == ["CB2", "CB1", "BL1"]   # a gas giant's continuum
assert pick(["MT3", "CB2", "MT2", "BL1"]) == ["CB2", "MT2", "BL1"]           # one methane band where it must
assert pick(["CB3", "CB1", "MT1", "UV1", "UV3"]) == ["CB3", "CB1", "UV3"]       # a Titan wind stare
assert pick(["IR3", "UV3", "UV1"]) == ["IR3", "UV3", "UV1"]                  # three: all of them, longest first
assert sets_passes.channels(["IR3", "GRN", "UV3", "UV1"], nm(["IR3", "GRN", "UV3", "UV1"])) == ("false", [0, 1, 2])
# a storm watch filed under a moon that rode along (or UNK) is drawn in its observation's body's color, not the moon's
# gray (calibration.mix_target): W1689643086_1 (HELENE, ISS_158SA_STORMW...); a moon's own observation keeps its target
storm = ["MT3", "CB2", "MT2"]
with cal.coloring("balanced"):
    rode = cal.color_mix("W", storm, "JANUS", obs="ISS_160SA_STORMW029_RIDER")
    assert np.allclose(rode, cal.eye_mix("W", storm, "SATURN")), rode
    assert np.allclose(cal.color_mix("W", storm, "UNK", obs="ISS_159SA_WIND5HR003_PRIME"), cal.eye_mix("W", storm, "SATURN"))
    gray = cal.color_mix("W", storm, "JANUS")
    assert np.allclose(gray[0], gray[1]) and np.allclose(gray[1], gray[2])          # no observation: as before
    assert np.allclose(cal.color_mix("W", storm, "JANUS", obs="ISS_160JA_JANUS001_PRIME"), gray)
    assert np.allclose(cal.color_mix("W", storm, "SATURN", obs="ISS_160TI_X"), cal.eye_mix("W", storm, "SATURN"))
    assert cal.mix_target("TITAN", storm, "W", "ISS_159SA_STORMW") == "TITAN"

print("ok")
