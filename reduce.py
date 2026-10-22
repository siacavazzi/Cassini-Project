import json, sys, numpy as np, pandas as pd
D = sys.argv[1]; O = D + "/out/"
PPI = "https://pds-ppi.igpp.ucla.edu/data/"
def iso(t): return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
def doy(s): return pd.to_datetime(s.str.replace(r"^(\d{4})-(\d{3})T", lambda m: m.group(1) + "-" + m.group(2) + "T", regex=True), format="%Y-%jT%H:%M:%S.%f")
def binned(t, v, t0, t1, n=400):
    edges = pd.date_range(t0, t1, periods=n + 1); idx = np.searchsorted(edges.values, t.values, side="right") - 1
    ok = (idx >= 0) & (idx < n); s = pd.Series(np.asarray(v)[ok]).groupby(idx[ok]).mean()
    mid = edges[:-1] + (edges[1] - edges[0]) / 2
    return [[iso(mid[i]), float(f"{x:.6g}")] for i, x in s.items() if np.isfinite(x)]
# ---------- INMS ----------
fs = ["201725809_L1A_06.CSV", "201725810_L1A_06.CSV"]
d = pd.concat([pd.read_csv(f"{D}/{f}", skiprows=[1, 2], low_memory=False) for f in fs])
d["t"] = doy(d.sclk); t1 = d.t.max(); t0 = t1 - pd.Timedelta(minutes=60)
d = d[d.t >= t0]
ser = {}
for m, name in [(2, "H2_mass2"), (4, "He_mass4"), (16, "CH4_mass16"), (18, "H2O_mass18"), (28, "N2_CO_C2H4_mass28"), (44, "CO2_C3H8_mass44"), (3, "HD_H3_mass3"), (15, "CH3_mass15"), (17, "OH_NH3_mass17")]:
    g = d[d.mass_per_charge == m]; ser[name] = binned(g.t, g.c1rate, t0, t1)
    if m in (2, 4, 16, 18, 28): ser[name + "_det2"] = binned(g.t, g.c2rate, t0, t1)
g = d.groupby("cyc_num") if False else None
ser["altitude_km"] = binned(d.t, d.alt_t, t0, t1)
last = iso(t1)
json.dump({"source": [PPI + "CO-S-INMS-3-L1A-U-V2.0/DATA/2017/244_273_SEP/258/" + f for f in fs], "dataset": "CO-S-INMS-3-L1A-U-V2.0",
  "time": "UTC (spacecraft event time)", "instrument": "INMS closed source neutral (csn) mode, detector 1 count rate per mass",
  "last_sample": last, "window": [iso(t0), last], "bins": "400 equal bins over the window, mean of samples in each bin; empty bins dropped",
  "series": ser, "units": {k: ("km (alt_t, INMS file's altitude above Saturn)" if k == "altitude_km" else "counts/s, detector 2 (c2rate, low gain), uncalibrated" if k.endswith("_det2") else "counts/s, detector 1 (c1rate, high gain), uncalibrated, not density") for k in ser},
  "note": "Detector 1 saturates as the air thickens: from about 10:31 its rate drops to 0 while detector 2 (roughly 1/2000 the gain at the highest rates; no clean constant ratio) keeps counting. Use *_det2 for the last minute."},
  open(O + "finale_inms.json", "w"), separators=(",", ":"))
print("INMS", last, {k: len(v) for k, v in ser.items()})
# ---------- MAG ----------
m = pd.read_csv(f"{D}/17258_FGM_KRTP.TAB", sep=r"\s+", header=None, names=["t", "Br", "Bth", "Bph"])
m["t"] = pd.to_datetime(m.t); t1 = m.t.max(); t0 = t1 - pd.Timedelta(minutes=60); m = m[m.t >= t0]
m["B"] = np.sqrt(m.Br ** 2 + m.Bth ** 2 + m.Bph ** 2)
ser = {k: binned(m.t, m[c], t0, t1) for k, c in [("B_magnitude", "B"), ("B_r", "Br"), ("B_theta", "Bth"), ("B_phi", "Bph")]}
ser["B_magnitude_last120s_1s"] = binned(m.t, m.B, t1 - pd.Timedelta(seconds=120), t1, 120)
last = iso(t1)
json.dump({"source": [PPI + "CO-E_SW_J_S-MAG-3-RDR-FULL-RES-V2.0/DATA/2017/244_258_SEP/17258_FGM_KRTP.TAB"], "dataset": "CO-E_SW_J_S-MAG-3-RDR-FULL-RES-V2.0",
  "time": "UTC (spacecraft event time)", "instrument": "MAG fluxgate (FGM), full resolution (~32 samples/s), KRTP coordinates; |B| computed here",
  "last_sample": last, "window": [iso(t0), last], "bins": "400 equal bins (about 9 s) over the window, mean; plus |B| at 1 s for the last 120 s",
  "series": ser, "units": {k: "nT" for k in ser}}, open(O + "finale_mag.json", "w"), separators=(",", ":"))
print("MAG", last, {k: len(v) for k, v in ser.items()})
# ---------- RPWS ----------
rows = [l.split() for l in open(f"{D}/RPWS_KEY__2017258_2.TAB")]
freq = np.array(rows[0][2:], float); E_f, B_f = freq[:73], freq[73:]
t = pd.to_datetime(pd.Series([r[0] for r in rows[1:]]).str.replace(r"^(\d{4})-(\d{3})T", lambda x: x.group(1) + "-" + x.group(2) + "T", regex=True), format="%Y-%jT%H:%M:%S.%f")
v = np.array([r[2:] for r in rows[1:]], float); q = np.array([r[1] for r in rows[1:]], int)
E, B = v[:, :73], v[:, 73:]
t1 = t.max(); keep = (t >= t1 - pd.Timedelta(minutes=60)).values & (q == 0)
t, E, B = t[keep], E[keep], B[keep]
def band(S, f, lo, hi):
    w = (f >= lo) & (f < hi); df = np.gradient(f)[w]
    return (np.nan_to_num(S[:, w]) * df).sum(1)
ser = {"E_power_total": [[iso(a), float(f"{x:.4g}")] for a, x in zip(t, band(E, E_f, 0, 1e9))],
       "E_power_below_1kHz": [[iso(a), float(f"{x:.4g}")] for a, x in zip(t, band(E, E_f, 0, 1e3))],
       "E_power_1kHz_100kHz": [[iso(a), float(f"{x:.4g}")] for a, x in zip(t, band(E, E_f, 1e3, 1e5))],
       "E_power_above_100kHz": [[iso(a), float(f"{x:.4g}")] for a, x in zip(t, band(E, E_f, 1e5, 1e9))],
       "B_power_total": [[iso(a), float(f"{x:.4g}")] for a, x in zip(t, band(B, B_f, 0, 1e9))]}
last = iso(t1)
with np.errstate(divide="ignore"):
    spec = np.where(E > 0, np.round(np.log10(np.where(E > 0, E, 1)), 2), None).tolist()
json.dump({"source": [PPI + "CO-V_E_J_S_SS-RPWS-4-SUMM-KEY60S-V1.0/DATA/KEY_PARAMS/T20172XX/RPWS_KEY__2017258_2.TAB"], "dataset": "CO-V_E_J_S_SS-RPWS-4-SUMM-KEY60S-V1.0",
  "time": "UTC (spacecraft event time, start of each 60 s average)", "instrument": "RPWS key parameters, 60 s averages, quality flag 0 only",
  "last_sample": last, "window": [iso(t.min()), last], "bins": "native 60 s; band powers = spectral density integrated over frequency",
  "series": ser, "units": {k: ("V^2/m^2" if k.startswith("E") else "nT^2") for k in ser},
  "spectrogram": {"times": [iso(a) for a in t], "freq_hz": [float(f"{x:.4g}") for x in E_f], "log10_E_density_V2_m2_Hz": spec}},
  open(O + "finale_rpws.json", "w"), separators=(",", ":"))
print("RPWS", last, {k: len(v) for k, v in ser.items()})
