#!/usr/bin/env python3
"""The label loader skips the archive's stray label copies ("<frame> (1).LBL" beside the frame's own label, audit S5).
  python web/test_stray_labels.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import label_handler as lh


def main():
    names = ["N1507733542_2.LBL", "N1507733542_2.png", "N1507733542_2 (1).LBL", "N1507733542_2.prefix.gz",
             "W1600000000_1 (2).lbl", "w1600000000_1.LBL", "N1700000000_1 (1).LBL", "N1700000000_2.LBL"]
    got = lh.frame_labels(names)
    # a copy beside its twin (any case) is left out; a "(1)" with no twin is the frame's only label and stays
    assert got == ["N1507733542_2.LBL", "w1600000000_1.LBL", "N1700000000_1 (1).LBL", "N1700000000_2.LBL"], got
    assert lh.frame_labels([]) == []
    print("stray label copies skipped, twinless ones kept: ok")


if __name__ == "__main__":
    main()
