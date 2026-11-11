// The public site's canonical keys (web/public/keys.json, policy.json): a line-for-line port of keys.py for the Worker
// (WP4) and the page's public switch (WP5). Both are tested against key_fixtures.json (test_keys.py, test_keys.mjs).
//
//   import { makeKeys } from "./keys.mjs";
//   const K = makeKeys(keysJson, policyJson);       // the two contract files, however the caller loads them
//   K.canonical("GET", "/frames/color.webp?ids=...&size=1024", tags)   -> the same object keys.py's canonical gives
//
//   node web/public/keys.mjs '/frames/movie/N1500060789_2.webp?size=1024'   prints the answer as JSON
//
// makeKeys takes the parsed JSON so the Worker can bundle it (no file system there); loadKeys() reads it from disk in node.

export function makeKeys(KEYS, POLICY) {
  const FRAME_ID = /^[NW]\d{10}_\d+$/;
  const CHARSET = new RegExp(KEYS.value_charset);
  const WHOLE = /^-?\d+$/;
  const ALL_SIZES = KEYS.sizes.all_sizes;
  const ROUTES = POLICY.routes.map(r => ({ ...r, _re: new RegExp(r.pattern) }));
  class Refused extends Error {}

  // name -> first value, as the server's parse_qs reads a query: blank values are as if missing, the first of a
  // repeated name wins. Values are percent-decoded and '+' is a space.
  function parseQuery(query) {
    const out = {};
    for (const part of query ? query.split("&") : []) {
      const i = part.indexOf("=");
      if (i < 0) continue;
      const dec = s => { try { return decodeURIComponent(s.replace(/\+/g, " ")); } catch (e) { return s; } };
      const name = dec(part.slice(0, i)), value = dec(part.slice(i + 1));
      if (value === "" || name in out) continue;
      out[name] = value;
    }
    return out;
  }

  function size(v, spec) {
    const built = spec.built;
    if (v === "full") {
      const full = spec.full;
      if (full === null || full === undefined) throw new Refused("size full is not built for this route");
      if (full === "full") return "full";
      v = String(full);
    }
    let n;
    if (v === undefined || !WHOLE.test(v)) n = spec.default;
    else {
      const asked = parseInt(v, 10);
      n = ALL_SIZES.reduce((best, s) => (Math.abs(s - asked) < Math.abs(best - asked) ? s : best));   // the first of a tie wins
    }
    if (!built.includes(n)) {
      const above = built.filter(b => b >= n);
      n = above.length ? Math.min(...above) : Math.max(...built);
    }
    return String(n);
  }

  function flag(v, spec) {
    let n;
    if (v === undefined) n = spec.default;
    else if (spec.read === "not0") n = v === "0" ? 0 : 1;
    else if (spec.read === "eq1") n = v === "1" ? 1 : 0;
    else n = 1;   // nonempty
    if (spec.allowed && !spec.allowed.includes(n)) throw new Refused(`${n} is not offered on the public site`);
    return String(n);
  }

  function int(v, spec) {
    let n;
    if (v === undefined) n = spec.default;
    else {
      if (!WHOLE.test(v)) throw new Refused("not a whole number");
      n = Math.max(spec.min, Math.min(spec.max, parseInt(v, 10)));
    }
    if (spec.allowed && !spec.allowed.includes(n)) throw new Refused(`${n} is not offered on the public site`);
    return String(n);
  }

  function enumOf(v, spec) {
    v = v === undefined ? spec.default : v;
    if (!spec.allowed.includes(v)) throw new Refused(`${pyRepr(v)} is not offered on the public site`);
    return v;
  }

  function id(v) {
    if (v === undefined) return null;
    if (!FRAME_ID.test(v)) throw new Refused("not a frame id");
    return v;
  }

  function ids(v, spec) {
    if (v === undefined) return null;
    const list = v.split(",").filter(Boolean);
    if (!(spec.min <= list.length && list.length <= spec.max) || !list.every(i => FRAME_ID.test(i)))
      throw new Refused(`takes ${spec.min} to ${spec.max} frame ids`);
    if (spec.same_camera && new Set(list.map(i => i[0])).size > 1) throw new Refused("frame ids from one camera");
    return list.join(",");
  }

  // Python's repr of a short string, so refusal texts match keys.py's word for word
  function pyRepr(s) { return s.includes("'") && !s.includes('"') ? `"${s}"` : `'${s.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`; }

  const READ = { size, flag, int, enum: enumOf, id, ids };

  const dflt = spec => (spec.type === "id" || spec.type === "ids") ? null
    : (spec.default !== undefined && spec.default !== null ? String(spec.default) : null);

  function routeOf(method, path, q) {
    for (const r of ROUTES) {
      if (r.method !== method || !r._re.test(path)) continue;
      const mq = r.match_query || {};
      if (Object.entries(mq).every(([name, want]) => (want === "*" ? name in q : q[name] === want))) return r;
    }
    return null;
  }

  function key(r, path, params, tags) {
    const tag = (tags || {})[r.family] ?? "{tag}";
    const query = Object.keys(params).sort().map(k => `${k}=${params[k]}`).join("&");
    return `${r.family}/${tag}/${path.slice(1)}` + (query ? `~${query}` : "");
  }

  function splitUrl(url) {
    let s = url;
    const m = /^[a-z][a-z0-9+.-]*:\/\/[^/?#]*/i.exec(s);
    if (m) s = s.slice(m[0].length) || "/";
    s = s.split("#")[0];
    const i = s.indexOf("?");
    return i < 0 ? [s, ""] : [s.slice(0, i), s.slice(i + 1)];
  }

  function canonical(method, url, tags) {
    const [path, query] = splitUrl(url);
    const q = parseQuery(query);
    const out = { route: null, store: "refused", refused: null, key: null, fallback: [], params: {}, download: q.download === "1" };
    const r = routeOf(method, path, q);
    if (!r) { out.refused = "route: not a route of the frame server"; return out; }
    out.route = r.id; out.store = r.store;
    if (r.store === "refused") { out.refused = "route: " + (r.why || "not on the public site"); return out; }
    if (r.store === "manifest") out.field = r.field;
    if (r.store === "manifest" || r.store === "worker") return out;
    const g = KEYS.global, specs = r.params || {}, params = {};
    try {
      for (const [name, v] of Object.entries(q)) {
        if (name in g.drop && !(name in specs)) continue;
        if (name in g.default_only && !(name in specs)) {
          if (v !== g.default_only[name]) throw new Refused(`param ${name}: only ${pyRepr(g.default_only[name])} is offered on the public site`);
          continue;
        }
        if (!(name in specs)) throw new Refused(`param ${name}: not a parameter of this route`);
      }
      for (const [name, spec] of Object.entries(specs)) {
        if (spec.type === "drop") continue;
        let v;
        try { v = READ[spec.type](q[name], spec); } catch (e) { if (e instanceof Refused) throw new Refused(`param ${name}: ${e.message}`); throw e; }
        if (v === null) { if (spec.required) throw new Refused(`param ${name}: required`); continue; }
        if (v === dflt(spec) && !spec.keep) continue;
        if (!CHARSET.test(v)) throw new Refused(`param ${name}: characters the public site does not use`);
        params[name] = v;
      }
      if (r.require_one_of && !r.require_one_of.some(n => n in params))
        throw new Refused("param " + r.require_one_of.join("|") + ": one of them is needed");
    } catch (e) {
      if (!(e instanceof Refused)) throw e;
      out.store = "refused"; out.refused = e.message; return out;
    }
    out.params = params;
    const m = r._re.exec(path), groups = {};
    (r.groups || []).forEach((g, i) => { groups[g] = m[i + 1]; });
    if (r.store === "table") {
      const frame = groups.id, t = KEYS.tables, tag = (tags || {}).table ?? "{tag}";
      const fill = { center: params.center ?? "1", color: params.color ?? "0", laps: params.laps ?? "1", w: params.w ?? "0", h: params.h ?? "0", m: "{m}" };
      const part = t.parts[r.part].replace(/\{(\w+)\}/g, (_, k) => fill[k]);
      out.frame = frame; out.part = part;
      out.alias_key = t.alias_key.replace("{tag}", tag).replace("{shard}", frame[0] + frame.slice(1, 6));
      out.part_key = t.part_key.replace("{tag}", tag).replace("{part}", part);
      if (r.zero_size_answer != null && ((params.w ?? "0") === "0" || (params.h ?? "0") === "0")) out.answer = r.zero_size_answer;
      if (r.no_alias_answer != null) out.no_alias_answer = r.no_alias_answer;
      return out;
    }
    out.family = r.family;
    out.key = key(r, path, params, tags);
    for (const fb of r.fallback || []) {
      if (Object.entries(fb.when).every(([k, v]) => params[k] === v)) {
        const p = { ...params, ...(fb.set || {}) };
        for (const k of fb.unset || []) delete p[k];
        out.fallback.push(key(r, path, p, tags));
      }
    }
    if (new TextEncoder().encode(out.key).length > KEYS.max_key_bytes)
      Object.assign(out, { store: "refused", refused: "key: longer than R2 allows", key: null, fallback: [] });
    return out;
  }

  return { canonical, parseQuery, routeOf };
}

// node only: the contract files beside this module
export async function loadKeys() {
  const fs = await import("node:fs"), path = await import("node:path"), url = await import("node:url");
  const here = path.dirname(url.fileURLToPath(import.meta.url));
  const read = f => JSON.parse(fs.readFileSync(path.join(here, f), "utf8"));
  return makeKeys(read("keys.json"), read("policy.json"));
}

if (typeof process !== "undefined" && process.argv && import.meta.url === (await import("node:url")).pathToFileURL(process.argv[1] || "").href) {
  const K = await loadKeys();
  for (const u of process.argv.slice(2)) console.log(JSON.stringify(K.canonical("GET", u), null, 1));
}
