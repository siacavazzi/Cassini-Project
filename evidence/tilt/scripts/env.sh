for f in /Volumes/SAM_IAC_PHOTO/cassini-work/archives/cassiniprojectJAN05.zip /Volumes/SAM_IAC_PHOTO/cassini-work/archives/cassini_lut8.zip; do
  [ -s "$f" ] || { echo "MISSING $f, refusing to run"; exit 1; }
done
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 CASSINI_WORKERS=1 CASSINI_MOVIE_WORKERS=1 CASSINI_ROLL_WORKERS=1
export CASSINI_DATA=/Volumes/SAM_IAC_PHOTO/cassini-work/archives/cassini_lut8.zip
export CASSINI_KERNELS=/Volumes/SAM_IAC_PHOTO/cassini-work/archives/cassiniprojectJAN05.zip
export CASSINI_SPICE_CACHE=/Volumes/LaCie/claude_scratch_spk/usgs_render_spice_cache CASSINI_KEEP_SPICE_CACHE=1
export CASSINI_CISSCAL=/Volumes/LaCie/cassini_calibration/cisscal
export CASSINI_GEOMETRY_CACHE=/Volumes/LaCie/claude_scratch_spk/geometry.sqlite
export CASSINI_INDEX_CACHE=/Users/lazarus/dev/scratch/saturnposter-zipindex
export CASSINI_FULLRES_CACHE=/Volumes/SAM_IAC_PHOTO/cassini-work/scratch-tilt/_tilt/fullres
export MPLBACKEND=Agg
PY=/Users/lazarus/dev/Cassini-Project/.venv/bin/python
