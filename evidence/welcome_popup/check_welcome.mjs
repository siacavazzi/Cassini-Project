// checks the welcome's first-visit logic: node flow.mjs <url> <outdir>
import { chromium } from "/Users/samiacavazzi/Development/wt-public-wp0/node_modules/playwright/index.mjs";
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

// 4. ?tour=0 and ?welcome=0 keep it away; ?welcome=1 forces it
for (const [qs, want] of [["tour=0", false], ["welcome=0", false]]) {
  const ctx = await browser.newContext(vp); const p = await ctx.newPage();
  await p.goto(url + "&" + qs); ok(`?${qs} keeps the welcome away`, (await opened(p)) === want); await ctx.close();
}
await browser.close();
console.log(results.join("\n"));
