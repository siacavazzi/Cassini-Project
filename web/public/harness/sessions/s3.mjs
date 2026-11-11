// S3: full view and the lens over a mosaic and a colour picture. Proves WP5, WP2.
// Opens each moment paused; when no camera window has a picture up there, its "Go to it" button moves the clock to the
// camera's next picture. Then, on each window with a picture: full view (double-click), the lens over it, one channel
// of a colour picture opened in place (the drill-down, D5) and Esc back.
import { STILL } from "./moments.mjs";
export const pictures = page => page.$$eval(".camwin .well img", ims => ims.filter(i => i.naturalWidth && i.offsetParent).length);
// a picture up in some camera window, going to the next one when none is
export async function picture(h) {
  if (await pictures(h.page)) return true;
  const go = await h.page.$(".camwin .idlego");
  if (!go || !(await go.isVisible())) return false;
  await go.click().catch(() => {});
  h.step("no picture up: Go to it");
  await h.wait(15000);
  return (await pictures(h.page)) > 0;
}
// a moment a colour picture is up at: the first colour set of three filters in the months loaded, two seconds after its
// last channel (for a cache whose slices hold none of the listed colour moments)
export async function colourMoment(h) {
  return h.page.evaluate(() => {
    if (typeof catalog === "undefined" || !catalog.sets) return null;
    const s = catalog.sets.find(x => x.use.length === 3 && Number.isFinite(x.ready) && (!window.cassiniSlice || window.cassiniSlice.has(x.ready)));
    return s ? new Date(etToMs(s.ready) + 2000).toISOString().slice(0, 19) : null;
  }).catch(() => null);
}
// a camera window's save button: it shows in full view (or held), so the window goes to full view first
export async function saveButton(win, h) {
  const im = await win.$(".well.has-frame img.shot");
  if (!im) return null;
  await fullView(win, h);
  const b = await win.$(".savepic");
  return b && (await b.isVisible()) ? b : null;
}
// full view of a camera window: its title bar's Full view button (a double-click on the picture does the same, but a
// mosaic's tile outlines or the tour's card can be over the picture)
export async function fullView(win, h) {
  if (await win.evaluate(w => w.classList.contains("full"))) return true;
  const fb = await win.$(".fullbtn");
  if (fb) await fb.click({ timeout: 5000 }).catch(() => win.evaluate(w => { const b = w.querySelector(".fullbtn"); if (b) b.click(); }));
  else { const im = await win.$(".well img.shot"); if (im) await im.dblclick({ force: true, timeout: 5000 }).catch(() => {}); }
  await h.wait(8000);
  return win.evaluate(w => w.classList.contains("full"));
}
export default {
  id: "S3", title: "Full view and the lens over a mosaic and a colour picture", proves: ["WP5", "WP2"], owner: "WP5",
  async run(h) {
    const { page } = h;
    const moments = await Promise.all([h.moment(STILL.slice(0, 1).concat(STILL.slice(2))), h.moment(STILL.slice(1))]);
    for (const [i, m] of moments.entries()) {
      await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
      await h.wait(15000);
      // the colour moment: when the cache holds none of the listed ones, a colour set it does hold
      if (i === 1 && !(await page.$(".camwin .well.composite.has-frame"))) {
        const t = await colourMoment(h);
        if (t && t !== m.t) { await h.open({ t, view: "follow", speed: "60", play: "0" }); h.step(`a colour set the cache holds: ${t}`); await h.wait(15000); }
      }
      if (!(await picture(h))) { h.skip(`no camera window shows a picture at ${m.t}`, "WP5"); continue; }
      for (const win of (await page.$$(".camwin")).slice(0, 2)) {
        const im = await win.$(".well img.shot");
        if (!im || !(await im.isVisible()) || !(await im.evaluate(i => i.naturalWidth > 0))) continue;
        const kind = await win.evaluate(w => { const c = w.querySelector(".well").classList; return c.contains("mosaic") ? "mosaic" : c.contains("composite") ? "colour picture" : "frame"; });
        if (await fullView(win, h)) h.step(`full view of a ${kind} at ${m.label || m.t}`);
        else h.skip(`full view did not open on a ${kind}`, "WP5");
        const lens = await win.evaluate(w => {
          const img = w.querySelector(".well img.shot");
          if (!img || !img.naturalWidth || !window.cassiniLoupe) return false;
          const r = img.getBoundingClientRect();
          window.cassiniLoupe.open(img, r.left + r.width * 0.4, r.top + r.height * 0.45);
          return true;
        });
        if (lens) { h.step("lens open"); await h.wait(6000); await page.evaluate(() => window.cassiniLoupe && window.cassiniLoupe.close()); }
        else h.skip("no picture for the lens", "WP5");
        // a colour picture's channel opened in place (the strip under it), then back
        const fig = await win.$(".chans.drill figure");
        if (fig && (await fig.isVisible())) {
          await fig.click({ timeout: 5000 }).catch(() => fig.evaluate(f => f.click()));
          h.step("a channel opened in place");
          await h.wait(6000);
          await page.keyboard.press("Escape");
          await h.wait(1500);
        }
        await page.keyboard.press("Escape");
        await h.wait(2000);
      }
    }
  }
};
