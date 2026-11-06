"""ba.py NAME [N] : before (top) over after (bottom), N frames evenly over the run, each labelled with its frame,
filter and what it shows (SET = a held color set, OWN+COLOR = its own picture in the set's color, OWN = gray)"""
import sys, glob, os, json, hashlib
from PIL import Image, ImageDraw
AFT = os.environ.get("AFT", "after")
name = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
def rows(side):
    out = {}
    for l in open(f"{side}/{name}/log.txt").read().splitlines()[1:]:
        p = l.split(" ", 5)
        if len(p) > 4 and p[3] == "ok":
            rep = json.loads(p[5]) if len(p) > 5 and p[5].startswith("{") else {}
            out[p[1]] = (p[2], "OWN+COLOR" if rep.get("tint") else "SET" if rep.get("color") else "OWN")
    return out
A, B = rows(AFT), rows("before")
fa = sorted(glob.glob(f"{AFT}/{name}/[0-9]*.webp")); fb = {os.path.basename(f): f for f in glob.glob(f"before/{name}/[0-9]*.webp")}
pick = [fa[round(i * (len(fa) - 1) / (N - 1))] for i in range(N)]
W = 220; S = Image.new("RGB", (W * N, 2 * W + 60), (34, 34, 34)); d = ImageDraw.Draw(S)
def flat(f):
    im = Image.open(f).convert("RGBA"); bg = Image.new("RGBA", im.size, (0, 0, 0, 255)); bg.alpha_composite(im); return bg.convert("RGB").resize((W, W))
for i, f in enumerate(pick):
    b = os.path.basename(f); fid = b[4:-5]
    if b in fb: S.paste(flat(fb[b]), (i * W, 30))
    S.paste(flat(f), (i * W, W + 58))
    d.text((i * W + 3, 2), f"{fid} {B.get(fid, ('', ''))[0]}", fill=(225, 225, 225))
    d.text((i * W + 3, 15), f"before: {B.get(fid, ('', '?'))[1]}", fill=(255, 150, 130) if B.get(fid, ('', ''))[1] == "SET" else (225, 225, 225))
    d.text((i * W + 3, W + 32), f"after: {A.get(fid, ('', '?'))[1]}", fill=(140, 230, 150))
S.save(f"{name}-before-{AFT}.png")
# distinct pictures in each run
for side in ("before", AFT):
    fs = sorted(glob.glob(f"{side}/{name}/[0-9]*.webp"))
    print(name, side, "frames", len(fs), "distinct pictures", len({hashlib.md5(open(x, "rb").read()).hexdigest() for x in fs}))
