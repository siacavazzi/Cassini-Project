# Notes

Write-ups from work that ran on Sam's MacBook before it was cleared (2026-10-19), kept so they are not lost.

- `huygens-data-findings.md`: what the Huygens downloads (DTWG trajectory, DISR imager) contain and how they
  were used for the Huygens exporters in `web/huygens/`. Paths in it point at the old MacBook folder; the raw
  data now lives on the Mac Mini in `~/agents/shared/macbook-handoff/huygens-data`.
- `huygens-data-scripts/`: the small label, table and SPK coverage scripts used for those findings.
- `lean-archive-test/`: the 12-bit frame format test that led to the lean archive plan (8-bit square-root LUT
  codes), including the old `calibration.py` span bug that PR #9 fixed.

Left out of the repo (still on the Mac Mini in `~/agents/shared/macbook-handoff/`): benchmark and pipeline
logs, the 16,722-line Huygens download manifest, per-frame metrics, and copies of tools that are already in
`web/` and `web/huygens/`.
