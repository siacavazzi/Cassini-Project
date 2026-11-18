import sys, subprocess, time, os
from playwright.sync_api import sync_playwright
root = os.path.expanduser("~/cassini-build/denoise/wt/web/cassini-os"); port = 8971
srv = subprocess.Popen([sys.executable, os.path.expanduser("~/cassini-build/denoise/proxy.py"), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
EXE = os.path.expanduser("~/Library/Caches/ms-playwright/chromium-1194/chrome-mac/Chromium.app/Contents/MacOS/Chromium")
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=2)
        pg.on("pageerror", lambda e: print("pageerror", e))
        pg.goto(f"http://127.0.0.1:{port}/index.html?t=2017-06-18T01:20:00&play=0&frames=http://127.0.0.1:9", wait_until="domcontentloaded")
        pg.wait_for_function("!!(window.cassiniStudio && window.cassiniStudio.apply)", timeout=120000)
        pg.wait_for_timeout(6000)
        skip = pg.get_by_role("button", name="Just explore")
        if skip.count(): skip.first.click(); pg.wait_for_timeout(1000)
        pg.evaluate("""async () => { const bl = await (await fetch('/_dn/N1876443795_1.png')).blob();
          window.cassiniStudio.open({ kind: 'picture', blob: bl, edit: 'ex:2,wt:60', item: { title: 'Enceladus plume · N1876443795_1' } }); }""")
        pg.wait_for_timeout(4000)
        for k, v in enumerate(["0", "60"]):
            pg.evaluate("v => { const i = document.querySelector('.sturow[data-k=denoise] input'); i.value = v; i.dispatchEvent(new Event('input')); i.dispatchEvent(new Event('change')); }", v)
            pg.wait_for_timeout(2500)
            pg.screenshot(path=os.path.expanduser(f"~/cassini-build/denoise/ev/ui_{k}.png"))
        print("rows", pg.evaluate("[...document.querySelectorAll('#stuadjust .sturow')].map(r => r.dataset.k).join(',')"))
        print("recipe", pg.evaluate("window.cassiniStudio.encode(window.cassiniStudio.state.p)"))
        b.close()
finally:
    srv.terminate()
