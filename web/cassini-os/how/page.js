// The "How the pictures are made" page: the flow at the top, the filter chart, the compare sliders and the mosaic
// scrubber. Every picture is one the pipeline drew (make_images.py); pictures.json holds the server's own numbers.
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const fmt = (v) => Math.round(v).toLocaleString("en-US");
  let facts = {};

  // ---- compare slider: picture a on the left of the bar, b on the right -----------------------------------------
  function compare(el, a, b, left, right) {
    el.innerHTML = "";
    const under = new Image();
    under.src = b;
    under.alt = right;
    const top = document.createElement("div");
    top.className = "top";
    const over = new Image();
    over.src = a;
    over.alt = left;
    top.appendChild(over);
    const bar = document.createElement("div");
    bar.className = "bar";
    const l = document.createElement("span"), r = document.createElement("span");
    l.className = "lab l"; l.textContent = left;
    r.className = "lab r"; r.textContent = right;
    el.append(under, top, bar, l, r);
    let at = el._at == null ? 0.5 : el._at;
    function set(f) {
      at = el._at = Math.max(0, Math.min(1, f));
      top.style.width = at * 100 + "%";
      bar.style.left = at * 100 + "%";
      over.style.height = el.clientHeight + "px";
    }
    under.onload = () => set(at);
    set(at);
    el.setAttribute("tabindex", "0");
    el.setAttribute("role", "slider");
    el.setAttribute("aria-label", `${left} on the left, ${right} on the right`);
    el.onpointerdown = (e) => { el.setPointerCapture(e.pointerId); move(e); el.onpointermove = move; };
    el.onpointerup = () => (el.onpointermove = null);
    el.onkeydown = (e) => { if (e.key === "ArrowLeft") set(at - 0.05); if (e.key === "ArrowRight") set(at + 0.05); };
    function move(e) { const r = el.getBoundingClientRect(); set((e.clientX - r.left) / r.width); }
    window.addEventListener("resize", () => set(at));
  }

  // ---- the flow (raw frames + SPICE -> color, body location -> mosaic), the poster GIF -------------------------
  const flow = { n: 1, timer: null };
  const JUP_TIMES = ["04:19", "04:27", "04:34", "04:41", "04:49", "04:56", "05:04", "05:11", "05:19"];
  // preload every picture of the flow so it plays without gaps
  for (let n = 1; n <= 9; n++) for (const k of ["raw-CB2", "raw-GRN", "raw-BL1", "color", "mosaic"]) new Image().src = `img/jup-${n}-${k}.jpg`;
  function showFlow(n) {
    flow.n = n;
    $$("[data-flow]").forEach((img) => (img.src = `img/jup-${n}-${img.dataset.flow}.jpg`));
    $(".flow-n").value = n;
    $("#flow .count").textContent = `pointing ${n} of 9`;
    const s = facts[`jup-${n}-spice`];
    $('[data-spice="time"]').textContent = "2000-12-29 " + JUP_TIMES[n - 1];
    if (!s) return;
    $('[data-spice="km"]').textContent = fmt(s.km) + " km";
    $('[data-spice="sample"]').textContent = fmt(s.sample);
    $('[data-spice="line"]').textContent = fmt(s.line);
    $('[data-spice="north"]').textContent = s.north.toFixed(1) + "°";
    // Jupiter's disk on the sensor's own pixels: its center where SPICE puts it, its radius from the range
    const r = 71492 / s.km * 166953.3;
    const disk = $('[data-where="disk"]'), dot = $('[data-where="dot"]'), ray = $('[data-where="ray"]');
    disk.setAttribute("cx", s.sample); disk.setAttribute("cy", s.line); disk.setAttribute("r", r);
    dot.setAttribute("cx", s.sample); dot.setAttribute("cy", s.line);
    ray.setAttribute("x2", s.sample); ray.setAttribute("y2", s.line);
    $('[data-where="img"]').setAttribute("href", `img/jup-${n}-raw-GRN.jpg`);
  }
  function playFlow(on) {
    clearInterval(flow.timer);
    flow.timer = on ? setInterval(() => showFlow(flow.n % 9 + 1), 1700) : null;
    $(".flow-play").setAttribute("aria-pressed", on);
    $(".flow-play").textContent = on ? "Pause" : "Play";
  }
  $(".flow-play").addEventListener("click", () => playFlow(!flow.timer));
  $(".flow-n").addEventListener("input", (e) => { playFlow(false); showFlow(+e.target.value); });

  // ---- the filter chart --------------------------------------------------------------------------------------
  // effective wavelengths (nm) with the other wheel clear, from filter_calibration.csv (the NAC's)
  const FILTERS = [["UV1", 267], ["UV2", 307], ["UV3", 343], ["BL2", 441], ["BL1", 457], ["GRN", 569], ["CB1", 620],
    ["MT1", 619], ["RED", 651], ["HAL", 656], ["MT2", 727], ["CB2", 751], ["IR1", 751], ["IR2", 861], ["MT3", 889],
    ["IR3", 926], ["CB3", 938], ["IR4", 1002]];
  const USED = ["RED", "GRN", "BL1"];
  function filterChart() {
    const W = 1000, H = 130, x = (nm) => 30 + (nm - 250) / (1050 - 250) * (W - 60);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cassini narrow-angle camera filters from 267 to 1002 nm">`;
    s += `<defs><linearGradient id="vis" x1="0" x2="1"><stop offset="0" stop-color="#7b3cff"/><stop offset=".2" stop-color="#3c6bff"/><stop offset=".4" stop-color="#3cd27a"/><stop offset=".58" stop-color="#f3e23c"/><stop offset=".75" stop-color="#ff8a3c"/><stop offset="1" stop-color="#e3383c"/></linearGradient></defs>`;
    s += `<rect x="${x(380)}" y="96" width="${x(700) - x(380)}" height="6" rx="3" fill="url(#vis)" opacity=".85"/>`;
    s += `<text x="${x(540)}" y="122" fill="rgba(232,236,242,.55)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">what the eye sees</text>`;
    s += `<text x="${x(300)}" y="122" fill="rgba(232,236,242,.4)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">ultraviolet</text>`;
    s += `<text x="${x(880)}" y="122" fill="rgba(232,236,242,.4)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">infrared</text>`;
    for (let nm = 300; nm <= 1000; nm += 100) {
      s += `<line x1="${x(nm)}" x2="${x(nm)}" y1="86" y2="91" stroke="rgba(232,236,242,.3)"/><text x="${x(nm)}" y="82" fill="rgba(232,236,242,.35)" font-size="10" text-anchor="middle" font-family="Menlo, monospace">${nm}</text>`;
    }
    const rows = [];
    FILTERS.forEach(([name, nm]) => {
      // stack labels that would overlap on rows
      let row = 0;
      while (rows[row] != null && x(nm) - rows[row] < 44) row++;
      rows[row] = x(nm);
      const used = USED.includes(name), y = 52 - row * 20;
      s += `<g><title>${name} · ${nm} nm</title><line x1="${x(nm)}" x2="${x(nm)}" y1="${y + 4}" y2="94" stroke="${used ? "#ffc478" : "rgba(138,182,255,.45)"}" stroke-width="${used ? 2 : 1}"/>`;
      s += `<text x="${x(nm)}" y="${y}" fill="${used ? "#ffc478" : "rgba(232,236,242,.75)"}" font-size="12" text-anchor="middle" font-family="Menlo, monospace">${name}</text></g>`;
    });
    $("#filters").innerHTML = s + "</svg>";
  }

  // ---- one pipeline step off, on its own example --------------------------------------------------------------
  const STEPS = [
    { key: "fill", a: "raw", al: "raw", name: "Whole pipeline", note: "Dione, 4 May 2006: the archive's frame next to the same frame through the pipeline: lost lines filled, calibrated and turned north up." },
    { key: "fill", a: "off", al: "fill off", name: "Fill lost lines", note: "The same frame through the pipeline with only the fill turned off: the lines lost in transmission stay as gaps. On, they are filled from the lines above and below." },
    { key: "twohz", a: "off", al: "2 Hz off", name: "2 Hz banding", note: "Iapetus, 7 October 2004, a faint frame. The camera's electronics picked up a 2 Hz hum that shows as horizontal bands; it is measured line by line, from the frame's own dark sky where there is enough of it, and taken out." },
  ];
  function steps() {
    const chips = $("#step-chips");
    STEPS.forEach((s, i) => {
      const b = document.createElement("button");
      b.textContent = s.name;
      b.onclick = () => pick(i);
      chips.appendChild(b);
    });
    function pick(i) {
      $$("button", chips).forEach((b, j) => b.setAttribute("aria-pressed", i === j));
      const s = STEPS[i];
      compare($("#step-compare"), `img/step-${s.key}-${s.a}.jpg`, `img/step-${s.key}-on.jpg`, s.al, "pipeline");
      $("#step-note").textContent = s.note;
    }
    pick(0);
  }

  // ---- color: lined up or not, natural color or filters straight, calibrated or not ----------------------------
  const COLOR = [
    { name: "Lining up", a: "rhea-color-noalign", al: "not lined up", note: "Off: the channels as the camera took them, with red and blue fringes at the edges." },
    { name: "Natural color", a: "rhea-color-rawfilters", al: "filters straight", note: "Filters straight: each filter in one channel, without the color matrix." },
    { name: "Calibrated", a: "rhea-color-nocal", al: "not calibrated", note: "Not calibrated: each filter on its own stretch." },
  ];
  function colors() {
    const chips = $("#color-chips");
    COLOR.forEach((c, i) => {
      const b = document.createElement("button");
      b.textContent = c.name;
      b.onclick = () => pick(i);
      chips.appendChild(b);
    });
    function pick(i) {
      $$("button", chips).forEach((b, j) => b.setAttribute("aria-pressed", i === j));
      const c = COLOR[i];
      compare($("#color-compare"), `img/${c.a}.jpg`, "img/rhea-color.jpg", c.al, "pipeline");
      $("#color-note").textContent = c.note;
    }
    pick(0);
  }

  // ---- mosaic scrubber ------------------------------------------------------------------------------------------
  function mosaic() {
    const set = (n) => { $("#mos-img").src = `img/jup-${n}-mosaic.jpg`; $("#mos-count").textContent = `${n} of 9 pointings`; };
    $("#mos-n").addEventListener("input", (e) => set(+e.target.value));
    set(9);
  }

  filterChart();
  steps();
  colors();
  mosaic();
  const c = $("#center-compare");
  compare(c, c.dataset.a, c.dataset.b, c.dataset.left, c.dataset.right);
  fetch("pictures.json").then((r) => r.json()).then((j) => { facts = j; showFlow(flow.n); }).catch(() => showFlow(flow.n));
  showFlow(1);
  playFlow(!matchMedia("(prefers-reduced-motion: reduce)").matches);
})();
