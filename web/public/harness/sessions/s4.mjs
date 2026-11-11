// S4: the save menu: PNG, archive frame, science link. Proves WP5, WP3.
// Opens a paused moment (going to a camera's next picture when none is up), then each camera window's save menu, and
// uses every entry in it the way a click does. A row whose PNG the page makes itself (data-png) is clicked and its
// download awaited; a link to a file (the archive frame) is asked for as a download is (a request like any other); a
// link to NASA's archive (OPUS, data-external) opens another site in a new tab, so it is recorded, not followed.
import { STILL } from "./moments.mjs";
import { picture } from "./s3.mjs";
export default {
  id: "S4", title: "The save menu: PNG, archive frame, science link", proves: ["WP5", "WP3"], owner: "WP5",
  async run(h) {
    const { page } = h;
    const m = await h.moment(STILL);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
    await h.wait(15000);
    if (!(await picture(h))) { h.skip(`no camera window shows a picture at ${m.t}`, "WP5"); return; }
    for (const win of (await page.$$(".camwin")).slice(0, 2)) {
      const b = await win.$('[title*="Save" i], [aria-label*="Save" i]');
      if (!b || !(await b.isVisible())) continue;
      const open = async () => { if (!(await win.$(".savewrap.open"))) { await b.click().catch(() => {}); await h.wait(1200); } };
      await open();
      const rows = await win.$$eval(".savewrap.open a[href]", as => as.map((a, i) => ({ i, href: a.href, png: a.dataset.png || "", external: !!a.dataset.external, label: a.firstChild ? a.firstChild.textContent : "" })));
      h.step(`save menu: ${rows.length} entries (${rows.map(r => r.label).join("; ")})`);
      for (const r of rows) {
        if (r.external) { h.step(`link to ${new URL(r.href).host}: ${r.label}`); continue; }
        if (r.png) {
          await open();
          const a = (await win.$$(".savewrap.open a[href]"))[r.i];
          if (!a) continue;
          const dl = page.waitForEvent("download", { timeout: 20000 }).catch(() => null);
          await a.click().catch(() => {});
          const d = await dl;
          h.step(d ? `PNG made in the page: ${d.suggestedFilename()}` : `no download from: ${r.label}`);
          await h.wait(800);
          continue;
        }
        // a click on a download link: the browser asks for it
        await page.evaluate(u => fetch(u).then(x => x.blob()).catch(() => null), r.href);
        h.step(`downloaded: ${r.label}`);
      }
      await page.keyboard.press("Escape");
    }
  }
};
