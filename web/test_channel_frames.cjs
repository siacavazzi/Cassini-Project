// The filter strip under a camera window: every frame of it that has been taken opens in the window, whatever the
// window is showing (a composite, a movie, a mosaic or a lone frame), and an opened frame or channel switches between
// Processed and As taken (the archive frame, /frames/<ID>.webp).
// node web/test_channel_frames.cjs BASE [UTC ...] : BASE a preview server with a built cache (its site and frames);
// the moments default to color sets the sampler cache holds. Exits 1 when a taken frame does not open or a switch
// does not show the archive frame.
const { chromium } = require("playwright");
const [base, ...given] = process.argv.slice(2);
const moments = given.length ? given : ["1999-06-24T20:27:05", "2000-12-11T22:04:06", "2006-09-08T04:48:07", "2011-02-26T15:45:44", "2017-04-13T08:46:01"];
if (!base) { console.error("usage: node test_channel_frames.cjs BASE [UTC ...]"); process.exit(2); }
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let fails = 0, opened = 0;
  for (const t of moments) {
    const p = await (await b.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
    await p.addInitScript(() => { try { localStorage.setItem("cassini-os-settings-v1", JSON.stringify({ "interface.tips": false, "interface.autohide": false })); localStorage.setItem("cassini-welcome", "1"); } catch (e) {} });
    await p.goto(`${base}/?t=${t}Z&play=0&welcome=0&tour=0`, { timeout: 120000 });
    await p.waitForFunction(() => document.getElementById("loading") && document.getElementById("loading").hidden, null, { timeout: 240000 });
    await p.getByText("Skip tour").click({ timeout: 3000 }).catch(() => {});
    await p.waitForLoadState("networkidle", { timeout: 90000 }).catch(() => {});
    await p.waitForTimeout(6000);
    for (const cam of ["N", "W"]) {
      const W = `.camwin[data-cam="${cam}"]`;
      const n = await p.evaluate(sel => { const w = document.querySelector(sel); return w && !w.closest(".win").hidden && w.querySelector(".chans.on") ? w.querySelectorAll(".chans figure").length : 0; }, W);
      for (let j = 0; j < n; j++) {
        const fig = `${W} .chans figure:nth-of-type(${j + 1})`;
        if (await p.evaluate(sel => document.querySelector(sel).classList.contains("waiting"), fig)) continue;
        const id = await p.evaluate(sel => document.querySelector(sel).dataset.id, fig);
        await p.evaluate(sel => document.querySelector(sel).click(), fig);
        const state = () => p.evaluate(sel => { const w = document.querySelector(sel), s = w.querySelector(".shot");
          return { held: w.closest(".win").dataset.held === "1", src: s.dataset.src || "", w: s.complete ? s.naturalWidth : 0, sw: !!w.querySelector(".takenseg") }; }, W);
        const until = async ok => { for (let i = 0; i < 40; i++) { const s = await state(); if (ok(s)) return s; await p.waitForTimeout(500); } return state(); };
        // the frame itself, or (a composite up) its channel cut from the composite
        const a = await until(s => s.held && s.w > 0 && (s.src.includes(id) || /[?&]channel=/.test(s.src)));
        const name = `${t} ${cam} #${j + 1}`;
        if (!a.held || !a.w || !a.sw || !(a.src.includes(id) || /[?&]channel=/.test(a.src))) { fails++; console.log("FAIL open", name, JSON.stringify(a)); }
        else {
          opened++;
          await p.evaluate(sel => document.querySelector(`${sel} .takenseg button[data-taken="1"]`).click(), W);
          const r = await until(s => s.src.includes(`/frames/${id}.webp`) && s.w > 0);
          if (!r.src.includes(`/frames/${id}.webp`) || !r.w) { fails++; console.log("FAIL as taken", name, JSON.stringify(r)); }
          else console.log("ok", name, a.src.replace(/^https?:\/\/[^/]+/, ""), "->", r.src.replace(/^https?:\/\/[^/]+/, ""));
        }
        await p.evaluate(sel => { const l = document.querySelector(`${sel} .crumbs button[data-lv="live"]`); if (l) l.click(); }, W);
        await p.waitForTimeout(1000);
      }
    }
    await p.context().close();
  }
  await b.close();
  console.log(`${opened} frames opened, ${fails} failures`);
  process.exit(fails || !opened ? 1 : 0);
})();
