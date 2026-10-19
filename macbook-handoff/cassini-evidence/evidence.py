import os, sys, time, json
sys.path.insert(0, os.getcwd())
import index_maker as im, color_image as cd
label = sys.argv[1]
orig = im.get_images
times = {}
def pick(r, f):
    if len(r) == 0: return r
    if len(f) == 3:
        return r[r["seconds_1970"] >= 970413901].iloc[:10]
    step = max(1, len(r) // 10)
    return r.iloc[::step].iloc[:10]
def limited(camera, target, delta, filters, start_loc, make_csv=False):
    t = time.time(); r = orig(camera, target, delta, filters, start_loc, make_csv)
    times["search_" + "_".join(filters)] = round(time.time() - t, 2)
    return pick(r, filters) if r is not None else r
im.get_images = limited
for f, mosaic in [(["CL1,CL2"], False), (["RED","BL1"], False), (["RED","GRN","VIO"], True)]:
    folder = "_".join(f).replace(",", "_")
    os.makedirs(f"output/{folder}", exist_ok=True)
    t = time.time()
    try:
        cd.export_sequence("ISSWA", f, "JUPITER", 300, folder, mosaic, 0)
    except Exception as e:
        print("SEQUENCE FAILED", folder, repr(e))
    times["render_" + folder] = round(time.time() - t, 1)
    times["frames_" + folder] = len(os.listdir(f"output/{folder}"))
json.dump(times, open("output/times.json", "w"), indent=1)
print(times)
