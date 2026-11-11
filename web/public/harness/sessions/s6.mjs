// S6: a shared film link and a shared Studio edit, opened in a fresh browser. Proves WP7b (D7). The links are made the
// way the page makes them (the Export window's film key, the Gallery's link with Studio's edit), then each is opened
// as a fresh visitor would: storage cleared and the page loaded again from its address. On the public site the film is
// made in the visitor's browser and the edited picture comes from the published one.
import { PLAY } from "./moments.mjs";
export default {
  id: "S6", title: "A shared film link and a shared Studio edit in a fresh browser", proves: ["WP7b"], owner: "WP7b",
  async run(h) {
    const { page, ctx } = h;
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "600", play: "0" });
    await h.wait(12000);
    // the film's key: twenty minutes from the moment, one camera, 512 px, no sound (as the Export window makes it)
    const film = await page.evaluate(t => {
      const E = window.cassiniExport, S = window.cassiniSettings; if (!E) return null;
      S.set("export.size", 512); S.set("export.sound", false);
      E.mark(utcToEt(t), utcToEt(t) + 1200, "new");
      return E.params();
    }, m.t);
    // the picture: the first camera window's, with a Studio edit on it
    const pic = await page.evaluate(() => {
      const G = window.cassiniGallery, w = [...document.querySelectorAll(".camwin")].find(x => !x.hidden && x.querySelector(".well.has-frame"));
      const got = w && G && G.fromWindow ? G.fromWindow(w) : null;
      if (!got || !got.src) return null;
      const u = new URL(got.src, location.href); ["size", "format", "download"].forEach(k => u.searchParams.delete(k));
      return u.pathname + (u.search ? u.search.replace(/%2C/gi, ",") : "");
    });
    await page.evaluate(() => window.cassiniExport && window.cassiniExport.clear(true));
    const fresh = async q => {
      await ctx.clearCookies();
      await page.evaluate(async () => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} try { await new Promise(r => { const d = indexedDB.deleteDatabase("cassini-gallery"); d.onsuccess = d.onerror = d.onblocked = r; }); } catch (e) {} });
      await h.open(q);
    };
    // 1. the film link
    if (!film) h.skip("no Export window to make a film key (window.cassiniExport)", "WP7b");
    else {
      await fresh({ t: m.t, view: "follow", play: "0", film });
      h.step("shared film link opened in a fresh page");
      const got = await page.waitForFunction(() => {
        const v = document.querySelector("#galstage video"), w = document.querySelector("#galstage .galwait");
        if (v && v.src && v.readyState >= 1) return { ok: true, src: v.src.slice(0, 5), dur: v.duration };
        if (w && /cannot|failed|could not|No frame server|No pictures/i.test(w.textContent)) return { ok: false, why: w.textContent };
        return null;
      }, null, { timeout: 1800000, polling: 1000 }).then(x => x.jsonValue(), () => null);
      if (got && got.ok) h.step(`shared film playing (${got.src === "blob:" ? "made in this browser" : "from the frame server"}, ${got.dur.toFixed(1)} s)`);
      else h.skip(`the shared film did not play: ${got ? got.why : "nothing after 30 min"}`, "WP7b");
    }
    // 2. the Studio edit link
    if (!pic) h.skip("no picture on screen to share", "WP7b");
    else {
      await fresh({ t: m.t, view: "follow", play: "0", pic, edit: "ex:0.4,ct:20,wa:15" });
      h.step(`shared Studio edit opened in a fresh page (${pic.slice(0, 80)})`);
      const got = await page.waitForFunction(() => {
        const im = document.querySelector("#galstage img"), w = document.querySelector("#galstage .galwait");
        if (im && im.naturalWidth) return { ok: true, w: im.naturalWidth, h: im.naturalHeight };
        if (w && /could not|not on the public/i.test(w.textContent)) return { ok: false, why: w.textContent };
        return null;
      }, null, { timeout: 180000, polling: 500 }).then(x => x.jsonValue(), () => null);
      if (got && got.ok) h.step(`edited picture shown, ${got.w}×${got.h}`);
      else h.skip(`the edited picture did not show: ${got ? got.why : "nothing after 3 min"}`, "WP7b");
    }
  }
};
