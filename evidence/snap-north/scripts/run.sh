#!/bin/zsh
W=/Volumes/SAM_IAC_PHOTO/cassini-work
source $W/scratch-tilt/_tilt/env.sh >/dev/null || exit 1
for side in after before; do
  if [ $side = after ]; then cd $W/wt-snapnorth; S=_snap/render.py; else cd $W/wt-snapnorth-before; S=render_snap.py; fi
  export CASSINI_FULLRES_CACHE=$W/wt-snapnorth/_snap/cache-$side/fullres
  nice -n 19 $PY $S $W/wt-snapnorth/_snap/out-$side $W/wt-snapnorth/_snap/cache-$side/cache 2>&1 | grep -v -i warning
  ~/agents/bin/job update snapnorth "$side done" --pct $([ $side = after ] && echo 50 || echo 95)
done
~/agents/bin/job done snapnorth "renders finished"
echo ALLDONE
