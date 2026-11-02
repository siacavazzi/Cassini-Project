"""
Makes web/test_data/cisscal_noise_ref.npz, the reference web/test_cisscal_noise.py checks cisscal_noise.py against: the
real CISSCAL 4.1 (IDL, COISS_0011/extras/cisscal.tar.gz; the scratch branch claude/cisscal-idl-src has it with the raw
frames) run in GDL (apt install gnudatalanguage) on four raw EDRs.

  1. git archive origin/claude/cisscal-idl-src cisscal_idl cisscal_ref | tar x -C REF
  2. copy run_ref.pro, grid_ref.pro, savgol.pro (GDL 1.0.4 has no SAVGOL: the least-squares stand-in, equal to
     scipy's savgol_coeffs) and guiprint.pro (CISSCAL_Log's GUI hook, printing) from here into REF/cisscal_idl, and
     make filterhum_verbatim.pro: the filter section of cassimg__twohz.pro copied as it is (this script does it)
  3. in REF: for each frame  gdl -e "!path='REF/cisscal_idl:'+!path & run_ref, 'cisscal_ref/raw/F.IMG', 'out/F'"
     (writes the image after the table, the bias, the 2 Hz step and the pairs step), then gdl -e "... & grid_ref"
  4. python evidence/cisscal_noise/make_reference.py REF
"""
import json
import sys

import numpy as np

sys.path.insert(0, ".")
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("ca", "helper programs/convert_archive.py")
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)

KEYS = ("INSTRUMENT_ID", "INSTRUMENT_MODE_ID", "INST_CMPRS_TYPE", "INST_CMPRS_RATIO", "DATA_CONVERSION_TYPE",
        "GAIN_MODE_ID", "DELAYED_READOUT_FLAG", "INSTRUMENT_DATA_RATE", "FLIGHT_SOFTWARE_VERSION_ID",
        "READOUT_CYCLE_INDEX", "ANTIBLOOMING_STATE_FLAG", "BIAS_STRIP_MEAN", "LINES", "LINE_SAMPLES", "EXPOSURE_DURATION")


def filterhum_verbatim(ref):
    src = open(f"{ref}/cisscal_idl/cassimg__twohz.pro").read()
    a = src.index("w=(size(hum))[1]")
    b = src.index("hum = shumx[100:100+w-1]") + len("hum = shumx[100:100+w-1]")
    body = (src[a:b].replace("IF not (*(*(*CalOptions).twohz).imagemean).onoff THEN BEGIN", "IF oc THEN BEGIN")
            .replace("if self.Instrument eq 'ISSNA' THEN", "if instrument eq 'ISSNA' THEN")
            .replace("lbreak = self->LineBreak()", ""))
    open(f"{ref}/cisscal_idl/filterhum_verbatim.pro", "w").write(
        "function filterhum_verbatim, hum, instrument, lbreak, oc\n" + body + "\nreturn, hum\nend\n")


def main(ref):
    out = {}
    labels = {}
    for fid in ("N1513700682_1", "N1510252949_1", "N1511812952_1"):
        img, pre = ca.read_img(f"{ref}/cisscal_ref/raw/{fid}.IMG")
        info = ca.parse_label(open(f"{ref}/cisscal_ref/raw/{fid}.LBL", encoding="latin-1").read())
        labels[fid] = {k: info.get(k, "") for k in KEYS}
        load = lambda s: np.fromfile(f"{ref}/out/{fid}_{s}.f32", "<f4").reshape(1024, 1024)  # noqa: E731
        lut, bias, twohz, pairs = (load(s) for s in ("0lut", "1bias", "2twohz", "3pairs"))
        ok = lut != 0
        out[f"{fid}/prefix"] = pre
        out[f"{fid}/bias"] = np.nanmedian(np.where(ok, lut - bias, np.nan), axis=1)
        out[f"{fid}/hum"] = np.nanmedian(np.where(ok, bias - twohz, np.nan), axis=1)
        changed = np.argwhere(pairs != twohz)
        out[f"{fid}/pair_pixels"] = changed
        # 7x7 patches of the image going into the pairs step round every pixel it changed, and what CISSCAL made of them
        patches_in, patches_out = [], []
        for y, x in changed:
            ys, xs = np.arange(y - 3, y + 4) % 1024, np.arange(x - 3, x + 4) % 1024
            patches_in.append(twohz[np.ix_(ys, xs)])
            patches_out.append(pairs[np.ix_(ys, xs)])
        out[f"{fid}/pairs_in"] = np.array(patches_in, np.float32).reshape(-1, 7, 7)
        out[f"{fid}/pairs_out"] = np.array(patches_out, np.float32).reshape(-1, 7, 7)
        out[f"{fid}/pairs_count"] = np.array(int(np.sum(twohz != pairs)))
    tok = open(f"{ref}/out/linebreak_grid.txt").read().split()
    out["grid"] = np.array([tok[i:i + 8] for i in range(0, len(tok), 8)])
    out["filterhum"] = np.fromfile(f"{ref}/out/filterhum.f32", "<f4")
    out["labels"] = np.array(json.dumps(labels))
    np.savez_compressed("web/test_data/cisscal_noise_ref.npz", **out)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--filter-only":
        filterhum_verbatim(sys.argv[1])
    else:
        main(sys.argv[1])
