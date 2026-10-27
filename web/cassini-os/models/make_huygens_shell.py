"""Huygens entry shell for the landing cutscene: ESA's own model, in two parts that separate during the descent.

Source: the ESA SPICE Service's Huygens dataset, misc/cosmo/models/huyprobe.cmod (Celestia binary model; the same mesh
as huygens.3ds there), https://spiftp.esac.esa.int/data/SPICE/HUYGENS/misc/cosmo/models/ (copy on branch
assets/huygens-models, assets-huygens/bin/). CC BY-NC 3.0 IGO, credit the ESA SPICE Service.

The model's eight meshes are split into the two parts that came off one after the other: the front shield (the heat
shield's cone with its rim and the ring behind it, and the three fittings on that ring), released 32.5 s into the
descent, and the back cover (with the pilot chute's lid on top), pulled off by the pilot chute at 2.5 s. The model's
materials are flat colors (all of the shell one saturated yellow), so each is drawn as what it stands for: the back cover
and the inside of the shield in gold foil like the descent module, the shield's outer face (its heat-protection tiles) a
pale grey-tan, its rim and ring aluminium, the three fittings dark. Scaled so the front shield is 2.7 m across (ESA), turned so the probe's spin axis is +Y with the
heat shield facing -Y, and placed in the descent module's frame (make_huygens_dm.py: base of its fore dome at y = 0):
the module's drum sits on the ring behind the heat shield, its fore dome in the cone.

  python make_huygens_shell.py huyprobe.cmod huygens_shell.glb.b64.txt
"""
import base64, json, struct, sys
import numpy as np


def read_cmod(path):
    """Materials (diffuse colors) and meshes (positions, normals, triangle lists with a material each) of a binary cmod."""
    b = open(path, "rb").read()
    assert b[:16] == b"#celmodel_binary"
    o, mats, meshes = 16, [], []

    def take(fmt):
        nonlocal o
        v = struct.unpack_from("<" + fmt, b, o)
        o += struct.calcsize("<" + fmt)
        return v

    while o < len(b):
        (t,) = take("h")
        if t == 1001:                                   # material
            m = {}
            while True:
                (p,) = take("h")
                if p == 1002:
                    break
                if p in (1003, 1004, 1014):             # diffuse, specular, emissive: a color
                    take("h"); c = take("3f")
                    if p == 1003: m["diffuse"] = c
                elif p in (1005, 1006):                 # specular power, opacity
                    take("h"); take("f")
                elif p == 1007:                         # texture
                    take("hh"); (n,) = take("H"); o += n
                elif p == 1015:
                    take("h")
                else:
                    raise ValueError(f"material property {p}")
            mats.append(m)
        elif t == 1009:                                 # mesh
            take("h"); desc = []
            while True:
                (s,) = take("h")
                if s == 1012:
                    break
                desc.append((s, take("h")[0]))
            take("h"); (n,) = take("I")
            width = {0: 1, 1: 2, 2: 3, 3: 4, 4: 1}
            stride = 4 * sum(width[f] for _, f in desc)
            raw = np.frombuffer(b, np.uint8, n * stride, o).reshape(n, stride); o += n * stride
            attrs, off = {}, 0
            for s, f in desc:
                w = 4 * width[f]
                if f != 4:
                    attrs[s] = raw[:, off:off + w].copy().view(np.float32).reshape(n, width[f])
                off += w
            groups = []
            while True:
                (pt,) = take("h")
                if pt == 1010:
                    break
                mi, c = take("II")
                idx = np.frombuffer(b, np.uint32, c, o).copy(); o += 4 * c
                assert pt == 0, "triangle lists only"
                groups.append((mi, idx))
            meshes.append((attrs[0], attrs.get(3), groups))
        else:
            raise ValueError(f"token {t}")
    return mats, meshes


src, out = sys.argv[1], sys.argv[2]
mats, meshes = read_cmod(src)
allP = np.concatenate([m[0] for m in meshes])
cy, cz = (allP[:, 1].min() + allP[:, 1].max()) / 2, (allP[:, 2].min() + allP[:, 2].max()) / 2
rim = np.hypot(allP[:, 1] - cy, allP[:, 2] - cz).max()
k = 1.35 / rim                                          # model units to metres
# the descent module's fore dome reaches 0.37 m below its drum, which sits on the ring behind the heat shield (x 7.68)
X_BASE = 7.68 + 0.37 / k
# ESA's materials by index: 0 the three fittings (red), 1 the ring behind the shield (grey), 2 the rim, 3 the shell
GOLD, TILES = (0.78, 0.62, 0.32), (0.74, 0.70, 0.62)
COLORS = {0: (0.2, 0.19, 0.18), 1: (0.62, 0.63, 0.65), 2: (0.66, 0.66, 0.67), 3: GOLD}
PARTS = {"front_shield": [0, 1, 2, 3, 4, 6], "back_cover": [5, 7]}
blobs, views, accessors, gmeshes, nodes = [], [], [], [], []


def add(arr, target=34962):
    off = sum(len(x) for x in blobs)
    blobs.append(arr.tobytes())
    views.append({"buffer": 0, "byteOffset": off, "byteLength": len(blobs[-1]), "target": target})
    return len(views) - 1


for name, ids in PARTS.items():
    prims = []
    for mi in sorted({g[0] for i in ids for g in meshes[i][2]}):
        pos, nor, col = [], [], []
        for i in ids:
            P, N, groups = meshes[i]
            for gm, idx in groups:
                if gm != mi:
                    continue
                q = P[idx]
                pos.append(np.stack([(q[:, 1] - cy) * k, (X_BASE - q[:, 0]) * k, (q[:, 2] - cz) * k], 1))
                nq = N[idx] if N is not None else np.zeros_like(q)
                nor.append(np.stack([nq[:, 1], -nq[:, 0], nq[:, 2]], 1))
                c = np.tile(COLORS.get(mi, (0.7, 0.7, 0.7)), (len(q), 1))
                if name == "front_shield" and mi == 3:
                    c[nor[-1][:, 1] < -0.3] = TILES
                col.append(c)
        pos = np.concatenate(pos).astype(np.float32); nor = np.concatenate(nor).astype(np.float32)
        nor /= np.linalg.norm(nor, axis=1)[:, None] + 1e-12
        col = np.concatenate(col).astype(np.float32)
        a = len(accessors)
        accessors.append({"bufferView": add(pos), "componentType": 5126, "count": len(pos), "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()})
        accessors.append({"bufferView": add(nor), "componentType": 5126, "count": len(nor), "type": "VEC3"})
        accessors.append({"bufferView": add(col), "componentType": 5126, "count": len(col), "type": "VEC3"})
        prims.append({"attributes": {"POSITION": a, "NORMAL": a + 1, "COLOR_0": a + 2}, "material": 0})
    gmeshes.append({"name": name, "primitives": prims})
    nodes.append({"name": name, "mesh": len(gmeshes) - 1})

materials = [{"name": "shell", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.35, "roughnessFactor": 0.5}, "doubleSided": True}]
bin_ = b"".join(blobs)
gltf = {
    "asset": {"version": "2.0", "generator": "make_huygens_shell.py", "copyright": "ESA SPICE Service (Huygens SPICE dataset, doi:10.5270/esa-ssem3np), CC BY-NC 3.0 IGO"},
    "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gmeshes, "materials": materials,
    "buffers": [{"byteLength": len(bin_)}], "bufferViews": views, "accessors": accessors,
}
js = json.dumps(gltf, separators=(",", ":")).encode()
js += b" " * (-len(js) % 4)
glb = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(bin_)) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(bin_), b"BIN\0") + bin_
open(out, "w").write(base64.b64encode(glb).decode())
for nd, gm in zip(nodes, gmeshes):
    ys = [accessors[p["attributes"]["POSITION"]]["min"][1] for p in gm["primitives"]], [accessors[p["attributes"]["POSITION"]]["max"][1] for p in gm["primitives"]]
    print(nd["name"], "y %.2f..%.2f m" % (min(ys[0]), max(ys[1])))
print(out, "scale %.4f m per unit" % k, len(glb), "bytes")
