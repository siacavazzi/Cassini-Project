// The pointing diagram on the "How the pictures are made" page: roughly how SPICE says where a body lands on
// Cassini's sensor, for a real frame (pointing.json, made by make_pointing.py from the pipeline's own
// bootleg_autonav.find_target and SPICE). Cassini at the origin looks along +z (x = sensor right, y = sensor up); the
// body sits where SPICE puts it, drawn with its real surface map turned the way SPICE says it was turned. A plane
// facing the camera at the body's distance, the four rays through the sensor's corners meeting it, and where the
// body's own ray lands among those four corners is where it lands on the sensor. bootleg_autonav.project does the same
// sum without the plane: sample = 511.5 - x / z * scale, line = 511.5 - y / z * scale.
(function () {
  "use strict";
  const root = document.getElementById("pointing");
  if (!root) return;
  const canvas = root.querySelector("canvas.scene");
  const sensor = root.querySelector("canvas.sensor");
  const ctx = canvas.getContext("2d");
  const sctx = sensor.getContext("2d");
  const $ = (s) => root.querySelector(s);
  const T = 0.34;            // tan of half the field of view as drawn (the NAC's real one is 0.0031: far too thin to see)
  const C = 511.5;           // middle of the 1024 x 1024 sensor, 0-based pixels
  const D = 9;               // the body's distance as drawn
  const fmt = (v) => Math.round(v).toLocaleString("en-US");
  const state = { frames: [], k: 0, yaw: -0.85, pitch: 0.32, tex: {}, raw: {}, sphere: null };

  // ---- the body's real surface map, sampled per pixel ------------------------------------------------------------
  function loadTexture(f) {
    if (state.tex[f.texture]) return;
    const im = new Image();
    state.tex[f.texture] = { ready: false };
    im.onload = () => {
      const c = document.createElement("canvas");
      c.width = im.naturalWidth; c.height = im.naturalHeight;
      const g = c.getContext("2d");
      g.drawImage(im, 0, 0);
      state.tex[f.texture] = { ready: true, w: c.width, h: c.height, px: g.getImageData(0, 0, c.width, c.height).data };
      state.sphere = null;
      draw();
    };
    im.src = f.texture;
  }
  // the globe as seen from the diagram's own view, its pixels from the map: a normal on screen turned back into the
  // diagram's axes (undoing the view's turn), then into the body's frame (world_to_body), to a longitude and latitude
  // (the map's middle is 0 degrees, east to the right, north up), lit by the Sun's direction
  function globe(rr, f) {
    const key = [Math.round(rr), state.yaw.toFixed(3), state.pitch.toFixed(3), state.k].join();
    if (state.sphere && state.sphere.key === key) return state.sphere.canvas;
    const t = state.tex[f.texture];
    const n = Math.max(8, Math.ceil(rr)) * 2, c = document.createElement("canvas");
    c.width = c.height = n;
    const g = c.getContext("2d"), img = g.createImageData(n, n), out = img.data;
    const M = f.world_to_body, sun = f.sun;
    const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw), cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const vx = (i + 0.5 - n / 2) / (n / 2), vy = -(j + 0.5 - n / 2) / (n / 2), q = 1 - vx * vx - vy * vy;
        if (q <= 0) continue;
        const vz = -Math.sqrt(q);
        // undo the pitch, then the yaw (proj below)
        const y1 = vy * cp + vz * sp, z1 = -vy * sp + vz * cp;
        const wx = vx * cy + z1 * sy, wz = -vx * sy + z1 * cy, wy = y1;
        const bx = M[0][0] * wx + M[0][1] * wy + M[0][2] * wz;
        const by = M[1][0] * wx + M[1][1] * wy + M[1][2] * wz;
        const bz = M[2][0] * wx + M[2][1] * wy + M[2][2] * wz;
        let a = 160;
        if (t && t.ready) {
          const lon = Math.atan2(by, bx), lat = Math.asin(Math.max(-1, Math.min(1, bz)));
          const u = Math.floor(((0.5 + lon / (2 * Math.PI)) % 1 + 1) % 1 * t.w), v = Math.min(t.h - 1, Math.floor((0.5 - lat / Math.PI) * t.h));
          a = t.px[(v * t.w + u) * 4];
        }
        const L = Math.max(0, wx * sun[0] + wy * sun[1] + wz * sun[2]);
        const o = (j * n + i) * 4, val = Math.min(255, a * (0.06 + 1.05 * L));
        out[o] = out[o + 1] = out[o + 2] = val;
        out[o + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    state.sphere = { key, canvas: c };
    return c;
  }

  // ---- 3D: orbit camera around the middle of the scene -------------------------------------------------------
  function view() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    return { w, h, f: Math.min(w, h) * 1.55, cx: w / 2, cy: h / 2 + 10, target: [0, 0, D * 0.52], dist: D * 1.9 + 4 };
  }
  function proj(p, v) {
    let x = p[0] - v.target[0], y = p[1] - v.target[1], z = p[2] - v.target[2];
    const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
    [x, z] = [x * cy - z * sy, x * sy + z * cy];
    const cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
    [y, z] = [y * cp - z * sp, y * sp + z * cp];
    z += v.dist;
    const s = v.f / z;
    return [v.cx + x * s, v.cy - y * s, s, z];
  }
  let V = null;
  function line(a, b, color, width, dash) {
    const p = proj(a, V), q = proj(b, V);
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    if (dash) ctx.setLineDash(dash);
    ctx.beginPath();
    ctx.moveTo(p[0], p[1]);
    ctx.lineTo(q[0], q[1]);
    ctx.stroke();
    ctx.restore();
  }
  function label(p, text, color, dx, dy, align) {
    const q = proj(p, V);
    ctx.save();
    ctx.font = "12px " + getComputedStyle(document.body).getPropertyValue("--mono");
    ctx.fillStyle = color;
    ctx.textAlign = align || "left";
    ctx.fillText(text, q[0] + (dx || 0), q[1] + (dy || 0));
    ctx.restore();
  }
  // a numbered badge that ties a part of the drawing to its step in the list beside it
  function badge(p, n, color, dx, dy) {
    const q = proj(p, V);
    ctx.save();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(q[0] + dx, q[1] + dy, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#0b1220";
    ctx.font = "bold 11px " + getComputedStyle(document.body).getPropertyValue("--mono");
    ctx.textAlign = "center";
    ctx.fillText(String(n), q[0] + dx, q[1] + dy + 4);
    ctx.restore();
  }

  function draw() {
    const f = state.frames[state.k];
    if (!f) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    V = view();
    const css = getComputedStyle(document.body);
    const ACC = css.getPropertyValue("--accent").trim(), WARM = css.getPropertyValue("--warm").trim();
    const DIM = "rgba(232,236,242,.35)", TXT = "rgba(232,236,242,.8)";
    const fx = (f.sample - C) / 512, fy = (f.line - C) / 512, rpx = f.radius_km / f.km * f.scale;
    const bx = fx * T * D, by = -fy * T * D, rWorld = rpx / 512 * T * D;
    const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => [a * T * D, b * T * D, D]);

    line([0, 0, 0], [0, 0, D * 1.25], DIM, 1, [3, 5]);
    // the body, with its real map, then the plane and rays over it
    const b = proj([bx, by, D], V), rr = Math.max(4, rWorld * b[2]);
    ctx.save();
    ctx.globalAlpha = 0.95;
    ctx.drawImage(globe(rr, f), b[0] - rr, b[1] - rr, rr * 2, rr * 2);
    ctx.restore();
    // 2: the plane facing the camera at the body's distance
    const k = 1.4, pts = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, c]) => proj([a * T * D * k, c * T * D * k, D], V));
    ctx.save();
    ctx.fillStyle = "rgba(138,182,255,.06)";
    ctx.strokeStyle = "rgba(138,182,255,.28)";
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
    badge([-T * D * k, -T * D * k, D], 2, "rgba(138,182,255,.9)", 0, 14);
    // 3: the four corner rays and the footprint they cut out of the plane
    corners.forEach((c) => line([0, 0, 0], [c[0] * 1.12, c[1] * 1.12, c[2] * 1.12], ACC, 1.3));
    const fp = corners.map((c) => proj(c, V));
    ctx.save();
    ctx.strokeStyle = ACC;
    ctx.lineWidth = 2;
    ctx.fillStyle = "rgba(138,182,255,.08)";
    ctx.beginPath();
    fp.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
    const names = ["(0, 1023)", "(1023, 1023)", "(1023, 0)", "(0, 0)"];
    corners.forEach((c, i) => label(c, names[i], ACC, c[0] < 0 ? -6 : 6, c[1] < 0 ? 16 : -6, c[0] < 0 ? "right" : "left"));
    badge([T * D * 0.55 * 1.12, T * D * 0.55 * 1.12, D * 0.55], 3, ACC, 0, -14);
    // 4: where the body's ray meets the plane, measured across and down the footprint
    line([-T * D, by, D], [T * D, by, D], WARM, 1, [4, 4]);
    line([bx, T * D, D], [bx, -T * D, D], WARM, 1, [4, 4]);
    badge([T * D, by, D], 4, WARM, 16, 0);
    // 1: the ray from Cassini to the body, with its length
    line([0, 0, 0], [bx, by, D], WARM, 2.2);
    ctx.save();
    ctx.fillStyle = WARM;
    ctx.beginPath();
    ctx.arc(b[0], b[1], 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    label([bx / 2, by / 2, D / 2], fmt(f.km) + " km", WARM, 8, -8);
    badge([bx * 0.3, by * 0.3, D * 0.3], 1, WARM, 0, 18);
    // Cassini at the origin: a small box with its dish
    const o = proj([0, 0, 0], V);
    ctx.save();
    ctx.fillStyle = "#cfd6df";
    ctx.fillRect(o[0] - 6, o[1] - 5, 12, 10);
    ctx.strokeStyle = "#cfd6df";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.ellipse(o[0] - 10, o[1], 4, 11, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    label([0, 0, 0], "Cassini", TXT, 0, 26, "center");
    label([bx, by, D], f.target, TXT, rr + 6, 4);
    drawSensor(f, rpx, ACC, WARM);
  }

  function drawSensor(f, rpx, ACC, WARM) {
    const dpr = window.devicePixelRatio || 1, S = sensor.clientWidth;
    sensor.style.height = S + "px";
    if (sensor.width !== Math.round(S * dpr) || sensor.height !== Math.round(S * dpr)) { sensor.width = sensor.height = Math.round(S * dpr); }
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sctx.clearRect(0, 0, S, S);
    const pad = 22, side = S - pad * 2, k = side / 1024;
    sctx.fillStyle = "#050505";
    sctx.fillRect(pad, pad, side, side);
    const im = state.raw[f.id];
    if (im && im.complete && im.naturalWidth) sctx.drawImage(im, pad, pad, side, side);
    // where SPICE says the body is: its center and its outline
    const x = pad + f.sample * k, y = pad + f.line * k;
    sctx.save();
    sctx.strokeStyle = WARM;
    sctx.setLineDash([4, 4]);
    sctx.lineWidth = 1;
    sctx.beginPath();
    sctx.moveTo(pad, y); sctx.lineTo(pad + side, y);
    sctx.moveTo(x, pad); sctx.lineTo(x, pad + side);
    sctx.stroke();
    sctx.setLineDash([]);
    sctx.lineWidth = 1.5;
    sctx.beginPath();
    sctx.arc(x, y, rpx * k, 0, Math.PI * 2);
    sctx.stroke();
    sctx.fillStyle = WARM;
    sctx.beginPath();
    sctx.arc(x, y, 4, 0, Math.PI * 2);
    sctx.fill();
    sctx.restore();
    sctx.strokeStyle = ACC;
    sctx.lineWidth = 1.5;
    sctx.strokeRect(pad, pad, side, side);
    sctx.font = "10px " + getComputedStyle(document.body).getPropertyValue("--mono");
    sctx.fillStyle = "rgba(232,236,242,.5)";
    sctx.textAlign = "left";
    sctx.fillText("0", pad - 2, pad - 6);
    sctx.textAlign = "right";
    sctx.fillText("1023", pad + side + 2, pad - 6);
  }

  function readout() {
    const f = state.frames[state.k];
    const rpx = f.radius_km / f.km * f.scale;
    root.querySelectorAll("[data-p]").forEach((el) => {
      const v = { km: fmt(f.km) + " km", light: f.light_s.toFixed(1) + " s", across: (f.sample / 1024 * 100).toFixed(1) + "%",
        down: (f.line / 1024 * 100).toFixed(1) + "%", sample: fmt(f.sample), line: fmt(f.line), radius: fmt(rpx) + " px",
        name: f.target, id: f.id, scale: fmt(f.scale) }[el.dataset.p];
      if (v != null) el.textContent = v;
    });
    root.querySelectorAll(".presets button").forEach((b, i) => b.setAttribute("aria-pressed", i === state.k));
  }
  function use(k) {
    state.k = k;
    state.sphere = null;
    loadTexture(state.frames[k]);
    readout();
    draw();
  }

  // drag to turn the view (dragging up tips the scene's near side up, as when turning an object in the hand)
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY, state.yaw, state.pitch]; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    state.yaw = drag[2] + (e.clientX - drag[0]) * 0.008;
    state.pitch = Math.max(-1.2, Math.min(1.2, drag[3] - (e.clientY - drag[1]) * 0.006));
    draw();
  });
  canvas.addEventListener("pointerup", () => (drag = null));
  window.addEventListener("resize", draw);

  fetch("pointing.json").then((r) => r.json()).then((frames) => {
    state.frames = frames;
    const box = $(".presets");
    frames.forEach((f, i) => {
      const im = new Image();
      im.onload = draw;
      im.src = `img/point-${f.id}.jpg`;
      state.raw[f.id] = im;
      const b = document.createElement("button");
      b.textContent = `${f.target} · ${f.date || f.time.slice(0, 8)}`;
      b.onclick = () => use(i);
      box.appendChild(b);
    });
    use(0);
  });
})();
