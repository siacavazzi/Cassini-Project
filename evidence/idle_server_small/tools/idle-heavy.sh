#!/bin/zsh
# deepopt thread: the heavy part of the idle-server measurements, run inside one limiter job of 2 slots (it waits its
# turn behind the overnight cache build). Every run is capped: the server or driver is stopped when its footprint
# passes 10 GB, so the runaway under test cannot take this Mac's memory.
#  1. BEFORE: main 02598865's server started on an empty cache and sent no request, footprint every 2 s
#  2. which warm-up: the thumbnails warm-up alone, one highlight at a time, and what holds the memory at the cap
#  3. AFTER (only when runs/idle/after-ready exists): the fixed server (work-idle) the same way as 1
# An empty cache is the worst case of a cache that does not match the code's versions: nothing the server's own
# versions name is there.
D=/Users/samiacavazzi/cassini-build/deepopt; source $D/env.sh; I=$D/runs/idle
B=$D/work-idle-base; W=$D/work-idle
export PYTHONUNBUFFERED=1
free=$(df -k /System/Volumes/Data | tail -1 | awk '{print int($4/1048576)}')
if [ $free -lt 60 ]; then echo "not started: only $free GB free"; exit 1; fi
date "+%H:%M:%S before"
cd $B   # the server is run from its checkout (stacking reads Image_index.csv from the working directory)
CASSINI_GEOMETRY_CACHE=$I/geometry-before.sqlite $PY $D/prof/idle_watch.py --out $I/before --cap-gb 10 --max-s 900 -- \
  $PY web/frames/frame_server.py --site web/cassini-os --port 8971 --cache $I/cache-before --usage off
date "+%H:%M:%S parts"
cd $B
CASSINI_GEOMETRY_CACHE=$I/geometry-parts.sqlite $PY $D/prof/idle_parts.py --wt $B --site $B/web/cassini-os --cache $I/cache-parts \
  --part thumbs --cap-gb 10 --max-s 1200 > $I/parts-thumbs.log 2>&1
echo "parts exit $?"
if [ -f $I/after-ready ]; then
  date "+%H:%M:%S after"
  cd $W
  CASSINI_GEOMETRY_CACHE=$I/geometry-after.sqlite $PY $D/prof/idle_watch.py --out $I/after-heavy --cap-gb 10 --max-s 900 \
    --check "http://127.0.0.1:8972/" --check "http://127.0.0.1:8972/health" --check "http://127.0.0.1:8972/version.json" \
    --check "http://127.0.0.1:8972/data/mission.json" --check "http://127.0.0.1:8972/data/highlights.json" \
    --check "http://127.0.0.1:8972/frames/thumb.webp?color=N1352055787_2,N1352055720_2,N1352055683_2" \
    --check "http://127.0.0.1:8972/frames/thumb.webp?mosaic=N1356763606_1&frame=W1356763606_1" \
    --check "http://127.0.0.1:8972/frames/W1356763606_1.webp?size=256" -- \
    $PY web/frames/frame_server.py --site web/cassini-os --port 8972 --cache $I/cache-after-heavy --usage off
  date "+%H:%M:%S parts after"
  CASSINI_GEOMETRY_CACHE=$I/geometry-parts.sqlite $PY $D/prof/idle_parts.py --wt $W --site $W/web/cassini-os --cache $I/cache-parts-after \
    --part thumbs,icons --cap-gb 10 --max-s 1200 --holders > $I/parts-thumbs-after.log 2>&1
  echo "parts after exit $?"
fi
#  4. the page shows the same: one small highlight pass (Mimas 126MI, 37 frames) built by the pre-build with main's
#     code, then its thumbnail made by main and by the fix, each on a clone of that cache: the same bytes
if [ -f $I/after-ready ]; then
  date "+%H:%M:%S built pass"
  P=MIMAS_ISS_126MI_GEOLOG002_PRIME_N_0; H='{"mosaic": "N1644781904_1"}'
  cp -c $INP/geometry-usgs.sqlite $I/geometry-built.sqlite
  cd $B
  CASSINI_GEOMETRY_CACHE=$I/geometry-built.sqlite PYTHONHASHSEED=0 $PY -u web/frames/prebuild.py mosaics --cache $I/cache-built \
    --status $I/status-built --disk "" --live "" --max-load 400 --min-free 20 --pause $I/pause-built --threads 1 \
    --only $I/ids-$P.txt > $I/built-prebuild.log 2>&1
  echo "prebuild exit $?"
  cp -c -R $I/cache-built $I/cache-built-before; cp -c -R $I/cache-built $I/cache-built-after
  cp -c $I/geometry-built.sqlite $I/geometry-built-before.sqlite; cp -c $I/geometry-built.sqlite $I/geometry-built-after.sqlite
  cd $B; CASSINI_GEOMETRY_CACHE=$I/geometry-built-before.sqlite $PY $D/prof/one_thumb.py --wt $B --cache $I/cache-built-before \
    --hint "$H" --out $I/thumb-built-before.webp > $I/thumb-built-before.log 2>&1
  cd $W; CASSINI_GEOMETRY_CACHE=$I/geometry-built-after.sqlite $PY $D/prof/one_thumb.py --wt $W --cache $I/cache-built-after \
    --hint "$H" --out $I/thumb-built-after.webp > $I/thumb-built-after.log 2>&1
  shasum $I/thumb-built-before.webp $I/thumb-built-after.webp
  cmp -s $I/thumb-built-before.webp $I/thumb-built-after.webp && echo "built-pass thumbnail: IDENTICAL" || echo "built-pass thumbnail: DIFFERENT"
fi
date "+%H:%M:%S done"
echo IDLE HEAVY DONE
