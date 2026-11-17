#!/bin/zsh
# deepopt thread: the 8996 preview's own case on my copy, inside one limiter job of 2 slots. The preview runs code
# c7d77bc4 on the f9ab1b4 cache; its twelve highlight mosaic passes and its thumb-v23 folder (16 of 27 thumbnails,
# numbers 0 to 15) are copied to runs/idle/cache-f9, its geometry file to runs/idle/geometry-f9.sqlite. Every run
# works on an APFS clone of that copy and is stopped when its footprint passes 10 GB.
#  1. the missing thumbnails one at a time, each in a process of its own, with the footprint and what every thread is
#     in every 5 s, and what holds the memory when the cap stops it: 16 (the 728-frame north-polar movie) first
#  2. BEFORE: c7d77bc4's server started on the copy and sent no request, footprint every 2 s
#  3. AFTER (only when runs/idle/after2-ready exists): the same with the fix (work-idle-c7fix), then its thumbnails
#     one at a time as in 1, and the routes a page asks for
D=/Users/samiacavazzi/cassini-build/deepopt; source $D/env.sh; I=$D/runs/idle
C7=$D/work-idle-c7; FX=$D/work-idle-c7fix
export PYTHONUNBUFFERED=1
free=$(df -k /System/Volumes/Data | tail -1 | awk '{print int($4/1048576)}')
if [ $free -lt 60 ]; then echo "not started: only $free GB free"; exit 1; fi
clone() { [ -e $I/$1 ] && { echo "$I/$1 is there already: not reused"; exit 1; }; cp -c -R $I/cache-f9 $I/$1; cp -c $I/geometry-f9.sqlite $I/$1.sqlite; }   # $1: a new name under runs/idle

date "+%H:%M:%S parts before"
clone f9-parts; cd $C7
for k in 16 17 18 19 23 25 "20,21,22,24,26"; do
  CASSINI_GEOMETRY_CACHE=$I/f9-parts.sqlite $PY $D/prof/idle_parts.py --wt $C7 --site $C7/web/cassini-os --cache $I/f9-parts \
    --part thumbs --thumbs $k --cap-gb 10 --max-s 900 --stacks-every 5 > $I/f9-parts-${k//,/_}.log 2>&1
  echo "thumbnail $k exit $? $(date +%H:%M:%S)"
done

date "+%H:%M:%S before"
clone f9-before; cd $C7
CASSINI_GEOMETRY_CACHE=$I/f9-before.sqlite $PY $D/prof/idle_watch.py --out $I/f9-before-run --cap-gb 10 --max-s 900 -- \
  $PY web/frames/frame_server.py --site web/cassini-os --port 8973 --cache $I/f9-before --usage off

if [ -f $I/after2-ready ]; then
  date "+%H:%M:%S after"
  clone f9-after; cd $FX
  CASSINI_GEOMETRY_CACHE=$I/f9-after.sqlite $PY $D/prof/idle_watch.py --out $I/f9-after-run --cap-gb 10 --max-s 900 \
    --check "http://127.0.0.1:8974/" --check "http://127.0.0.1:8974/health" --check "http://127.0.0.1:8974/version.json" \
    --check "http://127.0.0.1:8974/data/mission.json" --check "http://127.0.0.1:8974/data/highlights.json" \
    --check "http://127.0.0.1:8974/frames/thumb.webp?mosaic=W1750962990_1&color=W1750962915_1,W1750962932_1,W1750962898_1&frame=W1750962990_1" \
    --check "http://127.0.0.1:8974/frames/thumb.webp?mosaic=N1644781904_1" \
    --check "http://127.0.0.1:8974/frames/W1750962990_1.webp?size=256" -- \
    $PY web/frames/frame_server.py --site web/cassini-os --port 8974 --cache $I/f9-after --usage off
  date "+%H:%M:%S parts after"
  # (a clone without the kept thumbnails: the fix makes all 27, for the before/after sheet)
  [ -e $I/f9-parts-after ] && { echo "f9-parts-after is there already"; exit 1; }
  mkdir $I/f9-parts-after; cp -c -R $I/cache-f9/obs-v119-q95 $I/f9-parts-after/; cp -c $I/geometry-f9.sqlite $I/f9-parts-after.sqlite
  cd $FX
  CASSINI_GEOMETRY_CACHE=$I/f9-parts-after.sqlite $PY $D/prof/idle_parts.py --wt $FX --site $FX/web/cassini-os --cache $I/f9-parts-after \
    --part thumbs --cap-gb 10 --max-s 900 --stacks-every 5 --holders > $I/f9-parts-after.log 2>&1
  echo "parts after exit $? $(date +%H:%M:%S)"
fi
date "+%H:%M:%S done"
echo IDLE HEAVY2 DONE
