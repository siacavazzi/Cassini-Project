#!/usr/bin/env python3
"""idle_chart.py BEFORE_DIR AFTER_DIR OUT.png [--cap-gb 10]

The footprint over time of two idle frame servers (idle_watch.py's footprint.csv in each folder) on one axis: main
and the fix, each started on an empty cache and sent no request. Writes OUT.png and, beside it, OUT.md: the same
numbers as a table (the footprint at fixed times), for anyone who cannot read the chart."""
import csv, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

before_dir, after_dir, out = sys.argv[1:4]


def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


cap = float(opt("--cap-gb", "10"))
B_NAME, A_NAME = opt("--before-name", "main 02598865"), opt("--after-name", "This branch")
B_END, A_END = opt("--before-end", "still climbing"), opt("--after-end", "idle")
TITLE = opt("--title", "An idle frame server's memory: main against this branch")
SUB = opt("--subtitle", "Each started on an empty cache with the site, then left alone. MacBook Pro, 2026-11-17.")
SHOW_CAP = "--no-cap-line" not in sys.argv
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BEFORE, AFTER = "#2a78d6", "#eb6834"   # categorical slots 1 and 2, validated together (CVD and contrast pass)


def read(folder):
    rows = list(csv.DictReader(open(os.path.join(folder, "footprint.csv"))))
    return [float(r["seconds"]) for r in rows], [float(r["footprint_mb"]) / 1000 for r in rows], [float(r["cpu_seconds"]) for r in rows]


def result(folder):
    try:
        return open(os.path.join(folder, "result.txt")).read().strip()
    except OSError:
        return ""


bt, bf, bc = read(before_dir)
at, af, ac = read(after_dir)
plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})
fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=200)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
ax.plot(at, af, color=AFTER, lw=2, solid_capstyle="round", label=A_NAME)
ax.plot(bt, bf, color=BEFORE, lw=2, solid_capstyle="round", label=B_NAME)
xmax = max(at[-1], bt[-1]) * 1.02
top = max(cap * 1.12, max(bf) * 1.05) if SHOW_CAP else max(max(bf), max(af)) * 1.45
ax.set_xlim(0, xmax); ax.set_ylim(0, top)
if SHOW_CAP:
    ax.axhline(cap, color=INK2, lw=1, ls=(0, (4, 4)))
    ax.text(xmax * 0.995, cap + 0.15, f"{cap:g} GB: the measurement's own limit, the server is stopped here", ha="right", va="bottom",
            color=INK2, fontsize=9.5)
# direct labels at each line's last point (ink, beside a mark of the series colour)
ax.plot([bt[-1]], [bf[-1]], "o", ms=7, color=BEFORE, mec=SURFACE, mew=2)
ax.plot([at[-1]], [af[-1]], "o", ms=7, color=AFTER, mec=SURFACE, mew=2)
right = bt[-1] > xmax * 0.6
if SHOW_CAP:
    ax.annotate(f"{B_NAME}: {bf[-1]:.1f} GB after {bt[-1]:.0f} s, {B_END}", (bt[-1], bf[-1]), xytext=(-10 if right else 10, 10 if right else -4),
                textcoords="offset points", ha="right" if right else "left", va="bottom" if right else "top", color=INK, fontsize=10.5)
else:
    # (a long, wandering line: its label goes in the clear band above the data, not on it)
    ax.text(0.012, 0.955, f"{B_NAME}: {bf[-1]:.1f} GB after {bt[-1]:.0f} s (peak {max(bf):.1f} GB), {B_END}", transform=ax.transAxes,
            ha="left", va="top", color=INK, fontsize=10.5)
aright = at[-1] > xmax * 0.6
ax.annotate(f"{A_NAME}: {af[-1]:.1f} GB, {A_END} (peak {max(af):.1f} GB)", (at[-1], af[-1]),
            xytext=(-8 if aright else 10, (-12 if right and aright else 9) if SHOW_CAP else -14),
            textcoords="offset points", ha="right" if aright else "left", va=("top" if right and aright else "bottom") if SHOW_CAP else "top",
            color=INK, fontsize=10.5)
ax.set_xlabel("seconds since the server started (no request sent)"); ax.set_ylabel("physical footprint, GB")
ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID); ax.tick_params(length=0)
ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.56 if SHOW_CAP else 0.80), frameon=False, fontsize=10.5, handlelength=1.6)
fig.suptitle(TITLE, x=0.065, ha="left", fontsize=14, fontweight="bold", y=0.972)
fig.text(0.065, 0.905, SUB, ha="left", va="center", fontsize=10.5, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.885))
fig.savefig(out, facecolor=SURFACE)


def at_time(ts, fs, t):
    best = None
    for x, f in zip(ts, fs):
        if x <= t:
            best = f
    return best


with open(os.path.splitext(out)[0] + ".md", "w") as fh:
    fh.write(f"| seconds since start | {B_NAME}, GB | {A_NAME}, GB |\n|---|---|---|\n")
    for t in (10, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600):
        b, a = at_time(bt, bf, t) if t <= bt[-1] + 2 else None, at_time(at, af, t) if t <= at[-1] + 2 else None
        if b is None and a is None:
            continue
        fh.write(f"| {t} | {'stopped' if b is None else f'{b:.2f}'} | {'ended' if a is None else f'{a:.2f}'} |\n")
    fh.write(f"\n{B_NAME}: peak {max(bf):.2f} GB, {bc[-1]:.0f} CPU seconds in {bt[-1]:.0f} s; {result(before_dir)}\n\n")
    fh.write(f"{A_NAME}: peak {max(af):.2f} GB, {ac[-1]:.0f} CPU seconds in {at[-1]:.0f} s; {result(after_dir)}\n")
print(open(os.path.splitext(out)[0] + ".md").read())
