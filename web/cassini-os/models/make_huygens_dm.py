"""Huygens descent module for the landing cutscene: ESA's own mesh, made into a small GLB the page loads.

Source: the ESA SPICE Service's Huygens dataset, misc/cosmo/models/huygens.obj (the same mesh as Asm2.stl and
huygens.cmod, which ESA's Cosmographia "Huygens descent" uses), https://spiftp.esac.esa.int/data/SPICE/HUYGENS/misc/cosmo/models/
(copy on branch assets/huygens-models, assets-huygens/huygens.obj). CC BY-NC 3.0 IGO, credit the ESA SPICE Service.

The mesh has no materials, so each face is colored by where it is: the top platform silver, the shell gold foil, the
spin vanes and brackets out past the rim aluminium, the small parts standing on the platform (antennas) dark.
Scaled so the drum is 1.3 m across (ESA), turned so the probe's spin axis (the mesh's +Z, antennas up) is +Y, and
moved so its lowest point is at y = 0 on the axis. Flat normals.

  python make_huygens_dm.py huygens.obj huygens_dm.glb.b64.txt
"""
import base64, json, struct, sys
import numpy as np

src, out = sys.argv[1], sys.argv[2]
V, F = [], []
for line in open(src):
    p = line.split()
    if p and p[0] == "v":
        V.append([float(x) for x in p[1:4]])
    elif p and p[0] == "f":
        idx = [int(x.split("/")[0]) - 1 for x in p[1:]]
        F += [[idx[0], idx[i], idx[i + 1]] for i in range(1, len(idx) - 1)]
V, F = np.array(V), np.array(F)
r = np.hypot(V[:, 0], V[:, 1])
R = np.percentile(r, 95)                      # the drum's radius in mesh units
k = 0.65 / R
P = np.stack([V[:, 0], V[:, 2], -V[:, 1]], 1) * k
P[:, 1] -= P[:, 1].min()
tri = P[F]                                    # faces x 3 x 3
n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
c = tri.mean(1)
rc = np.hypot(c[:, 0], c[:, 2])
# the top platform: the flat upward faces near the top of the drum
top_y = np.percentile(P[:, 1], 75)
gold, silver, alu, dark = (0.78, 0.62, 0.32), (0.78, 0.79, 0.8), (0.6, 0.62, 0.64), (0.15, 0.15, 0.16)
col = np.tile(gold, (len(F), 1))
plat = (n[:, 1] > 0.8) & (c[:, 1] > top_y - 0.05)
col[plat] = silver
col[(c[:, 1] > top_y + 0.06) & (rc < 0.5)] = dark
col[rc > 0.66] = alu
pos = tri.reshape(-1, 3).astype(np.float32)
nor = np.repeat(n, 3, 0).astype(np.float32)
rgb = np.repeat(col, 3, 0).astype(np.float32)
blobs = [pos.tobytes(), nor.tobytes(), rgb.tobytes()]
offs = np.cumsum([0] + [len(b) for b in blobs])
gltf = {
    "asset": {"version": "2.0", "generator": "make_huygens_dm.py", "copyright": "ESA SPICE Service (Huygens SPICE dataset, doi:10.5270/esa-ssem3np), CC BY-NC 3.0 IGO"},
    "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "huygens_descent_module", "mesh": 0}],
    "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2}, "material": 0}]}],
    "materials": [{"name": "foil", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.35, "roughnessFactor": 0.45}, "doubleSided": True}],
    "buffers": [{"byteLength": int(offs[-1])}],
    "bufferViews": [{"buffer": 0, "byteOffset": int(offs[i]), "byteLength": len(blobs[i]), "target": 34962} for i in range(3)],
    "accessors": [
        {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
        {"bufferView": 1, "componentType": 5126, "count": len(pos), "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": len(pos), "type": "VEC3"},
    ],
}
js = json.dumps(gltf, separators=(",", ":")).encode()
js += b" " * (-len(js) % 4)
bin_ = b"".join(blobs)
glb = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(bin_)) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(bin_), b"BIN\0") + bin_
open(out, "w").write(base64.b64encode(glb).decode())
print(out, len(F), "triangles", "height %.2f m" % P[:, 1].max(), "top platform y %.2f" % top_y, "silver", int(plat.sum()), "alu", int((rc > 0.66).sum()))
