// S1: default play from a Moment, both cameras. Proves WP5, WP6.
// The clock moves in fixed steps rather than in real time, so every run asks for the same stretch the same way, however
// fast the machine or the network: the moment opens paused, then the clock goes forward STEP seconds of mission time
// at a time, as play at 60× would, and each step is held until the page's requests are answered (at most CAP ms).
// minutes × 60 steps cover what that many minutes of play at 60× cover (three hours of mission time by default).
import { PLAY } from "./moments.mjs";
const STEP = 60, QUIET = 400, CAP = 8000;
export default {
  id: "S1", title: "Default play from a Moment, both cameras", proves: ["WP5", "WP6"], owner: "WP5",
  async run(h) {
    const { page } = h;
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "0" });
    const n = Math.round(h.minutes * 60), et0 = await page.evaluate(() => state.et);
    h.step(`stepping from ${m.label || m.t}: ${n} steps of ${STEP} s of mission time`);
    await h.idle(QUIET, 30000);
    let slow = 0;
    for (let i = 1; i <= n; i++) {
      await page.evaluate(et => { state.et = et; }, et0 + i * STEP);
      if (!(await h.idle(QUIET, CAP))) slow++;
    }
    const et1 = await page.evaluate(() => state.et);
    h.step(`stepped ${Math.round(et1 - et0)} s of mission time${slow ? `; ${slow} steps still asking after ${CAP / 1000} s` : ""}`);
  }
};
