// checks the welcome's first-visit logic: node check_welcome.mjs <page url with ?query> <outdir>  (needs playwright installed)
import { chromium } from "playwright";
const [url, out] = process.argv.slice(2);
const browser = await chromium.launch();
const results = [];
const ok = (name, cond) => { results.push(`${cond ? "PASS" : "FAIL"} ${name}`); };
const opened = page => page.waitForFunction(() => window.cassiniWelcome && cassiniWelcome.on, null, { timeout: 60000 }).then(() => true, () => false);
const tourOn = page => page.waitForFunction(() => window.cassiniTutorial && cassiniTutorial.active, null, { timeout: 20000 }).then(() => true, () => false);
const vp = { viewport: { width: 1600, height: 1000 } };

// 1. new visitor: welcome shows, tour does not start on its own; "Take the tour" starts the tour
{ const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url); ok("new visitor sees the welcome", await opened(p));
  ok("tour not running under the welcome", !(await p.evaluate(() => cassiniTutorial.active)));
  await p.click("#welcome .wtour"); ok("Take the tour starts the tour", await tourOn(p));
  await p.waitForTimeout(800); await p.screenshot({ path: `${out}/after-take-tour.png` });
  const ck = (await ctx.cookies()).find(c => c.name === "cassini-welcome");
  ok("cookie set (cassini-welcome=1, ~1 year)", ck && ck.value === "1" && ck.expires * 1000 - Date.now() > 360 * 864e5);
  await p.keyboard.press("Escape");
  await p.reload(); ok("reload: welcome does not show again", !(await opened(p)));
  ok("reload: tour does not start again", !(await p.evaluate(() => cassiniTutorial.active)));
  await ctx.close(); }

// 2. new visitor who picks "Just explore": no tour now, none next visit
{ const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url); await opened(p); await p.click("#welcome [data-w=explore]:not(.wx)");
  await p.waitForTimeout(1500); ok("Just explore: welcome closes", !(await p.evaluate(() => cassiniWelcome.on)));
  ok("Just explore: no tour", !(await tourOn(p)));
  await p.screenshot({ path: `${out}/after-explore.png` });
  await p.reload(); ok("Just explore then reload: nothing pops up", !(await opened(p)) && !(await p.evaluate(() => cassiniTutorial.active)));
  // reopen from the Cassini OS menu
  await p.evaluate(() => document.querySelector('[data-act="welcome"]').click());
  ok("Cassini OS menu > Welcome reopens it", await opened(p));
  await p.keyboard.press("Escape"); await p.waitForTimeout(600);
  ok("Escape closes it", !(await p.evaluate(() => cassiniWelcome.on)));
  // reopen from About
  await p.evaluate(() => cassiniAbout.open("Cassini OS")); await p.waitForTimeout(300);
  await p.screenshot({ path: `${out}/about.png` });
  await p.click('#about [data-act="welcome"]'); ok("About > Show the welcome again reopens it", await opened(p));
  ok("About closed behind it", await p.evaluate(() => document.getElementById("about").hidden));
  await ctx.close(); }

// 3. returning visitor who had finished the old tour: sees the welcome once, not the tour
{ const ctx = await browser.newContext(vp);
  await ctx.addInitScript(() => { if (!sessionStorage.x) { localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: 1, tips: {} })); sessionStorage.x = 1; } });
  const p = await ctx.newPage(); await p.goto(url);
  ok("old tour-seen visitor sees the welcome once", await opened(p));
  await p.click("#welcome .wx"); await p.reload();
  ok("…and not again after closing it", !(await opened(p)));
  await ctx.close(); }

// 5. keys while the welcome is open do not reach the page; Enter presses the focused button
{ const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url); await opened(p); await p.waitForTimeout(300);
  await p.evaluate(() => { window.__k = 0; window.addEventListener("keydown", () => window.__k++); });
  for (const k of ["f", "m", "Meta+]", "Control+[", "ArrowRight", "ArrowLeft"]) await p.keyboard.press(k);
  const st5 = await p.evaluate(() => ({ k: window.__k, on: cassiniWelcome.on, tour: cassiniTutorial.active })); if (st5.k || !st5.on) console.log("detail5", JSON.stringify(st5));
  ok("page shortcuts get no keys while the welcome is open", st5.k === 0 && st5.on);
  await p.keyboard.press("Enter"); ok("Enter on the focused Take the tour starts the tour", await tourOn(p));
  await ctx.close(); }

// 5b. Tab to "Just explore" and Enter: closes, no tour
{ const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url); await opened(p); await p.waitForTimeout(800);
  await p.keyboard.press("Shift+Tab"); const f = await p.evaluate(() => document.activeElement.textContent);
  await p.keyboard.press("Enter"); await p.waitForTimeout(1500);
  ok("Shift+Tab to Just explore, Enter: closes with no tour", f === "Just explore" && !(await p.evaluate(() => cassiniWelcome.on || cassiniTutorial.active)));
  await ctx.close(); }

// 6. a tour started from the menu before the welcome is due is not stopped by it
{ const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url); await p.waitForFunction(() => window.cassiniTutorial, null, { timeout: 60000 });
  await p.evaluate(() => cassiniTutorial.start()); await p.waitForTimeout(9000);
  ok("menu-started tour keeps running, no welcome over it", await p.evaluate(() => cassiniTutorial.active && !cassiniWelcome.on));
  await ctx.close(); }

// 4. ?tour=0 and ?welcome=0 keep it away; ?welcome=1 forces it
for (const [qs, want] of [["tour=0", false], ["welcome=0", false]]) {
  const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url + "&" + qs); ok(`?${qs} keeps the welcome away`, (await opened(p)) === want); await ctx.close();
}
await browser.close();
console.log(results.join("\n"));
