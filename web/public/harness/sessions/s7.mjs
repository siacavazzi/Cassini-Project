// S7: Studio: open a mosaic, change its looks, export. Proves WP7b. WP7b owns this file.
import { STILL } from "./moments.mjs";
export default {
  id: "S7", title: "Studio: open a mosaic, change its looks, export", proves: ["WP7b"], owner: "WP7b",
  async run(h) {
    const { page } = h;
    const m = await h.moment(STILL);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
    await h.wait(15000);
    const opened = await page.evaluate(() => {
      const img = [...document.querySelectorAll(".camwin .well img")].find(i => i.naturalWidth && i.offsetParent);
      if (!img || !window.cassiniStudio) return false;
      window.cassiniStudio.open({ kind: "picture", url: img.dataset.src || img.src });
      return true;
    });
    if (!opened) { h.skip("no picture or no Studio (window.cassiniStudio)", "WP7b"); return; }
    h.step("Studio open on a camera picture");
    await h.wait(15000);
    h.skip("change its looks and export: scripted by WP7b", "WP7b");
    await page.evaluate(() => window.cassiniStudio && window.cassiniStudio.close());
  }
};
