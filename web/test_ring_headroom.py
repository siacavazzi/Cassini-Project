"""A ring pass's white has headroom (obs_mosaic.RING_HEADROOM): since CISSCAL's defect repair (#153) its 99.9th percentile
is the brightest ringlet, and the rings drew ~15% brighter than before; a moon's pass keeps its white. Run: python web/test_ring_headroom.py"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

assert om.RING_HEADROOM > 1
assert om._ring({"key": ("SATURN", "ISS_124RI_RDHRCOMP001_VIMS", "N", 0)})
assert not om._ring({"key": ("RHEA", "ISS_049RH_SHAPE001_PRIME", "N", 0)})
assert not om._ring({"key": ("DAPHNIS", "ISS_115RI_MNRNGSHAD004_PRIME", "N", 0)})   # a moon's pass, its own white
print("ok")
