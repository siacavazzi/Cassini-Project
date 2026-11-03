"""PR12 (tile placement): a mosaic leaves out a tile the camera saturated over nearly all of what is lit in it
(obs_mosaic._silhouette, SATURATED_LIT), as it leaves out one saturated all over: it holds only the body's outline
drawn white, which on Iapetus ISS_049IA_REGMAPTRL001 stood ~250 px out in the sky as a second limb. Tile reports as
the Mac Mini's cache has them (N1568160488_2 and N1568160638_2 left out; the other tiles of the pass kept).
Run: python web/test_mosaic_silhouette.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

box = {"offset": [-1741.0, 311.0], "box": [-663, -662, 1323, 1324], "outline": [[0, 0]] * 4}
ghost = dict(box, n=69, id="N1568160488_2", filter="CL1/CL2", saturated=0.4035, lit=0.4054, lost=0.002)
ghost2 = dict(box, n=70, id="N1568160638_2", filter="CL1/CL2", saturated=0.4022, lit=0.4049)
surface = dict(box, n=57, id="N1568159640_2", filter="CL1/CL2")                      # nothing saturated
arc = dict(box, n=3, id="N1", filter="CL1/CL2", saturated=0.09, lit=0.3)            # a ring arc, a third saturated
speck = dict(box, n=4, id="N2", filter="CL1/CL2", saturated=0.01, lit=0.011)        # a star, under OVER_LEAST
unplaced = {"n": 68, "id": "N1568160367_2", "filter": "CL1/CL2", "saturated": 0.9674,
            "why": "saturated all over (97%): left out of the mosaic"}
for t in (ghost, ghost2):
    out = om._silhouette(t)
    assert "offset" not in out and "box" not in out and "outline" not in out and "left out" in out["why"], out
    assert out["id"] == t["id"] and out["saturated"] == t["saturated"]
    print(t["id"], "->", out["why"])
for t in (surface, arc, speck, unplaced):
    assert om._silhouette(t) is t, t
print("mosaic silhouette: ok")
