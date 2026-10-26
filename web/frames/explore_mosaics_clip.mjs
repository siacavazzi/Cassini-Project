// Records exploring a mosaic in Cassini OS (pictures program phase 4): the camera window in full view, a frame outlined
// under the pointer, the arrow keys stepping the outline, Enter opening the frame as in the mosaic, the "On its own"
// switch and back, the arrow key opening the next frame, Esc back to the mosaic. Screenshots and info.json in OUT; with
// VIDEO=1 a .webm of the whole run.
//
//   node web/frames/explore_mosaics_clip.mjs http://127.0.0.1:8829 OUT 2006-09-15T17:06:48 W
//
// Needs the playwright package (NODE_PATH or a node_modules beside it) and a Chromium (CHROME=its path).
import { createRequire } from "module";
import fs from "fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [base, out, t, cam = "N"] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const vp = { width: 1440, height: 900 };
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined, args: ["--use-gl=swiftshader", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({ viewport: vp, ...(process.env.VIDEO ? { recordVideo: { dir: out, size: vp } } : {}) });
const page = await ctx.newPage();
page.on("pageerror", e => console.log("PAGEERROR", e.message));
await page.goto(`${base}/?t=${t}&speed=600&play=0`, { waitUntil: "domcontentloaded", timeout: 120000 });
await page.waitForFunction(() => typeof catalog !== "undefined" && catalog && catalog.byCam, null, { timeout: 240000 });
await page.evaluate(() => { if (state.playing) setPlaying(false); });
const card = `.camwin[data-cam="${cam}"]:not([data-body])`;
const t0 = Date.now();
await page.waitForFunction(c => { const w = document.querySelector(c); return w && w.querySelector(".well").classList.contains("mosaic") && w.querySelector(".shot").naturalWidth; }, card, { timeout: 600000 });
const info = { mosaicAfterS: (Date.now() - t0) / 1000 };
await page.locator(`${card} .fullbtn`).click();
await page.evaluate(() => document.activeElement && document.activeElement.blur());
await page.waitForFunction(c => document.querySelector(c).classList.contains("full") && document.querySelector(`${c} .shot`).naturalWidth > 600, card, { timeout: 600000 }).catch(() => {});
await page.waitForTimeout(2500);
const look = n => page.evaluate(c => ({ tip: document.querySelector(`${c} .tiletip:not([hidden]) b`)?.textContent || null,
  src: document.querySelector(`${c} .shot`).dataset.src, size: [document.querySelector(`${c} .shot`).naturalWidth, document.querySelector(`${c} .shot`).naturalHeight],
  tag: document.querySelector(`${c} .kindtag`).textContent, switch: document.querySelector(`${c} .ownbtn`)?.textContent || null }), card).then(v => (info[n] = v));
const snap = n => page.screenshot({ path: `${out}/${n}.png` });
const loaded = (part, ms = 300000) => page.waitForFunction(([c, p]) => { const s = document.querySelector(`${c} .shot`); return (s.dataset.src || "").includes(p) && s.complete && s.naturalWidth; }, [card, part], { timeout: ms }).catch(() => {});
const box = await page.evaluate(c => { const i = document.querySelector(`${c} .shot`), r = i.getBoundingClientRect(); const s = Math.min(r.width / i.naturalWidth, r.height / i.naturalHeight); const w = i.naturalWidth * s, h = i.naturalHeight * s; return { x: r.left + (r.width - w) / 2, y: r.top + (r.height - h) / 2, w, h }; }, card);
await snap("01_mosaic");
await page.mouse.move(box.x + box.w * 0.25, box.y + box.h * 0.3, { steps: 20 });
await page.mouse.move(box.x + box.w * 0.5, box.y + box.h * 0.5, { steps: 30 });
await page.waitForTimeout(1500); await look("hover"); await snap("02_hover");
for (const [k, n] of [["ArrowRight", "03_right"], ["ArrowRight", "04_right"], ["ArrowDown", "05_down"]]) {
  await page.keyboard.press(k); await page.waitForTimeout(1200); await look(n); await snap(n);
}
await page.keyboard.press("Enter");
await loaded("/p/"); await page.mouse.move(vp.width / 2, vp.height - 4); await page.waitForTimeout(2500);
await look("opened"); await snap("06_opened_as_in_mosaic");
if (await page.locator(`${card} .ownbtn`).count()) {
  await page.locator(`${card} .ownbtn`).click(); await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await loaded("/frames/color.webp"); await loaded("/frames/processed/", 1000); await page.waitForTimeout(2500); await look("onItsOwn"); await snap("07_on_its_own");
  await page.locator(`${card} .ownbtn`).click(); await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await loaded("/p/"); await page.waitForTimeout(2000); await look("backAsInMosaic");
}
await page.keyboard.press("ArrowRight"); await loaded("/p/"); await page.waitForTimeout(2500); await look("next"); await snap("08_next_frame");
await page.keyboard.press("Escape"); await page.waitForTimeout(3000); await look("esc"); await snap("09_back_to_mosaic");
info.link = page.url();
fs.writeFileSync(`${out}/info.json`, JSON.stringify(info, null, 1));
console.log(JSON.stringify(info, null, 1));
await ctx.close(); await browser.close();
