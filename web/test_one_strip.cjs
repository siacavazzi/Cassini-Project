// One strip under a camera window: the frames that went into a color picture are tagged with their channel's color in
// the picture strip (no separate filter row while the strip is up), a double click on a strip picture opens it on its
// own (Processed / As taken), and a full camera window holds the Replay window's transport and speed, steps a
// picture with the arrows and the arrow keys, and gives the controls back when it leaves full view.
// node web/test_one_strip.cjs BASE [UTC ...] : BASE a preview server with a built cache. Exits 1 on any failure.
const { chromium } = require("playwright");
const [base, ...given] = process.argv.slice(2);
const moments = given.length ? given : ["2004-02-16T13:27:49", "2005-02-06T13:01:08"];
if (!base) { console.error("usage: node test_one_strip.cjs BASE [UTC ...]"); process.exit(2); }
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let fails = 0;
  const check = (t, what, ok, got) => { console.log(`${ok ? "ok  " : "FAIL"} ${t} ${what}${ok ? "" : ` (${JSON.stringify(got)})`}`); if (!ok) fails++; };
  for (const t of moments) {
    const p = await (await b.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
    p.on("pageerror", e => check(t, "no page error", false, e.message));
    await p.addInitScript(() => { try { localStorage.setItem("cassini-os-settings-v1", JSON.stringify({ "interface.tips": false, "interface.autohide": false })); localStorage.setItem("cassini-welcome", "1"); } catch (e) {} });
    await p.goto(`${base}/?t=${t}Z&play=0&welcome=0&tour=0`, { timeout: 120000 });
    await p.waitForFunction(() => document.getElementById("loading") && document.getElementById("loading").hidden, null, { timeout: 240000 });
    await p.getByText("Skip tour").click({ timeout: 3000 }).catch(() => {});
    await p.waitForLoadState("networkidle", { timeout: 90000 }).catch(() => {});
    await p.waitForTimeout(6000);
    const W = "#imgcard";
    const st = () => p.evaluate(sel => { const w = document.querySelector(sel); return {
      chansShown: !!w.querySelector(".chans") && getComputedStyle(w.querySelector(".chans")).display !== "none",
      tagged: w.querySelectorAll(".filmstrip .thumbs img.chan").length, count: w.querySelector(".fscount").textContent,
      statInRow: !!w.querySelector(".filmstrip .fsrow .capstat"), playIn: document.getElementById("play").closest(".win").id,
      clock: document.getElementById("clock").textContent, tag: w.querySelector(".kindtag").textContent }; }, W);
    let s = await st();
    check(t, "no filter row while the strip is up", !s.chansShown, s);
    check(t, "color channels tagged in the strip", s.tagged > 0, s.tagged);
    check(t, "camera state in the strip's row", s.statInRow, s);
    await p.evaluate(sel => document.querySelector(sel).querySelector(".fullbtn").click(), W);
    await p.waitForTimeout(3000);
    s = await st();
    check(t, "full view holds the transport", s.playIn === "imgcard", s.playIn);
    const before = s.count;
    await p.keyboard.press("ArrowRight"); await p.waitForTimeout(1500);
    s = await st();
    check(t, "arrow key steps a picture", s.count !== before, [before, s.count]);
    const c2 = s.count;
    await p.click(`${W} .pstep[data-d="-1"]`); await p.waitForTimeout(1500);
    s = await st();
    check(t, "picture arrow steps back", s.count !== c2, [c2, s.count]);
    // a double click (two clicks in place) on a tagged picture opens it on its own
    const im = await p.$(`${W} .thumbs img.chan`);
    const r = await im.boundingBox(), x = r.x + r.width / 2, y = r.y + r.height / 2;
    await p.mouse.dblclick(x, y);
    await p.waitForTimeout(4000);
    s = await st();
    check(t, "double click opens the frame on its own", /ON ITS OWN/.test(s.tag), s.tag);
    const sw = await p.$(`${W} .takenseg button[data-taken="1"]`);
    check(t, "opened frame has Processed / As taken", !!sw, null);
    if (sw) { await sw.click({ force: true }); await p.waitForTimeout(3000); s = await st(); check(t, "As taken shows the archive frame", /AS TAKEN/.test(s.tag), s.tag); }
    await p.keyboard.press("Escape"); await p.waitForTimeout(800);
    await p.keyboard.press("Escape"); await p.waitForTimeout(1500);
    s = await st();
    check(t, "leaving full view gives the transport back", s.playIn === "dock", s.playIn);
    await p.context().close();
  }
  await b.close();
  console.log(fails ? `${fails} failed` : "all passed");
  process.exit(fails ? 1 : 0);
})();
