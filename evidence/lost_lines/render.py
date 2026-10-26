# Renders the test pictures the way the frame server makes a processed frame or color composite
# (frame_server.composite: color_image.load_aligned), as PNG with alpha, plus each report. Run it from the repo
# root of the version to render (old, then new) with the live server's CASSINI_* variables set:
# python evidence/lost_lines/render.py IDS_FILE OUTDIR
import os, sys, json
sys.path.insert(0, os.path.join(os.getcwd(), "web", "frames"))
import frame_server as fs

ids_file, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
for line in open(ids_file):
    kind, ids = line.split()
    ids = ids.split(",")
    name = "_".join(ids)
    try:
        im, report = fs.composite(ids)
    except Exception as e:
        report, im = {"error": str(e)}, None
    if im is not None:
        im.save(os.path.join(out, name + ".png"))
    json.dump(dict(report, kind=kind), open(os.path.join(out, name + ".json"), "w"), default=str)
    print(name, kind, report.get("lost_px"), report.get("stacked"))
