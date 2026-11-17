#!/bin/zsh
# deepopt thread: the AFTER runs of the rewritten fix (a thumbnail's pass picture is shrunk from one the cache holds,
# obs_mosaic.kept_webp), inside one limiter job of 2 slots. Every run is stopped when its footprint passes 10 GB.
#  1. the 8996 preview's case: its code c7d77bc4 with the fix (work-idle-c7fix) started on a clone of my copy of its
#     highlight passes and thumbnails, sent no request; then the routes a page asks for
#  2. all 27 thumbnails made by the fix on a clone of that copy WITHOUT its kept thumbnails, one after another with
#     the footprint beside each: for the before/after sheet against the 16 the old code had made
#  3. main with the fix (work-idle) on an empty cache, as the first run's "after" (that one had the first cut)
# The BEFORE runs are the earlier jobs': runs/idle/f9-before-run (c7d77bc4 on the copy) and runs/idle/before (main,
# empty cache).
D=/Users/samiacavazzi/cassini-build/deepopt; source $D/env.sh; I=$D/runs/idle
FX=$D/work-idle-c7fix; W=$D/work-idle
export PYTHONUNBUFFERED=1
free=$(df -k /System/Volumes/Data | tail -1 | awk '{print int($4/1048576)}')
if [ $free -lt 60 ]; then echo "not started: only $free GB free"; exit 1; fi
for name in f9-after2 f9-parts-after2 cache-after-main2; do
  [ -e $I/$name ] && { echo "$I/$name is there already: not reused"; exit 1; }
done

date "+%H:%M:%S after on the preview copy"
cp -c -R $I/cache-f9 $I/f9-after2; cp -c $I/geometry-f9.sqlite $I/f9-after2.sqlite
cd $FX
CASSINI_GEOMETRY_CACHE=$I/f9-after2.sqlite $PY $D/prof/idle_watch.py --out $I/f9-after2-run --cap-gb 10 --max-s 900 \
  --check "http://127.0.0.1:8975/" --check "http://127.0.0.1:8975/health" --check "http://127.0.0.1:8975/version.json" \
  --check "http://127.0.0.1:8975/data/mission.json" --check "http://127.0.0.1:8975/data/highlights.json" \
  --check "http://127.0.0.1:8975/frames/thumb.webp?mosaic=W1750962990_1&color=W1750962915_1,W1750962932_1,W1750962898_1&frame=W1750962990_1" \
  --check "http://127.0.0.1:8975/frames/thumb.webp?mosaic=N1644781904_1" \
  --check "http://127.0.0.1:8975/frames/thumb.webp?mosaic=W1859483408_1" \
  --check "http://127.0.0.1:8975/frames/W1750962990_1.webp?size=256" -- \
  $PY web/frames/frame_server.py --site web/cassini-os --port 8975 --cache $I/f9-after2 --usage off

date "+%H:%M:%S thumbnails by the fix"
mkdir $I/f9-parts-after2; cp -c -R $I/cache-f9/obs-v119-q95 $I/f9-parts-after2/; cp -c $I/geometry-f9.sqlite $I/f9-parts-after2.sqlite
cd $FX
CASSINI_GEOMETRY_CACHE=$I/f9-parts-after2.sqlite $PY $D/prof/idle_parts.py --wt $FX --site $FX/web/cassini-os --cache $I/f9-parts-after2 \
  --part thumbs --cap-gb 10 --max-s 900 --stacks-every 5 --holders > $I/f9-parts-after2.log 2>&1
echo "thumbnails exit $? $(date +%H:%M:%S)"

date "+%H:%M:%S after on main, empty cache"
cp -c $INP/geometry-usgs.sqlite $I/geometry-after-main2.sqlite
cd $W
CASSINI_GEOMETRY_CACHE=$I/geometry-after-main2.sqlite $PY $D/prof/idle_watch.py --out $I/after-main2 --cap-gb 10 --max-s 900 \
  --check "http://127.0.0.1:8976/" --check "http://127.0.0.1:8976/health" \
  --check "http://127.0.0.1:8976/data/mission.json" \
  --check "http://127.0.0.1:8976/frames/thumb.webp?color=N1352055787_2,N1352055720_2,N1352055683_2" \
  --check "http://127.0.0.1:8976/frames/thumb.webp?mosaic=N1356763606_1&frame=W1356763606_1" \
  --check "http://127.0.0.1:8976/frames/thumb.webp?mosaic=N1644781904_1" -- \
  $PY web/frames/frame_server.py --site web/cassini-os --port 8976 --cache $I/cache-after-main2 --usage off
#  4. what the coordinator plans for 8996 today: the OLD code c7d77bc4, with thumbnails 16 and 19 already in the
#     cache (my two files), started and sent no request; then, once it is idle, what a camera window asks for when
#     a person opens the north polar movie (its picture at the first, a middle and the last frame, at 1024 and 512,
#     and the same for the 251SA movie), with the footprint sampled until the server is idle again
date "+%H:%M:%S old code with thumbnails 16 and 19 in place, then a window on the movie"
[ -e $I/f9-two-old ] && { echo "f9-two-old is there already"; exit 1; }
cp -c -R $I/cache-f9 $I/f9-two-old; cp -c $I/geometry-f9.sqlite $I/f9-two-old.sqlite
cp $I/thumbs-8996/c2cb1c30a55f9c2032d4.webp $I/thumbs-8996/c2cb1c30a55f9c2032d4.json $I/thumbs-8996/061b6b0b89ed85d03827.webp \
   $I/thumbs-8996/061b6b0b89ed85d03827.json $I/f9-two-old/thumb-v23/
cd $D/work-idle-c7
M="mode=rolling&laps=1"
CASSINI_GEOMETRY_CACHE=$I/f9-two-old.sqlite $PY $D/prof/idle_watch.py --out $I/f9-two-old-run --cap-gb 10 --max-s 900 \
  --check "http://127.0.0.1:8977/frames/movie/W1750962990_1.webp?size=1024&$M" \
  --check "http://127.0.0.1:8977/frames/movie/W1750962990_1.webp?size=512&$M" \
  --check "http://127.0.0.1:8977/frames/movie/W1750904325_1.webp?size=1024&$M" \
  --check "http://127.0.0.1:8977/frames/movie/W1750933965_1.webp?size=1024&$M" \
  --check "http://127.0.0.1:8977/frames/movie/W1859483408_1.webp?size=1024&$M" \
  --check "http://127.0.0.1:8977/frames/movie/W1859503273_1.webp?size=1024&$M" \
  --check "http://127.0.0.1:8977/frames/thumb.webp?mosaic=W1750962990_1&color=W1750962915_1,W1750962932_1,W1750962898_1&frame=W1750962990_1" -- \
  $PY web/frames/frame_server.py --site web/cassini-os --port 8977 --cache $I/f9-two-old --usage off
date "+%H:%M:%S done"
echo IDLE HEAVY3 DONE
