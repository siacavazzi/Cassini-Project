import sys, os, numpy as np
from PIL import Image

a, b = sys.argv[1], sys.argv[2]
fa, fb = sorted(os.listdir(a)), sorted(os.listdir(b))
print(f"{a}: {len(fa)} files, {b}: {len(fb)} files, same names: {fa == fb}")
only = set(fa) ^ set(fb)
if only:
    print("not in both:", sorted(only))
exact = 0
for f in sorted(set(fa) & set(fb)):
    x = np.asarray(Image.open(os.path.join(a, f)))
    y = np.asarray(Image.open(os.path.join(b, f)))
    if x.shape != y.shape:
        print(f"{f}: shape {x.shape} vs {y.shape}")
        continue
    if np.array_equal(x, y):
        exact += 1
        continue
    d = np.abs(x.astype(int) - y.astype(int))
    px = d.any(axis=-1) if d.ndim == 3 else d > 0
    # where the differing pixels are: within 16 px of the frame edge vs interior
    h, w = px.shape
    edge = np.zeros_like(px); edge[:16] = edge[-16:] = True; edge[:, :16] = edge[:, -16:] = True
    print(f"{f}: max abs diff {d.max()}, differing pixels {px.mean():.4%} "
          f"({px.sum()} px, {(px & edge).sum()} within 16px of edge)")
print(f"exact matches: {exact}/{len(set(fa) & set(fb))}")
