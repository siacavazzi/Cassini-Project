"""Makes the instrument samples for Cassini OS's picture notes (sound.html, Settings > Sound > Instrument).

Fetches each instrument's single-note recordings from the Versilian Community Sample Library (VCSL) and
VSCO 2 Community Edition (both CC0, Versilian Studios) on raw.githubusercontent.com, and writes one short mono mp3
per recorded note into sounds/<instrument>/, plus sounds/index.json (the notes each instrument has, as MIDI
numbers, and the level that puts it beside the synthesized chimes). The page loads an instrument's files only when
it is picked.

    python web/cassini-os/sounds/make_sounds.py [--only piano,harp]

Needs ffmpeg. The file names come from the libraries' trees (git clone --filter=blob:none --no-checkout of
github.com/sgossner/VCSL and VSCO-2-CE, then git ls-tree), listed below so this runs without them.
"""
import argparse, json, os, re, subprocess, sys, urllib.parse, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = "https://raw.githubusercontent.com/sgossner/{repo}/master/{path}"
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
midi = lambda n: 12 * (int(n[-1]) + 1) + NOTE[n[0]] + (1 if "#" in n else 0)

# instrument: repo, folder, file names (note is the {} in the pattern), seconds kept, fade
SETS = {
    "piano": ("VCSL", "Chordophones/Zithers/Grand Piano, Steinway B/Sus", "JHPiano_Sus_Close_{}_vl3_rr1.wav",
              "C2 D2 E2 F#2 G#2 A#2 C3 D3 E3 F#3 G#3 A#3 C4 D4 E4 F#4 G#4 A#4 C5 D5 E5 F#5 G#5 A#5 C6 D6 E6 F#6 G#6 A#6 C7 D7 E7 F#7 G#7", 4.0),
    "hand-chimes": ("VCSL", "Idiophones/Struck Idiophones/Hand Chimes", "sus_{}_r01_main.wav",
              "C3 D3 E3 F#3 G#3 A#3 C4 D4 E4 F#4 G#4 A4 C5 D5 E5 F#5 G#5 A#5 C6", 4.0),
    "glockenspiel": ("VCSL", "Idiophones/Struck Idiophones/Glockenspiel", "glock_medium_{}_01.wav",
              "G4 C5 G5 C6 G6 C7", 2.5),
    "vibraphone": ("VCSL", "Idiophones/Struck Idiophones/Vibraphone/Soft Mallets", "Vibes_soft_{}_v2_rr1_Main.wav",
              "F2 A2 C3 E3 G3 B3 D4 F4 A4 C5 E5", 4.0),
    "vibraphone-bowed": ("VCSL", "Idiophones/Struck Idiophones/Vibraphone/Bowed", "Vibes_bowed_{}_rr1_Main.wav",
              "A2 E3 G3 D4 A4 E5", 5.0),
    "marimba": ("VCSL", "Idiophones/Struck Idiophones/Marimba", "Marimba_hit_Outrigger_{}_med_01.wav",
              "F1 C2 G2 B2 F3 C4 G4 B4 F5 C6", 2.5),
    "kalimba": ("VCSL", "Idiophones/Plucked Idiophones/Kalimba, Tanzania", None,
              "G1 G#1 B1 C#2 D#2 F2 G2 A#2 C#3 D#3 F3 G3 A#3 C#4 D4 D#4 F4 G4 A#4 B4 C#5 E5 F#5 G#5 C#6", 2.5),
    "harp": ("VCSL", "Chordophones/Composite Chordophones/Concert Harp", "KSHarp_{}_mf1.wav",
              "B1 D2 F2 A2 C3 E3 G3 B3 D4 F4 A4 C5 E5 G5 B5 D6 F6 A6 B6", 4.0),
    "tubular-bells": ("VCSL", "Idiophones/Struck Idiophones/Tubular Bells 2", None,
              "C4 D4 E4 F4 G4 A4 B4 C5 D5 E5 F5", 4.0),
    "wine-glasses": ("VCSL", "Idiophones/Friction Idiophones/Wine Glasses/Sustains/Slow", None,
              "D#4 F#4 A#4 D5", 5.0),
    "organ": ("VCSL", "Aerophones/Edge-blown Aerophones/Pipe Organ/Quiet", "NT5_Man3Quiet_{}_rr1.wav",
              "C1 D#1 F#1 A1 C2 D#2 F#2 A2 C3 D#3 F#3 A3 C4 D#4 F#4 A4 C5 D#5 F#5 A5 C6", 5.0),
    "violins": ("VSCO-2-CE", "Strings/Violin Section/susVib", "VlnEns_susVib_{}_v1.wav",
              "G2 A2 B2 D3 F#3 A3 C4 E4 G4 B4 D5", 5.0),
    "cellos": ("VSCO-2-CE", "Strings/Cello Section/susvib", "susvib_{}_v1_1.wav",
              "C1 E1 G1 B1 D2 F2 A2 C3 E3 G3 B3 D4 F4", 5.0),
    "nepalese-bells": ("VCSL", "Idiophones/Struck Idiophones/Hand Bells, Nepalese", None, "", 3.0),
}
# folders whose file names do not follow one pattern
ODD = {
    "kalimba": {"G1": "k12", "G#1": "k11", "B1": "k13", "C#2": "k10", "D#2": "k14", "F2": "k9alt", "G2": "k15", "A#2": "k8",
                "C#3": "k16", "D#3": "k7", "F3": "k17", "G3": "k6", "A#3": "k18", "C#4": "k5", "D4": "k19", "D#4": "k20",
                "F4": "k21", "G4": "k22", "A#4": "k2", "B4": "k23", "C#5": "k24", "E5": "k25", "F#5": "k1", "G#5": "k26", "C#6": "k27"},
    "tubular-bells": {"C4": "1", "D4": "1", "E4": "1", "F4": "2", "G4": "1", "A4": "1", "B4": "1", "C5": "1", "D5": "2", "E5": "1", "F5": "2"},
    "wine-glasses": {"D#4": "glass1_D#4_Slow_1", "F#4": "glass2_F#4_Slow_1", "A#4": "glass3_A#4_Slow_1", "D5": "glass4_D5_Slow_2"},
}
# instruments that hold a note: level by a steadier tone's rms, as they do not die away like a bell
SUSTAINED = {"vibraphone-bowed", "wine-glasses", "organ", "violins", "cellos"}
# the unpitched Nepalese bells: three bells, given notes a fifth and a fourth apart so they still follow the scale
BELLS = {"HB_1.wav": 76, "HB_2.wav": 83, "HB_3.wav": 88}


def name_of(inst, n):
    if inst == "kalimba": return f"MBira3_pluck_Main_{n}_{ODD[inst][n]}_50_100_rr2.wav"
    if inst == "tubular-bells": return f"TB_hit_{n}_v2_{ODD[inst][n]}.wav"
    if inst == "wine-glasses": return f"{ODD[inst][n]}_Main.wav"
    if inst == "harp" and n == "C3": return "KSHarp_C3_mf3.wav"
    return SETS[inst][2].format(n)


def decode(data):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", "44100", "-f", "f32le", "pipe:1"], input=data, capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def level(inst, clips, peak=1.0):
    """The gain that puts an instrument beside the FM bell: a bell's first second has an rms about a third of its
    peak; a held note is set lower, as it does not die away."""
    part = slice(22050, 3 * 44100) if inst in SUSTAINED else slice(0, 44100)   # a held note after its swell
    rms = float(np.median([np.sqrt(np.mean((x[part] / peak * 0.89) ** 2)) for x in clips]))
    return round(max(0.3, min(4.0, (0.12 if inst in SUSTAINED else 0.3) / max(1e-3, rms))), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--levels", action="store_true", help="only work out the levels again, from the mp3s already made")
    a = ap.parse_args()
    out_index = os.path.join(HERE, "index.json")
    index = json.load(open(out_index)) if os.path.exists(out_index) else {}
    if a.levels:
        for inst, e in index.items():
            e["gain"] = level(inst, [decode(open(os.path.join(HERE, inst, f"{m}.mp3"), "rb").read()) for m in e["notes"]])
        json.dump(dict(sorted(index.items())), open(out_index, "w"), indent=1)
        return
    for inst, (repo, folder, pat, notes, secs) in SETS.items():
        if a.only and inst not in a.only.split(","): continue
        files = [(f, m) for f, m in BELLS.items()] if inst == "nepalese-bells" else [(name_of(inst, n), midi(n)) for n in notes.split()]
        clips = {}
        for f, m in files:
            url = RAW.format(repo=repo, path=urllib.parse.quote(f"{folder}/{f}"))
            x = decode(urllib.request.urlopen(url, timeout=60).read())
            start = int(np.argmax(np.abs(x) > 0.003 * np.abs(x).max()))   # from the note's first sound
            x = x[max(0, start - 30): max(0, start - 30) + int(secs * 44100)]
            fade = int(min(0.6, secs * 0.25) * 44100)
            x[-fade:] *= np.linspace(1, 0, fade) ** 2
            clips[m] = x
            print(inst, f, m, f"{len(x) / 44100:.2f}s", file=sys.stderr)
        # one level for the whole instrument, so its notes keep their own balance
        peak = max(float(np.abs(x).max()) for x in clips.values())
        d = os.path.join(HERE, inst); os.makedirs(d, exist_ok=True)
        for old in os.listdir(d): os.remove(os.path.join(d, old))
        for m, x in clips.items():
            y = (x / peak * 0.89).astype(np.float32)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", "44100", "-ac", "1", "-i", "pipe:0",
                            "-c:a", "libmp3lame", "-b:a", "64k", os.path.join(d, f"{m}.mp3")], input=y.tobytes(), check=True)
        index[inst] = {"notes": sorted(clips), "gain": level(inst, clips.values(), peak)}
    json.dump(dict(sorted(index.items())), open(out_index, "w"), indent=1)


if __name__ == "__main__":
    main()
