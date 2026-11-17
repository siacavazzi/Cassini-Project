"""solve_diff.py MAIN_CACHE FIX_CACHE NAME [FRAME ...]: where each tile of a pass's mosaic view is drawn in two builds'
caches, as a fresh process (a server) lays it out at the frames given (1 the first; default: the middle and the
last), and the solve files each build left. Both caches are read through clones the caller made (a layout may write
into its cache). The moves are in reference pixels (the pass's plan) and in pixels of the 1,024 px view."""
import glob, json, math, os, sys
wt = os.environ["WT"]; sys.path.insert(0, os.path.join(wt, "web", "frames"))
import prebuild, calibration, obs_mosaic as om
main, fix, name = sys.argv[1:4]
u = next(u for u in prebuild.all_passes() if "_".join(map(str, u["key"])) == name)
n = len(u["frames"])
frames = [int(x) for x in sys.argv[4:]] or [max(1, n // 2), n]
print(f"{name}: {n} frames, kind {u.get('kind')}, toss-up {bool(u.get('tossup'))}")
for label, cache in (("main", main), ("fix", fix)):
    folder = glob.glob(os.path.join(cache, "obs-*", name + "*"))
    for f in sorted(glob.glob(os.path.join(folder[0], "*.json"))) if folder else []:
        try:
            d = json.load(open(f))
        except ValueError:
            continue
        if isinstance(d, dict) and "moves" in d:
            moved = {k: v for k, v in d["moves"].items() if any(abs(x) > 0.005 for x in v[:2])}
            pairs = d.get("pairs", {})
            used = sum(isinstance(v, dict) for v in pairs.values())
            print(f"  {label} {os.path.basename(f)}: solved on {len(d['tiles'])} tiles, {len(moved)} moved, "
                  f"{used} of {len(pairs)} pairs used, kept {d.get('kept')} measured {d.get('measured')}")
            print("     moves:", json.dumps({k: [round(x, 2) for x in v[:2]] for k, v in d["moves"].items()}))
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    for j in frames:
        got = {}
        for label, cache in (("main", main), ("fix", fix)):
            made = om.layout(u, j - 1, cache)
            if not made:
                got[label] = None
                continue
            p, tiles, rect = made[0], made[1], made[2]
            scale = 1024 * p["k"] / (max(rect[2], rect[3]) * p["k"]) if rect[2] and rect[3] else 0.0
            got[label] = ({t["n"]: t for t in tiles if "offset" in t}, rect, 1024 / max(rect[2], rect[3]), made[-1] if isinstance(made[-1], str) else "")
        if not got["main"] or not got["fix"]:
            print(f"frame {j}: no layout in", [k for k, v in got.items() if not v])
            continue
        (ta, ra, sa, na), (tb, rb, sb, nb) = got["main"], got["fix"]
        print(f"frame {j} of {n}: view rect main {[round(x, 1) for x in ra]} fix {[round(x, 1) for x in rb]}; 1,024 px view = {sa:.4f} px a reference px")
        print(f"   names: main {na} | fix {nb}")
        print("   | tile | drawn at, main (ref px) | drawn at, fix | moved by, ref px | moved by, px of the 1,024 view | redrawn (main / fix) | turned (main / fix) |")
        print("   |---|---|---|---|---|---|---|")
        worst = 0.0
        for k in sorted(set(ta) | set(tb)):
            a, b = ta.get(k), tb.get(k)
            if a is None or b is None:
                print(f"   | {k} | {'-' if a is None else 'drawn'} | {'-' if b is None else 'drawn'} | | | | |")
                continue
            ax, ay = a["offset"][0] + a["box"][0], a["offset"][1] + a["box"][1]
            bx, by = b["offset"][0] + b["box"][0], b["offset"][1] + b["box"][1]
            dx, dy = bx - ax, by - ay
            worst = max(worst, math.hypot(dx, dy) * sa)
            print(f"   | {k} | {ax:.2f}, {ay:.2f} | {bx:.2f}, {by:.2f} | {dx:+.2f}, {dy:+.2f} | {dx * sa:+.2f}, {dy * sa:+.2f} | "
                  f"{'yes' if 'pic' in a else 'no'} / {'yes' if 'pic' in b else 'no'} | {a.get('turn', 0) or 0:.3f} / {b.get('turn', 0) or 0:.3f} |")
        print(f"   furthest a tile moves: {worst:.2f} px of the 1,024 px view; box sizes differ: "
              f"{[k for k in ta if k in tb and [round(x, 2) for x in ta[k]['box'][2:]] != [round(x, 2) for x in tb[k]['box'][2:]]]}")
