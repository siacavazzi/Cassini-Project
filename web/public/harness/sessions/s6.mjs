// S6: a shared film link and a shared Studio edit, opened in a fresh browser. Proves WP7b. WP7b owns this file: the
// share links are made by the Gallery and Studio it changes. Until then the session opens a moment and records the
// skip, so the before numbers show the session as not yet scripted rather than as clean.
import { PLAY } from "./moments.mjs";
export default {
  id: "S6", title: "A shared film link and a shared Studio edit in a fresh browser", proves: ["WP7b"], owner: "WP7b",
  async run(h) {
    const m = await h.moment(PLAY);
    await h.open({ t: m.t, view: "follow", speed: "600", play: "0" });
    h.skip("open a shared film link and a shared Studio edit: scripted by WP7b", "WP7b");
  }
};
