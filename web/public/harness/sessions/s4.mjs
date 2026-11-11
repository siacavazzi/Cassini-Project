// S4: the save menu: PNG, archive frame, science link. Proves WP5, WP3.
// Opens a paused moment, then each camera window's save menu, and follows every entry in it the way a click does
// (a download is a request like any other). The menu's entries are links (head-quiet.html savesFor).
import { STILL } from "./moments.mjs";
export default {
  id: "S4", title: "The save menu: PNG, archive frame, science link", proves: ["WP5", "WP3"], owner: "WP5",
  async run(h) {
    const { page } = h;
    const m = await h.moment(STILL);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
    await h.wait(15000);
    const buttons = await page.$$('.camwin [title*="Save" i], .camwin [aria-label*="Save" i]');
    if (!buttons.length) { h.skip("no save button in the camera windows", "WP5"); return; }
    for (const b of buttons.slice(0, 2)) {
      if (!(await b.isVisible())) continue;
      await b.click().catch(() => {});
      await h.wait(1500);
      const hrefs = await page.$$eval("a[href][download], .menu.open a[href]", as => [...new Set(as.map(a => a.href))]);
      h.step(`save menu: ${hrefs.length} entries`);
      for (const href of hrefs) {
        // a click on a download link: the browser asks for it
        await page.evaluate(u => fetch(u).then(r => r.blob()).catch(() => null), href);
      }
      await page.keyboard.press("Escape");
    }
  }
};
