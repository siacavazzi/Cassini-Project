"""Check that obs_mosaic.detail's luminance, the sum of the three channels over 3, is numpy's mean over the channels to
the bit for every 8-bit colour (2^24), as float32 the way detail has them.
Run: python web/test_detail_mean.py"""
import numpy as np

v = np.arange(256, dtype=np.float32)
r, g, b = np.meshgrid(v, v, v, indexing="ij")
rgb = np.stack([r, g, b], axis=-1).reshape(4096, 4096, 3)
mean = rgb.mean(axis=2)
summed = (rgb[..., 0] + rgb[..., 1] + rgb[..., 2]) / 3
assert summed.dtype == mean.dtype == np.float32 and summed.shape == mean.shape
assert summed.tobytes() == mean.tobytes()
# as detail gets them: a uint8 RGBA picture's colour channels as float32, a view with the alpha's stride
rgba = np.random.default_rng(3).integers(0, 256, (517, 389, 4)).astype(np.uint8)
x = rgba[..., :3].astype(np.float32)
assert ((x[..., 0] + x[..., 1] + x[..., 2]) / 3).tobytes() == x.mean(axis=2).tobytes()
print(f"{rgb.shape[0] * rgb.shape[1] + rgba.shape[0] * rgba.shape[1]} colours ok")
