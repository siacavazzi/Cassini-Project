// S3: full view and the lens over a mosaic and a colour picture. Proves WP5, WP2.
import { STILL } from "./moments.mjs";
export const pictures = page => page.$$eval(".camwin .well img", ims => ims.filter(i => i.naturalWidth && i.offsetParent).length);
export default {
  id: "S3", title: "Full view and the lens over a mosaic and a colour picture", proves: ["WP5", "WP2"], owner: "WP5",
  async run(h) {
    const { page } = h;
    for (const m of (await Promise.all([h.moment(STILL.slice(0, 1).concat(STILL.slice(2))), h.moment(STILL.slice(1))]))) {
      await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
      await h.wait(15000);
      const wins = await page.$$(".camwin .well img");
      if (!wins.length) { h.skip(`no camera window shows a picture at ${m.t}`, "WP5"); continue; }
      for (const im of wins.slice(0, 2)) {
        if (!(await im.isVisible())) continue;
        await im.dblclick().catch(() => {});   // full view (double-click a picture)
        h.step(`full view at ${m.label || m.t}`);
        await h.wait(8000);
        const lens = await page.evaluate(() => {
          const img = [...document.querySelectorAll(".camwin .well img")].find(i => i.naturalWidth && i.offsetParent);
          if (!img || !window.cassiniLoupe) return false;
          const r = img.getBoundingClientRect();
          window.cassiniLoupe.open(img, r.left + r.width * 0.4, r.top + r.height * 0.45);
          return true;
        });
        if (lens) { h.step("lens open"); await h.wait(6000); await page.evaluate(() => window.cassiniLoupe && window.cassiniLoupe.close()); }
        else h.skip("no picture for the lens", "WP5");
        await page.keyboard.press("Escape");
        await h.wait(2000);
      }
    }
  }
};
