#!/usr/bin/env python3
"""The explainer animation, put together from capture.py's pictures: how 60 raw exposures become one mosaic.

  python animate.py CAPTURE_DIR OUT.mp4 [--fps 30] [--only SCENE] [--still T OUT.png]

This script does no image processing of its own. Every picture it shows is a file capture.py saved from a pipeline
call; here they are only cropped to their drawn part, resized, cross-faded and labelled. The outlines are the tiles'
own outlines from obs_mosaic.layout. Needs Pillow, numpy and ffmpeg.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG = (0, 0, 0)
INK = (236, 236, 232)
DIM = (150, 150, 146)
FAINT = (70, 70, 70)
ACCENT = (255, 122, 46)
TINT = {"RED": (255, 96, 80), "GRN": (110, 220, 120), "BL1": (96, 150, 255), "CL1/CL2": (225, 225, 225), "L": (225, 225, 225)}
NAME = {"RED": "red", "GRN": "green", "BL1": "blue", "CL1/CL2": "clear"}
HELV = "/System/Library/Fonts/HelveticaNeue.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
_fonts = {}


def font(size, weight="regular"):
    key = (size, weight)
    if key not in _fonts:
        try:
            _fonts[key] = (ImageFont.truetype(MONO, size) if weight == "mono" else
                           ImageFont.truetype(HELV, size, index={"regular": 0, "bold": 1, "light": 7, "medium": 10}[weight]))
        except OSError:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def span(t, a, b):
    """0 before a, 1 after b, eased between (t, a, b in the scene's own 0..1)"""
    return ease((t - a) / max(1e-6, b - a))


_cache = {}


def load(path):
    """a capture picture on black, cropped to its drawn part (alpha), RGB"""
    if path not in _cache:
        im = Image.open(path)
        if im.mode == "RGBA":
            box = im.getchannel("A").getbbox()
            if box:
                im = im.crop(box)
            bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
            bg.alpha_composite(im)
            im = bg
        _cache[path] = im.convert("RGB")
    return _cache[path]


def fit(im, w, h, key=None):
    """im resized to fit in w x h (kept by key)"""
    k = ("fit", key or id(im), w, h)
    if k not in _cache:
        s = min(w / im.width, h / im.height)
        _cache[k] = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    return _cache[k]


def put(frame, im, cx, cy, alpha=1.0):
    """im centred on (cx, cy), faded in by alpha"""
    x, y = round(cx - im.width / 2), round(cy - im.height / 2)
    if alpha >= 0.999:
        frame.paste(im, (x, y))
    elif alpha > 0.001:
        under = frame.crop((x, y, x + im.width, y + im.height))
        frame.paste(Image.blend(under, im, alpha), (x, y))
    return x, y


def text(d, xy, s, size, fill=INK, weight="regular", anchor="la", alpha=1.0):
    if alpha <= 0.01:
        return
    fill = tuple(round(BG[i] + (fill[i] - BG[i]) * alpha) for i in range(3))
    d.text(xy, s, font=font(size, weight), fill=fill, anchor=anchor)


class Film:
    """the capture folder's pictures and the scenes drawn from them"""

    def __init__(self, src):
        self.src = src
        j = lambda *p: json.load(open(os.path.join(src, *p)))
        self.unit = j("unit.json")
        self.frames = self.unit["frames"]   # [id, filter, t]
        self.meta = j("raw", "meta.json")
        self.layout = j("layout.json")
        self.grow = j("grow", "grow.json")
        self.variants = j("variants", "variants.json")
        self.calls = j("variants", "final_steps", "calls.json")
        hero = sorted(glob.glob(os.path.join(src, "chain", "*.json")))[0]
        self.hero = os.path.basename(hero)[:-5]
        self.chain = json.load(open(hero))
        self.set_ids = j("set", "set.json")["ids"]
        self.n = len(self.frames)
        self.minutes = round((float(self.frames[-1][2]) - float(self.frames[0][2])) / 60)
        self.pointings = self._pointings()
        self.scenes = [
            ("title", 4.0, self.title), ("raw", 7.0, self.raw_wall), ("clean", 16.0, self.clean), ("all", 4.5, self.all_clean),
            ("place", 13.0, self.place), ("register", 8.0, self.register),
            ("seams", 8.0, self.seams), ("colour", 15.0, self.colour), ("final", 8.0, self.final)]
        self.steps = ["Raw", "Clean", "Place", "Register", "Blend", "Colour", "Finished"]
        self.step_of = {"title": -1, "raw": 0, "clean": 1, "all": 1, "place": 2, "register": 3, "seams": 4,
                        "colour": 5, "final": 6}
        self.crop = self._content()

    def _pointings(self):
        """frames grouped as the camera took them (a short clear, the colours, a long clear at each pointing): a new
        group when a clear frame follows a clear one"""
        groups, last = [], None
        for i, (fid, f, t) in enumerate(self.frames):
            if not groups or (f == "CL1/CL2" and last == "CL1/CL2"):
                groups.append([])
            groups[-1].append(i)
            last = f
        return groups

    def _content(self, margin=0.05):
        """the part of the mosaic's canvas the finished picture fills, as fractions (x0, y0, x1, y1), with a margin"""
        im = load_full(os.path.join(self.src, "variants", "final.png"))
        box = im.convert("L").point(lambda v: 255 if v > 14 else 0).getbbox() or (0, 0, *im.size)
        mx, my = margin * im.width, margin * im.width
        return (max(0, box[0] - mx) / im.width, max(0, box[1] - my) / im.height,
                min(im.width, box[2] + mx) / im.width, min(im.height, box[3] + my) / im.height)

    def mosaic(self, path):
        """a mosaic picture (any size of the same canvas) cut to the part the finished picture fills"""
        key = ("mosaic", path)
        if key not in _cache:
            im = load_full(path)
            c = self.crop
            _cache[key] = im.crop((round(c[0] * im.width), round(c[1] * im.height), round(c[2] * im.width), round(c[3] * im.height)))
        return _cache[key]

    # ---- shared furniture -------------------------------------------------------------------------------------
    def base(self, scene, num=None, title=None, lines=(), call=None, alpha=1.0):
        frame = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(frame)
        at = self.step_of[scene]
        if at >= 0:
            x = 96
            for i, s in enumerate(self.steps):
                on = i == at
                text(d, (x, 1018), f"{i + 1:02d}", 15, ACCENT if on else FAINT, "mono")
                text(d, (x + 30, 1015), s.upper(), 17, INK if on else (FAINT if i > at else DIM), "medium" if on else "regular")
                wdt = d.textlength(s.upper(), font=font(17, "medium")) + 30
                if on:
                    d.rectangle((x, 1044, x + wdt, 1046), fill=ACCENT)
                x += wdt + 44
            text(d, (W - 96, 1016), "FAREWELL TO SATURN  ·  13 SEPT 2017", 15, FAINT, "mono", "ra")
        if title:
            text(d, (96, 64), num or "", 40, ACCENT, "medium", alpha=alpha)
            text(d, (96 + (70 if num else 0), 64), title, 40, INK, "medium", alpha=alpha)
            for i, s in enumerate(lines):
                text(d, (96, 124 + i * 34), s, 24, DIM, alpha=alpha)
            if call:
                text(d, (W - 96, 78), call, 16, FAINT, "mono", "ra", alpha=alpha)
        return frame, d

    def raw(self, i):
        return load(os.path.join(self.src, "raw", self.frames[i][0] + ".png"))

    def clean_frame(self, i):
        return load(os.path.join(self.src, "frames", self.frames[i][0] + ".png"))

    def wall_cells(self):
        """the frame wall: one column a pointing, in the order taken"""
        cols = len(self.pointings)
        rows = max(len(g) for g in self.pointings)
        cell = min((W - 192 - (cols - 1) * 10) // cols, (760 - (rows - 1) * 10) // rows)
        x0 = (W - cols * cell - (cols - 1) * 10) // 2
        y0 = 210
        out = {}
        for c, g in enumerate(self.pointings):
            for r, i in enumerate(g):
                out[i] = (x0 + c * (cell + 10) + cell // 2, y0 + r * (cell + 10) + cell // 2)
        return out, cell

    # ---- scenes: each draws its frame at t in 0..1 ---------------------------------------------------------------
    def title(self, t):
        frame, d = self.base("title")
        a = span(t, 0.05, 0.3) * (1 - span(t, 0.88, 1.0))
        text(d, (W // 2, 400), "How a mosaic is made", 84, INK, "medium", "ma", a)
        text(d, (W // 2, 520), f"{self.n} raw exposures from Cassini's wide-angle camera become one picture of Saturn.", 30, DIM, anchor="ma", alpha=a)
        text(d, (W // 2, 566), "Every image in this film is an output of the project's own pipeline.", 30, DIM, anchor="ma", alpha=a)
        text(d, (W // 2, 660), "FAREWELL TO SATURN  ·  13 SEPTEMBER 2017  ·  TWO DAYS BEFORE THE END OF THE MISSION", 17, ACCENT, "mono", "ma", a)
        return frame

    def raw_wall(self, t):
        frame, d = self.base("raw", "01", "Raw exposures, as received",
                             [f"{self.n} frames in {self.minutes} minutes: {len(self.pointings)} pointings, each taken through clear, blue, green and red filters,",
                              "with short and long exposures. Upside down, unaligned, uncalibrated."], "label_handler.export  data_source.imread")
        cells, cell = self.wall_cells()
        for i in range(self.n):
            a = span(t, 0.05 + 0.6 * i / self.n, 0.05 + 0.6 * i / self.n + 0.08)
            if a > 0:
                cx, cy = cells[i]
                x, y = put(frame, fit(self.raw(i), cell, cell, ("raw", i)), cx, cy, a)
                f = self.frames[i][1]
                d.rectangle((x, y + cell - 4, x + cell - 1, y + cell - 1), fill=tuple(round(v * a) for v in TINT.get(f, INK)))
        for k, (f, c) in enumerate(TINT.items()):
            if f in NAME:
                x = W - 96 - 4 * 130 + k * 130
                d.rectangle((x, 986 - 6, x + 14, 986 + 8), fill=c)
                text(d, (x + 22, 976), NAME[f], 17, DIM)
        return frame

    def shown(self):
        """the hero frame's steps that are shown: (chain row or None for the raw frame, name, sentence, change)"""
        shown = [(None, "Raw exposure", "The 8-bit codes Cassini sent home.", 0.0)]
        words = {
            "as_taken": ("Turn north up", "SPICE gives the camera's roll: the frame is turned so north is up."),
            "fill": ("Fill lost pixels", "Pixels lost on the way to Earth are filled from their neighbours."),
            "calibrate": ("Calibrate", "Codes back to counts, bias and shutter removed, divided by exposure: true brightness (I/F)."),
            "twohz": ("Remove 2 Hz hum", "A faint line-by-line hum from the camera's electronics is measured and taken off."),
            "dark": ("Subtract dark current", "The sensor's own glow, modelled pixel by pixel, is subtracted."),
            "pairs": ("Fix bright/dark pairs", "Anti-blooming pixel pairs are repaired."),
            "flat": ("Flat field", "Uneven pixel sensitivity and dust rings on the optics are divided out."),
            "hotpix": ("Repair hot pixels", "Hot pixels and cosmic ray hits are replaced."),
            "skysmooth": ("Smooth the sky", "Coding steps left in the empty sky are smoothed."),
            "stack": ("Merge exposures", "The short and long exposures of this pointing are merged, so bright and dark both hold detail."),
            "geom": ("Undo lens distortion", "The wide-angle lens bends the picture slightly: it is resampled onto a straight grid."),
        }
        for row in self.chain:
            ch = row["change"]
            if row["step"] != "as_taken" and not ch:
                continue   # (a step with nothing to do on this frame)
            shown.append((row, *words[row["step"]], ch or 0.0))
        return shown

    def clean(self, t):
        """one frame: its raw codes, then the pipeline's steps turned on one at a time"""
        hi = [i for i, f in enumerate(self.frames) if f[0] == self.hero][0]
        info = self.meta[self.hero]
        shown = self.shown()
        n = len(shown)
        edges = np.linspace(0.02, 0.97, n + 1)
        k = min(n - 1, int(np.searchsorted(edges, t, side="right")) - 1) if t >= edges[0] else 0
        k = max(0, k)
        local = (t - edges[k]) / (edges[k + 1] - edges[k])
        frame, d = self.base("clean", "02", "Clean one frame", ["Each exposure goes through the same chain. One step at a time:"],
                             "color_image.processed_frame  calibration.calibrate")
        side = 760
        pic = lambda j: fit(self.raw(hi), side, side, ("raw", hi)) if shown[j][0] is None else \
            fit(load(os.path.join(self.src, "chain", f"{self.hero}__{self.chain.index(shown[j][0]):02d}_{shown[j][0]['step']}.png")), side, side, ("chain", j))
        cx, cy = 96 + side // 2, 590
        if k > 0:
            put(frame, pic(k - 1), cx, cy)
        put(frame, pic(k), cx, cy, span(local, 0.0, 0.35) if k > 0 else span(t, 0.0, 0.03))
        # the steps as a list, ticked as they are applied
        x, y = 96 + side + 90, 250
        for j, (row, name, why, ch) in enumerate(shown):
            done, now = j < k, j == k
            yy = y + j * 44
            if now:
                d.rectangle((x - 22, yy + 4, x - 16, yy + 28), fill=ACCENT)
            text(d, (x, yy), name, 27, INK if now else (DIM if done else FAINT), "medium" if now else "regular")
            if done or now:
                text(d, (x + 330, yy + 6), "✓" if done else "", 20, ACCENT, "mono")
        text(d, (x, y + n * 44 + 40), shown[k][1], 34, INK, "medium")
        words_ = shown[k][2].split()
        line, yy = "", y + n * 44 + 92
        for wd in words_ + [None]:
            if wd is None or d.textlength(line + " " + wd, font=font(24)) > W - 96 - x:
                text(d, (x, yy), line.strip(), 24, DIM)
                line, yy = "", yy + 34
            if wd:
                line += " " + wd
        text(d, (96, 590 + side // 2 + 14), f"{self.hero}  ·  {NAME.get(self.frames[hi][1], '')} filter  ·  {float(info['EXPOSURE_DURATION']):.0f} ms", 15, FAINT, "mono")
        return frame

    def all_clean(self, t):
        frame, d = self.base("all", "02", "Clean every frame", [f"The same chain runs on all {self.n} exposures."],
                             "color_image.processed_frame")
        cells, cell = self.wall_cells()
        for i in range(self.n):
            cx, cy = cells[i]
            put(frame, fit(self.raw(i), cell, cell, ("raw", i)), cx, cy)
            a = span(t, 0.1 + 0.55 * i / self.n, 0.1 + 0.55 * i / self.n + 0.12)
            put(frame, fit(self.clean_frame(i), cell, cell, ("clean", i)), cx, cy, a)
        return frame

    def colour_set(self, t):
        frame, d = self.base("set", "03", "Point: line the filters up",
                             ["Red, green and blue are taken seconds apart while the spacecraft drifts. SPICE pointing puts each on the",
                              "sky; then the three are registered on each other so one pointing has no colour fringes."],
                             "color_image.load_aligned")
        side = 760
        a = load(os.path.join(self.src, "set", "unaligned.png"))
        b = load(os.path.join(self.src, "set", "aligned.png"))
        # the whole pointing on the left, a close-up of its limb on the right, both switching together
        on = span(t, 0.45, 0.6)
        for im, key in ((a, "ua"), (b, "al")):
            alpha = 1.0 if key == "ua" else on
            put(frame, fit(im, side, side, ("set", key)), 96 + side // 2, 590, alpha)
            s = im.width / 4
            cxp, cyp = im.width * 0.30, im.height * 0.42
            crop = im.crop((round(cxp - s / 2), round(cyp - s / 2), round(cxp + s / 2), round(cyp + s / 2)))
            put(frame, fit(crop, side, side, ("setz", key)), W - 96 - side // 2, 590, alpha)
        text(d, (96, 590 + side // 2 + 14), "ONE POINTING, THREE FILTERS", 15, FAINT, "mono")
        text(d, (W - 96 - side, 590 + side // 2 + 14), "CLOSE-UP ×4", 15, FAINT, "mono")
        text(d, (W - 96, 590 + side // 2 + 14), "REGISTERED" if on > 0.5 else "AS TAKEN", 15, ACCENT, "mono", "ra")
        return frame

    def _canvas(self):
        """where the mosaic goes on screen: (x, y, w, h)"""
        x0, y0, w, h = self.layout["rect"]
        c = self.crop
        w, h = w * (c[2] - c[0]), h * (c[3] - c[1])
        s = min((W - 192) / w, 740 / h)
        return (W - w * s) / 2, 225 + (740 - h * s) / 2, w * s, h * s

    def _outline(self, tile):
        x0, y0, w, h = self.layout["rect"]
        cx, cy, cw, ch = self._canvas()
        c = self.crop
        return [(cx + ((px - x0) / w - c[0]) / (c[2] - c[0]) * cw, cy + ((py - y0) / h - c[1]) / (c[3] - c[1]) * ch)
                for px, py in tile["outline"]]

    def place(self, t):
        frame, d = self.base("place", "03", "Place: the mosaic grows",
                             ["SPICE says where the camera pointed for every exposure. Each cleaned frame is drawn north up, at one scale,",
                              "where it belongs. Clear frames lay down the brightness; colour arrives as each red, green, blue set completes."],
                             "obs_mosaic.tile  obs_mosaic.so_far")
        cx, cy, cw, ch = self._canvas()
        f = span(t, 0.03, 0.9) * (self.n - 1)
        k = int(f)
        pics = [os.path.join(self.src, "grow", f"{i:03d}.png") for i in range(self.n)]
        have = [i for i in range(self.n) if os.path.exists(pics[i])]
        cur = max([i for i in have if i <= k], default=None)
        prev = max([i for i in have if i < k], default=None)
        size = (round(cw), round(ch))
        g = lambda i: fit(self.mosaic(pics[i]), *size, ("grow", i))
        if prev is not None:
            put(frame, g(prev), W / 2, cy + ch / 2)
        if cur is not None:
            put(frame, g(cur), W / 2, cy + ch / 2, min(1.0, (f - k) * 2.5) if cur == k else 1.0)
        tiles = {tl["n"]: tl for tl in self.layout["tiles"] if "outline" in tl}
        for back in range(4):
            i = k - back
            if i in tiles and t < 0.93:
                a = (1 - back / 4) * (0.9 if back else 1.0)
                col = tuple(round(BG[c] + (TINT.get(self.frames[i][1], INK)[c] - BG[c]) * a) for c in range(3))
                pts = self._outline(tiles[i])
                d.line(pts + [pts[0]], fill=col, width=3 if back == 0 else 1)
        if t < 0.93:
            fid, flt, _ = self.frames[k]
            text(d, (96, 978), f"FRAME {k + 1:02d} / {self.n}", 17, INK, "mono")
            text(d, (290, 978), f"{fid}  ·  {NAME.get(flt, flt).upper()}", 17, TINT.get(flt, DIM), "mono")
        return frame

    def _variant(self, name):
        return self.mosaic(os.path.join(self.src, "variants", name + ".png"))

    def _zoom_box(self, a, b, share=0.2):
        """the part of the picture (share of its width, 4:3) where pictures a and b differ most"""
        key = ("zoom", id(a), id(b))
        if key not in _cache:
            small = 8
            da = np.abs(np.asarray(a.convert("L").reduce(small), np.float32) - np.asarray(b.convert("L").reduce(small), np.float32))
            bw = max(8, round(da.shape[1] * share))
            bh = round(bw * 3 / 4)
            ii = np.pad(da.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
            tot = ii[bh:, bw:] - ii[:-bh, bw:] - ii[bh:, :-bw] + ii[:-bh, :-bw]
            y, x = np.unravel_index(int(tot.argmax()), tot.shape)
            _cache[key] = (x * small, y * small, (x + bw) * small, (y + bh) * small)
        return _cache[key]

    def _compare(self, scene, num, title, lines, call, t, names, labels, zoom_on):
        """the whole mosaic small on the left and a close-up on the right, switching through the named variants"""
        frame, d = self.base(scene, num, title, lines, call)
        pics = [self._variant(nm) for nm in names]
        box = self._zoom_box(self._variant(zoom_on[0]), self._variant(zoom_on[1]))
        n = len(names)
        edges = np.linspace(0.0, 1.0, n + 1)
        k = min(n - 1, int(t * n))
        local = (t - edges[k]) * n
        lw, lh = 820, 720
        rw, rh = 880, 660
        lx, ly = 96 + lw / 2, 250 + lh / 2
        rx, ry = W - 96 - rw / 2, 250 + rh / 2
        for j in ([k - 1, k] if k else [k]):
            a = 1.0 if j < k or k == 0 else span(local, 0.0, 0.3)
            whole = fit(pics[j], lw, lh, ("var", names[j]))
            x, y = put(frame, whole, lx, ly, a)
            put(frame, fit(pics[j].crop(box), rw, rh, ("varz", names[j], box)), rx, ry, a)
        s = whole.width / pics[0].width
        d.rectangle((x + box[0] * s, y + box[1] * s, x + box[2] * s, y + box[3] * s), outline=ACCENT, width=2)
        d.rectangle((rx - rw / 2, ry - rh / 2, rx + rw / 2 - 1, ry + rh / 2 - 1), outline=ACCENT, width=2)
        text(d, (rx - rw / 2, ry + rh / 2 + 16), labels[k], 22, ACCENT, "medium")
        for j in range(n):
            d.rectangle((rx + rw / 2 - (n - j) * 34, ry + rh / 2 + 24, rx + rw / 2 - (n - j) * 34 + 24, ry + rh / 2 + 30),
                        fill=ACCENT if j == k else FAINT)
        return frame

    def register(self, t):
        moved = self.variants["aligned"].get("moved", {})
        far = max((float(np.hypot(*v)) for v in moved.values()), default=0.0)
        return self._compare("register", "04", "Register: fix the last few pixels",
                             [f"Pointing from SPICE is good to a few pixels. Filters are lined up on each other, overlapping frames and the ring",
                              f"pattern are matched, and one solve nudges {len(moved)} of the {self.n} frames into place (by up to {far:.0f} px here)."],
                             "obs_mosaic.ring_moves  obs_mosaic.panel_places", t,
                             ["spice_only", "aligned", "spice_only", "aligned"],
                             ["SPICE POINTING ONLY", "REGISTERED", "SPICE POINTING ONLY", "REGISTERED"], ("spice_only", "aligned"))

    def seams(self, t):
        return self._compare("seams", "05", "Blend and level the seams",
                             ["Frames taken minutes apart differ slightly in brightness. Seams are routed where neighbours agree,",
                              "feathered, and the brightness steps between frames are levelled out."],
                             "mosaic.composite  (blend, level)", t,
                             ["aligned", "blended", "final"], ["HARD EDGES", "BLENDED", "BLENDED AND LEVELLED"], ("aligned", "final"))

    def colour(self, t):
        d0 = os.path.join(self.src, "variants", "final_steps")
        path = lambda label: os.path.join(d0, f"{self.calls.index(label) + 1:02d}_{label}.png")
        used = self.layout["used"]
        planes = [f"filter_mosaic_{f.replace('/', '-')}" for f in used]
        stages = []   # (title, sentence, call, [pictures])
        stages.append(("One mosaic per filter", "All the red frames make one mosaic, all the green another, all the blue a third.",
                       "obs_mosaic.filter_mosaic", planes))
        stages.append(("Mix the colour", "The three become red, green and blue of one picture, balanced to what an eye would see.",
                       "obs_mosaic.colour_picture", ["colour_picture"]))
        if "filter_mosaic_L" in self.calls:
            stages.append(("Sharper brightness", "The clear-filter frames, merged from short and long exposures, make a cleaner brightness layer.",
                           "obs_mosaic.filter_mosaic (luminance)", ["filter_mosaic_L"]))
            stages.append(("Colour over brightness", "The colour is laid over that brightness layer: detail from clear, hue from the filters.",
                           "obs_mosaic.over_grey", ["over_grey"]))
        last = [c for c in ("ring_white", "detail") if c in self.calls]
        if last:
            stages.append(("Finish", "Whites are set on the rings and fine detail is brought out. Done.",
                           "obs_mosaic." + "  obs_mosaic.".join(last), [last[-1]]))
        n = len(stages)
        k = min(n - 1, int(t * n))
        local = t * n - k
        title, why, call, pics = stages[k]
        frame, d = self.base("colour", "06", "Colour: " + title[0].lower() + title[1:], [why], call)
        cx, cy, cw, ch = self._canvas()

        def draw(stage, alpha):
            ps = stage[3]
            if len(ps) == 1:
                put(frame, fit(self.mosaic(path(ps[0])), round(cw), round(ch), ("col", ps[0])), W / 2, cy + ch / 2, alpha)
            else:
                w1 = (W - 192 - 40 * (len(ps) - 1)) / len(ps)
                for i, pth in enumerate(ps):
                    im = fit(self.mosaic(path(pth)), round(w1), 600, ("col3", pth))
                    x = 96 + w1 / 2 + i * (w1 + 40)
                    put(frame, im, x, 560, alpha)
                    f = used[i]
                    text(d, (x, 560 + im.height / 2 + 24), NAME.get(f, f).upper(), 20, TINT.get(f, INK), "medium", "ma", alpha)
        if k > 0 and local < 0.3 and len(stages[k - 1][3]) == 1 and len(pics) == 1:
            draw(stages[k - 1], 1.0)
            draw(stages[k], span(local, 0.0, 0.3))
        else:
            draw(stages[k], span(local, 0.0, 0.2) if (k == 0 or len(pics) > 1 or len(stages[k - 1][3]) > 1) else 1.0)
        return frame

    def final(self, t):
        frame, d = self.base("final")
        im = self._variant("final")
        a = span(t, 0.0, 0.12)
        big = fit(im, W - 60, 790, ("final",))
        put(frame, big, W / 2, 425, a)
        b = span(t, 0.2, 0.4)
        stats = [(str(self.n), "exposures"), (str(len(self.pointings)), "pointings"), ("4", "filters"),
                 (str(self.minutes), "minutes"), (str(len(self.shown()) - 1), "steps per frame"), ("1", "picture")]
        for i, (num, lab) in enumerate(stats):
            x = 200 + i * (W - 400) / (len(stats) - 1)
            text(d, (x, 846), num, 56, INK, "medium", "ma", b)
            text(d, (x, 912), lab, 20, DIM, anchor="ma", alpha=b)
        text(d, (W // 2, 968), f"Images NASA / JPL-Caltech / Space Science Institute  ·  processed by the Cassini Project pipeline, commit {self.unit.get('commit', '')[:8]}",
             15, FAINT, "mono", "ma", b)
        return frame

    # ---- the film ----------------------------------------------------------------------------------------------------
    def at(self, seconds):
        for name, dur, fn in self.scenes:
            if seconds < dur:
                return name, fn(seconds / dur)
            seconds -= dur
        return self.scenes[-1][0], self.scenes[-1][2](1.0)

    @property
    def length(self):
        return sum(s[1] for s in self.scenes)


def load_full(path):
    """a capture picture on black, whole (not cropped: mosaics keep their canvas so they stay registered)"""
    key = ("full", path)
    if key not in _cache:
        im = Image.open(path)
        if im.mode == "RGBA":
            bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
            bg.alpha_composite(im)
            im = bg
        _cache[key] = im.convert("RGB")
    return _cache[key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", help="one scene by name")
    ap.add_argument("--still", type=float, action="append", help="a single frame at this second (out is then a PNG pattern with %%s)")
    a = ap.parse_args()
    film = Film(a.src)
    if a.only:
        film.scenes = [s for s in film.scenes if s[0] == a.only]
    if a.still:
        for s in a.still:
            name, frame = film.at(s)
            frame.save(a.out % f"{s:05.1f}_{name}")
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(a.fps), "-i", "-",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(film.length * a.fps)
    fade = int(0.35 * a.fps)
    prev_name, since = None, 0
    for i in range(total):
        name, frame = film.at(i / a.fps)
        since = 0 if name != prev_name else since + 1
        prev_name = name
        if since < fade and i >= fade:   # each scene fades up from black
            frame = Image.blend(Image.new("RGB", (W, H), BG), frame, ease((since + 1) / fade))
        ff.stdin.write(frame.tobytes())
        if i % (a.fps * 5) == 0:
            print(f"{i / a.fps:5.0f} s of {film.length:.0f}  {name}", flush=True)
    ff.stdin.close()
    sys.exit(ff.wait())


if __name__ == "__main__":
    main()
