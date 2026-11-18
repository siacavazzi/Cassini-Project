// Ambient mode before a camera's first picture (the start of the mission): the page must keep running.
// It used to throw in the camera windows' update (a held window with no body and no picture named a body that was not
// there), which stopped the frame loop: the clock froze and the page was dead until reload.
//   npm i playwright-core
//   node ambient_no_picture.cjs BASE_URL [OUT.png]     exits 1 on a page error or a stopped clock
//   CHANNEL=chrome  use the installed Google Chrome; SOFTWARE=1  SwiftShader (cloud containers)
const { chromium } = require("playwright-core");
const [base, shot] = process.argv.slice(2), env = process.env;
(async () => {
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, args });
  const page = await (await br.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
  const errors = [];
  page.on("pageerror", e => errors.push((e.stack || e.message).split("\n").slice(0, 3).join(" <- ")));
  // an hour after the data begins, long before the first picture, a minute of mission time a second
  await page.goto(`${base.replace(/\/$/, "")}/?t=1997-10-15T10:30:00&ambient=60&welcome=0&tour=0`);
  await page.waitForFunction(() => typeof coverage !== "undefined" && coverage[1] && typeof tracks !== "undefined" && tracks.CASSINI && document.getElementById("loading").hidden, null, { timeout: 180000, polling: 200 });
  await page.waitForTimeout(5000);
  const a = await page.evaluate(() => ({ et: state.et, ambient: !!(window.cassiniAmbient && cassiniAmbient.on) }));
  await page.waitForTimeout(3000);
  const b = await page.evaluate(() => ({ et: state.et, utc: new Date(etToMs(state.et)).toISOString() }));
  if (shot) await page.screenshot({ path: shot });
  const moved = b.et - a.et, ok = a.ambient && !errors.length && moved > 60;
  console.log(JSON.stringify({ ambient: a.ambient, clockMovedSecondsIn3s: +moved.toFixed(1), clock: b.utc, pageErrors: errors, ok }, null, 1));
  await br.close();
  process.exit(ok ? 0 : 1);
})();
