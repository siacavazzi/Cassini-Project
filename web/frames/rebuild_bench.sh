#!/bin/bash
# The rebuild benchmark on this machine (rebuild_bench.py): the opt-audit sample copied out of the archive, then
# every phase on one core twice, then several copies of a phase at once (every core). One summary line per run;
# the JSON files (each item's time, every file's hash) go to $B/out.
#   B=<empty work folder> ARCHIVE=<cassini_lut8.zip> GEOMETRY=<geometry.sqlite> REPO=<checkout> PY=<venv python> \
#     bash web/frames/rebuild_bench.sh [copies at once, default "4 <cores>"]
# The geometry cache is copied (sqlite3 .backup, so a live one is copied whole) and the archive only read.
set -u
here=$(cd "$(dirname "$0")" && pwd)
cores=$(sysctl -n hw.ncpu 2>/dev/null || nproc)
copies=${1:-"4 $cores"}
mkdir -p "$B/out" "$B/scratch"
cd "$B" || exit 1
export CASSINI_INDEX_CACHE=${CASSINI_INDEX_CACHE:-$REPO/zip_index}
"$PY" "$here/rebuild_bench.py" sample "$ARCHIVE" "$B/sample.zip" || { echo "the sample is not the cloud's; stopping"; exit 1; }
sqlite3 "$GEOMETRY" ".backup '$B/geometry.sqlite'" || cp "$GEOMETRY" "$B/geometry.sqlite"
export CASSINI_DATA=$B/sample.zip CASSINI_INDEX_CACHE=$B/zip_index CASSINI_SPICE_CACHE=$B/spice_cache
export CASSINI_GEOMETRY_CACHE=$B/geometry.sqlite MPLBACKEND=Agg FRAME_SERVER_QUIET=1 PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 REPO SCRATCH=$B/scratch
echo "code $(git -C "$REPO" log --oneline -1 | cut -c1-60); $("$PY" -c 'import platform, numpy, cv2, PIL; print(platform.platform(), platform.python_version(), "numpy", numpy.__version__, "cv2", cv2.__version__, "PIL", PIL.__version__)')"
for phase in frames processed composites movies mosaics; do
  for run in 1 2; do
    PHASE=$phase OUT=$B/out/one-$phase-$run.json "$PY" "$here/rebuild_bench.py" 2>/dev/null
  done
done
for phase in processed movies; do
  for k in $copies; do
    t0=$("$PY" -c 'import time; print(time.time())')
    for i in $(seq 1 "$k"); do
      PHASE=$phase OUT=$B/out/par$k-$phase-$i.json "$PY" "$here/rebuild_bench.py" >/dev/null 2>&1 &
    done
    wait
    "$PY" -c "import time; print('$phase: $k copies at once, all done in', round(time.time() - $t0, 2), 's')"
  done
done
