# Mission replay data

Tools that turn the SPICE kernels and `Image_index.csv` into small files a browser can load for the 3D mission replay.

| File | What it does |
| --- | --- |
| `export_tracks.py` | Writes `tracks/<body>/<year>.bin`, `catalog/<year>.json`, `encounters.json` and `manifest.json` |
| `verify_tracks.py` | Checks random points in every track against SPICE and draws overview plots |
| `tracks.js` | Browser/Node reader: `loadTrack(url)`, `positionAt(track, et)`, `utcToEt(iso)` |
| `test_tracks.mjs` | Prints interpolated positions from Node, for comparison with SPICE |

## Running

Only the SPK, LSK and PCK kernels are needed (about 1 GB), plus the yearly meta-kernels from `cosp_1000/index`:

```
kernels/
  mk/cas_YYYY*.tm
  spk/  lsk/  pck/
```

```
python web/export_tracks.py --kernels kernels --out replay_data [--highlights encounters_ranked.csv]
python web/verify_tracks.py --kernels kernels --data replay_data --plots plots
```

A full run takes about half an hour on one core; most of it is the flyby search.

## Formats

All positions are J2000, origin at the solar system barycentre, in km; times are TDB seconds past J2000 (SPICE ephemeris time).

Track files are a 16-byte header (`CTRK`, u16 version, u16 flags, u32 count, u32 reserved) followed by `f64 t[count]`, `f64 pos[3*count]` and `f32 vel[3*count]`. Interpolate with cubic Hermite between neighbouring samples (`tracks.js` does this). Samples are adaptive: the exporter bisects until the interpolation error, seen from Cassini, is under 5 microradians (about one narrow-angle camera pixel).

`catalog/<year>.json` holds column arrays, one entry per image: `id`, `et`, `cam` (N or W), `f1`, `f2`, `target`, `obs`, `range_km`, `phase_deg`, `km_per_px`, `missing_lines`.

`encounters.json` lists every closest approach (`kind: "flyby"`, with distance, altitude and speed, plus `photo_score` when the highlight scoring matched it) and mission milestones (`kind: "milestone"`).

`manifest.json` lists every body's chunks and coverage, and its IAU rotation constants and radii from the PCK.

Spacecraft attitude is not exported yet: it needs the CK kernels (about 35 GB), which only exist on the LaCie drive.
