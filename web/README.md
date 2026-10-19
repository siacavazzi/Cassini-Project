# Mission replay data

Tools that turn the SPICE kernels and `Image_index.csv` into small files a browser can load for the 3D mission replay.

| File | What it does |
| --- | --- |
| `export_tracks.py` | Writes `tracks/<body>/<year>.bin`, `catalog/<year>.json`, `encounters.json` and `manifest.json` |
| `verify_tracks.py` | Checks random points in every track against SPICE and draws overview plots |
| `tracks.js` | Browser/Node reader: `loadTrack(url)`, `positionAt(track, et)`, `utcToEt(iso)` |
| `test_tracks.mjs` | Prints interpolated positions from Node, for comparison with SPICE |
| `export_attitude.py` | Writes `attitude/<year>.bin` from the CK kernels in the archive zip |
| `verify_attitude.py` | Checks `attitudeAt()` from `tracks.js` against SPICE for random weeks of every exported year |
| `test_attitude.mjs` | Prints interpolated attitudes from Node (used by `verify_attitude.py`) |

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

`attitude/<year>.bin` (from `export_attitude.py`, which needs the CK kernels, about 35 GB, so it runs against the archive zip on the LaCie) is a 16-byte header (`CATT`, u16 version, u16 flags, u32 n_images, u32 n_background) followed by `f32 image_q[4*n_images]` (camera pointing at each image's mid-time, in catalog order, NaN where there is no CK data), `f64 bg_t[n_background]` and `f32 bg_q[4*n_background]` (spacecraft body attitude every 10 minutes). Quaternions are SPICE style (w, x, y, z) for the rotation J2000 -> frame.

In the browser, `parseAttitude(buffer, catalog.cam)` reads a year and `buildAttitude([{ file, et: catalog.et, cam: catalog.cam }, ...])` merges the background samples with every image's pointing (turned into body pointing with the fixed camera mounting from `cas_v41.tf`) into one series. `attitudeAt(att, et)` slerps between neighbouring samples; across gaps longer than an hour it holds the earlier attitude and eases into the next sample over its last 10 minutes. It returns the J2000 -> `CASSINI_SC_COORD` quaternion; for a three.js object (body -> world) use `new Quaternion(-x, -y, -z, w)`.

```
python web/verify_attitude.py --zip /Volumes/LaCie/cassiniprojectJAN05.zip --data replay_data \
    --catalog replay_data/catalog --tmp /Volumes/LaCie/verify_tmp
```

## Replay prototype

`replay/index.html` is the first viewer: the Saturn system for one year on the exported tracks, with a timeline to scrub or play, camera-frame density, and jumps to flybys. Build its data, then serve the folder with any static server:

```
python web/replay/build_data.py --data replay_data --year 2005 [--attitude replay_data/attitude] [--huygens <huygens replay folder>]
cd web/replay && python -m http.server
```

With `--attitude`, the year's pointing file is copied in (it must come from the same catalog export; the script checks the image count). The viewer then turns Cassini's model with the real attitude (dish on body -Z, cameras on body -Y) and draws the camera cone along the actual NAC or WAC boresight, rolled like the frame. Without it, the dish faces Earth and the cone is aimed at each frame's target.

With `--huygens` (the folder from `tools/build_huygens_track.py`, PR #10), the 2004 or 2005 build also gets `data/huygens.json`: the probe's track from separation to the day after landing, its event times and a 20 s altitude table for the descent. The viewer then shows the probe with its path relative to Titan, a Huygens focus button and an altitude line in the header. Without the file the viewer runs as before.

The page is written as an artifact body (no `<html>` wrapper); browsers render it as is.
