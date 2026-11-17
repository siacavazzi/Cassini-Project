#!/usr/bin/env python3
"""twin_survey.py CACHE: in a cache built by main, how many movie pictures are another kept picture to the bit: evened
frames (exposure on) against the frame with no exposure asked, by the gain in their report; planes (color off)
against the color frame, by whether that was drawn grey of the same held frame. Pictures, reports and recovery maps
compared."""
import collections, glob, json, os, sys
root = os.path.join(sys.argv[1], "obs-v119-q95")
ev, pl = collections.Counter(), collections.Counter()
for d in sorted(glob.glob(root + "/*/movie-3/*")):
    for f in glob.glob(d + "/*.webp"):
        if f.endswith(".hdr.webp"):
            continue
        base = os.path.basename(f)
        same = lambda a, b: os.path.exists(a) == os.path.exists(b) and (not os.path.exists(a) or open(a, "rb").read() == open(b, "rb").read())
        if "_e8r8" in base:
            plain = f.replace("_e8r8", "")
            if not os.path.exists(plain):
                continue
            rep, prep = json.load(open(f[:-4] + "json")), json.load(open(plain[:-4] + "json"))
            built = {}
            for k, v in prep.items():
                if k == "centred":
                    built["exposure"] = {"smooth": rep["exposure"]["smooth"], "gain": 1.0}
                built[k] = v
            ev[(rep["exposure"]["gain"] == 1.0, same(f, plain), json.dumps(built) == open(f[:-4] + "json").read(),
                same(f[:-5] + ".hdr.webp", plain[:-5] + ".hdr.webp"))] += 1
        elif "_0_0_c2" in base and "_d0" not in base:
            col = f.replace("_0_0_c2", "_0_1_c2")
            if not os.path.exists(col):
                continue
            rp, rc = json.load(open(f[:-4] + "json")), json.load(open(col[:-4] + "json"))
            grey = not any(k in rc for k in ("color", "ids", "tint", "per_body"))
            pl[(grey and rp.get("held") == rc.get("held"), same(f, col), open(f[:-4] + "json").read() == open(col[:-4] + "json").read(),
                same(f[:-5] + ".hdr.webp", col[:-5] + ".hdr.webp"))] += 1
for name, c, rule in (("evened frames", ev, "gain exactly 1"), ("planes", pl, "color frame drawn grey of the same held frame")):
    n = sum(c.values()); twins = sum(v for k, v in c.items() if k[0])
    ok = sum(v for k, v in c.items() if k[0] and k[1] and k[2] and k[3])
    print(f"{name}: {n} with their other picture kept; {twins} meet the rule ({rule}); of those {ok} have the same picture, "
          f"report and recovery map to the bit; {sum(v for k, v in c.items() if not k[0] and k[1])} more are the same picture without meeting it (drawn as before)")
