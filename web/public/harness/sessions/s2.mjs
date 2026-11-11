// S2: movie mode at high speed through a movie pass and a mosaic movie. Proves WP5.
import { MOVIE } from "./moments.mjs";
export default {
  id: "S2", title: "Movie mode at high speed through a movie pass and a mosaic movie", proves: ["WP5"], owner: "WP5",
  async run(h) {
    const m = await h.moment(MOVIE);
    await h.open({ t: m.t, view: "follow", speed: "3600", play: "1", movie: "1" });
    h.step(`movie mode from ${m.label || m.t} for ${h.minutes} min`);
    await h.wait(h.minutes * 60000);
  }
};
