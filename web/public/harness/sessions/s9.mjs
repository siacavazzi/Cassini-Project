// S9: every visible setting toggled in turn. Proves WP6. Each setting is set to each of its other values (a toggle
// flipped, a choice's every option, a range's far end), held a few seconds while the windows answer, then reset.
import { PLAY } from "./moments.mjs";
export default {
  id: "S9", title: "Every visible setting toggled in turn", proves: ["WP6"], owner: "WP6",
  async run(h) {
    const { page } = h;
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
    await h.wait(10000);
    const defs = await page.evaluate(() => (window.cassiniSettings ? window.cassiniSettings.defined : [])
      .filter(d => d.type !== "action" && !d.hidden).map(d => ({ key: d.key, type: d.type, value: d.value, min: d.min, max: d.max, options: (d.options || []).map(o => o[0]) })));
    if (!defs.length) { h.skip("no settings (window.cassiniSettings)", "WP6"); return; }
    const hidden = await page.evaluate(() => window.cassiniSettings.defined.filter(d => d.hidden).length);
    h.step(`public switch ${await page.evaluate(() => window.cassiniPublic === true) ? "on" : "off"}: ${hidden} settings hidden`);
    for (const d of defs) {
      const values = d.type === "toggle" ? [!d.value] : d.type === "choice" ? d.options.filter(o => o !== d.value)
        : d.type === "range" ? [d.value === d.max ? d.min : d.max] : [];
      for (const v of values) {
        await page.evaluate(([k, v]) => window.cassiniSettings.set(k, v), [d.key, v]);
        await h.wait(2500);
      }
      await page.evaluate(([k, v]) => window.cassiniSettings.set(k, v), [d.key, d.value]);
    }
    h.step(`${defs.length} settings toggled`);
  }
};
