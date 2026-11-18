"""render.py CODE OUT ID[,ID..] ...: each set through CODE's frame_server.composite (the pipeline's still/composite path,
last step sharpen.adaptive_sharpen), saved as PNG + report JSON"""
import sys, os, json
code, out = sys.argv[1], sys.argv[2]
os.environ.setdefault("RENDER_HOME", os.getcwd())
sys.path[:0] = [code + "/web/frames", code]; os.chdir(code)
import frame_server as fs
ds = fs.data_source
if ds.using_zip():
    ds._zip_index()
import sharpen
if os.environ.get("DN"):     # evidence only: a taste option's (from, full, most), or "off"
    if os.environ["DN"] == "off":
        sharpen.DENOISE_MAX = 0.0
    else:
        sharpen.DENOISE_FROM, sharpen.DENOISE_FULL, sharpen.DENOISE_MAX = map(float, os.environ["DN"].split(","))
out = os.path.abspath(os.path.join(os.environ.get("RENDER_HOME", "."), out))
os.makedirs(out, exist_ok=True)
for s in sys.argv[3:]:
    ids = s.split(",")
    try:
        im, rep = fs.composite(ids)
    except Exception as e:  # noqa
        print("FAIL", s, repr(e)); continue
    name = "_".join(ids)
    im.save(os.path.join(out, name + ".png"))
    json.dump({k: v for k, v in rep.items() if k != "hdr"}, open(os.path.join(out, name + ".json"), "w"), default=str)
    print("ok", name, rep.get("sharpen"), flush=True)
