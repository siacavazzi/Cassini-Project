// S8: phone viewport, default play. Proves WP5.
import { PLAY } from "./moments.mjs";
export default {
  id: "S8", title: "Phone viewport, default play", proves: ["WP5"], owner: "WP5",
  context: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
             userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1" },
  async run(h) {
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "60", play: "1" });
    h.step(`phone, playing ${m.label || m.t} for ${h.minutes} min`);
    await h.wait(h.minutes * 60000);
  }
};
