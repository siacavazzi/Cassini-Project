// Checks the picture footprints (view.footprints, updateFootprints in web/replay/index.html) on a real stretch of the
// mission and saves stills of them. Needs the replay data for the year with its pointing (data/attitude).
//   node footprints.cjs ORIGIN OUT [UTC]      ORIGIN like http://127.0.0.1:8765, OUT a folder for the stills
//   UTC defaults to 2017-04-26T08:50:00 (the first Grand Finale dive, the high-resolution WAC strip of Saturn)
//   SOFTWARE=1 SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
// Checks:
//   - off by default: nothing drawn until the setting is turned on
//   - each footprint's middle is where the camera's boresight met the body at that frame (the pointing, Cassini's and
//     the body's positions then, carried to the body's surface as it is now), within 0.01°, for every footprint whose
//     frame is still the last few minutes (the body has hardly turned, so the check is in Cassini's own view)
//   - the count follows the slider, newest first, never a frame after the clock
let pw; try { pw = require("playwright-core"); } catch (e) { pw = require("playwright"); }
const fs = require("fs"), path = require("path");
const [origin, out, utc = "2017-04-26T08:50:00"] = process.argv.slice(2);
const env = process.env;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await pw.chromium.launch({ args });
  const page = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on("pageerror", e => { console.log("PAGEERROR", e.message); process.exitCode = 1; });
  if (env.THREE_DIR) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
      r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  }
  await page.addInitScript(() => { try { localStorage.clear(); localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: 1, tips: {} })); } catch (e) {} });
  await page.goto(`${origin}/?t=${utc}&view=saturn&speed=600&play=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 300000 });
  await page.waitForTimeout(3000);
  const drawn = () => page.evaluate(() => Object.values(fpState.groups).filter(g => g.visible).length);
  ok(!(await page.evaluate(() => cassiniSettings.get("view.footprints"))) && await drawn() === 0, "off by default: no footprints drawn");
  await page.screenshot({ path: path.join(out, "saturn_off.png") });

  await page.evaluate(() => { cassiniSettings.set("view.footprints", true); cassiniSettings.set("view.footprintCount", 200); });
  await page.waitForTimeout(3000);
  const r = await page.evaluate(() => {
    const list = fpState.list, mid = (FP_GRID * FP_GRID - 1) / 2, worst = [];
    for (const f of list) {
      if (state.et - f.et > 600) break;
      // the boresight at the frame: the pointing then, from Cassini then
      const q = attitudeAt(att, f.et, new Float64Array(4)), c = CAM_TO_BODY[f.cam], qc = new Float64Array(4);
      qmul([c[0], -c[1], -c[2], -c[3]], q, qc, 0);
      const bore = q2rows(qc)[2];
      // the footprint's middle, body-fixed -> J2000 at the frame, from Cassini at the frame
      const B = iauMatrix(bodies[f.body], f.et), p = f.pts.subarray(3 * mid, 3 * mid + 3);
      const pc = positionAt(tracks.CASSINI, f.et, v3()), pb = positionAt(tracks[f.body], f.et, v3());
      const w = [0, 1, 2].map(k => pb[k] - pc[k] + KM * (p[0] * B[0][k] + p[1] * B[1][k] + p[2] * B[2][k]));
      const ang = Math.acos(Math.min(1, dot(norm(w), bore))) * 180 / Math.PI;
      // and where the same point is drawn now: the group's transform without its lift, from Cassini now
      const g = fpState.groups[f.body], lift = g.scale.x / enlargeOf(f.body);
      const v = new THREE.Vector3(p[0], p[1], p[2]).applyQuaternion(g.quaternion).multiplyScalar(g.scale.x / lift).add(g.position);
      const Bn = iauMatrix(bodies[f.body], state.et), pbn = positionAt(tracks[f.body], state.et, v3());
      const wn = [0, 1, 2].map(k => pbn[k] + KM * (p[0] * Bn[0][k] + p[1] * Bn[1][k] + p[2] * Bn[2][k]));
      const sc = toScene(sub(wn, pos[state.focus], v3()), new THREE.Vector3()).multiplyScalar(1 / KM);
      worst.push({ id: catalog.id[f.k], ang, drawnOffKm: sc.distanceTo(v) * KM });
    }
    const ets = list.map(f => f.et);
    return { n: list.length, worst, newestFirst: ets.every((t, i) => !i || t <= ets[i - 1]), noneAfter: ets.every(t => t <= state.et + 1e-6), bodies: [...new Set(list.map(f => f.body))] };
  });
  console.log(JSON.stringify({ n: r.n, bodies: r.bodies, checked: r.worst.length, worst: r.worst.sort((a, b) => b.ang - a.ang).slice(0, 3) }));
  ok(r.n === 200 && r.newestFirst && r.noneAfter, `200 footprints, newest first, none after the clock (${r.n})`);
  ok(r.worst.length > 0 && r.worst.every(w => w.ang < 0.01), `each recent footprint's middle on its frame's boresight (${r.worst.length} frames, worst ${r.worst.length ? r.worst[0].ang.toExponential(2) : "-"}°)`);
  ok(r.worst.every(w => w.drawnOffKm < 1), "drawn where the body-fixed point is now (under 1 km)");
  await page.screenshot({ path: path.join(out, "saturn_on.png") });
  // against the camera cone the viewer draws (updateFov, its own code): with the clock on the newest frame, the
  // cone's axis goes through that footprint's middle
  await page.evaluate(() => { cassiniSettings.set("view.conesEverywhere", true); state.et = fpState.list[0].et + 0.01; });
  await page.waitForTimeout(1500);
  const cone = await page.evaluate(() => {
    const f = fpState.list[0], g = fpState.groups[f.body], mid = (FP_GRID * FP_GRID - 1) / 2, p = f.pts.subarray(3 * mid, 3 * mid + 3);
    const v = new THREE.Vector3(p[0], p[1], p[2]).applyQuaternion(g.quaternion).multiplyScalar(enlargeOf(f.body)).add(g.position).sub(cassini.position);
    const axis = new THREE.Vector3(0, 0, 1).applyQuaternion(fov.quaternion);
    return { id: catalog.id[f.k], visible: fov.visible, ang: v.angleTo(axis) * 180 / Math.PI, km: v.length() * KM };
  });
  console.log(JSON.stringify(cone));
  ok(cone.visible && cone.ang < 0.01, `the camera cone's axis meets the newest footprint (${cone.id}, ${cone.ang.toExponential(2)}° at ${Math.round(cone.km)} km)`);
  await page.evaluate(() => cassiniSettings.set("view.footprintCount", 20));
  ok(await page.waitForFunction(() => fpState.list.length === 20, null, { timeout: 20000 }).then(() => true, () => false), "the slider sets how many");
  await page.evaluate(() => cassiniSettings.set("view.footprints", false));
  ok(await page.waitForFunction(() => Object.values(fpState.groups).every(g => !g.visible), null, { timeout: 20000 }).then(() => true, () => false), "off again: nothing drawn");
  console.log(await page.evaluate(() => location.href));
  await br.close();
})();
