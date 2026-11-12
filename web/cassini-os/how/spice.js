// The SPICE section of the "How the pictures are made" page: three small animations, each drawn from real SPICE output
// - where things are (SPK): Cassini and the moons over three weeks around 4 Jan 2008, from above Saturn's pole (spice.json)
// - which way Cassini faced (CK): the narrow-angle camera's footprint stepping over Jupiter, 29 Dec 2000 (pictures.json,
//   the geometry cache's place of Jupiter in each frame)
// - a body's size and spin (PCK): Dione, its radii and its turn of 131.5 degrees a day (spice.json), on its surface map
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const css = getComputedStyle(document.body);
  const ACC = css.getPropertyValue("--accent").trim() || "#8ab6ff", WARM = css.getPropertyValue("--warm").trim() || "#ffc478";
  const MONO = css.getPropertyValue("--mono");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function fit(canvas) {
    const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return [g, w, h];
  }
  // run draw(t) while the canvas is on screen
  function animate(canvas, draw) {
    let on = false, start = performance.now();
    new IntersectionObserver((es) => { on = es[0].isIntersecting; if (on) requestAnimationFrame(loop); }).observe(canvas);
    function loop(now) {
      draw(reduced ? 0 : (now - start) / 1000);
      if (on && !reduced) requestAnimationFrame(loop);
    }
    draw(0);
  }

  Promise.all([fetch("spice.json").then((r) => r.json()), fetch("pictures.json").then((r) => r.json())]).then(([sp, pics]) => {
    spk(sp);
    ck(pics);
    pck(sp);
  });

  // ---- SPK: where things are ---------------------------------------------------------------------------------------
  function spk(sp) {
    const canvas = $("#spk"), n = sp.cassini.length;
    let ext = 0;
    sp.cassini.forEach(([x, y]) => (ext = Math.max(ext, Math.abs(x), Math.abs(y))));
    Object.values(sp.moons).forEach((t) => t.forEach(([x, y]) => (ext = Math.max(ext, Math.abs(x), Math.abs(y)))));
    animate(canvas, (t) => {
      const [g, w, h] = fit(canvas), s = (Math.min(w, h) / 2 - 14) / ext, cx = w / 2, cy = h / 2;
      const P = ([x, y]) => [cx + x * s, cy - y * s];
      // the moment loops through the three weeks, resting on the Dione frame
      const cyc = 10, u = (t % cyc) / cyc, k = Math.min(n - 1, Math.floor(u * n));
      // orbits (the moons' whole tracks) and Cassini's path so far
      Object.entries(sp.moons).forEach(([name, tr]) => {
        g.strokeStyle = "rgba(232,236,242,.14)";
        g.beginPath();
        tr.forEach((p, i) => { const q = P(p); i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]); });
        g.stroke();
      });
      g.strokeStyle = "rgba(138,182,255,.35)";
      g.beginPath();
      sp.cassini.forEach((p, i) => { const q = P(p); i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]); });
      g.stroke();
      // Saturn
      g.fillStyle = "#d9c9a3";
      g.beginPath();
      g.arc(cx, cy, Math.max(3, sp.saturn_radius * s), 0, Math.PI * 2);
      g.fill();
      // the moons and Cassini at moment k
      g.font = "11px " + MONO;
      Object.entries(sp.moons).forEach(([name, tr]) => {
        const q = P(tr[k]);
        g.fillStyle = name === "Dione" ? WARM : "#e8ecf2";
        g.beginPath();
        g.arc(q[0], q[1], name === "Titan" ? 4 : 2.6, 0, Math.PI * 2);
        g.fill();
        if (name === "Titan" || name === "Dione") g.fillText(name, q[0] + 6, q[1] - 4);
      });
      const c = P(sp.cassini[k]), d = P(sp.moons.Dione[k]);
      g.strokeStyle = WARM;
      g.setLineDash([4, 4]);
      g.beginPath(); g.moveTo(c[0], c[1]); g.lineTo(d[0], d[1]); g.stroke();
      g.setLineDash([]);
      g.fillStyle = ACC;
      g.beginPath(); g.arc(c[0], c[1], 4, 0, Math.PI * 2); g.fill();
      g.fillText("Cassini", c[0] + 7, c[1] + 12);
      const day = new Date(Date.parse(sp.start + "Z") + k * sp.step_h * 3600e3);
      g.fillStyle = "rgba(232,236,242,.6)";
      g.fillText(day.toISOString().slice(0, 10), 10, h - 10);
    });
  }

  // ---- CK: which way the camera pointed ----------------------------------------------------------------------------
  function ck(pics) {
    const canvas = $("#ck"), N = 9, frames = [];
    for (let i = 1; i <= N; i++) if (pics[`jup-${i}-spice`]) frames.push(pics[`jup-${i}-spice`]);
    const TIMES = ["04:19", "04:27", "04:34", "04:41", "04:49", "04:56", "05:04", "05:11", "05:19"];
    animate(canvas, (t) => {
      const [g, w, h] = fit(canvas), f0 = frames[0];
      if (!f0) return;
      const R = 71492 / f0.km * 166953.3, s = Math.min(w, h) / 2 / (R + 900), k = Math.floor(t / 0.9) % (N + 3);
      g.save();
      g.translate(w / 2, h / 2);
      g.scale(s, s);
      // Jupiter, north up
      g.fillStyle = "rgba(255,196,120,.10)";
      g.strokeStyle = "rgba(255,196,120,.65)";
      g.lineWidth = 2 / s;
      g.beginPath(); g.arc(0, 0, R, 0, Math.PI * 2); g.fill(); g.stroke();
      // each pointing's sensor square where the camera pointed: Jupiter's place on the sensor turned back to north up
      frames.slice(0, Math.min(k + 1, N)).forEach((f, i) => {
        g.save();
        g.rotate(-f.north * Math.PI / 180);
        g.translate(-f.sample, -f.line);
        g.strokeStyle = i === Math.min(k, N - 1) ? ACC : "rgba(138,182,255,.35)";
        g.lineWidth = (i === Math.min(k, N - 1) ? 3 : 1.5) / s;
        g.strokeRect(0, 0, 1024, 1024);
        g.restore();
      });
      g.restore();
      g.font = "11px " + MONO;
      g.fillStyle = "rgba(232,236,242,.6)";
      g.fillText(`2000-12-29 ${TIMES[Math.min(k, N - 1)]} UTC · pointing ${Math.min(k + 1, N)} of 9`, 10, h - 10);
    });
  }

  // ---- PCK: a body's size and spin ---------------------------------------------------------------------------------
  function pck(sp) {
    const canvas = $("#pck"), im = new Image();
    let tex = null;
    im.onload = () => {
      const c = document.createElement("canvas");
      c.width = im.naturalWidth; c.height = im.naturalHeight;
      const g = c.getContext("2d");
      g.drawImage(im, 0, 0);
      tex = { w: c.width, h: c.height, px: g.getImageData(0, 0, c.width, c.height).data };
    };
    im.src = "../data/textures/1k/dione.webp";
    const R = sp.dione.radii_km, spin = sp.dione.spin_deg_per_day, tilt = 0.35;
    const sun = [-0.55, 0.25, -0.8];
    let buf = null;
    animate(canvas, (t) => {
      const [g, w, h] = fit(canvas), r = Math.floor(Math.min(w, h) * 0.34), n = r * 2;
      if (!buf || buf.width !== n) { buf = document.createElement("canvas"); buf.width = buf.height = n; }
      const bg = buf.getContext("2d"), img = bg.createImageData(n, n), out = img.data;
      // one turn every 12 s on screen (Dione's real day is 360 / spin days)
      const lon0 = (t / 12) * 2 * Math.PI, ct = Math.cos(tilt), st = Math.sin(tilt);
      for (let j = 0; j < n; j++) {
        for (let i = 0; i < n; i++) {
          const x = (i + 0.5 - r) / r, y = -(j + 0.5 - r) / r, q = 1 - x * x - y * y;
          if (q <= 0) continue;
          const z = -Math.sqrt(q);                         // towards the viewer
          // body frame: tip the pole towards the viewer, then spin about it
          const by = y * ct - z * st, bz = y * st + z * ct; // bz along the viewer's line after the tilt
          const lat = Math.asin(Math.max(-1, Math.min(1, by)));
          const lon = Math.atan2(x, -bz) + lon0;
          let a = 170;
          if (tex) {
            const u = Math.floor(((0.5 + lon / (2 * Math.PI)) % 1 + 1) % 1 * tex.w), v = Math.min(tex.h - 1, Math.floor((0.5 - lat / Math.PI) * tex.h));
            a = tex.px[(v * tex.w + u) * 4];
          }
          const L = Math.max(0, (x * sun[0] + y * sun[1] + z * sun[2]) / Math.hypot(...sun));
          const o = (j * n + i) * 4, val = Math.min(255, a * (0.12 + 1.0 * L));
          out[o] = out[o + 1] = out[o + 2] = val;
          out[o + 3] = 255;
        }
      }
      bg.putImageData(img, 0, 0);
      const cx = w / 2, cy = h / 2 + 4;
      g.drawImage(buf, cx - r, cy - r);
      // the spin axis through the poles, tipped like the globe
      g.strokeStyle = WARM;
      g.lineWidth = 1.5;
      g.setLineDash([4, 4]);
      g.beginPath(); g.moveTo(cx, cy - r * ct - 28); g.lineTo(cx, cy + r * ct + 28); g.stroke();
      g.setLineDash([]);
      // the radius
      g.strokeStyle = ACC;
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + r, cy); g.stroke();
      g.font = "11px " + MONO;
      g.fillStyle = ACC;
      g.fillText(`${Math.round((R[0] + R[1] + R[2]) / 3)} km`, cx + r * 0.35, cy - 6);
      g.fillStyle = WARM;
      g.fillText("north pole", cx + 8, cy - r * ct - 18);
      g.fillStyle = "rgba(232,236,242,.6)";
      g.fillText(`Dione · one turn every ${(360 / spin).toFixed(2)} days`, 10, h - 10);
    });
  }
})();
