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
    // one resize listener per slider, however often its pictures change
    if (el._resize) window.removeEventListener("resize", el._resize);
    el._resize = () => set(at);
    window.addEventListener("resize", el._resize);
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
    // the frames turned north up, as the mosaic is (they were taken turned; turned here only to read them against it)
    const a = -s.north, fit = 1 / (Math.abs(Math.cos(a * Math.PI / 180)) + Math.abs(Math.sin(a * Math.PI / 180)));
    $$("[data-flow]").forEach((img) => { if (img.dataset.flow !== "mosaic") img.style.transform = `rotate(${a}deg) scale(${fit})`; });
    $("#where-turn").setAttribute("transform", `rotate(${a} 512 512)`);
  }
  function playFlow(on) {
    clearInterval(flow.timer);
    flow.timer = on ? setInterval(() => showFlow(flow.n % 9 + 1), 1700) : null;
    $(".flow-play").setAttribute("aria-pressed", on);
    $(".flow-play").textContent = on ? "Pause" : "Play";
  }
  $(".flow-play").addEventListener("click", () => playFlow(!flow.timer));
  $(".flow-n").addEventListener("input", (e) => { playFlow(false); showFlow(+e.target.value); });

  // ---- the narrow-angle camera's filters: its two wheels and a wavelength chart, one card explaining each ----------
  // Slots from the camera's flight filter placement (ISS calibration report, Figure 4.2.1-1); effective wavelengths and
  // each filter's reason from the camera description in NASA's archive (iss-na-camera-description, Table 1)
  const F = {
    CL1: [651, "clear", "Clear", "No filter at all: a wide-open slot that lets the most light through, for black-and-white pictures and to pair with any filter on the other wheel. It sits in the wheel's home slot, because if a wheel ever stuck, it was most likely to stick at home."],
    CL2: [651, "clear", "Clear", "The second wheel's clear slot, its home position, so a filter on the first wheel can be used on its own."],
    RED: [649, "color", "Red", "Broadband red. With green and blue it makes a natural color picture, close to what an eye would have seen."],
    GRN: [569, "color", "Green", "Broadband green, the middle channel of a natural color picture."],
    BL1: [455, "color", "Blue", "Broadband blue, the blue channel of a natural color picture."],
    BL2: [441, "color", "Blue (medium band)", "A narrower blue, for color measurements and, paired with the polarizers, for polarization."],
    UV1: [264, "uv", "Ultraviolet 1", "Ultraviolet, invisible to the eye. Small haze particles (aerosols) scatter ultraviolet strongly, so hazes high in Titan's and Saturn's atmospheres stand out. Only the narrow-angle camera can see ultraviolet: its mirrors and a special coating on its sensor let it reach down to 200 nm."],
    UV2: [306, "uv", "Ultraviolet 2", "Ultraviolet, for hazes (aerosols) and color in the ultraviolet."],
    UV3: [343, "uv", "Ultraviolet 3", "Near ultraviolet, for hazes (aerosols), color and, with the polarizers, polarization. Common in false color sets of Titan and Saturn's moons."],
    MT1: [619, "methane", "Methane 1 (weak)", "Centered on a weak methane absorption band. Methane gas soaks up light at this color, so the deeper the light has to travel, the darker it gets: clouds look bright only if they sit high. Comparing the three methane bands shows how high clouds and haze are (vertical sounding), mainly for Titan's atmosphere."],
    MT2: [727, "methane", "Methane 2 (medium)", "A medium-strength methane band. Light reaches less deep here than in MT1, so it picks out higher clouds. Used for cloud heights on Saturn, Jupiter and Titan."],
    MT3: [889, "methane", "Methane 3 (strong)", "The strongest methane band: almost all light from deep down is absorbed, so only the highest hazes and clouds show. Saturn's and Jupiter's high hazes glow in it."],
    CB1: [619, "continuum", "Continuum 1", "The 'control' for MT1: the same part of the spectrum just outside the methane band, so the difference between the two shows the methane absorption. It is two-lobed, with a pass band on each side of the methane band."],
    CB2: [750, "continuum", "Continuum 2", "The control for MT2, just beside its methane band. It sees the main visible cloud deck. Jupiter's color portrait used it in place of red."],
    CB3: [938, "continuum", "Continuum 3", "The control for MT3, and the camera's best look through Titan's haze: at this near-infrared color the haze is thin enough to see surface features below."],
    HAL: [656, "special", "H-alpha", "A very narrow filter at the red glow of hydrogen (H-alpha), for catching lightning on Saturn's night side."],
    IR1: [750, "ir", "Infrared 1", "Broadband near-infrared color."],
    IR2: [861, "ir", "Infrared 2", "Broadband near-infrared color, also covering an absorption band seen in the rings."],
    IR3: [928, "ir", "Infrared 3", "Broadband near-infrared color. Often the 'red' of false color sets."],
    IR4: [1001, "ir", "Infrared 4", "The longest wavelengths the camera sees, near the limit of its silicon sensor."],
    P0: [633, "pol", "Polarizer 0°", "One of three visible-light polarizers, turned 0°, 60° and 120°. Light scattered by haze and ring particles is partly polarized; three pictures through the three polarizers give how much and in which direction, whichever way the camera is turned."],
    P60: [633, "pol", "Polarizer 60°", "The 60° visible polarizer (see P0)."],
    P120: [633, "pol", "Polarizer 120°", "The 120° visible polarizer (see P0)."],
    IRP0: [738, "pol", "Infrared polarizer", "An infrared polarizer. Light scattered by Titan's haze is polarized, so a polarizer can cut some of the haze's glow and help see through it to the surface."],
  };
  const KIND = { clear: "#cfd6df", color: null, uv: "#9b7bff", methane: "#ff8a5c", continuum: "#ffc478", special: "#ff5c7a", ir: "#c9604a", pol: "#7fd3c8" };
  const COLOR_OF = { RED: "#e5554a", GRN: "#58c46a", BL1: "#5a8cff", BL2: "#6d8fff" };
  const WHEELS = [
    { name: "Wheel 1 (front)", slots: ["CL1", "RED", "BL1", "UV2", "UV1", "IRP0", "P120", "P60", "P0", "HAL", "IR4", "IR2"], dir: 1 },
    { name: "Wheel 2 (back)", slots: ["CL2", "GRN", "UV3", "BL2", "MT2", "CB2", "MT3", "CB3", "MT1", "CB1", "IR3", "IR1"], dir: -1 },
  ];
  const fill = (n) => COLOR_OF[n] || KIND[F[n][1]];
  function showFilter(n) {
    const f = F[n], card = $("#filter-card");
    if (!f) return;
    card.innerHTML = `<div class="kicker">${n} · ${f[0]} nm</div><b>${f[2]}</b><p>${f[3]}</p>`;
    $$("[data-filter]").forEach((el) => el.classList.toggle("on", el.dataset.filter === n));
  }
  function filterWheels() {
    const box = $("#wheels");
    WHEELS.forEach((w) => {
      const R = 120, r = 26, c = 150;
      let s = `<figure><svg viewBox="0 0 300 300" role="group" aria-label="${w.name} of the narrow-angle camera">`;
      s += `<circle cx="${c}" cy="${c}" r="${R + 34}" fill="rgba(255,255,255,.03)" stroke="rgba(255,255,255,.18)"/>`;
      s += `<circle cx="${c}" cy="${c}" r="5" fill="rgba(255,255,255,.25)"/>`;
      w.slots.forEach((n, i) => {
        const a = (-90 + w.dir * i * 30) * Math.PI / 180, x = c + R * Math.cos(a), y = c + R * Math.sin(a);
        s += `<g class="slot" data-filter="${n}" tabindex="0" role="button" aria-label="${n}, ${F[n][2]}">`;
        s += `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill(n)}" fill-opacity=".22" stroke="${fill(n)}" stroke-width="1.5"/>`;
        s += `<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="12" font-family="Menlo, monospace" fill="#fff">${n}</text></g>`;
      });
      s += `<text x="${c}" y="${c + 24}" text-anchor="middle" font-size="10" font-family="Menlo, monospace" fill="rgba(232,236,242,.45)">home ↑</text>`;
      box.insertAdjacentHTML("beforeend", s + `</svg><figcaption>${w.name}</figcaption></figure>`);
    });
  }
  function filterChart() {
    const W = 1000, H = 130, x = (nm) => 30 + (nm - 250) / (1050 - 250) * (W - 60);
    let s = `<svg viewBox="0 0 ${W} ${H + 26}" role="group" aria-label="The narrow-angle camera's filters by wavelength, 264 to 1001 nm"><g transform="translate(0,26)">`;
    s += `<defs><linearGradient id="vis" x1="0" x2="1"><stop offset="0" stop-color="#7b3cff"/><stop offset=".2" stop-color="#3c6bff"/><stop offset=".4" stop-color="#3cd27a"/><stop offset=".58" stop-color="#f3e23c"/><stop offset=".75" stop-color="#ff8a3c"/><stop offset="1" stop-color="#e3383c"/></linearGradient></defs>`;
    s += `<rect x="${x(380)}" y="96" width="${x(700) - x(380)}" height="6" rx="3" fill="url(#vis)" opacity=".85"/>`;
    s += `<text x="${x(540)}" y="122" fill="rgba(232,236,242,.55)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">what the eye sees</text>`;
    s += `<text x="${x(300)}" y="122" fill="rgba(232,236,242,.4)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">ultraviolet</text>`;
    s += `<text x="${x(880)}" y="122" fill="rgba(232,236,242,.4)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">infrared</text>`;
    for (let nm = 300; nm <= 1000; nm += 100) {
      s += `<line x1="${x(nm)}" x2="${x(nm)}" y1="86" y2="91" stroke="rgba(232,236,242,.3)"/><text x="${x(nm)}" y="82" fill="rgba(232,236,242,.35)" font-size="10" text-anchor="middle" font-family="Menlo, monospace">${nm}</text>`;
    }
    const rows = [];
    Object.keys(F).filter((n) => !/^(CL|P\d|IRP)/.test(n)).sort((a, b) => F[a][0] - F[b][0]).forEach((n) => {
      const nm = F[n][0];
      let row = 0;
      while (rows[row] != null && x(nm) - rows[row] < 44) row++;
      rows[row] = x(nm);
      const y = 52 - row * 20;
      s += `<g class="slot" data-filter="${n}" tabindex="0" role="button" aria-label="${n}, ${F[n][2]}"><rect x="${x(nm) - 20}" y="${y - 14}" width="40" height="${94 - y + 14}" fill="transparent"/>`;
      s += `<line x1="${x(nm)}" x2="${x(nm)}" y1="${y + 4}" y2="94" stroke="${fill(n)}" stroke-width="1.5"/>`;
      s += `<text x="${x(nm)}" y="${y}" fill="rgba(232,236,242,.85)" font-size="12" text-anchor="middle" font-family="Menlo, monospace">${n}</text></g>`;
    });
    $("#filters").innerHTML = s + "</g></svg>";
  }
  function filters() {
    filterWheels();
    filterChart();
    $$("[data-filter]").forEach((el) => {
      el.addEventListener("mouseenter", () => showFilter(el.dataset.filter));
      el.addEventListener("focus", () => showFilter(el.dataset.filter));
      el.addEventListener("click", () => showFilter(el.dataset.filter));
    });
    showFilter("MT3");
  }

  // ---- one pipeline step off, on its own example --------------------------------------------------------------
  const STEPS = [
    { key: "fill2", a: "alloff", al: "all off", name: "Enceladus: everything", note: "Enceladus, 14 July 2005: past the ragged edge, every other line was cut short on the way to Earth. The pipeline fills each gap from the lines on either side." },
    { key: "fill2", a: "off", al: "fill off", name: "Enceladus: lost lines", note: "Enceladus with only the fill turned off: the cut-short lines stay as gaps." },
    { key: "ering", a: "alloff", al: "all off", name: "E ring: everything", note: "Enceladus inside the E ring, 15 September 2006, the day Cassini passed through Saturn's shadow. The bottom of the frame was lost; a block that big is left empty (only another frame can fill it, in a mosaic)." },
    { key: "fill", a: "alloff", al: "all off", name: "Dione: everything", note: "Dione, 4 May 2006: the frame placed the same way with every clean-up and calibration step off (left), and on: lost lines filled, the camera's offset, hum and dark current taken out, and the brightness put on a real scale." },
    { key: "fill", a: "off", al: "fill off", name: "Dione: lost lines", note: "Dione through the pipeline with only the fill turned off: the lines lost in transmission stay as gaps. On, they are filled from the lines above and below." },
    { key: "twohz", a: "alloff", al: "all off", name: "Iapetus: everything", note: "Iapetus, 7 October 2004, a faint frame, with every clean-up and calibration step off (left) and on." },
    { key: "twohz", a: "off", al: "2 Hz off", name: "Iapetus: 2 Hz banding", note: "Iapetus, 7 October 2004, a faint frame. The camera's electronics picked up a 2 Hz hum that shows as horizontal bands; it is measured line by line, from the frame's own dark sky where there is enough of it, and taken out." },
  ];
  const RAW = [
    { id: "N1500061303_1", name: "Enceladus", cap: "Enceladus, 14 July 2005", note: "A close pass over Enceladus. Past the ragged edge, every other line was cut short on the way to Earth." },
    { id: "N1525449680_5", name: "Dione", cap: "Dione, 4 May 2006", note: "Lines lost in bands, plus cosmic-ray hits and a few stars." },
    { id: "W1537014482_1", name: "E ring", cap: "Enceladus in the E ring, 15 September 2006", note: "The wide-angle camera looking through Saturn's faint E ring, the day Cassini passed through Saturn's shadow; the bottom of the frame never arrived." },
    { id: "W1476557029_1", name: "Saturn", cap: "Saturn, 15 October 2004", note: "A clean frame, but gray, stretched, and with Saturn's rings standing on end because of how Cassini was turned." },
    { id: "N1611563684_1", name: "Titan", cap: "Titan, 25 January 2009", note: "Titan's haze through the red filter: one of three frames of the color picture in section 07." },
  ];
  function raws() {
    const chips = $("#raw-chips");
    RAW.forEach((r, i) => {
      const b = document.createElement("button");
      b.textContent = r.name;
      b.onclick = () => pick(i);
      chips.appendChild(b);
    });
    function pick(i) {
      $$("button", chips).forEach((b, j) => b.setAttribute("aria-pressed", i === j));
      const r = RAW[i];
      $("#raw-img").src = `img/raw-${r.id}.jpg`;
      $("#raw-cap").textContent = `${r.cap}, ${r.id} · the PNG copy the pipeline starts from`;
      $("#raw-note").textContent = r.note;
    }
    pick(0);
  }
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
  const TARGETS = [
    { key: "titan", nm: [649, 569, 455], name: "Titan · 25 Jan 2009", note: "Titan from the narrow-angle camera: its orange haze, blue at the rim where the thin upper haze scatters blue light." },
    { key: "saturn", nm: [647, 568, 463], name: "Saturn · 15 Oct 2004", note: "Saturn and its rings from the wide-angle camera, three months after Cassini arrived." },
    { key: "jupiter", nm: [649, 569, 455], name: "Jupiter · 10 Feb 2001", note: "A crescent Jupiter as Cassini left it behind. Its channels were far apart, so turning the lining up off splits it into colored crescents." },
  ];
  const COLOR = [
    { name: "Lining up", a: "noalign", al: "not lined up", note: "Off: the channels as the camera took them." },
    { name: "Natural color", a: "rawfilters", al: "filters straight", note: "Filters straight: each filter in one channel, without the color matrix." },
    { name: "Calibrated", a: "nocal", al: "not calibrated", note: "Not calibrated: each filter on its own stretch." },
  ];
  function colors() {
    let target = TARGETS[0], cmp = 0;
    const tchips = $("#color-targets"), chips = $("#color-chips");
    TARGETS.forEach((t, i) => {
      const b = document.createElement("button");
      b.textContent = t.name;
      b.onclick = () => { target = TARGETS[i]; show(); };
      tchips.appendChild(b);
    });
    COLOR.forEach((c, i) => {
      const b = document.createElement("button");
      b.textContent = c.name;
      b.onclick = () => { cmp = i; show(); };
      chips.appendChild(b);
    });
    function show() {
      $$("button", tchips).forEach((b, j) => b.setAttribute("aria-pressed", TARGETS[j] === target));
      $$("button", chips).forEach((b, j) => b.setAttribute("aria-pressed", j === cmp));
      ["red", "green", "blue"].forEach((k, i) => {
        $(`#ch-${k}`).src = `img/color-${target.key}-${k}.jpg`;
        // each camera's own effective wavelength for the filter (the wide-angle camera's differ a little)
        $(`#nm-${k}`).textContent = `${["RED", "GRN", "BL1"][i]} · ${target.nm[i]} nm`;
      });
      const c = COLOR[cmp];
      compare($("#color-compare"), `img/color-${target.key}-${c.a}.jpg`, `img/color-${target.key}.jpg`, c.al, "pipeline");
      $("#color-note").textContent = target.note + " " + c.note;
    }
    show();
  }

  // ---- mosaic scrubber ------------------------------------------------------------------------------------------
  function mosaic() {
    // pictures 1-9: the first lap, 10-18: the second, each tile replacing its spot from the lap before
    const LAP_START = ["04:18", "05:32"];
    let timer = null;
    const set = (n) => {
      $("#mos-img").src = `img/jup-${n}-mosaic.jpg`;
      $("#mos-n").value = n;
      const lap = n <= 9 ? 1 : 2, k = n <= 9 ? n : n - 9;
      $("#mos-count").textContent = `lap ${lap} (from ${LAP_START[lap - 1]} UTC) · pointing ${k} of 9`;
    };
    for (let n = 1; n <= 18; n++) new Image().src = `img/jup-${n}-mosaic.jpg`;
    const stop = () => { clearInterval(timer); timer = null; $("#mos-play").textContent = "Play"; $("#mos-play").setAttribute("aria-pressed", false); };
    $("#mos-n").addEventListener("input", (e) => { stop(); set(+e.target.value); });
    $("#mos-play").addEventListener("click", () => {
      if (timer) return stop();
      if (+$("#mos-n").value >= 18) set(1);
      $("#mos-play").textContent = "Pause";
      $("#mos-play").setAttribute("aria-pressed", true);
      timer = setInterval(() => { const n = +$("#mos-n").value; if (n >= 18) return stop(); set(n + 1); }, 650);
    });
    set(9);
  }

  // ---- centering: the frames as taken, and the same pictures moved and turned by SPICE's numbers ---------------
  function centering() {
    let n = 1, timer = null;
    for (let k = 1; k <= 9; k++) new Image().src = `img/center-${k}.jpg`;
    const placed = $("#ctr-placed");
    function show(k) {
      n = k;
      $("#ctr-raw").src = placed.src = `img/center-${k}.jpg`;
      const g = facts[`center-${k}`];
      if (g) {
        // turn about the moon's center (north angle, counterclockwise in the picture, so a negative CSS turn), then move
        // that center to the middle; in percent of the picture so it holds at any size
        const s = g.sample / 1024 * 100, l = g.line / 1024 * 100;
        placed.style.transformOrigin = `${s}% ${l}%`;
        placed.style.transform = `translate(${50 - s}%, ${50 - l}%) rotate(${-g.north}deg)`;
        $("#ctr-count").textContent = `frame ${k} of 9 · ${g.id} · center at sample ${fmt(g.sample)}, line ${fmt(g.line)} · north ${g.north.toFixed(1)}°`;
      }
    }
    function play(on) {
      clearInterval(timer);
      timer = on ? setInterval(() => show(n % 9 + 1), 900) : null;
      $("#ctr-play").textContent = on ? "Pause" : "Play";
      $("#ctr-play").setAttribute("aria-pressed", on);
    }
    $("#ctr-play").addEventListener("click", () => play(!timer));
    show(1);
    play(!matchMedia("(prefers-reduced-motion: reduce)").matches);
    $("#ctr-note").textContent = "Enceladus, 4 December 2016, from 310,000 km. Both sides show the archive's frame as it is; only its place and turn change.";
    return show;
  }
  let showCenter = null;

  filters();
  showCenter = centering();
  raws();
  steps();
  colors();
  mosaic();
  fetch("pictures.json").then((r) => r.json()).then((j) => { facts = j; showFlow(flow.n); showCenter(1); }).catch(() => showFlow(flow.n));
  showFlow(1);
  playFlow(!matchMedia("(prefers-reduced-motion: reduce)").matches);
})();
