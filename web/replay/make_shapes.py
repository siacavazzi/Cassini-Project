#!/usr/bin/env python3
"""
Turns the real shape models of Saturn's small moons into the viewer's mesh files
(data/textures/models/<moon>.mesh.b64.txt), so they show as the lumpy bodies Cassini photographed instead of
smooth ellipsoids.

The shapes are Thomas, P., Joseph, J., and Ansty, T., Saturn Small Moon Shape Models V1.0,
urn:nasa:pds:saturn_satellite_shape_models::1.0, NASA Planetary Data System, 2018 (doi:10.26033/ewy3-jy61), CC0,
built from Cassini ISS images. They are read from CelestiaProject/CelestiaContent's models/ folder, which carries
them as binary .cmod files (README: "Models of Pan, Daphnis, Atlas, Prometheus, Pandora, Epimetheus, Janus, Telesto,
Calypso, Helene, and Hyperion are from https://sbn.psi.edu/pds/resource/saturnsatshapes.html"):

  git clone --depth 1 --filter=blob:none --sparse https://github.com/CelestiaProject/CelestiaContent.git
  git -C CelestiaContent sparse-checkout set models
  python web/replay/make_shapes.py CelestiaContent/models

Each model is cut down to about --triangles triangles (a moon a few tens of km across never fills enough of the screen
to need the full 27k) and written as the format the viewer's loadShapes reads: "CMS1", uint32 nvert, uint32 nidx,
int16 xyz (fraction of the largest radius, body axes: x toward Saturn, z the pole), uint16 uv, uint16 indices,
base64 wrapped like the Hyperion and Phoebe files.
"""
import argparse
import base64
import os
import struct

import numpy as np

MOONS = ["pan", "daphnis", "atlas", "prometheus", "pandora", "epimetheus", "janus", "telesto", "calypso", "helene"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "textures", "models")
FLOATS = {0: 1, 1: 2, 2: 3, 3: 4, 4: 1}   # floats per vertex attribute format (UByte4 is one 4-byte word)


def read_cmod(path):
    """Positions and triangle indices of a binary Celestia model."""
    b = open(path, "rb").read()
    assert b[:16] == b"#celmodel_binary", path
    p = 16

    def u16():
        nonlocal p
        p += 2
        return struct.unpack_from("<H", b, p - 2)[0]

    def u32():
        nonlocal p
        p += 4
        return struct.unpack_from("<I", b, p - 4)[0]

    def skip_value():
        nonlocal p
        t = u16()
        if t in (1, 2, 3, 4):
            p += 4 * t
        elif t == 5:
            p += u16()
        elif t in (6, 7):
            p += 4 if t == 6 else 12
        else:
            raise ValueError(f"value type {t} at {p}")

    pos, idx = [], []
    while p < len(b):
        tok = u16()
        if tok == 1001:   # material
            while True:
                t = u16()
                if t == 1002:
                    break
                if t == 1007:
                    u16()
                if t == 1015:
                    u16()
                    continue
                skip_value()
        elif tok == 1009:   # mesh
            assert u16() == 1011
            desc = []
            while True:
                s = u16()
                if s == 1012:
                    break
                desc.append((s, u16()))
            assert u16() == 1013
            n = u32()
            stride = sum(FLOATS[f] for _, f in desc)
            v = np.frombuffer(b, "<f4", n * stride, p).reshape(n, stride)
            p += 4 * n * stride
            base = sum(len(x) for x in pos)
            pos.append(v[:, :3].copy())
            while True:
                kind = u16()
                if kind == 1010:
                    break
                u32()
                k = u32()
                assert kind == 0, f"primitive {kind}"
                idx.append(np.frombuffer(b, "<u4", k, p).astype(np.int64) + base)
                p += 4 * k
        else:
            raise ValueError(f"token {tok} at {p}")
    P = np.concatenate(pos)
    # Celestia models are y-up with +z toward the viewer; the body frame has z = pole: (x, y, z) -> (x, -z, y)
    return np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1), np.concatenate(idx).reshape(-1, 3)


def weld(P, F):
    """Merges vertices at the same place (the models repeat them along texture seams), so the cut keeps the surface closed."""
    key = np.round(P / np.abs(P).max() * 1e5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    F = inv.reshape(-1)[F]
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    return P[first], F


def simplify(P, F, triangles):
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(P.astype(np.float64), F.astype(np.int32))
    s.simplify_mesh(target_count=triangles, aggressiveness=5, preserve_border=True, verbose=False)
    P, F, _ = s.getMesh()
    return P, F


def write_mesh(P, F, path):
    P = P / np.linalg.norm(P, axis=1).max()
    head = b"CMS1" + struct.pack("<II", len(P), F.size)
    body = np.round(P * 32767).astype("<i2").tobytes() + np.zeros((len(P), 2), "<u2").tobytes() + F.astype("<u2").tobytes()
    data = head + body + b"\0" * (-(len(head) + len(body)) % 4)
    with open(path, "w") as fh:
        fh.write(base64.b64encode(data).decode() + "\n")
    return len(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", help="CelestiaContent's models/ folder")
    ap.add_argument("--triangles", type=int, default=6000)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    for moon in MOONS:
        P, F = weld(*read_cmod(os.path.join(args.models, f"{moon}.cmod")))
        n0 = len(F)
        P, F = simplify(P, F, args.triangles)
        assert len(P) < 65536
        size = write_mesh(P, F, os.path.join(args.out, f"{moon}.mesh.b64.txt"))
        ext = np.abs(P).max(0) / np.linalg.norm(P, axis=1).max()
        print(f"{moon:11s} {n0:6d} -> {len(F):5d} triangles, {size / 1024:4.0f} KB, extent x:y:z {ext.round(2)}")


if __name__ == "__main__":
    main()
