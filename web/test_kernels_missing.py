"""Missing SPICE kernels stop the work (data_source.KernelsMissing), never a picture made without them.

  python web/test_kernels_missing.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import data_source as ds  # noqa: E402
import bootleg_autonav as ba  # noqa: E402


def raises(f):
    try:
        f()
    except ds.KernelsMissing as e:
        return str(e)
    except Exception as e:   # a plain Exception would be swallowed by the pipeline's fallbacks
        raise AssertionError(f"not KernelsMissing: {type(e).__name__}: {e}")
    raise AssertionError("no KernelsMissing")


assert not issubclass(ds.KernelsMissing, Exception)   # (so "except Exception" fallbacks never swallow it)

# no meta-kernel for the year (CASSINI_KERNELS unset: the frames archive has no cosp_1000/index)
ds.get_kernel_source = lambda: "cassini_lut8.zip"
ds.listdir, ba.extra_kernels = (lambda p: []), (lambda: [])
msg = raises(lambda: ba.load_kernels(2017, 2017))
assert "2017" in msg, msg
ds.listdir = lambda p: ["cas_2016_iss_v06.tm"]
real_furnsh_metakernel, ds.furnsh_metakernel = ds.furnsh_metakernel, (lambda p: None)
assert "2017" in raises(lambda: ba.load_kernels(2016, 2017))
print("no meta-kernel for a year stops the load; ok")
ds.furnsh_metakernel = real_furnsh_metakernel

# a meta-kernel whose kernels are mostly missing from the archive
ds.using_zip = lambda src: True
ds.read_text = lambda p: "\\begindata\nKERNELS_TO_LOAD = ( " + " ".join(f"'$K/ck/{k}.bc'" for k in range(10)) + " )\n\\begintext\n"
loaded = []
import spiceypy as sp  # noqa: E402
sp.furnsh = loaded.append


def extract(path, missing):
    if int(path.rsplit("/", 1)[1].split(".")[0]) in missing:
        raise FileNotFoundError(path)
    return path


ds.extract_to_cache = lambda p: extract(p, {3})
ds.furnsh_metakernel("cas_2015_iss_v08.tm")   # one missing (2015's ck/15201_15201ra_hf.bc): the rest load
assert len(loaded) == 9, loaded
ds.extract_to_cache = lambda p: extract(p, set(range(2, 10)))
raises(lambda: ds.furnsh_metakernel("cas_2017_iss_v03.tm"))
print("a meta-kernel missing more than", ds.MISSING_KERNELS_OK, "kernels stops the load; ok")
