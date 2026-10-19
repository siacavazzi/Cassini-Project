"""Minimal binary PGM (P5) reader that keeps raw values (Pillow rescales 16-bit PGMs by maxval)."""
import re
import numpy as np


def read_pgm(path):
    b = open(path, "rb").read()
    # header: magic, width, height, maxval, each separated by whitespace (comments allowed)
    tokens, pos = [], 0
    while len(tokens) < 4:
        m = re.compile(rb"\s*(#[^\n]*\n\s*)*(\S+)").match(b, pos)
        tokens.append(m.group(2)); pos = m.end()
    assert tokens[0] == b"P5", tokens[0]
    w, h, maxval = int(tokens[1]), int(tokens[2]), int(tokens[3])
    pos += 1
    dt = ">u2" if maxval > 255 else "u1"
    a = np.frombuffer(b, dt, w * h, pos).reshape(h, w).astype(np.float64)
    return a, maxval
