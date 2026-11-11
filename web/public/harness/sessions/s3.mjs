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
export default {
  id: "S3", title: "Full view and the lens over a mosaic and a colour picture", proves: ["WP5", "WP2"], owner: "WP5",
  async run(h) {
    const { page } = h;
    for (const m of (await Promise.all([h.moment(STILL.slice(0, 1).concat(STILL.slice(2))), h.moment(STILL.slice(1))]))) {
      await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
      await h.wait(15000);
      if (!(await picture(h))) { h.skip(`no camera window shows a picture at ${m.t}`, "WP5"); continue; }
      for (const win of (await page.$$(".camwin")).slice(0, 2)) {
        const im = await win.$(".well img.shot");
        if (!im || !(await im.isVisible()) || !(await im.evaluate(i => i.naturalWidth > 0))) continue;
        const kind = await win.evaluate(w => { const c = w.querySelector(".well").classList; return c.contains("mosaic") ? "mosaic" : c.contains("composite") ? "colour picture" : "frame"; });
        await im.dblclick().catch(() => {});   // full view (double-click a picture)
        h.step(`full view of a ${kind} at ${m.label || m.t}`);
        await h.wait(8000);
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
          await fig.click().catch(() => {});
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
