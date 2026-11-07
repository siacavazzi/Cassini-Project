"""Opens the HDR page PR on :8930 with an HDR screen emulated (CDP) and with SDR, at the 2006-09-15 backlit set; records
which camera pictures were asked with hdr=1 and what came back; screenshots."""
import sys, json, time
from playwright.sync_api import sync_playwright
out = sys.argv[1]
URL = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8930/?t=2006-09-15T09:23:10&view=saturn&play=0"
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    for mode in (sys.argv[2].split(",") if len(sys.argv) > 2 else ("hdr", "sdr", "hdr-off")):
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        cdp = pg.context.new_cdp_session(pg)
        cdp.send("Emulation.setEmulatedMedia", {"features": [{"name": "dynamic-range", "value": "high" if mode != "sdr" else "standard"}]})
        if mode != "sdr":
            # an HDR screen (Chrome's CDP media emulation does not cover dynamic-range)
            pg.add_init_script("const _mm=window.matchMedia.bind(window);window.matchMedia=q=>/dynamic-range:\\s*high/.test(q)?{matches:true,media:q,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}}:_mm(q);")
        if mode == "hdr-off":
            pg.add_init_script("try{const k='cassini-os-settings-v1';const s=JSON.parse(localStorage.getItem(k)||'{}');s['cameras.hdr']='off';localStorage.setItem(k,JSON.stringify(s));}catch(e){}")
        got = []
        pg.on("response", lambda r: got.append([r.url.split('8930')[1][:160], r.status, r.headers.get("content-type"), r.headers.get("x-hdr")]) if any(k in r.url for k in ("/frames/color", "/frames/processed", "/frames/movie/", "/frames/mosaic/")) else None)
        pg.goto(URL, wait_until="domcontentloaded")
        time.sleep(45)
        info = pg.evaluate("""() => ({hdrScreen: matchMedia('(dynamic-range: high)').matches, q: window.cassiniHdr ? window.cassiniHdr(1024) : null,
            limit: getComputedStyle(document.documentElement).getPropertyValue('--hdr-limit'),
            imgLimit: (()=>{const i=document.querySelector('#app img'); return i ? getComputedStyle(i).dynamicRangeLimit : null})()})""")
        pg.screenshot(path=f"{out}/{mode}.png")
        res[mode] = {"info": info, "pictures": got}
        pg.close()
    b.close()
json.dump(res, open(f"{out}/result-{'-'.join(res)}.json", "w"), indent=1)
for m, r in res.items():
    print(m, r["info"], len(r["pictures"]))
    for x in r["pictures"][:6]: print("   ", x)
