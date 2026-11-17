"""Audit: read every label in the archive and keep the fields the findings need (read-only)."""
import sys, os, json, multiprocessing as mp
sys.path.insert(0, os.path.expanduser("~/cassini-build/audit/main"))
os.chdir(os.path.expanduser("~/cassini-build/audit/main"))
import data_source as ds
KEYS = ["INSTRUMENT_ID","INSTRUMENT_MODE_ID","INST_CMPRS_TYPE","INST_CMPRS_RATIO","DATA_CONVERSION_TYPE","GAIN_MODE_ID",
        "EXPOSURE_DURATION","FILTER_NAME","TARGET_NAME","OBSERVATION_ID","IMAGE_MID_TIME","IMAGE_TIME","MISSING_LINES",
        "MISSING_PACKET_FLAG","SHUTTER_STATE_ID","SHUTTER_MODE_ID","BIAS_STRIP_MEAN","FLIGHT_SOFTWARE_VERSION_ID",
        "LINES","ANTIBLOOMING_STATE_FLAG","CALIBRATION_LAMP_STATE_FLAG","DELAYED_READOUT_FLAG","LIGHT_FLOOD_STATE_FLAG",
        "IMAGE_NUMBER","DARK_STRIP_MEAN","VALID_MAXIMUM","EXPECTED_MAXIMUM","INST_CMPRS_PARAM","TELEMETRY_FORMAT_ID","INSTRUMENT_DATA_RATE","OPTICS_TEMPERATURE","DETECTOR_TEMPERATURE","SEQUENCE_ID","SPACECRAFT_CLOCK_START_COUNT","SPACECRAFT_CLOCK_STOP_COUNT","IMAGE_OBSERVATION_TYPE"]
def work(args):
    folder, names = args
    out = []
    for n in names:
        try:
            info = {}
            for line in ds.read_text(folder + "/" + n).splitlines():
                line = line.strip()
                if "=" in line:
                    v = line.replace(" ", "").replace('"', "").replace("\\", "").split("=")
                    info[v[0]] = v[1]
            out.append([n.split(".")[0]] + [info.get(k) for k in KEYS])
        except Exception as e:
            out.append([n.split(".")[0], "ERROR " + str(e)[:80]])
    return out
if __name__ == "__main__":
    jobs = []
    for folder in ("nac_data", "wac_data"):
        names = [n for n in ds.listdir(folder) if n.upper().endswith(".LBL")]
        print(folder, len(names), flush=True)
        jobs += [(folder, names[i:i + 2000]) for i in range(0, len(names), 2000)]
    rows = []
    with mp.Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 6) as pool:
        for k, part in enumerate(pool.imap_unordered(work, jobs)):
            rows += part
            if k % 20 == 0:
                print(k, len(jobs), len(rows), flush=True)
    with open(sys.argv[1], "w") as f:
        json.dump({"keys": ["frame"] + KEYS, "rows": rows}, f)
    print("done", len(rows))
