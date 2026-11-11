#!/bin/zsh
# run.sh: AFTER then BEFORE, one process at a time, nice 19, fresh scratch caches on the T7
W=/Volumes/SAM_IAC_PHOTO/cassini-work
source $W/scratch-tilt/_tilt/env.sh || exit 1
for side in after before; do
  if [ $side = after ]; then cd $W/scratch-tilt; S=_tilt/mm; else cd $W/scratch-tilt-before; S=_mm; fi
  export CASSINI_FULLRES_CACHE=$W/scratch-tilt-cache-$side/fullres
  nice -n 19 $PY $S/render_mm.py $S/picks.json $W/scratch-tilt/_tilt/mm/out-$side $W/scratch-tilt-cache-$side/cache 2>&1 | grep -v -i warning
  ~/agents/bin/job update tilt-mm "$side done" --pct $([ $side = after ] && echo 50 || echo 95)
done
echo ALLDONE
