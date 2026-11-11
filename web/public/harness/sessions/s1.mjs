// S1: default play from a Moment for three minutes, both cameras. Proves WP5, WP6.
import { PLAY } from "./moments.mjs";
export default {
  id: "S1", title: "Default play from a Moment, both cameras", proves: ["WP5", "WP6"], owner: "WP5",
  async run(h) {
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "1" });
    h.step(`playing ${m.label || m.t} for ${h.minutes} min`);
    await h.wait(h.minutes * 60000);
  }
};
