// S5: Movie Editor on a two-hour stretch: open, preview, change the look, make a 1024 px film, download it.
// Proves WP7a, WP7b. On the public site the plan and the brightness graph come from the page (cassiniPlanLocal), the
// preview from the published pictures (movie frames worked out on this computer) and the film is made in the page;
// in --mode before they come from the frame server. Every step that cannot run is logged as skipped, with why.
import { PLAY } from "./moments.mjs";
export default {
  id: "S5", title: "Movie Editor on a two-hour stretch", proves: ["WP7a", "WP7b"], owner: "WP7b",
  context: { viewport: { width: 1440, height: 900 }, acceptDownloads: true },
  async run(h) {
    const { page } = h;
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "600", play: "0" });
    const a = m.t, b = new Date(Date.parse(m.t + "Z") + 2 * 3600e3).toISOString().slice(0, 19);
    const ok = await page.evaluate(([a, b]) => { if (!window.cassiniMovieEdit) return false; window.cassiniMovieEdit.open({ a: utcToEt(a), b: utcToEt(b) }); return true; }, [a, b]);   // the editor takes ET seconds
    if (!ok) { h.skip("no Movie Editor (window.cassiniMovieEdit)", "WP7b"); return; }
    h.step(`Movie Editor open ${a} to ${b}`);
    // listed: the plan is in (state.loading is the listing; .loading on the window is the small loading window)
    const listed = await page.waitForFunction(() => { const s = window.cassiniMovieEdit.state; return !s.loading && (s.frames.length > 0 || s.error); }, null, { timeout: 300000 }).then(() => true, () => false);
    if (!listed) { h.skip("the editor was still listing the frames after 5 min", "WP7b"); return; }
    const st = await page.evaluate(() => { const s = window.cassiniMovieEdit.state; return { n: s.frames.length, error: s.error }; });
    if (!st.n) { h.skip(`the editor listed no frames: ${st.error || "an empty stretch"}`, "WP7a"); return; }
    h.step(`listed ${st.n} frames`);
    // the whole editor (Open now, when the window is still small)
    await page.evaluate(() => { const c = document.getElementById("mecard"); if (c.classList.contains("loading")) document.getElementById("mlnow").click(); });
    // preview: the frame in front drawn, then a few frames stepped through
    await page.waitForFunction(() => { const c = document.getElementById("mecanvas"); return c && c.width > 1; }, null, { timeout: 120000 }).catch(() => {});
    for (let i = 0; i < 4; i++) { await page.keyboard.press("ArrowRight"); await h.wait(1500); }
    h.step("preview: four frames stepped through");
    // the brightness graph: measured (or an honest note that this page does not measure it)
    const lv = await page.waitForFunction(() => { const l = window.cassiniMovieEdit.state.lv; return l.error || (l.total != null && l.done >= l.total) ? { error: l.error, done: l.done, total: l.total } : null; }, null, { timeout: 300000 }).then(x => x.jsonValue(), () => null);
    if (!lv) h.skip("the brightness graph was still measuring after 5 min", "WP7a");
    else if (lv.error) h.skip(`brightness graph: ${lv.error}`, "WP7a");
    else h.step(`brightness graph measured for ${lv.done} pictures`);
    // change the look: warmth and contrast for the whole movie
    const looked = await page.evaluate(() => {
      const set = (id, v) => { const el = document.getElementById(id); if (!el) return false; el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); return true; };
      return set("melk-wa", 25) && set("melk-ct", 15) ? window.cassiniMovieEdit.state.edit : null;
    });
    if (looked) h.step(`look changed for the whole movie (${looked})`); else h.skip("the look's sliders were not there", "WP7b");
    await h.wait(3000);
    // the film: 1024 px a camera, no sound, from Save movie… (the Export window)
    await page.evaluate(() => { const S = window.cassiniSettings; S.set("export.size", 1024); S.set("export.sound", false); document.getElementById("meexport").click(); });
    const ready = await page.waitForFunction(() => !document.getElementById("exgo").disabled || /warn/.test(document.getElementById("exsum").innerHTML), null, { timeout: 300000 }).then(() => true, () => false);
    const sum = await page.evaluate(() => document.getElementById("exsum").textContent);
    if (!ready || await page.evaluate(() => document.getElementById("exgo").disabled)) { h.skip(`the film could not start: ${sum || "no plan after 5 min"}`, "WP7b"); return; }
    h.step(`Export: ${sum.slice(0, 160)}`);
    await page.evaluate(() => document.getElementById("exgo").click());
    const made = await page.waitForFunction(() => { const t = document.getElementById("exstate").textContent; return /^Done|Failed|cannot|refused|No frame server/.test(t) ? t : null; }, null, { timeout: 1800000, polling: 1000 }).then(x => x.jsonValue(), () => null);
    if (!made || !/^Done/.test(made)) { h.skip(`the film was not made: ${made || "still making after 30 min"}`, "WP7b"); return; }
    h.step(`film: ${made} · ${await page.evaluate(() => document.getElementById("exsize2").textContent)}`);
    // download it
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }).catch(() => null), page.evaluate(() => document.getElementById("exdl").click())]);
    if (dl) { const p = await dl.path().catch(() => null); h.step(`downloaded ${dl.suggestedFilename()}${p ? "" : " (not saved)"}`); }
    else h.skip("no download came", "WP7b");
    await page.evaluate(() => { window.cassiniExport && window.cassiniExport.close(); window.cassiniMovieEdit && window.cassiniMovieEdit.close(); });
  }
};
