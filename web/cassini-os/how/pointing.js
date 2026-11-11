// The pointing diagram on the "How the pictures are made" page: roughly how SPICE says where a body lands on
// Cassini's sensor. Cassini at the origin looks along +z; the body sits at (bx, by, D). A plane facing the camera at
// the body's distance, the four rays through the sensor's corners meeting it, and where the body's own ray lands
// among those four corners is where the body lands on the sensor. bootleg_autonav.project does the same sum without
// the plane: sample = 511.5 - x / z * scale, line = 511.5 - y / z * scale (scale = focal length / pixel size).
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
  const SCALE = 166953.3;    // NAC focal length / pixel size (cas_iss_v10.ti), pixels per unit of tan off the axis
  const C = 511.5;           // middle of the 1024 x 1024 sensor, 0-based pixels

  // presets: real numbers from the geometry cache (bootleg_autonav.find_target) for real frames
  const PRESETS = {
    rhea: { name: "Rhea", id: "N1484528732_1", when: "16 Jan 2005", km: 495886, radius: 764, sample: 507.9, line: 509.2,
            img: "img/point-rhea.jpg", note: "Rhea sits almost dead center, 257 pixels across in radius." },
    jupiter: { name: "Jupiter", id: "N1356755453_1", when: "29 Dec 2000", km: 9865102, radius: 71492, sample: 1297.4, line: -307.0,
               img: "img/point-jupiter.jpg", note: "Jupiter's center is off the sensor, up and to the right: only its lower-left edge is in the picture. The center is still known exactly." },
  };
  const state = { preset: "rhea", fx: 0, fy: 0, D: 9, step: 1, yaw: -0.95, pitch: 0.38, km: 0, radius: 0, img: null };
  const imgs = {};
  for (const k in PRESETS) {
    const im = new Image();
    im.onload = draw;
    im.src = PRESETS[k].img;
    imgs[k] = im;
  }

  function usePreset(k) {
    const p = PRESETS[k];
    state.preset = k;
    state.fx = (p.sample - C) / 512;
    state.fy = (p.line - C) / 512;
    state.km = p.km;
    state.radius = p.radius;
    state.D = 9;
    $(".fx").value = state.fx;
    $(".fy").value = state.fy;
    $(".dist").value = 1;
    root.querySelectorAll(".presets button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.preset === k));
    $(".preset-note").textContent = p.note;
    draw();
  }

  // ---- 3D: orbit camera around the middle of the scene -------------------------------------------------------
  function view() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    return { w, h, f: Math.min(w, h) * 1.25, cx: w / 2, cy: h / 2 + 10, target: [0, 0, state.D * 0.52], dist: state.D * 1.9 + 4 };
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
  let curV = null;
  function line(a, b, color, width, dash) {
    const v = curV;
    const p = proj(a, v), q = proj(b, v);
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
  function label(p, v, text, color, dx, dy, align) {
    const q = proj(p, v);
    ctx.save();
    ctx.font = "12px " + getComputedStyle(document.body).getPropertyValue("--mono");
    ctx.fillStyle = color;
    ctx.textAlign = align || "left";
    ctx.fillText(text, q[0] + (dx || 0), q[1] + (dy || 0));
    ctx.restore();
  }

  function numbers() {
    const D = state.D, scaleDist = state.km * (D / 9) / 9;   // km per drawn unit, the preset's distance at D = 9
    const bx = state.fx * T * D, by = -state.fy * T * D;
    const sample = C + state.fx * 512, line = C + state.fy * 512;
    const km = state.km * (D / 9);
    const rpx = state.radius / km * SCALE;
    return { bx, by, D, sample, line, km, rpx, rWorld: rpx / 512 * T * D, scaleDist };
  }

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const v = (curV = view()), n = numbers(), s = state.step, D = n.D;
    const css = getComputedStyle(document.body);
    const ACC = css.getPropertyValue("--accent").trim(), WARM = css.getPropertyValue("--warm").trim();
    const DIM = "rgba(232,236,242,.35)", TXT = "rgba(232,236,242,.8)";
    const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => [a * T * D, b * T * D, D]);

    // camera axis, faint
    line([0, 0, 0], [0, 0, D * 1.25], DIM, 1, [3, 5]);
    // 2: the plane facing the camera at the body's distance (drawn a little wider than the footprint)
    if (s >= 2) {
      const k = 1.4, pts = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => proj([a * T * D * k, b * T * D * k, D], v));
      ctx.save();
      ctx.fillStyle = "rgba(138,182,255,.07)";
      ctx.strokeStyle = "rgba(138,182,255,.28)";
      ctx.beginPath();
      pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.restore();
      label([T * D * k, -T * D * k, D], v, "plane at the body's distance", "rgba(138,182,255,.75)", 6, 14);
    }
    // 3: the four corner rays and the footprint they cut out of the plane
    if (s >= 3) {
      corners.forEach((c) => line([0, 0, 0], [c[0] * 1.12, c[1] * 1.12, c[2] * 1.12], ACC, 1.3));
      const pts = corners.map((c) => proj(c, v));
      ctx.save();
      ctx.strokeStyle = ACC;
      ctx.lineWidth = 2;
      ctx.fillStyle = "rgba(138,182,255,.10)";
      ctx.beginPath();
      pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.restore();
      // corner names in sensor pixels
      const names = ["(0, 1023)", "(1023, 1023)", "(1023, 0)", "(0, 0)"];
      corners.forEach((c, i) => label(c, v, names[i], ACC, c[0] < 0 ? -6 : 6, c[1] < 0 ? 16 : -6, c[0] < 0 ? "right" : "left"));
    }
    // the body, a shaded sphere (lit from the left), behind the lines that pass in front of it
    const b = proj([n.bx, n.by, D], v);
    const rr = Math.max(4, n.rWorld * b[2]);
    ctx.save();
    const g = ctx.createRadialGradient(b[0] - rr * 0.4, b[1] - rr * 0.35, rr * 0.1, b[0], b[1], rr);
    g.addColorStop(0, state.preset === "jupiter" ? "#e9dcc4" : "#dcdcdc");
    g.addColorStop(0.75, state.preset === "jupiter" ? "#8f7a5f" : "#6c6c6c");
    g.addColorStop(1, "#1d1d1d");
    ctx.fillStyle = g;
    ctx.globalAlpha = s >= 2 ? 0.92 : 1;
    ctx.beginPath();
    ctx.arc(b[0], b[1], rr, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    // 1: the ray from Cassini to the body, with its length
    line([0, 0, 0], [n.bx, n.by, D], WARM, 2.2);
    ctx.save();
    ctx.fillStyle = WARM;
    ctx.beginPath();
    ctx.arc(b[0], b[1], 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    label([n.bx / 2, n.by / 2, D / 2], v, Math.round(n.km).toLocaleString("en-US") + " km", WARM, 8, -8);
    if (s >= 4) {
      // where the body's ray meets the plane, measured across and down the footprint
      const left = [-T * D, n.by, D], right = [T * D, n.by, D], top = [n.bx, T * D, D], bottom = [n.bx, -T * D, D];
      line(left, right, WARM, 1, [4, 4]);
      line(top, bottom, WARM, 1, [4, 4]);
    }
    // Cassini at the origin: a small box with its dish facing the body
    const o = proj([0, 0, 0], v);
    ctx.save();
    ctx.fillStyle = "#cfd6df";
    ctx.fillRect(o[0] - 6, o[1] - 5, 12, 10);
    ctx.strokeStyle = "#cfd6df";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.ellipse(o[0] - 10, o[1], 4, 11, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    label([0, 0, 0], v, "Cassini", TXT, 0, 26, "center");
    label([n.bx, n.by, D], v, PRESETS[state.preset].name, TXT, rr + 6, 4);
    drawSensor(n, ACC, WARM);
    readout(n);
  }

  function drawSensor(n, ACC, WARM) {
    const dpr = window.devicePixelRatio || 1, S = sensor.clientWidth;
    sensor.style.height = S + "px";
    if (sensor.width !== Math.round(S * dpr) || sensor.height !== Math.round(S * dpr)) { sensor.width = sensor.height = Math.round(S * dpr); }
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sctx.clearRect(0, 0, S, S);
    const pad = 26, side = S - pad * 2, k = side / 1024;
    sctx.fillStyle = "#050505";
    sctx.fillRect(pad, pad, side, side);
    const im = imgs[state.preset];
    // the real picture only where the body is where the picture has it (the preset's own place and distance)
    const p = PRESETS[state.preset];
    const real = Math.abs(n.sample - p.sample) < 1 && Math.abs(n.line - p.line) < 1 && Math.abs(state.D - 9) < 1e-6;
    if (state.step >= 4 && im.complete && im.naturalWidth && real) {
      sctx.globalAlpha = 0.9;
      sctx.drawImage(im, pad, pad, side, side);
      sctx.globalAlpha = 1;
    } else if (state.step >= 4) {
      // the body's outline where this place and distance put it
      sctx.save();
      sctx.beginPath();
      sctx.rect(pad, pad, side, side);
      sctx.clip();
      sctx.strokeStyle = "rgba(232,236,242,.5)";
      sctx.setLineDash([3, 3]);
      sctx.beginPath();
      sctx.arc(pad + n.sample * k, pad + n.line * k, n.rpx * k, 0, Math.PI * 2);
      sctx.stroke();
      sctx.restore();
    }
    sctx.strokeStyle = ACC;
    sctx.lineWidth = 1.5;
    sctx.strokeRect(pad, pad, side, side);
    sctx.font = "10px " + getComputedStyle(document.body).getPropertyValue("--mono");
    sctx.fillStyle = "rgba(232,236,242,.5)";
    sctx.textAlign = "left";
    sctx.fillText("0", pad - 2, pad - 6);
    sctx.textAlign = "right";
    sctx.fillText("1023", pad + side + 2, pad - 6);
    sctx.fillText("sample →", pad + side, pad + side + 16);
    if (state.step < 4) {
      sctx.textAlign = "center";
      sctx.fillText("the sensor, 1024 × 1024", pad + side / 2, pad + side / 2);
      return;
    }
    // the dot, or an arrow at the edge pointing to it when it is off the sensor
    let x = pad + n.sample * k, y = pad + n.line * k;
    const inside = n.sample >= 0 && n.sample <= 1023 && n.line >= 0 && n.line <= 1023;
    sctx.strokeStyle = WARM;
    sctx.fillStyle = WARM;
    sctx.setLineDash([4, 4]);
    sctx.lineWidth = 1;
    const cx = Math.min(Math.max(x, pad), pad + side), cy = Math.min(Math.max(y, pad), pad + side);
    sctx.beginPath();
    sctx.moveTo(pad, cy); sctx.lineTo(pad + side, cy);
    sctx.moveTo(cx, pad); sctx.lineTo(cx, pad + side);
    sctx.stroke();
    sctx.setLineDash([]);
    if (inside) {
      sctx.beginPath();
      sctx.arc(x, y, 4.5, 0, Math.PI * 2);
      sctx.fill();
    } else {
      const a = Math.atan2(y - cy, x - cx);
      sctx.beginPath();
      sctx.moveTo(cx + Math.cos(a) * 9, cy + Math.sin(a) * 9);
      sctx.lineTo(cx + Math.cos(a + 2.5) * 9, cy + Math.sin(a + 2.5) * 9);
      sctx.lineTo(cx + Math.cos(a - 2.5) * 9, cy + Math.sin(a - 2.5) * 9);
      sctx.closePath();
      sctx.fill();
    }
  }

  function readout(n) {
    const f = (v) => Math.round(v).toLocaleString("en-US");
    const inside = n.sample >= 0 && n.sample <= 1023 && n.line >= 0 && n.line <= 1023;
    $(".r-dist").textContent = f(n.km) + " km";
    $(".r-across").textContent = state.step >= 4 ? (n.sample / 1024 * 100).toFixed(1) + "%" : "–";
    $(".r-down").textContent = state.step >= 4 ? (n.line / 1024 * 100).toFixed(1) + "%" : "–";
    $(".r-pixel").textContent = state.step >= 4 ? `sample ${f(n.sample)}, line ${f(n.line)}` + (inside ? "" : " (off the sensor)") : "–";
    $(".r-radius").textContent = state.step >= 4 ? f(n.rpx) + " px" : "–";
    root.querySelectorAll(".steps button").forEach((b) => b.setAttribute("aria-pressed", +b.dataset.step === state.step));
    root.querySelectorAll(".step-text").forEach((p) => (p.hidden = +p.dataset.step !== state.step));
  }

  // ---- controls ------------------------------------------------------------------------------------------------
  root.querySelectorAll(".steps button").forEach((b) => b.addEventListener("click", () => { stopPlay(); state.step = +b.dataset.step; draw(); }));
  root.querySelectorAll(".presets button").forEach((b) => b.addEventListener("click", () => usePreset(b.dataset.preset)));
  $(".fx").addEventListener("input", (e) => { state.fx = +e.target.value; draw(); });
  $(".fy").addEventListener("input", (e) => { state.fy = +e.target.value; draw(); });
  $(".dist").addEventListener("input", (e) => { state.D = 9 * +e.target.value; draw(); });
  let timer = null;
  function stopPlay() { if (timer) clearInterval(timer); timer = null; $(".play").textContent = "Play the steps"; }
  $(".play").addEventListener("click", () => {
    if (timer) return stopPlay();
    state.step = 1;
    draw();
    $(".play").textContent = "Stop";
    timer = setInterval(() => { if (state.step >= 5) return stopPlay(); state.step++; draw(); }, 2600);
  });
  // drag to turn the view
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY, state.yaw, state.pitch]; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    state.yaw = drag[2] + (e.clientX - drag[0]) * 0.008;
    state.pitch = Math.max(-1.2, Math.min(1.2, drag[3] + (e.clientY - drag[1]) * 0.006));
    draw();
  });
  canvas.addEventListener("pointerup", () => (drag = null));
  window.addEventListener("resize", draw);
  usePreset("rhea");
})();
