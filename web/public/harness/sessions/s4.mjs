// S4: the save menu: PNG, archive frame, science link. Proves WP5, WP3.
// Opens two paused moments (a colour set the cache holds, so its channels are in the menu, and a moment of single
// frames; a window with no picture goes to its camera's next one), puts each camera window with a picture in full view
// (where its save button is) and uses every entry of its save menu the way a click does. A row whose PNG the page
// makes itself (data-png) is clicked and its download awaited; a link to a file (the archive frame) is asked for as a
// download is (a request like any other); a link to NASA's archive (OPUS, data-external) opens another site in a new
// tab, so it is recorded, not followed.
import { STILL, PLAY } from "./moments.mjs";
import { picture, colourMoment, saveButton } from "./s3.mjs";
const click = el => el.evaluate(x => x.click());   // (a picture's overlays can cover the menu for the pointer)
export default {
  id: "S4", title: "The save menu: PNG, archive frame, science link", proves: ["WP5", "WP3"], owner: "WP5",
  async run(h) {
    const { page } = h;
    const first = await h.moment(STILL);
    await h.open({ t: first.t, view: "follow", speed: "60", play: "0" });
    await h.wait(15000);
    const colour = await colourMoment(h), frames = await h.moment(PLAY);
    for (const t of [colour || first.t, frames.t]) {
      await h.open({ t, view: "follow", speed: "60", play: "0" });
      h.step(`moment ${t}`);
      await h.wait(15000);
      if (!(await picture(h))) { h.skip(`no camera window shows a picture at ${t}`, "WP5"); continue; }
      for (const win of await page.$$(".camwin")) {
        if (!(await win.$(".well.has-frame"))) continue;
        const b = await saveButton(win, h);
        if (!b) { h.skip("no save button on this window's picture", "WP5"); continue; }
        const open = async () => { if (!(await win.$(".savewrap.open"))) { await click(b); await h.wait(1200); } };
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
            await click(a);
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
        await h.wait(500);
        await page.keyboard.press("Escape");   // out of full view
        await h.wait(1500);
      }
    }
  }
};
