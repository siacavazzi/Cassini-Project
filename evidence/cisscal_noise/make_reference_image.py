"""
Makes web/test_data/cisscal_image_ref.npz, the reference web/test_cisscal_noise.py checks cisscal_noise.image_hum
(the image mean method of cassimg__twohz.pro) against, from CISSCAL 4.1 run in GDL as in make_reference.py, with:

  - REF/im_idl/cassimg__twohz.pro: a copy whose first line of CassImg::TwoHz (the return on 8-bit table frames under
    12 e-/DN) is commented out, so the image mean method runs on the low gain table frames too; for N1513700682_1
    (12-bit) CISSCAL runs it as it is
  - REF/im_idl/run_im.pro (here): bias type IM (BIAS_STRIP_MEAN and the image mean 2 Hz method, threshold auto,
    pixrange 9: cisscal_default_options.txt), writing the image after the bias, after the 2 Hz step, the missing
    pixel array and the mask
  - N1511812952_1M: N1511812952_1 with lines 300, 302 and 610 and 900-1023 zeroed (lost in downlink), and 4 zeros in
    a row on line 500 (a run too short to count as missing)

  in REF: gdl -e "!path='REF/im_idl:REF/cisscal_idl:'+!path & run_im, 'cisscal_ref/raw/F.IMG', 'out_im/F'"
  python evidence/cisscal_noise/make_reference_image.py REF
"""
import json
import sys

import numpy as np

sys.path.insert(0, ".")
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("ca", "helper programs/convert_archive.py")
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)

FRAMES = ("N1511812952_1M", "N1511812985_1", "N1513700682_1")
KEYS = ("INSTRUMENT_ID", "INSTRUMENT_MODE_ID", "INST_CMPRS_TYPE", "INST_CMPRS_RATIO", "DATA_CONVERSION_TYPE",
        "GAIN_MODE_ID", "DELAYED_READOUT_FLAG", "INSTRUMENT_DATA_RATE", "FLIGHT_SOFTWARE_VERSION_ID",
        "READOUT_CYCLE_INDEX", "BIAS_STRIP_MEAN", "LINES", "LINE_SAMPLES")


def main(ref):
    out, labels = {}, {}
    for fid in FRAMES:
        raw, _ = ca.read_img(f"{ref}/cisscal_ref/raw/{fid}.IMG")
        info = ca.parse_label(open(f"{ref}/cisscal_ref/raw/{fid}.LBL", encoding="latin-1").read())
        labels[fid] = {k: info.get(k, "") for k in KEYS}
        load = lambda s: np.fromfile(f"{ref}/out_im/{fid}_{s}.f32", "<f4").reshape(1024, 1024)  # noqa: E731
        bias, twohz = load("1bias"), load("2twohz")
        missing = np.fromfile(f"{ref}/out_im/{fid}_missing.u8", np.uint8).reshape(1024, 1024).astype(bool)
        mask = np.fromfile(f"{ref}/out_im/{fid}_mask.u8", np.uint8).reshape(1024, 1024).astype(bool)
        out[f"{fid}/raw"] = raw.astype(np.uint8 if info["DATA_CONVERSION_TYPE"] == "TABLE" else np.int16)
        # the 2 Hz value CISSCAL took off each line (the same on every pixel of it but the missing ones, left at 0)
        with np.errstate(all="ignore"):
            out[f"{fid}/hum"] = np.nanmedian(np.where(missing, np.nan, bias - twohz), axis=1).astype(np.float32)
        out[f"{fid}/missing"] = np.packbits(missing)
        out[f"{fid}/mask"] = np.packbits(mask)
    out["labels"] = json.dumps(labels)
    np.savez_compressed("web/test_data/cisscal_image_ref.npz", **out)


if __name__ == "__main__":
    main(sys.argv[1])
