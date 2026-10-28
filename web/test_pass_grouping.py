"""How obs_mosaic.units groups an observation's frames into passes, on frames laid out as the Mac Mini's geometry
cache has the Jupiter approach's (2026-10-28, Sam's Jupiter edit): a frame far off the body (a clear frame pointed
at a moon, one UV1 frame 161 frames off) leaves the pass rather than making its lap too wide for a mosaic
(_drop_strays); a lap stopped short after a few frames joins the mosaic movie instead of splitting it (_piece);
two touching places are a 1x2 mosaic. Passes these rules group anew get their own folders (GROUPING); every other
pass keeps its own. Run: python web/test_pass_grouping.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import pandas as pd
import obs_mosaic as om

F5 = [("BL1", "CL2"), ("CL1", "MT2"), ("CL1", "CB2"), ("CL1", "MT3"), ("UV1", "CL2")]
Q4 = [(0.32, 0.34), (0.32, -0.36), (-0.39, -0.36), (-0.39, 0.34)]


class Obs:
    """frames of one observation: rows for the index, (x, y, z) for the geometry cache"""
    def __init__(self, name):
        self.name, self.rows, self.geo, self.t = name, [], {}, 975703142.0

    def frame(self, f, at, dt=55):
        fid = f"N{int(self.t)}_1"
        self.rows.append({"path": f"x/{fid}.png", "id": fid, "filter1": f[0], "filter2": f[1], "seconds_1970": self.t,
                          "TARGET_NAME": "JUPITER", "OBSERVATION_ID": self.name, "INSTRUMENT_ID": "ISSNA"})
        if at is not None:
            self.geo[fid] = (-at[0] * om.FRAME, -at[1] * om.FRAME, 3.0e7)
        self.t += dt
        return fid

    def lap(self, places=Q4, filters=F5, pause=4437):
        for p in places:
            for f in filters:
                self.frame(f, p)
        self.t += pause - 55


def units(*observations):
    rows = [r for o in observations for r in o.rows]
    idx = pd.DataFrame(rows)
    geo = {k: v for o in observations for k, v in o.geo.items()}
    groups = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices
    om._observations = lambda: (idx, groups)
    om.reel.geometry = lambda ids: {i: geo[i] for i in ids if i in geo}
    om.reel.wavelength = lambda inst, f: 600
    om._units.clear()
    om._unit_of.clear()
    rowmap = dict(zip(idx["id"], range(len(idx))))
    om._row_of = lambda: (idx, rowmap)
    return {o.name: om.units("JUPITER", o.name, "N") for o in observations}


def kinds(us):
    return [(u["kind"], len(u["frames"])) for u in us]


# 18ATM2X2A139: three laps, three frames of a fourth at one place, three laps, a lap with six clear frames 38 to 44
# frames off Jupiter, a last lap
a = Obs("ISS_C23JU_18ATM2X2A139_PRIME")
for _ in range(3):
    a.lap()
for f in F5[:3]:
    a.frame(f, Q4[0])
a.t += 5780 - 55
for _ in range(3):
    a.lap()
strays = []
for p in Q4:
    for f in F5:
        a.frame(f, p)
for x in (38.14, 38.66, 40.22, 41.80, 42.83, 43.99):
    strays.append(a.frame(("CL1", "CL2"), (x, -1.4)))
a.t += 4437
a.lap()
# 18ATM2X2B139: a lap whose UV1 frame at the last place is 161 frames off
b = Obs("ISS_C23JU_18ATM2X2B139_PRIME")
b.t = 975756602.0
b.lap(); b.lap()
for p in Q4[:3]:
    for f in F5:
        b.frame(f, p)
for f in F5[:4]:
    b.frame(f, Q4[3])
uv = b.frame(F5[4], (161.21, -2.8))
b.t += 4437
b.lap(); b.lap()
# ISS_C24JU_1X2NITE001: two touching places, four filters, seven laps 81 minutes apart
n = Obs("ISS_C24JU_1X2NITE001_PRIME")
n.t = 980091166.0
for _ in range(7):
    n.lap([(-0.49, 0.41), (-0.50, -0.39)], [("BL1", "CL2"), ("CL1", "GRN"), ("CL1", "CL2"), ("RED", "CL2")], pause=4860)
# ISS_C24JU_2X2ATM015 (as NAC took it: two places, nine filters) with two HAL frames 220 frames off, laps 1811 s apart
h = Obs("ISS_C24JU_2X2ATM015_PRIME")
h.t = 980593685.0
F9 = [("BL1", "CL2"), ("CL1", "CB2"), ("CL1", "CB3"), ("IRP0", "CB3"), ("CL1", "MT2"), ("CL1", "MT3"), ("P0", "GRN"), ("P60", "GRN"), ("P120", "GRN")]
for _ in range(6):
    for p in [(0.38, 0.39), (0.38, -0.39)]:
        for f in F9:
            h.frame(f, p, dt=30)
    h.frame(("HAL", "CL2"), (-219.42, -6.11), dt=30)
    h.frame(("HAL", "CL2"), (-219.43, -6.11), dt=30)
    h.t += 1811
# untouched: a plain 2x2, then a long stare inside it 40 minutes later (a movie, never a piece of the mosaic), and a
# pan 40 frames along (no strays: one patch)
c = Obs("ISS_C23JU_PLAIN2X2")
c.t = 976000000.0
c.lap(pause=2400)
for _ in range(40):
    c.frame(("CL1", "CB2"), (0.1, 0.1), dt=20)
s = Obs("ISS_C23JU_PAN")
s.t = 977000000.0
for k in range(41):
    s.frame(("CL1", "CB2"), (k * 1.0 - 20, 0.0), dt=150)

us = units(a, b, n, h, c, s)

A = us[a.name]
assert kinds(A) == [("mosaic_movie", 163)], kinds(A)
assert A[0]["off"] == set(strays) and A[0]["regrouped"] and om.folder(A[0], "/c").endswith("_0" + om.GROUPING)
# (the piece's three tiles run on into the next lap at the same place: eight laps, every one whole)
assert max(om.lap_of(A[0])) == 8 and om.lap_ends(A[0]) == [19, 39, 59, 82, 102, 122, 142, 162], om.lap_ends(A[0])
assert om.unit_of(strays[0]) is None and om.unit_of(a.rows[-1]["id"])[0] is A[0]
B = us[b.name]
assert kinds(B) == [("mosaic_movie", 99)] and B[0]["off"] == {uv}, kinds(B)
N = us[n.name]
assert kinds(N) == [("mosaic_movie", 56)] and N[0]["regrouped"], kinds(N)
assert om.lap_ends(N[0]) == [8 * k + 7 for k in range(7)], om.lap_ends(N[0])
H = us[h.name]
assert kinds(H) == [("mosaic_movie", 108)] and len(H[0]["off"]) == 12, kinds(H)
C = us[c.name]
assert kinds(C) == [("mosaic", 20), ("movie", 40)], kinds(C)
assert not any(u.get("regrouped") for u in C) and om.folder(C[0], "/c").endswith("ISS_C23JU_PLAIN2X2_N_0")
S = us[s.name]
assert len(S) == 1 and not S[0].get("off") and not S[0].get("regrouped") and len(S[0]["frames"]) == 41, kinds(S)
print("pass grouping ok:", {k: kinds(v) for k, v in us.items()})
