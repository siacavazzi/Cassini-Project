"""Parse DISR imager PDS3 labels into a CSV frame index."""
import sys, re, glob, csv, os
root = sys.argv[1]; out = sys.argv[2]
KEYS = ['PRODUCT_ID', 'SEQUENCE_NUMBER', 'IMAGE_ID', 'PRODUCT_TYPE', 'START_TIME', 'STOP_TIME',
        'SPACECRAFT_CLOCK_START_COUNT', 'EXPOSURE_DURATION', 'EXPOSURE_TYPE',
        'PREDICTED_ALTITUDE', 'SPACECRAFT_ALTITUDE_START', 'SPACECRAFT_ALTITUDE_END',
        'AZIMUTH_START', 'AZIMUTH_END', 'AZIMUTH_NORTH_START', 'AZIMUTH_NORTH_END',
        'EW_TILT_ANGLE_START', 'SPIN_RATE', 'LAMP_STATE']
rows = []
for lbl in sorted(glob.glob(os.path.join(root, '**', '*.LBL'), recursive=True)):
    txt = open(lbl, encoding='latin1').read()
    head = txt.split('DESCRIPTION', 1)[0]
    r = {'label': os.path.relpath(lbl, root)}
    for k in KEYS:
        m = re.search(r'^\s*(?:HUYGENS:)?' + re.escape(k) + r'\s*=\s*"?([^"/\n<]*)', head, re.M)
        r[k] = m.group(1).strip() if m else ''
    for k in ('num_cols', 'num_rows', 'cycle_num', 'dataset type'):
        m = re.search(r'^' + k + r':\s*(.+)$', txt, re.M)
        r[k] = m.group(1).strip() if m else ''
    rows.append(r)
with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(len(rows), 'labels ->', out)
