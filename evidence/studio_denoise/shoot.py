import sys, base64, json, subprocess, time, os
from playwright.sync_api import sync_playwright
root = os.path.expanduser("~/cassini-build/denoise/wt/web/cassini-os")
port = 8971
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
out = os.path.expanduser("~/cassini-build/denoise/ev/gl")
os.makedirs(out, exist_ok=True)
ids = sys.argv[1].split(",")
looks = sys.argv[2].split("|")
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/Users/samiacavazzi/Library/Caches/ms-playwright/chromium-1194/chrome-mac/Chromium.app/Contents/MacOS/Chromium", args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("console", lambda m: m.type == "error" and print("console:", m.text))
        pg.goto(f"http://127.0.0.1:{port}/index.html?t=2017-06-18T01:20:00&play=0&frames=http://127.0.0.1:9", wait_until="domcontentloaded")
        pg.wait_for_function("!!(window.cassiniStudio && window.cassiniStudio.apply)", timeout=120000)
        for i in ids:
            for k, lk in enumerate(looks):
                data = pg.evaluate("""async ([u, e]) => { const bl = await (await fetch(u)).blob(); const j = await window.cassiniStudio.apply(bl, e);
                  const r = new FileReader(); return await new Promise(res => { r.onload = () => res(r.result); r.readAsDataURL(j); }); }""", [f"/_dn/{i}.png", lk])
                open(f"{out}/{i}_{k}.jpg", "wb").write(base64.b64decode(data.split(",", 1)[1]))
                print("ok", i, k, lk)
        b.close()
finally:
    srv.terminate()
