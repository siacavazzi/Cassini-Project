// ---------- the Movie Editor's film plan, worked out on this computer (the public site: no frame server) ----------
// A line-for-line port of web/frames/export.py's options, plan (with complete_mosaics, cut, timing, frames,
// boomerang, width, height) and public_plan/source, for picture sizes up to 1024. What the frame server reads from its
// index (reel.load_index: Image_index.csv, the filter sets of sets_passes) and from obs_mosaic (each frame's pass, its
// kind, a toss-up, a mosaic movie's lap ends) the page reads from the replay data's month catalogs (build_data.py
// --groups: each frame's set and pass, the sets' channels and the passes' kinds; ut and tr: the index's second and
// order; raw_target: the index's target name) and, for a mosaic movie's lap ends only, the pass's kind table
// (/frames/mosaic/<ID>.webp?warm=1, obs_mosaic.kind_of). web/test_plan_local.py runs this file in node against
// export.plan on the same data and checks the answers are the same, field for field.
//
//   window.cassiniPlanLocal.plan(options[, tell]) -> Promise of /export/plan.json's answer, or {error}
//     options: the film's query as a plain object of strings (Object.fromEntries(new URLSearchParams(key))), as
//     export.options reads parse_qs; tell(done, total, step): how far it is ("frames"), as /export/plan-progress says
//   window.cassiniPlanLocal.source: where the data comes from (allMonths(): every month catalog, oldest first, each
//     {start, end (unix seconds), key, catalog() -> the month's JSON}; kind(id): the pass kind table of a frame;
//     maxPictures: CASSINI_EXPORT_MAX's cap, 0 for none). Overridable, as the tests and WP7b's stubs do.
// levels-local.js adds .levels (the exposure graph).
(function (root) {
  "use strict";
  // export.py's constants
  const FPS = 30, HOLD_MIN = 1 / FPS, HOLD_MAX = 0.5, TYPICAL = 1 / 8, ONLY = 1.5;
  const SIZES = [512, 768, 1024], FULL = "full", BUCKETS = [1024, 1536, 2048], CAPTION = 48, SKIP_NOTE = 3 * 3600;
  const PICTURES = ["movie", "color", "processed", "raw"];
  const LEVEL_EV = 2.0, EVEN_MOST = 30, CROP_LEAST = 0.05, NUDGE_MOST = 0.5, STEADY_MOST = 0.25;
  const PROGRESS_EVERY = 100;
  // calibration.LOOKS, COLORS, STEPS
  const LOOKS = ["balanced", "classic"], COLORS = ["natural", "raw", "eye", "false"];
  const STEPS = ["stack", "hdr", "fill", "calibrate", "twohz", "twohzsky", "skysmooth", "dark", "darksky", "pairs", "flat",
    "hotpix", "geom", "align", "blend", "level", "surface", "panels"];
  // build_data.py UT_BASE: a row's index second is UT_BASE + ut + floor(et)
  const UT_BASE = 946727930;
  // reel.wavelength's table: filter_calibration.csv's effective wavelengths, nm (test_plan_local.py checks it is the file's)
  const NM = /*NM*/{"ISSNA":{"BL1BL2":441.2,"BL1CB1":540.4,"BL1CB1A":516.6,"BL1CB1B":635.4,"BL1CB2":585.9,"BL1CB3":462.6,"BL1CBB":603.8,"BL1CL2":456.8,"BL1GRN":497.4,"BL1IR1":697.6,"BL1IR3":806.7,"BL1MT1":465.9,"BL1MT2":520.2,"BL1MT3":451.1,"BL1UV3":389.6,"CL1BL2":441.1,"CL1CB1":619.5,"CL1CB1A":602.9,"CL1CB1B":634.5,"CL1CB2":750.5,"CL1CB3":937.9,"CL1CBA":634.6,"CL1CBB":603.0,"CL1CL2":661.2,"CL1GRN":569.3,"CL1IR1":751.0,"CL1IR3":925.9,"CL1MT1":619.0,"CL1MT2":727.4,"CL1MT3":889.2,"CL1UV3":343.1,"HALBL2":586.0,"HALCB1":650.5,"HALCB1A":604.2,"HALCB1B":650.6,"HALCB2":663.5,"HALCB3":656.3,"HALCBA":652.7,"HALCL2":655.6,"HALGRN":648.0,"HALIR1":663.7,"HALIR3":662.5,"HALMT1":623.4,"HALMT2":676.7,"HALMT3":655.0,"HALUV3":603.7,"IR2BL2":871.1,"IR2CB1":730.2,"IR2CB1A":602.9,"IR2CB1B":761.9,"IR2CB2":768.4,"IR2CB3":933.5,"IR2CBA":638.9,"IR2CL2":860.8,"IR2GRN":829.6,"IR2IR1":827.4,"IR2IR3":901.4,"IR2MT1":871.9,"IR2MT2":791.9,"IR2MT3":889.2,"IR2UV3":845.0,"IR4BL2":734.2,"IR4CB1":624.1,"IR4CB1A":602.9,"IR4CB1B":634.6,"IR4CB2":750.6,"IR4CB3":972.9,"IR4CL2":1001.5,"IR4GRN":610.8,"IR4IR1":914.6,"IR4IR3":996.2,"IR4MT1":878.9,"IR4MT2":727.2,"IR4MT3":972.4,"IR4UV3":995.0,"IRP0BL2_B":762.9,"IRP0BL2":830.2,"IRP0CB1_B":615.2,"IRP0CB1":622.9,"IRP0CB1A_B":604.2,"IRP0CB1A":604.4,"IRP0CB1B_B":633.9,"IRP0CB1B":634.6,"IRP0CB2_B":750.5,"IRP0CB2":750.5,"IRP0CB3_B":937.9,"IRP0CB3":937.9,"IRP0CBA":634.7,"IRP0CBB":604.5,"IRP0CL2_B":662.0,"IRP0CL2":741.1,"IRP0GRN_B":612.0,"IRP0GRN":613.9,"IRP0IR1_B":730.2,"IRP0IR1":752.0,"IRP0IR3_B":934.5,"IRP0IR3":926.1,"IRP0MT1_B":618.9,"IRP0MT1":619.0,"IRP0MT2_B":727.4,"IRP0MT2":727.4,"IRP0MT3_B":889.7,"IRP0MT3":889.2,"IRP0UV3_B":853.4,"IRP0UV3":825.7,"P0BL2_B":439.9,"P0BL2":441.2,"P0CB1_B":623.7,"P0CB1":620.1,"P0CB1A_B":603.1,"P0CB1A":602.9,"P0CB1B_B":634.9,"P0CB1B":634.6,"P0CB2_B":750.7,"P0CB2":750.5,"P0CB3_B":738.2,"P0CB3":647.8,"P0CBA":634.7,"P0CBB":603.0,"P0CL2_B":738.3,"P0CL2":636.3,"P0GRN_B":566.5,"P0GRN":569.7,"P0IR1_B":761.1,"P0IR1":737.0,"P0IR3_B":768.5,"P0IR3":734.7,"P0MT1_B":619.2,"P0MT1":618.9,"P0MT2_B":727.5,"P0MT2":727.4,"P0MT3_B":739.3,"P0MT3":633.3,"P0UV3_B":348.0,"P0UV3":345.4,"P120BL2_B":439.9,"P120BL2":441.2,"P120CB1_B":623.7,"P120CB1":620.1,"P120CB1A_B":603.1,"P120CB1A":602.9,"P120CB1B_B":634.9,"P120CB1B":634.6,"P120CB2_B":750.7,"P120CB2":750.5,"P120CB3_B":738.2,"P120CB3":647.8,"P120CBA":634.7,"P120CBB":603.0,"P120CL2_B":738.3,"P120CL2":636.3,"P120GRN_B":566.5,"P120GRN":569.7,"P120IR1_B":761.1,"P120IR1":737.0,"P120IR3_B":768.5,"P120IR3":734.7,"P120MT1_B":619.2,"P120MT1":618.9,"P120MT2_B":727.5,"P120MT2":727.4,"P120MT3_B":739.3,"P120MT3":633.3,"P120UV3_B":348.0,"P120UV3":345.4,"P60BL2_B":439.9,"P60BL2":441.2,"P60CB1_B":623.7,"P60CB1":620.1,"P60CB1A_B":603.1,"P60CB1A":602.9,"P60CB1B_B":634.9,"P60CB1B":634.6,"P60CB2_B":750.7,"P60CB2":750.5,"P60CB3_B":738.2,"P60CB3":647.8,"P60CBA":634.7,"P60CBB":603.0,"P60CL2_B":738.3,"P60CL2":636.3,"P60GRN_B":566.5,"P60GRN":569.7,"P60IR1_B":761.1,"P60IR1":737.0,"P60IR3_B":768.5,"P60IR3":734.7,"P60MT1_B":619.2,"P60MT1":618.9,"P60MT2_B":727.5,"P60MT2":727.4,"P60MT3_B":739.3,"P60MT3":633.3,"P60UV3_B":348.0,"P60UV3":345.4,"REDBL2":629.9,"REDCB1":619.7,"REDCB1A":603.0,"REDCB1B":634.6,"REDCB2":744.3,"REDCB3":649.3,"REDCBA":634.6,"REDCBB":603.1,"REDCL2":650.7,"REDGRN":601.0,"REDIR1":701.9,"REDIR3":695.4,"REDMT1":618.9,"REDMT2":726.6,"REDMT3":646.4,"REDUV3":643.6,"UV1BL2":438.0,"UV1CB1":616.3,"UV1CB1A":601.9,"UV1CB1B":634.3,"UV1CB2":747.4,"UV1CB3":929.6,"UV1CL2":266.7,"UV1GRN":569.2,"UV1IR1":753.2,"UV1IR3":920.1,"UV1MT1":611.5,"UV1MT2":711.2,"UV1MT3":886.3,"UV1UV3":353.8,"UV2BL2":413.9,"UV2CB1":600.4,"UV2CB1A":589.0,"UV2CB1B":634.8,"UV2CB2":720.7,"UV2CB3":903.2,"UV2CL2":306.5,"UV2GRN":560.2,"UV2IR1":767.3,"UV2IR3":919.8,"UV2MT1":524.1,"UV2MT2":669.5,"UV2MT3":862.7,"UV2UV3":317.6},"ISSWA":{"CB2BL1":533.6,"CB2CL2":752.3,"CB2GRN":570.7,"CB2HAL":704.7,"CB2IR1":752.3,"CB2IRP0_B":752.3,"CB2IRP0":752.3,"CB2IRP90_B":752.3,"CB2IRP90":752.3,"CB2RED":747.3,"CB2VIO":670.3,"CB3BL1":485.4,"CB3CL2":938.4,"CB3GRN":579.8,"CB3HAL":708.5,"CB3IR1":817.0,"CB3IRP0_B":938.5,"CB3IRP0":938.6,"CB3IRP90_B":938.5,"CB3IRP90":938.6,"CB3RED":642.8,"CB3VIO":587.4,"CL1BL1":462.0,"CL1CL2":635.0,"CL1GRN":568.6,"CL1HAL":656.4,"CL1IR1":740.5,"CL1IRP0_B":637.1,"CL1IRP0":706.4,"CL1IRP90_B":637.1,"CL1IRP90":706.4,"CL1RED":647.6,"CL1VIO":419.7,"IR2BL1":822.9,"IR2CL2":852.0,"IR2GRN":806.2,"IR2HAL":862.9,"IR2IR1":826.3,"IR2IRP0_B":883.1,"IR2IRP0":852.1,"IR2IRP90_B":883.1,"IR2IRP90":852.1,"IR2RED":718.7,"IR2VIO":863.6,"IR3BL1":907.9,"IR3CL2":914.7,"IR3GRN":907.8,"IR3HAL":764.8,"IR3IR1":783.2,"IR3IRP0_B":925.7,"IR3IRP0":914.7,"IR3IRP90_B":925.7,"IR3IRP90":914.7,"IR3RED":690.2,"IR3VIO":907.4,"IR4BL1":496.3,"IR4CL2":1001.2,"IR4GRN":589.1,"IR4HAL":721.4,"IR4IR1":824.0,"IR4IRP0_B":1000.7,"IR4IRP0":1001.3,"IR4IRP90_B":1000.7,"IR4IRP90":1001.3,"IR4RED":648.3,"IR4VIO":636.5,"IR5BL1":469.2,"IR5CL2":1033.2,"IR5GRN":562.0,"IR5HAL":672.0,"IR5IR1":759.7,"IR5IRP0_B":1034.9,"IR5IRP0":1034.5,"IR5IRP90_B":1034.9,"IR5IRP90":1034.5,"IR5RED":651.3,"IR5VIO":463.7,"MT2BL1":488.1,"MT2CL2":728.6,"MT2GRN":582.4,"MT2HAL":674.1,"MT2IR1":728.4,"MT2IRP0_B":728.7,"MT2IRP0":728.6,"MT2IRP90_B":728.7,"MT2IRP90":728.6,"MT2RED":727.6,"MT2VIO":509.4,"MT3BL1":578.7,"MT3CL2":890.3,"MT3GRN":614.4,"MT3HAL":850.8,"MT3IR1":860.6,"MT3IRP0_B":890.0,"MT3IRP0":890.4,"MT3IRP90_B":890.0,"MT3IRP90":890.4,"MT3RED":656.8,"MT3VIO":775.8}}/*/NM*/;
  const wavelength = (camera, filters) => (NM[camera] && NM[camera][filters]) || 0;

  // ---------- Python's arithmetic ----------
  // round(x, n) for a double: the decimal nearest x's exact value, a tie (x * 2^(n+1) an odd whole number, the only
  // doubles exactly half way) to the even last digit; Number.toFixed rounds a tie away from zero
  function pyRound(x, n = 0) {
    if (!isFinite(x)) return x;
    if (n === 0) { let r = Math.round(x); if (r - x === 0.5 && r % 2 !== 0) r -= 1; return r === 0 ? 0 * Math.sign(x) || 0 : r; }
    const e = x * 2 ** (n + 1);
    if (Number.isInteger(e) && e % 2 !== 0 && Math.abs(x) < 1e15) {
      const h = x * 10 ** n, f = Math.floor(h);
      if (h - f === 0.5) return (f % 2 === 0 ? f : f + 1) / 10 ** n;
    }
    const v = Number(x.toFixed(n));
    return v === 0 ? 0 : v;
  }
  const pyMin = (a, b) => (b < a ? b : a), pyMax = (a, b) => (b > a ? b : a);
  // float(s) as Python reads a string (blanks round it, underscores between digits, inf, nan), else throws
  function pyFloat(s) {
    const t = String(s).trim();
    if (/^[+-]?(inf|infinity)$/i.test(t)) return t[0] === "-" ? -Infinity : Infinity;
    if (/^[+-]?nan$/i.test(t)) return NaN;
    const D = "\\d(?:_?\\d)*";
    if (!new RegExp(`^[+-]?(?:${D}(?:\\.(?:${D})?)?|\\.${D})(?:[eE][+-]?${D})?$`).test(t)) throw new Error(`could not convert string to float: '${s}'`);
    return Number(t.replace(/_/g, ""));
  }
  // int(s) of a string (a whole number), else throws
  function pyIntStr(s) {
    const t = String(s).trim();
    if (!/^[+-]?\d(?:_?\d)*$/.test(t)) throw new Error(`invalid literal for int() with base 10: '${s}'`);
    return parseInt(t.replace(/_/g, ""), 10);
  }
  // int(x) of a float: toward zero; nan and inf throw, as Python's do
  function pyIntF(x) {
    if (!isFinite(x)) throw new Error(isNaN(x) ? "cannot convert float NaN to integer" : "cannot convert float infinity to integer");
    return Math.trunc(x) || 0;
  }
  // an int(s or 0) where s is a query word: int() of the text (a decimal point is an error, as it is in Python)
  const intOr0 = s => (s ? pyIntStr(s) : 0);
  const median = a => { const s = Float64Array.from(a).sort(), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  // searchsorted(t, x, side) over a sorted array
  function searchsorted(t, x, right) {
    let lo = 0, hi = t.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (right ? t[m] <= x : t[m] < x) lo = m + 1; else hi = m; }
    return lo;
  }
  // the order CPython's set of these whole numbers (non-negative, added in this order) iterates in: export.plan's
  // {int(v) for v in set_of[lo:hi]}, whose order decides between two color mixes counted as often (Counter.most_common
  // takes the first counted); setobject.c's set_add_entry, set_table_resize and set_insert_clean
  function pySetOrder(values) {
    const LINEAR_PROBES = 9, PERTURB_SHIFT = 5;
    let size = 8, table = new Array(8).fill(null), fill = 0, used = 0;
    const seen = new Set();
    // the slot a key goes in: its hash's slot, the LINEAR_PROBES after it while they fit, then the perturbed jump
    const slot = (tab, n, key) => {
      const mask = n - 1;
      let i = key % n, perturb = key;
      for (;;) {
        let probes = i + LINEAR_PROBES <= mask ? LINEAR_PROBES : 0, j = i;
        do { if (tab[j] === null) return j; j++; } while (probes--);
        perturb = Math.floor(perturb / 2 ** PERTURB_SHIFT);
        i = (i * 5 + 1 + perturb) % n;
      }
    };
    for (const key of values) {
      if (seen.has(key)) continue;
      seen.add(key);
      table[slot(table, size, key)] = key; fill++; used++;
      if (fill * 5 >= (size - 1) * 3) {
        const minused = used > 50000 ? used * 2 : used * 4;
        let n = 8;
        while (n <= minused) n *= 2;
        const nt = new Array(n).fill(null);
        for (const k of table) if (k !== null) nt[slot(nt, n, k)] = k;
        table = nt; size = n; fill = used;
      }
    }
    return table.filter(k => k !== null);
  }

  // ---------- export.options ----------
  function unix(iso) {
    const s = String(iso).trim().replace(/Z+$/, "").replace(/ /g, "T").split(".")[0];
    const m = /^(\d{4})-(\d{1,2})-(\d{1,2})(?:T(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$/.exec(s);
    if (m) {
      const [y, mo, d, h, mi, se] = m.slice(1).map(v => (v === undefined ? 0 : +v));
      const back = new Date(Date.UTC(y, mo - 1, d));
      if (mo >= 1 && mo <= 12 && back.getUTCDate() === d && h < 24 && mi < 60 && se <= 61) return Date.UTC(y, mo - 1, d, h, mi, se) / 1000;
    }
    throw new Error(`not a UTC time: '${s}'`);
  }

  function options(q) {
    const get = (k, d) => (q[k] !== undefined && q[k] !== null && String(q[k]) !== "" ? String(q[k]) : d);
    const t0 = unix(get("from", "")), t1 = unix(get("until", ""));
    if (t1 <= t0) throw new Error("until must be after from");
    const cams = ["N", "W"].filter(c => get("cams", "NW").toUpperCase().includes(c)).join("") || "NW";
    let fps = get("fps", "auto");
    fps = fps === "auto" ? "auto" : pyMax(1, pyMin(FPS, pyIntF(pyFloat(fps))));
    let size = get("size", "1024");
    if (size !== FULL) {
      const n = pyIntStr(size), all = SIZES.concat(BUCKETS.slice(1));
      size = all.reduce((best, s) => (Math.abs(s - n) < Math.abs(best - n) ? s : best));
    }
    const look = get("look", LOOKS[0]), colors = get("colors", COLORS[0]);
    const movie = { center: get("center", "1") !== "0", trail: pyMax(0, pyMin(12, intOr0(get("trail", "0")))),
      laps: pyMax(1, pyMin(12, get("laps", "1") ? pyIntStr(get("laps", "1")) : 1)) };
    const fade = pyMax(0, pyMin(120, intOr0(get("fade", "0"))));
    Object.assign(movie, { fade, persist: fade ? pyMax(0, pyMin(100, intOr0(get("persist", "35")))) : 0 });
    if (get("whole", "0") === "1") Object.assign(movie, { whole: true, fade: 0, persist: 0 });
    if (get("complete", "0") === "1") movie.complete = true;
    if (get("sets", "1") === "0") movie.sets = false;
    const bg = get("bg", "000000").replace(/^#+/, "").toLowerCase();
    if (bg.length === 6 && /^[0-9a-f]{6}$/.test(bg) && bg !== "000000") movie.bg = bg;
    const mos = get("mos", "");
    if (mos === "whole") Object.assign(movie, { whole: true, complete: true, fade: 0, persist: 0 });
    else if (mos === "tiles") { delete movie.whole; delete movie.complete; }
    else if (mos === "off") { delete movie.whole; delete movie.complete; movie.mosaics = false; }
    const steady = pyMax(0, pyMin(60, intOr0(get("steady", "0"))));
    if (steady) movie.steady = steady;
    const exposure = pyMax(0, pyMin(30, intOr0(get("exposure", "0"))));
    if (exposure) movie.exposure = exposure;
    const cs = pyMax(0, pyMin(100, intOr0(get("cs", "0"))));
    if (cs) movie.colour = cs;
    const offs = get("off", "").split(",");
    const off = STEPS.filter(s => offs.includes(s)).join(",");
    const words = k => [...new Set(get(k, "").split(",").map(w => w.trim()).filter(Boolean))].sort();
    const kept = { drop: words("drop"), targets: words("targets").map(w => w.toUpperCase()).sort(), filters: words("filters") };
    const levels = {};
    for (const w of words("levels")) {
      const i = w.lastIndexOf(":"), k = i >= 0 ? w.slice(0, i) : "", v = i >= 0 ? w.slice(i + 1) : w;
      let x;
      try { x = pyFloat(v); } catch (e) { continue; }
      levels[k] = pyRound(pyMax(-LEVEL_EV, pyMin(LEVEL_EV, x)), 2);
    }
    const even = pyMax(0, pyMin(EVEN_MOST, pyIntF(pyFloat(get("even", "0") || 0))));
    // the look (edit) and single frames' looks (fedit) are kept as the editor sent them: the plan and the levels
    // never read them (studio_look.parse/override normalize them for the film's name only)
    const fedit = {};
    for (const w of get("fedit", "").split("|")) {
      const i = w.indexOf("~"), k = (i >= 0 ? w.slice(0, i) : w).trim(), r = i >= 0 ? w.slice(i + 1) : "";
      if (k && r) fedit[k] = r;
    }
    const box = k => {
      const p = get(k, "").split("_");
      if (p.length !== 4) return null;
      let v;
      try { v = p.map(s => pyMax(0.0, pyMin(1.0, pyRound(pyFloat(s), 4)))); } catch (e) { return null; }
      const [x0, y0, x1, y1] = v;
      if (x1 - x0 < CROP_LEAST || y1 - y0 < CROP_LEAST || (x0 === 0 && y0 === 0 && x1 === 1 && y1 === 1)) return null;
      return v;
    };
    let crop = box("crop");
    const crop2 = box("crop2");
    if (crop2 && !crop) crop = [0.0, 0.0, 1.0, 1.0];
    const nudge = {};
    for (const w of words("nudge")) {
      const [k, ...xy] = w.split(":");
      if (xy.length !== 2) continue;
      let d;
      try { d = xy.map(v => pyRound(pyMax(-NUDGE_MOST, pyMin(NUDGE_MOST, pyFloat(v))), 3)); } catch (e) { continue; }
      if (d[0] || d[1]) nudge[k] = d;
    }
    for (const w of words("steadied")) {
      const [k, ...xy] = w.split(":");
      if (xy.length !== 2) continue;
      let s;
      try { s = xy.map(v => pyMax(-STEADY_MOST, pyMin(STEADY_MOST, pyIntStr(v) / 1e5))); } catch (e) { continue; }
      const [dx, dy] = nudge[k] || [0.0, 0.0];
      if (s[0] || s[1]) nudge[k] = [pyRound(dx + s[0], 5), pyRound(dy + s[1], 5)];
    }
    const ctr = get("ctr", "");
    if (ctr === "0" || ctr === "1") movie.center = ctr === "1";
    const pictures = PICTURES.includes(get("pictures", "movie")) ? get("pictures", "movie") : "movie";
    const cut = {};
    for (const [k, v] of Object.entries(kept)) if (v.length) cut[k] = v;
    return { off, cut, edit: get("edit", ""), levels, even, fedit, frame: { crop, crop2, nudge },
      pictures, list: get("list", "0") === "1", hdr: get("hdr", "0") === "1",
      from: t0, until: t1, cams, fps, size,
      sound: get("sound", "1") !== "0", caption: get("caption", "1") !== "0", boom: get("boom", "0") === "1",
      look: LOOKS.includes(look) ? look : LOOKS[0], colors: COLORS.includes(colors) ? colors : COLORS[0], movie };
  }

  // ---------- the index the plan reads: the month catalogs, in the index's order ----------
  // sets_passes.is_polarizer, colour_filter
  const isPolarizer = (f1, f2) => (f1.startsWith("P") && /^\d$/.test(f1.slice(1, 2))) || f1.startsWith("IRP") || f2.startsWith("IRP");
  const colourFilter = (f1, f2) => (isPolarizer(f1, f2) ? null : [f1, f2].filter(f => !f.startsWith("CL")).join("/") || null);
  // ET - UTC (s) from a date on, for a catalog without ut (an older build): the index second is then estimated from et
  const LEAPS = [[-Infinity, 63.184], [Date.UTC(1999, 0, 1) / 1000, 64.184], [Date.UTC(2006, 0, 1) / 1000, 65.184],
    [Date.UTC(2009, 0, 1) / 1000, 66.184], [Date.UTC(2012, 6, 1) / 1000, 67.184], [Date.UTC(2015, 6, 1) / 1000, 68.184],
    [Date.UTC(2017, 0, 1) / 1000, 69.184]];
  const J2000 = 946728000;   // unix seconds of 2000-01-01T12:00:00 UTC
  const deltaEt = u => { let d = LEAPS[0][1]; for (const [at, v] of LEAPS) if (u >= at) d = v; return d; };
  const etOf = u => u - J2000 + deltaEt(u);
  const unixOfEt = et => { const u0 = et + J2000 - 69.184; return et + J2000 - deltaEt(u0 + 69.184 - deltaEt(u0)); };

  // the frames of the months loaded, one table: columns in the index's order plus each set's and pass's tables
  function index(parts) {
    const rows = [], seen = new Set(), sets = {}, passes = {};
    for (const c of parts) {
      const g = c.groups || { sets: {}, passes: {} }, raw = c.raw_target || {};
      Object.assign(sets, g.sets || {}); Object.assign(passes, g.passes || {});
      for (let k = 0; k < c.id.length; k++) {
        const id = c.id[k];
        if (seen.has(id)) continue;
        seen.add(id);
        const t = c.ut && c.ut[k] !== null && c.ut[k] !== undefined ? Math.floor(c.et[k]) + UT_BASE + c.ut[k] : Math.floor(unixOfEt(c.et[k]));
        rows.push({ id, t, tr: c.tr && c.tr[k] !== null && c.tr[k] !== undefined ? c.tr[k] : 0, at: rows.length,
          cam: c.cam[k] === "N" ? "N" : "W", target: raw[id] !== undefined ? raw[id] : c.target[k],
          obs: c.obs[k] === null || c.obs[k] === undefined ? null : c.obs[k], f1: String(c.f1[k]), f2: String(c.f2[k]),
          set: c.set ? c.set[k] : -1, pass: c.pass ? c.pass[k] : -1 });
      }
    }
    rows.sort((a, b) => a.t - b.t || a.tr - b.tr || a.at - b.at);
    const n = rows.length, row = new Map();
    const t = new Float64Array(n);
    rows.forEach((r, q) => { t[q] = r.t; row.set(r.id, q); });
    // reel.load_index's sets: {kind, use, rows, filters, ready}, from the data's sets and each frame's set
    const setRows = new Map();
    rows.forEach((r, q) => { if (r.set >= 0) { if (!setRows.has(r.set)) setRows.set(r.set, []); setRows.get(r.set).push(q); } });
    const setOf = rows.map(r => r.set), built = new Map();
    const set = s => {
      if (built.has(s)) return built.get(s);
      const g = sets[String(s)];
      let st = null;
      if (g) {
        const use = g[1].map(id => row.get(id));
        const rs = setRows.get(s) || [];
        st = { kind: g[0], use, rows: rs, filters: rs.map(q => colourFilter(rows[q].f1, rows[q].f2)),
          ready: use.every(q => q !== undefined) ? Math.max(...use.map(q => t[q])) : NaN };
      }
      built.set(s, st);
      return st;
    };
    return { rows, t, row, setOf, set, passes };
  }

  // ---------- where the data comes from ----------
  const FRAMES = (() => {   // the frame server (or the public frames host), as the camera windows choose it
    if (typeof location === "undefined") return "";
    const q = new URLSearchParams(location.search).get("frames");
    if (q) return q.replace(/\/$/, "");
    if (/^https?:$/.test(location.protocol) && !/claude\.ai$|claudeusercontent\.com$|claude\.site$/.test(location.hostname)) return location.origin;
    return "http://localhost:8765";
  })();
  const fetchJson = async url => { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); };
  let missionP = null;
  const dataSource = {
    maxPictures: 0,
    // all months, oldest first (to reach further back or on when a stretch's neighbours are needed)
    async allMonths() {
      missionP = missionP || (typeof mission !== "undefined" && mission ? Promise.resolve(mission) : fetchJson("data/mission.json"));
      const m = await missionP;
      return (m.months || []).filter(x => x.images !== 0).map(x => ({ start: unixOfEt(x.start), end: unixOfEt(x.end), key: x.catalog, catalog: () => fetchJson(x.catalog) }));
    },
    // the pass kind table of a frame (obs_mosaic.kind_of: lap_ends), the windows' warm=1 answer
    kind: id => fetchJson(`${FRAMES}/frames/mosaic/${id}.webp?warm=1`),
  };
  const got = new Map();   // month key -> its catalog's promise, kept (a failed one is asked again next time)
  const catalogOf = m => {
    const k = m.key || m.catalog;
    if (!got.has(k)) got.set(k, Promise.resolve().then(() => m.catalog()).catch(e => { got.delete(k); throw e; }));
    return got.get(k);
  };

  // the months the stretch needs: its own, the 64 frames before it (movie mode's look back), and every frame of a
  // set it shows (a set started before the stretch, its channels taken in the month before)
  async function load(opt, tell) {
    const all = await API.source.allMonths();
    if (!all.length) throw new Error("the replay data has no month catalogs");
    let i0 = all.findIndex(m => m.end > opt.from - 2 * 86400), i1 = all.length - 1;
    if (i0 < 0) i0 = all.length - 1;
    for (let k = all.length - 1; k >= 0; k--) if (all[k].start <= opt.until + 2 * 86400) { i1 = k; break; }
    i1 = Math.max(i1, i0);
    for (;;) {
      const parts = await Promise.all(all.slice(i0, i1 + 1).map(catalogOf));
      const ix = index(parts);
      const lo = searchsorted(ix.t, opt.from, false), hi = searchsorted(ix.t, opt.until, true);
      // a set whose channels are not all loaded: its months are before or after (both looked at in turn)
      let missing = false;
      for (let q = lo; q < hi && !missing; q++) { const st = ix.setOf[q] >= 0 ? ix.set(ix.setOf[q]) : null; missing = !!st && st.use.some(u => u === undefined); }
      if (i0 > 0 && (lo < 64 || missing)) { i0--; continue; }
      if (missing && i1 < all.length - 1) { i1++; continue; }
      return { ix, lo, hi };
    }
  }

  // ---------- export.plan ----------
  async function plan(opt, tell) {
    tell = tell || (() => {});
    if (big(opt)) throw new Error("films bigger than 1024 px a camera are made by the frame server");
    const { ix, lo, hi } = await load(opt, tell);
    const t = ix.t, R = ix.rows;
    const ids = R.map(r => r.id), targets = R.map(r => r.target), obs = R.map(r => (r.obs === null ? NaN : r.obs));
    const f1s = R.map(r => r.f1), f2s = R.map(r => r.f2), setOf = ix.setOf;
    const inst = q => (R[q].cam === "N" ? "ISSNA" : "ISSWA");
    const camOf = q => R[q].cam;
    // obs_mosaic's answers, from the data's passes
    const passRow = q => (R[q].pass >= 0 ? ix.passes[String(R[q].pass)] || null : null);
    const passKind = q => { const p = passRow(q); return p ? p[0] || null : null; };
    const tossup = q => { const p = passRow(q); return !!(p && p[5]); };
    const passOf = q => { const p = passRow(q); return p ? `${targets[q]}|${p[1]}|${R[q].cam}|${p[2]}` : null; };
    const kinds = new Map();
    const lapEnds = async q => {
      const k = String(R[q].pass);
      if (!kinds.has(k)) kinds.set(k, Promise.resolve().then(() => API.source.kind(ids[q])).then(j => new Set(j.lap_ends || []), () => null));
      return kinds.get(k);
    };
    // _lap_end: True when the frame finishes a lap, or when that cannot be told
    const lapEnd = async q => { const e = await lapEnds(q); return e === null ? true : e.has(ids[q]); };

    const last = {};
    for (let q = lo - 1; q > Math.max(-1, lo - 65); q--) if (!(camOf(q) in last)) last[camOf(q)] = q;
    const mixOf = st => st.use.map(u => st.filters[st.rows.indexOf(u)]);
    const counts = new Map();   // (cam, target) -> Map(mix -> count), in insertion order
    const inWindow = [];
    for (let q = lo; q < hi; q++) if (setOf[q] >= 0) inWindow.push(setOf[q]);
    for (const s of pySetOrder(inWindow)) {
      const st = ix.set(s);
      if (st && st.use.length >= 3) {
        const k = `${camOf(st.use[0])}\u0000${targets[st.use[0]]}`, m = JSON.stringify(mixOf(st));
        if (!counts.has(k)) counts.set(k, new Map());
        const c = counts.get(k);
        c.set(m, (c.get(m) || 0) + 1);
      }
    }
    const filmMix = new Map();
    for (const [k, c] of counts) { let best = null, n = -1; for (const [m, v] of c) if (v > n) { best = m; n = v; } filmMix.set(k, JSON.parse(best)); }
    const mix = st => {
      const want = filmMix.get(`${camOf(st.use[0])}\u0000${targets[st.use[0]]}`);
      if (!want || st.use.length < 3 || JSON.stringify(mixOf(st)) === JSON.stringify(want)) return st.use;
      const pairs = st.filters.map((f, j) => [f, st.rows[j]]).map((p, j) => [p, j]).sort((a, b) => t[a[0][1]] - t[b[0][1]] || a[1] - b[1]).map(x => x[0]);
      const newest = new Map();
      for (const [f, r] of pairs) newest.set(f, r);
      return want.every(f => newest.has(f)) ? want.map(f => newest.get(f)) : st.use;
    };
    let out = [];
    tell(0, hi - lo, "frames");
    const how = opt.pictures || "movie", mv = opt.movie;
    for (let q = lo; q < hi; q++) {
      if ((q - lo) % PROGRESS_EVERY === 0 && q > lo) tell(q - lo, hi - lo, "frames");
      const cam = camOf(q);
      const prev = last[cam];
      last[cam] = q;
      if (!opt.cams.includes(cam)) continue;
      const s = setOf[q];
      const st = s >= 0 ? ix.set(s) : null;
      let comp = false;
      if (st !== null && st.use.includes(q)) {
        let m = st.use[0];
        for (const u of st.use) if (t[u] > t[m]) m = u;
        comp = q === m;
      }
      let tile = prev !== undefined && targets[prev] === targets[q] && obs[prev] === obs[q] && (st === null || comp);
      let tries = [];
      let kind = how === "movie" || how === "color" ? passKind(q) : null;
      if (how === "color" && kind === "movie") kind = null;
      if (mv.mosaics === false && (kind === "mosaic" || kind === "mosaic_movie" || (kind === "movie" && tossup(q)))) { kind = null; tile = false; }
      if (how === "movie" && st !== null && mv.sets !== false && kind !== "mosaic" && kind !== "mosaic_movie" && t[q] !== st.ready) continue;
      if (kind === "movie") tries.push(["movie", ids[q]]);
      else if (kind === "mosaic_movie") {
        if (mv.whole && !(await lapEnd(q))) continue;
        tries.push(["rolling", ids[q]]);
      } else if (kind === "mosaic") tries.push(["mosaic", ids[q]]);
      else if (tile && mv.mosaics !== false) tries.push(["mosaic", comp ? ids[st.use[0]] : ids[q]]);
      if (comp) tries.push(["color", mix(st).map(u => ids[u])]);
      tries.push(["processed", ids[q]], ["frame", ids[q]]);
      if (how === "color") {
        const full = comp && st.use.length >= 3;
        const lap = kind === "mosaic_movie" && mv.whole && st !== null;
        if (!full && !lap) continue;
        const lead = (kind === "mosaic" || kind === "mosaic_movie") && (tries[0][0] === "mosaic" || tries[0][0] === "rolling") ? [tries[0]] : [];
        tries = lead.concat(full ? [["color", mix(st).map(u => ids[u])]] : [], [["processed", ids[q]], ["frame", ids[q]]]);
      } else if (how === "processed") tries = [["processed", ids[q]], ["frame", ids[q]]];
      else if (how === "raw") tries = [["frame", ids[q]]];
      const e = { id: ids[q], cam, t: t[q], target: typeof targets[q] === "string" ? targets[q] : "", filters: `${f1s[q]}/${f2s[q]}`,
        obs: typeof obs[q] === "string" ? obs[q] : "", try: tries, nm: wavelength(inst(q), f1s[q] + f2s[q]) };
      if (comp) {
        e.set = st.kind;
        e.set_nm = mix(st).map(u => wavelength(inst(u), f1s[u] + f2s[u]));
      }
      if (kind === "mosaic") e.pass = passOf(q);
      out.push(e);
    }
    if (mv.complete) out = completeMosaics(out);
    out = cut(out, opt);
    const max = API.source.maxPictures || 0;
    if (max && out.length > max && !opt.list)
      throw new Error(`${out.length.toLocaleString("en-US")} pictures: an export holds at most ${max.toLocaleString("en-US")}; pick a shorter stretch`);
    tell(hi - lo, hi - lo, "frames");
    timing(out, opt.fps);
    let forward = out.length;
    if (opt.boom && !opt.list && forward >= 3) out = boomerang(out);
    else forward = 0;
    const p = { pictures: out, count: out.length, seconds: pyRound(out.reduce((s, e) => s + e.frames, 0) / FPS, 2),
      frames: out.reduce((s, e) => s + e.frames, 0), width: width(opt), height: height(opt) };
    if (forward) p.boomerang = forward;
    return p;
  }

  function completeMosaics(pics) {
    const last = new Map();
    pics.forEach((e, i) => { if (e.pass) last.set(`${e.cam}\u0000${e.pass}`, i); });
    const out = [];
    pics.forEach((e, i) => {
      if (e.pass) {
        if (last.get(`${e.cam}\u0000${e.pass}`) !== i) return;
        e.try = [["mosaic", e.id]].concat(e.try.filter(x => x[0] !== "mosaic"));
      }
      out.push(e);
    });
    return out;
  }
  function cut(pics, opt) {
    const c = opt.cut || {};
    const drop = new Set(c.drop || []), targets = new Set(c.targets || []), filters = new Set(c.filters || []);
    if (!drop.size && !targets.size && !filters.size) return pics;
    return pics.filter(e => !drop.has(e.id) && (!targets.size || targets.has(e.target || "UNKNOWN")) && (!filters.size || filters.has(e.filters)));
  }
  function timing(pics, fps) {
    const gaps = [];
    for (let i = 1; i < pics.length; i++) gaps.push(pics[i].t - pics[i - 1].t);
    let holds;
    if (fps === "auto") {
      const pos = gaps.filter(g => g > 0);
      const c = pyMax(1e-3, median(pos.length ? pos : [1])) / TYPICAL;
      holds = gaps.map(g => pyMin(HOLD_MAX, pyMax(HOLD_MIN, g / c)));
      gaps.forEach((g, i) => { if (g > SKIP_NOTE && g / c > HOLD_MAX) pics[i].skipped = g; });
      holds.push(holds.length ? median(holds) : ONLY);
    } else {
      holds = gaps.map(() => 1 / fps);
      holds.push(gaps.length ? 1 / fps : ONLY);
    }
    pics.forEach((e, i) => { if (i < holds.length) e.hold = holds[i]; });
    frames(pics);
  }
  function frames(pics) {
    let at = 0.0, carry = 0.0;
    for (const e of pics) {
      const h = e.hold;
      const n = pyMax(1, pyRound(h * FPS + carry));
      carry += h * FPS - n;
      e.at = pyRound(at, 4); e.hold = pyRound(h, 4); e.frames = n;
      at += n / FPS;
    }
  }
  function boomerang(pics) {
    if (pics.length < 3) return pics;
    const out = pics.concat(pics.slice(0, -1).reverse().map(e => Object.assign({}, e, { back: true })));
    for (const e of out) delete e.at;
    frames(out);
    return out;
  }
  const big = opt => opt.size === FULL || opt.size > Math.max(...SIZES);
  const pane = opt => (big(opt) ? opt.pane || 1024 : opt.size);
  const width = opt => pane(opt) * opt.cams.length;
  const captionH = opt => (opt.caption ? 2 * pyRound(CAPTION * pane(opt) / 1024 / 2) : 0);
  const height = opt => pane(opt) + captionH(opt);

  // ---------- export.public_plan, source ----------
  function source(kind, arg) {
    if (kind === "movie") return `/frames/movie/${arg}.webp`;
    if (kind === "rolling") return `/frames/movie/${arg}.webp?mode=rolling`;
    if (kind === "mosaic") return `/frames/mosaic/${arg}.webp`;
    if (kind === "color") return `/frames/color.webp?ids=${arg.join(",")}`;
    if (kind === "processed") return `/frames/processed/${arg}.webp`;
    return `/frames/${arg}.webp`;
  }
  const KEEP = ["id", "cam", "t", "target", "filters", "obs", "nm", "set", "set_nm", "at", "hold", "frames", "skipped", "pass", "back"];
  function publicPlan(p) {
    const pics = p.pictures.map(e => {
      const o = {};
      for (const k of KEEP) if (k in e) o[k] = e[k];
      o.first = e.try[0][0]; o.src = source(...e.try[0]); o.tries = e.try.map(([k, a]) => [k, source(k, a)]);
      return o;
    });
    return Object.assign({}, p, { pictures: pics });
  }

  const API = {
    source: dataSource,
    frames: FRAMES,
    // the plan as /export/plan.json answers it, or {error} (a bad option, a size the page does not make, no data)
    async plan(q, tell) {
      try { return publicPlan(await plan(options(q || {}), tell)); } catch (e) { return { error: String(e && e.message || e) }; }
    },
    // the parts, for levels-local.js and the tests
    _: { options, plan, publicPlan, source, unix, pyRound, pyFloat, pySetOrder, index, timing, frames, boomerang, cut, wavelength, FPS, LEVEL_EV, unixOfEt, etOf },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.cassiniPlanLocal = Object.assign(root.cassiniPlanLocal || {}, API);
})(typeof window !== "undefined" ? window : globalThis);
