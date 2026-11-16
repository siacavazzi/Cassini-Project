"""flat_field's repaired maps and fallbacks: a map in CASSINI_CISSCAL_FIX is read in place of CISSCAL's cube, the
recipe of fetch_flat_fix gives a good map back from its slope file, and filter pairs with no slope file take the same
pair at another temperature, the polarizer's other angle, then its clear filter.
Run: python web/test_flat_fix.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib.util
import tempfile
import numpy as np
import flat_field as ff  # noqa: E402

spec = importlib.util.spec_from_file_location("fetch_flat_fix", os.path.join(os.path.dirname(ff.__file__), "helper programs", "fetch_flat_fix.py"))
fetch = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetch)

# the recipe: a slope file's middle median over it, summed modes from the slope averaged first
rng = np.random.default_rng(1)
slope = 900 * (1 + 0.02 * rng.standard_normal((1024, 1024)))
maps = fetch.maps(slope)
assert maps["full"].shape == (1024, 1024) and maps["sum2"].shape == (512, 512) and maps["sum4"].shape == (256, 256)
assert all(ff.usable_flat(m) for m in maps.values())
assert abs(float(np.median(maps["full"][312:712, 312:712])) - 1) < 1e-6

# a repaired map is read in place of the mirror's cube
with tempfile.TemporaryDirectory() as fix:
    os.makedirs(os.path.join(fix, "flat"))
    np.save(os.path.join(fix, "flat", "flat129.full.npy"), maps["full"])
    ff.FIX = fix
    ff._map.cache_clear()
    assert np.array_equal(ff._map("flat129", "full"), maps["full"])
    # the build's guard: CISSCAL's files without the repaired maps is no build
    try:
        ff.check_flat_fix(); raise AssertionError("a build without the repaired flat129 was let through")
    except ff.FlatFixMissing:
        pass
    for mode in ("full", "sum2", "sum4"):
        np.save(os.path.join(fix, "flat", f"flat129.{mode}.npy"), maps[mode])
    assert ff.check_flat_fix() == fix

# fallbacks, on a slope table of a few rows
rows = [["ISSWA", "p5", "CL1", "IRP90", "2", "OFF", "512", "SLOPE080.IMG"],
        ["ISSNA", "p5", "CL1", "UV3", "2", "ON", "1", "SLOPE120.IMG"],
        ["ISSNA", "m10", "CL1", "MT1", "2", "ON", "1", "SLOPE140.IMG"],
        ["ISSNA", "m10", "P0", "MT2", "2", "ON", "1", "SLOPE158.IMG"]]
ff._slope_db = lambda: rows
info = lambda cam, filt, temp="5.0": {"INSTRUMENT_ID": cam, "FILTER_NAME": filt, "OPTICS_TEMPERATURE": f"({temp},-999)"}
assert ff.flat_name(info("ISSWA", "(CL1,IRP0)")) == "flat080"             # the polarizer's other angle
assert ff.flat_name(info("ISSNA", "(CL1,UV3)", "-999.0")) == "flat120"     # unknown temperature: m10 as cisscal, then p5
assert ff.flat_name(info("ISSNA", "(IRP0,MT1)", "0.7")) == "flat140"       # no IRP0/MT1: its clear filter, another temperature
assert ff.flat_name(info("ISSNA", "(P120,MT2)", "0.7")) == "flat158"       # P120 -> P0 of the same family
assert ff.flat_name(info("ISSWA", "(CB3,HAL)")) is None                    # no rule reaches it: none, as cisscal
print("ok")
