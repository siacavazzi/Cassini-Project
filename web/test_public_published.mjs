// "Ask only what is published" (docs/public-site, WP5 #430): with the public switch on, a camera window asks the movie
// route for a frame only once its pass's steady table says the pre-build made a movie picture of it, and asks an
// exposure= frame only of a pass the page cannot even itself. Both answers come from steady-local.html's
// window.cassiniSteadyLocal (placed, evens), which head-quiet.html's playsMovie and publicMovieUrl read. This holds them
// against the tables a Worker can answer, with fetch standing in for the Worker:
//   - no table published (404): the frame is in no movie pass (policy.json steady_table), so placed is false and evens
//     says nothing (undefined): the window shows the frame itself and asks no exposure= variant;
//   - {"local": false}: a pass the server drew whole: placed true, evens false (its evened frames are published);
//   - a local table: placed true for the frames it places (t.n), false for a frame SPICE could not place; evens true
//     only when the page evens the pass (exposure.local, and for colour a set table);
//   - a table still being made ({"working": true}) or not here yet: undefined, so nothing is asked of the movie route;
//   - each table is asked once, at its canonical address (keys.mjs), whatever the window asks in between;
//   - with the switch off a 404 is not read as "no movie pass" (the private server makes tables on demand).
// Run: node web/test_public_published.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadKeys } from "./public/keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const K = await loadKeys();
const page = fs.readFileSync(path.join(here, "cassini-os", "src", "steady-local.html"), "utf8");
const script = page.slice(page.indexOf("<script>") + 8, page.indexOf("</script>"));
const F = "https://frames.example.org";
const tick = () => new Promise(r => setTimeout(r, 0));

let bad = 0, n = 0;
const check = (what, got, want) => { n++; if (got !== want) { bad++; console.log(`FAIL ${what}: ${got} (want ${want})`); } };

// a page with steady-local loaded and the frames host answering from `tables` (id -> table, or a status number)
function pageWith(pub, tables) {
  const asked = [], posted = [];
  const window = { cassiniPublic: pub, dispatchEvent() {} };
  const g = {
    fetch: async url => {
      asked.push(url);
      const id = new URL(url).pathname.split("/").pop().replace(".steady.json", "");
      const t = tables[id];
      if (t === undefined || typeof t === "number") return { ok: false, status: t || 404, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(t)) };
    },
    Worker: class { postMessage(m) { posted.push(m); } },
    URL: Object.assign(function (...a) { return new URL(...a); }, { createObjectURL: () => "blob:x" }),
    Event: class { constructor(type) { this.type = type; } },
    document: { createElement: () => ({ getContext: () => null }), addEventListener() {} }
  };
  new Function("window", "fetch", "Worker", "URL", "Event", "document", script)(window, g.fetch, g.Worker, g.URL, g.Event, g.document);
  return { L: window.cassiniSteadyLocal, asked, posted };
}

// frame ids: a pass with a local table (A, B placed; C listed but not placed), a pass the server drew, a frame in no pass
const A = "N1537000001_1", B = "N1537000061_1", C = "N1537000121_1", D = "W1537000200_1", E = "N1537000500_1", Wk = "N1537000900_1";
const local = (ex, colour, sets) => ({ local: true, ids: [A, B, C], n: [0, 1], exposure: { local: ex }, colour, sets });
const TABLES = { [A]: local(true, true, [[0, 1]]), [B]: local(true, true, [[0, 1]]), [C]: local(true, true, [[0, 1]]), [D]: { local: false }, [Wk]: { working: true } };

{
  const { L, asked, posted } = pageWith(true, TABLES);
  for (const id of [A, C, D, E, Wk]) check(`public: placed(${id}) before its table`, L.placed(F, id), undefined);
  check("public: evens(A) before its table", L.evens(F, A), undefined);
  await tick(); await tick(); await tick();
  check("public: placed(A), placed by its pass's table", L.placed(F, A), true);
  check("public: placed(B), the same table", L.placed(F, B), true);
  check("public: placed(C), a frame its table could not place", L.placed(F, C), false);
  check("public: placed(D), a pass the server drew", L.placed(F, D), true);
  check("public: placed(E), no table: in no movie pass", L.placed(F, E), false);
  check("public: placed(Wk), a table still being made", L.placed(F, Wk), undefined);
  check("public: evens(A), the page evens the pass", L.evens(F, A), true);
  check("public: evens(D), a pass the server drew (its exposure= frames are published)", L.evens(F, D), false);
  check("public: evens(E), no table: nothing to say", L.evens(F, E), undefined);
  check("public: the local pass's table goes to the worker under one key", new Set(posted.map(m => m.key)).size, 1);
  // asked again: no new request for a table already answered (A, B share one; D and E answered)
  const before = asked.filter(u => !u.includes(Wk)).length;
  for (let i = 0; i < 3; i++) for (const id of [A, B, C, D, E]) { L.placed(F, id); L.evens(F, id); }
  await tick();
  check("public: no table asked twice", asked.filter(u => !u.includes(Wk)).length, before);
  // every table asked at its canonical address, one the Worker answers
  for (const u of new Set(asked)) {
    const k = K.canonical("GET", u);
    check(`public: ${u.slice(F.length)} is answered (not refused)`, k.refused || "", "");
    check(`public: ${u.slice(F.length)} is canonical`, K.canonical("GET", u).key, k.key);
  }
}
{
  // a colour pass whose sets the table does not have: the server's evened colour frames are the published ones
  const { L } = pageWith(true, { [A]: local(true, true, null) });
  L.evens(F, A); await tick(); await tick();
  check("public: evens(A), colour table without sets", L.evens(F, A), false);
  const { L: L2 } = pageWith(true, { [A]: local(false, false, null) });
  L2.evens(F, A); await tick(); await tick();
  check("public: evens(A), exposure worked out by the server", L2.evens(F, A), false);
}
{
  // switch off: a 404 is not an answer (the private server makes the table on demand), so nothing is decided
  const { L } = pageWith(false, {});
  L.placed(F, E); await tick(); await tick();
  check("switch off: placed(E) after a 404", L.placed(F, E), undefined);
  check("switch off: evens(E) after a 404", L.evens(F, E), undefined);
}
console.log(`${n - bad} of ${n} checks pass`);
process.exit(bad ? 1 : 0);
