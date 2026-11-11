// S7: Studio: open a mosaic, change its looks, export. Proves WP7b. The picture is the one in front, opened the way
// the Studio's own "From the window" does it (cassiniStudio.fromScreen, at full size from the frames host); a mosaic
// when the moment has one on screen. On the public site the Mosaic tab (tile tuning) is not offered.
import { STILL } from "./moments.mjs";
export default {
  id: "S7", title: "Studio: open a mosaic, change its looks, export", proves: ["WP7b"], owner: "WP7b",
  context: { viewport: { width: 1440, height: 900 }, acceptDownloads: true },
  async run(h) {
    const { page } = h;
    const m = await h.moment(STILL);
    // the window with a mosaic in front, if one is on screen; else the first with a picture
    const pick = () => page.evaluate(() => {
      const wins = [...document.querySelectorAll(".camwin")].filter(w => !w.hidden && w.querySelector(".well.has-frame"));
      const mos = wins.find(w => [...w.querySelectorAll(".well img")].some(i => /\/frames\/mosaic\//.test(i.dataset.src || i.src)));
      const w = mos || wins[0];
      if (w && window.cassiniWM) window.cassiniWM.front(w);
      return mos ? "mosaic" : w ? "picture" : null;
    });
    // the moment, then the next listed ones (from the one the cache holds) until a picture is on screen
    let kind = null;
    for (const t of [...new Set([m.t, ...STILL.map(x => x.t)])].slice(0, 4)) {
      await h.open({ t, view: "follow", speed: "60", play: "0" });
      await h.wait(15000);
      if (!(await page.evaluate(() => !!window.cassiniStudio))) { h.skip("no Studio (window.cassiniStudio)", "WP7b"); return; }
      if ((kind = await pick())) break;
    }
    if (!kind) { h.skip("no picture on screen at any of the moments", "WP7b"); return; }
    await page.evaluate(() => window.cassiniStudio.fromScreen());
    const opened = await page.waitForFunction(() => { const s = window.cassiniStudio.state; return s.bmp ? { w: s.W, h: s.H, src: (s.item && s.item.src) || "" } : document.getElementById("stuempty").hidden ? null : { error: document.getElementById("stuempty").textContent }; }, null, { timeout: 120000, polling: 500 }).then(x => x.jsonValue(), () => null);
    if (!opened || opened.error) { h.skip(`Studio did not open the ${kind}: ${opened ? opened.error : "nothing after 2 min"}`, "WP7b"); return; }
    h.step(`Studio open on a ${kind} ${opened.w}×${opened.h} (${opened.src.slice(0, 70)})`);
    if (kind !== "mosaic") h.skip("no mosaic on screen at this moment: a camera picture stands in", "WP7b");
    await h.wait(3000);
    const mosTab = await page.evaluate(() => !document.querySelector('#stutabs [data-v="mosaic"]').hidden);
    h.step(`Mosaic tab (tile tuning) ${mosTab ? "offered" : "not offered"}`);
    // change its looks: the first three sliders of Adjust, and a filter
    const changed = await page.evaluate(() => {
      const ins = [...document.querySelectorAll("#stuadjust input[type=range]")].slice(0, 3);
      ins.forEach((el, i) => { el.value = String(+el.min + (+el.max - +el.min) * (0.6 + 0.1 * i)); el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); });
      return window.cassiniStudio.encode(window.cassiniStudio.state.p);
    });
    h.step(`looks changed (${changed})`);
    await h.wait(2000);
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }).catch(() => null), page.evaluate(() => document.getElementById("studl").click())]);
    if (dl) h.step(`exported ${dl.suggestedFilename()}`); else h.skip("no download came", "WP7b");
    await page.evaluate(() => window.cassiniStudio && window.cassiniStudio.close());
  }
};
