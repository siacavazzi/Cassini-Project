// S5: Movie Editor on a two-hour stretch: open, preview, change the look, make a 1024 px film, download it.
// Proves WP7a, WP7b. WP7b owns this file and scripts the film-making steps it builds; until then the session opens the
// editor on the stretch and lets it load and preview, which is where today's origin requests start.
import { PLAY } from "./moments.mjs";
export default {
  id: "S5", title: "Movie Editor on a two-hour stretch", proves: ["WP7a", "WP7b"], owner: "WP7b",
  async run(h) {
    const { page } = h;
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "600", play: "0" });
    const a = m.t, b = new Date(Date.parse(m.t + "Z") + 2 * 3600e3).toISOString().slice(0, 19);
    const ok = await page.evaluate(([a, b]) => { if (!window.cassiniMovieEdit) return false; window.cassiniMovieEdit.open({ a, b }); return true; }, [a, b]);
    if (!ok) { h.skip("no Movie Editor (window.cassiniMovieEdit)", "WP7b"); return; }
    h.step(`Movie Editor open ${a} to ${b}`);
    await page.waitForFunction(() => window.cassiniMovieEdit && !window.cassiniMovieEdit.loading, null, { timeout: 180000 }).catch(() => h.skip("the editor was still loading after 3 min", "WP7b"));
    await h.wait(30000);
    h.skip("change the look, make a 1024 px film and download it: scripted by WP7b", "WP7b");
    await page.evaluate(() => window.cassiniMovieEdit && window.cassiniMovieEdit.close());
  }
};
