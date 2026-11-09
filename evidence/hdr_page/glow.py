from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.goto("http://127.0.0.1:8930/?t=2006-09-15T09:23:10&view=saturn&play=0", wait_until="domcontentloaded"); pg.wait_for_timeout(8000)
    for v in (100, 40, 0):
        print(v, pg.evaluate(f"""() => {{ cassiniSettings.set('cameras.hdrGlow', {v}); const i=document.createElement('img'); document.getElementById('app').appendChild(i);
          const r=[getComputedStyle(document.documentElement).getPropertyValue('--hdr-limit'), getComputedStyle(i).dynamicRangeLimit]; i.remove(); return r; }}"""))
    print(pg.evaluate("navigator.userAgent.match(/Chrome\\/[0-9]+/)[0]"))
    b.close()
