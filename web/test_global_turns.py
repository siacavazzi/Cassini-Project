"""obs_mosaic.global_places with turns (CASSINI_GLOBAL_TURNS=1) on test_panel_register.py's scene with one pointing's
content turned 0.4 degrees as SPICE's twist would leave it: the solve turns it back (against the others), and the
pair_turn measure finds a turn made with cv2's own convention.
Run: python web/test_global_turns.py"""
import os
import sys

os.environ["CASSINI_GLOBAL_PANELS"] = "1"
os.environ["CASSINI_GLOBAL_TURNS"] = "1"
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "test_panel_register.py")).read()
scene = src[:src.index("cache = tempfile.mkdtemp()")].replace('os.environ["CASSINI_GLOBAL_PANELS"] = "0"', "")
g = {"__file__": os.path.join(here, "test_panel_register.py"), "__name__": "scene"}
exec(compile(scene, "test_panel_register_scene", "exec"), g)
om, tempfile, np, cv2, Image = g["om"], g["tempfile"], g["np"], g["cv2"], g["Image"]
reports, plan_, err, tiles_in, u, p = g["reports"], g["plan_"], g["err"], g["tiles_in"], g["u"], g["p"]
assert om.GLOBAL_TURNS

TURN = 0.4
cache = tempfile.mkdtemp()
td = tiles_in(cache)
# pointing 2's tiles (index 2) turned about the frame's middle, as a twist SPICE has off would draw it
im = np.asarray(Image.open(f"{td}/2.png").convert("RGBA"))
h, w = im.shape[:2]
m = cv2.getRotationMatrix2D((w / 2 - 0.5, h / 2 - 0.5), TURN, 1.0)
Image.fromarray(cv2.warpAffine(im, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)).save(f"{td}/2.png")
moved = om.panel_places(u, cache, p, reports)
turns = {n: (v[2] if len(v) > 2 else 0.0) for n, v in moved.items()}
rel = turns.get(2, 0.0) - np.median([turns.get(n, 0.0) for n in (0, 1, 3)])
print("turns", turns, "pointing 2 against the others", round(rel, 3))
assert abs(rel + TURN) < 0.1, rel
print("global turns: ok")
