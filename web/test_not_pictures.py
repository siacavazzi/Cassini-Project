#!/usr/bin/env python3
"""not_pictures.why: a label's shutter and lamp flags say whether its frame holds a picture.
  python web/test_not_pictures.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import not_pictures as npx


def main():
    lab = lambda **kv: "".join(f"  {k} = {v}\r\n" for k, v in kv.items()).encode()
    assert npx.why(lab(SHUTTER_STATE_ID='"DISABLED"', CALIBRATION_LAMP_STATE_FLAG='"OFF"')) == "dark"
    assert npx.why(lab(SHUTTER_STATE_ID="ENABLED", CALIBRATION_LAMP_STATE_FLAG="ON")) == "lamp"
    assert npx.why(lab(SHUTTER_STATE_ID="ENABLED", CALIBRATION_LAMP_STATE_FLAG='"N/A"')) is None
    assert npx.why(lab(SHUTTER_STATE_ID="DISABLED", CALIBRATION_LAMP_STATE_FLAG="ON")) == "dark"
    assert npx.why(b"") is None
    # (another keyword ending in the same name is not the flag)
    assert npx.why(lab(XSHUTTER_STATE_ID="DISABLED")) is None
    ids = npx.ids()
    assert len(ids) == 4066 and ids.get("N1338691304_1") == "dark" and ids.get("W1294561143_1") == "lamp", len(ids)
    print("darks and lamp frames read from their labels; the list holds 4,066: ok")


if __name__ == "__main__":
    main()
