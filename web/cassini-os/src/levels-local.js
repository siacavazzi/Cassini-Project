// ---------- the Movie Editor's exposure graph, worked out on this computer (the public site: no frame server) ----------
// A line-for-line port of web/frames/export.py's levels: each picture's brightness (brightness: the natural log of the
// median gray of its lit pixels, measured at LEVELS_SIDE px), measured on the picture the film shows for each frame at
// 512 px over black (Pictures.picture, _on_black), and Even out's change per picture (stretches, exposures:
// obs_mosaic.evened_gains, which the page has already, cassiniSteadyMath().evenedGains). Pillow's resampling
// (BILINEAR and LANCZOS, 8 bits a channel, premultiplied for RGBA), its RGB to L conversion and paste with a mask, and
// numpy's float32 percentile and median are ported as they compute. web/test_levels_local.py runs this file in node
// against the Python on the same pixels.
//
//   window.cassiniPlanLocal.levels(options, pictures[, tell]) -> Promise of /export/levels.json's answer
//     options: the film's query (plain object of strings, as plan takes); pictures: the plan's pictures (plan.json's
//     list, cams NW, nothing cut, as the editor loads it; or null: worked out here); tell(done, total) as it measures.
//   window.cassiniPlanLocal.source.picture(e, size, options) -> Promise of {data (RGBA), width, height} or null: the
//     picture of plan entry e (its tries in turn), overridable.
(function (root) {
  "use strict";
  const LEVELS_SIDE = 160, LEVELS_LIT = 0.04, MEASURE_SIZE = 512, AT_ONCE = 3;
  // obs_mosaic's exposure normalization constants evened_gains reads (test_levels_local.py checks them)
  const EXPOSURE = { flash: 3, gain: 4.0, roll: 0.75, free: 0.26 };
  const f32 = Math.fround;

  // ---------- Pillow ----------
  // Resample.c: the filters, precompute_coeffs, normalize_coeffs_8bpc, ImagingResampleHorizontal/Vertical_8bpc
  const FILTERS = {
    bilinear: { support: 1.0, f: x => { if (x < 0) x = -x; return x < 1.0 ? 1.0 - x : 0.0; } },
    lanczos: { support: 3.0, f: x => (x >= -3.0 && x < 3.0 ? sinc(x) * sinc(x / 3.0) : 0.0) },
  };
  function sinc(x) { if (x === 0.0) return 1.0; x = x * Math.PI; return Math.sin(x) / x; }
  const PRECISION_BITS = 32 - 8 - 2;
  function coeffs(inSize, in0, in1, outSize, filter) {
    const scale = (in1 - in0) / outSize;
    let filterscale = scale;
    if (filterscale < 1.0) filterscale = 1.0;
    const support = filter.support * filterscale;
    const ksize = Math.trunc(Math.ceil(support)) * 2 + 1;
    const kk = new Float64Array(outSize * ksize), bounds = new Int32Array(outSize * 2);
    for (let xx = 0; xx < outSize; xx++) {
      const center = in0 + (xx + 0.5) * scale, ss = 1.0 / filterscale;
      let ww = 0.0;
      let xmin = Math.trunc(center - support + 0.5);
      if (xmin < 0) xmin = 0;
      let xmax = Math.trunc(center + support + 0.5);
      if (xmax > inSize) xmax = inSize;
      xmax -= xmin;
      const k = xx * ksize;
      let x = 0;
      for (; x < xmax; x++) { const w = filter.f((x + xmin - center + 0.5) * ss); kk[k + x] = w; ww += w; }
      for (x = 0; x < xmax; x++) if (ww !== 0.0) kk[k + x] /= ww;
      for (; x < ksize; x++) kk[k + x] = 0;
      bounds[xx * 2] = xmin; bounds[xx * 2 + 1] = xmax;
    }
    // normalize_coeffs_8bpc: to fixed point
    const ik = new Float64Array(kk.length);
    for (let i = 0; i < kk.length; i++) ik[i] = kk[i] < 0 ? Math.trunc(-0.5 + kk[i] * (1 << PRECISION_BITS)) : Math.trunc(0.5 + kk[i] * (1 << PRECISION_BITS));
    return { ksize, k: ik, bounds };
  }
  const ONE = 2 ** PRECISION_BITS;
  const clip8 = v => (v >= ONE * 256 ? 255 : v <= 0 ? 0 : Math.floor(v / ONE));
  // ImagingResampleHorizontal_8bpc: every row of src from row `offset` on, to w columns
  function passH(src, w, rows, offset, c) {
    const B = src.bands, out = new Uint8ClampedArray(w * rows * 4);
    for (let yy = 0; yy < rows; yy++) {
      const row = (yy + offset) * src.width * 4;
      for (let xx = 0; xx < w; xx++) {
        const xmin = c.bounds[xx * 2], xmax = c.bounds[xx * 2 + 1], k = xx * c.ksize;
        const ss = [ONE / 2, ONE / 2, ONE / 2, ONE / 2];
        for (let x = 0; x < xmax; x++) { const p = row + (x + xmin) * 4, kx = c.k[k + x]; for (let b = 0; b < 4; b++) ss[b] += src.data[p + b] * kx; }
        const o = (yy * w + xx) * 4;
        if (B === 1) out[o] = clip8(ss[0]);
        else for (let b = 0; b < (B === 3 ? 3 : 4); b++) out[o + b] = clip8(ss[b]);
      }
    }
    return { data: out, width: w, height: rows, bands: B };
  }
  // ImagingResampleVertical_8bpc: every column of src, to h rows (bounds already relative to src's first row)
  function passV(src, h, c) {
    const B = src.bands, w = src.width, out = new Uint8ClampedArray(w * h * 4);
    for (let yy = 0; yy < h; yy++) {
      const ymin = c.bounds[yy * 2], ymax = c.bounds[yy * 2 + 1], k = yy * c.ksize;
      for (let xx = 0; xx < w; xx++) {
        const ss = [ONE / 2, ONE / 2, ONE / 2, ONE / 2];
        for (let y = 0; y < ymax; y++) { const p = ((y + ymin) * w + xx) * 4, ky = c.k[k + y]; for (let b = 0; b < 4; b++) ss[b] += src.data[p + b] * ky; }
        const o = (yy * w + xx) * 4;
        if (B === 1) out[o] = clip8(ss[0]);
        else for (let b = 0; b < (B === 3 ? 3 : 4); b++) out[o + b] = clip8(ss[b]);
      }
    }
    return { data: out, width: w, height: h, bands: B };
  }
  // ImagingResampleInner as in Pillow 13 (requirements.txt pins 13.0.0): when the height shrinks more than twice as
  // much as the width, the vertical pass runs first. im: {data (4 bytes a pixel), width, height, bands}; resample to
  // w x h with the whole picture as the box.
  function resize(im, w, h, filterName) {
    const filter = FILTERS[filterName], B = im.bands;
    if (w === im.width && h === im.height) return { data: Uint8ClampedArray.from(im.data), width: w, height: h, bands: B };
    const needH = w !== im.width, needV = h !== im.height;
    const horizontalFirst = !(im.height - h > 0 && im.height - h > (im.width - w) * 2);
    const ch = coeffs(im.width, 0, im.width, w, filter), cv = coeffs(im.height, 0, im.height, h, filter);
    let src = im;
    if (horizontalFirst) {
      if (needH) {
        const yFirst = cv.bounds[0], yLast = cv.bounds[h * 2 - 2] + cv.bounds[h * 2 - 1];
        if (yFirst !== 0) for (let i = 0; i < h; i++) cv.bounds[i * 2] -= yFirst;
        src = passH(src, w, yLast - yFirst, yFirst, ch);
      }
      if (needV) src = passV(src, h, cv);
    } else {
      if (needV) src = passV(src, h, cv);
      if (needH) src = passH(src, w, h, 0, ch);
    }
    return src;
  }
  const MULDIV255 = (a, b) => { const t = a * b + 128; return ((t >> 8) + t) >> 8; };
  const DIV255 = a => { const t = a + 128; return ((t >> 8) + t) >> 8; };
  // Image.resize of an RGBA picture: premultiplied (RGBA -> RGBa), resampled, back (RGBa -> RGBA)
  function resizeRGBA(im, w, h, filterName) {
    const pre = new Uint8ClampedArray(im.data.length);
    for (let i = 0; i < im.data.length; i += 4) { const a = im.data[i + 3]; pre[i] = MULDIV255(im.data[i], a); pre[i + 1] = MULDIV255(im.data[i + 1], a); pre[i + 2] = MULDIV255(im.data[i + 2], a); pre[i + 3] = a; }
    const r = resize({ data: pre, width: im.width, height: im.height, bands: 4 }, w, h, filterName), d = r.data;
    for (let i = 0; i < d.length; i += 4) {
      const a = d[i + 3];
      if (a !== 255 && a !== 0) for (let b = 0; b < 3; b++) d[i + b] = Math.min(255, Math.floor((255 * d[i + b]) / a));
    }
    return r;
  }
  const pyRound = x => { let r = Math.round(x); if (r - x === 0.5 && r % 2 !== 0) r -= 1; return r; };

  // Pictures._on_black: the picture (RGBA) size px on its longest side (LANCZOS), over the Background (bg, hex)
  function onBlack(im, size, bg) {
    let p = { data: im.data, width: im.width, height: im.height, bands: 4 };
    if (Math.max(p.width, p.height) !== size) {
      const s = size / Math.max(p.width, p.height);
      p = resizeRGBA(p, Math.max(1, pyRound(p.width * s)), Math.max(1, pyRound(p.height * s)), "lanczos");
    }
    const c = bg ? [parseInt(bg.slice(0, 2), 16), parseInt(bg.slice(2, 4), 16), parseInt(bg.slice(4, 6), 16)] : [0, 0, 0];
    const out = new Uint8ClampedArray(p.width * p.height * 4), d = p.data;
    for (let i = 0; i < out.length; i += 4) {
      const m = d[i + 3];
      for (let b = 0; b < 3; b++) out[i + b] = DIV255(c[b] * (255 - m) + d[i + b] * m);
      out[i + 3] = 255;
    }
    return { data: out, width: p.width, height: p.height, bands: 3 };
  }

  // ---------- numpy, float32 ----------
  // np.percentile(v, q) of a float32 array, method linear, as numpy 2 computes it in float32 (q / float32(100))
  function percentile32(sorted, q) {
    const n = sorted.length, qq = f32(f32(q) / f32(100));
    const vi = f32(f32(f32(n * qq) + f32(1 - qq)) - 1);
    let prev = Math.floor(vi), next = prev + 1;
    if (vi >= n - 1) { prev = n - 1; next = n - 1; }
    if (vi < 0) { prev = 0; next = 0; }
    const g = f32(vi - prev), a = sorted[prev], b = sorted[next], diff = f32(b - a);
    return g >= 0.5 ? f32(b - f32(diff * f32(1 - g))) : f32(a + f32(diff * g));
  }
  // np.median of a float32 array: the middle one, or the float32 mean of the middle two
  function median32(sorted) {
    const n = sorted.length, m = n >> 1;
    return n % 2 ? sorted[m] : f32(f32(sorted[m - 1] + sorted[m]) / 2);
  }

  // export.brightness of an RGB picture ({data, width, height}): the log, or null with too little lit
  function brightness(im) {
    const k = LEVELS_SIDE / Math.max(im.width, im.height);
    let p = { data: im.data, width: im.width, height: im.height, bands: 3 };
    if (k < 1) p = resize(p, Math.max(1, pyRound(im.width * k)), Math.max(1, pyRound(im.height * k)), "bilinear");
    const n = p.width * p.height, all = new Float32Array(n);
    let m = 0;
    const low = f32(1 / 255);
    for (let i = 0; i < n; i++) {
      const d = p.data, o = i * 4;
      const L = (d[o] * 19595 + d[o + 1] * 38470 + d[o + 2] * 7471 + 0x8000) >>> 16;
      const v = f32(L / 255);
      if (v > low) all[m++] = v;
    }
    if (m < 64) return null;
    const v = all.subarray(0, m).sort();
    const thr = f32(LEVELS_LIT * Math.max(percentile32(v, 99.5), 1e-6));
    let first = m;
    while (first > 0 && v[first - 1] > thr) first--;
    const lit = v.subarray(first);
    return lit.length >= 64 ? f32(Math.log(median32(lit))) : null;
  }

  // ---------- export.stretches, exposures, levels ----------
  function stretches(pics) {
    const out = [], last = new Map();
    pics.forEach((e, i) => {
      const first = e.first || (e.try ? e.try[0][0] : "frame");
      const k = JSON.stringify([first, first === "color" || (first === "mosaic" && !!e.set), e.target]);
      let run = last.get(e.cam);
      if (run === undefined || run[0] !== k) { run = [k, []]; last.set(e.cam, run); out.push(run[1]); }
      run[1].push(i);
    });
    return out;
  }
  // np.interp(x, xp, fp) at x = 0..n-1 (xp increasing): numpy's compiled loop
  function interp(n, xp, fp) {
    const out = new Float64Array(n), L = xp.length;
    for (let x = 0; x < n; x++) {
      if (x < xp[0]) out[x] = fp[0];
      else if (x >= xp[L - 1]) out[x] = fp[L - 1];
      else {
        let j = 0;
        while (j + 1 < L && xp[j + 1] <= x) j++;
        if (xp[j] === x) out[x] = fp[j];
        else { const slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]); out[x] = slope * (x - xp[j]) + fp[j]; }
      }
    }
    return out;
  }
  const evener = () => {
    const M = root.cassiniSteadyMath ? root.cassiniSteadyMath() : null;
    return M && M.evenedGains ? (logs, smooth) => M.evenedGains(logs, smooth, EXPOSURE) : null;
  };
  function exposures(opt, pics, logs, R) {
    const n = pics.length, lv = opt.levels || {};
    const pts = [];
    pics.forEach((e, i) => { if (Object.prototype.hasOwnProperty.call(lv, e.id)) pts.push([i, lv[e.id]]); });
    const line = pts.length ? interp(n, pts.map(p => p[0]), pts.map(p => p[1])) : new Float64Array(n);
    const even = new Float64Array(n);
    const fn = opt.even && logs && Object.keys(logs).length ? evener() : null;
    if (fn) {
      for (let run of stretches(pics)) {
        run = run.filter(i => logs[pics[i].id] !== undefined && logs[pics[i].id] !== null);
        if (run.length >= EXPOSURE.flash) fn(run.map(i => logs[pics[i].id]), opt.even).forEach((g, j) => { even[run[j]] = Math.log2(g); });
      }
    }
    const total = Array.from(line, (v, i) => Math.min(Math.max(v + even[i], -2 * R.LEVEL_EV), 2 * R.LEVEL_EV));
    const r4 = v => R.pyRound(v, 4);
    return [total.map(r4), Array.from(line, r4), Array.from(even, r4)];
  }

  // the address of a try as export.html's pictureUrl builds it: the movie style only on movie and rolling routes (the
  // public site's policy refuses it elsewhere), the look on all but plain frames, and the film's Auto center
  // (options' movie.center, which export.Pictures draws with: _centred for color and processed pictures, centre= for
  // movies); plain: a color or processed picture as it is, the stand-in when the server does not centre it (404).
  // Then cassiniExport.publicUrl when the public site has it.
  function pictureUrl(kind, src, size, frames, center, plain) {
    const sep = src.includes("?") ? "&" : "?",
      look = root.cassiniLook ? root.cassiniLook({ center: center && !plain && (kind === "color" || kind === "processed") }) : "",
      style = root.cassiniMovieStyle ? root.cassiniMovieStyle({ center }) : "", base = (/^https?:/.test(src) ? src : frames + src) + sep + `size=${size}`;
    const url = kind === "movie" ? `${base}&color=1${style}${look}` : kind === "rolling" ? `${base}${style}${look}` : kind === "frame" ? base : `${base}${look}`;
    return root.cassiniExport && root.cassiniExport.publicUrl ? root.cassiniExport.publicUrl(url) : url;
  }
  async function fetchRGBA(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) return null;
      const bmp = await createImageBitmap(await r.blob(), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
      const c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext("2d", { colorSpace: "srgb" });
      g.drawImage(bmp, 0, 0);
      return { data: g.getImageData(0, 0, bmp.width, bmp.height).data, width: bmp.width, height: bmp.height };
    } catch (err) { return null; }
  }
  // the picture of plan entry e at size px as the frame server makes it for the film (opt: the parsed options), RGBA,
  // its tries in turn (null: none)
  async function picture(e, size, opt) {
    const P = root.cassiniPlanLocal, frames = (P && P.frames) || "", center = !!(opt && opt.movie && opt.movie.center);
    for (const [kind, src] of e.tries || []) {
      const url = pictureUrl(kind, src, size, frames, center), plain = pictureUrl(kind, src, size, frames, center, true);
      const im = await fetchRGBA(url) || (plain !== url ? await fetchRGBA(plain) : null);
      if (im) return im;
    }
    return null;
  }

  const measured = new Map();   // levels key -> {logs: {id: log or null}}
  async function levels(q, pictures, tell) {
    const P = root.cassiniPlanLocal, R = P._;
    tell = tell || (() => {});
    let opt;
    try { opt = R.options(q || {}); } catch (e) { return { done: 0, total: null, even_ready: !!evener(), error: String(e.message || e), level: {} }; }
    const key = JSON.stringify([opt.from, opt.until, opt.pictures, opt.look, opt.colors, opt.off, opt.movie]);
    try {
      if (!pictures) pictures = R.publicPlan(await R.plan(Object.assign({}, opt, { cams: "NW", cut: {}, list: true }))).pictures;
      let m = measured.get(key);
      if (!m) {
        m = { logs: {} };
        const total = pictures.length;
        let done = 0, next = 0;
        tell(0, total);
        const one = async () => {
          while (next < pictures.length) {
            const e = pictures[next++];
            const im = await P.source.picture(e, MEASURE_SIZE, opt);
            const lv = im ? brightness(onBlack(im, MEASURE_SIZE, opt.movie.bg)) : null;
            m.logs[e.id] = lv === null ? null : R.pyRound(lv, 5);
            tell(++done, total);
          }
        };
        await Promise.all(Array.from({ length: AT_ONCE }, one));
        measured.set(key, m);
        while (measured.size > 8) measured.delete(measured.keys().next().value);
      }
      const n = Object.keys(m.logs).length;
      const out = { done: n, total: n, even_ready: !!evener(), error: null, level: {} };
      for (const [k, v] of Object.entries(m.logs)) out.level[k] = v === null ? null : R.pyRound(v / Math.log(2), 4);
      if (opt.even && evener()) {
        const pics = (await R.plan(Object.assign({}, opt, { list: true }))).pictures;
        for (const e of pics) e.first = e.try[0][0];
        const ev = exposures(opt, pics, m.logs, R)[2];
        out.even = {};
        pics.forEach((e, i) => { if (ev[i]) out.even[e.id] = ev[i]; });
      }
      return out;
    } catch (e) {
      return { done: 0, total: null, even_ready: !!evener(), error: String(e.message || e), level: {} };
    }
  }

  const API = { levels, _levels: { pictureUrl, picture, brightness, onBlack, resize, resizeRGBA, percentile32, median32, stretches, exposures, interp, EXPOSURE, measured } };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else {
    const P = root.cassiniPlanLocal = root.cassiniPlanLocal || {};
    P.levels = levels; P._levels = API._levels;
    P.source = P.source || {};
    if (!P.source.picture) P.source.picture = picture;
  }
})(typeof window !== "undefined" ? window : globalThis);
