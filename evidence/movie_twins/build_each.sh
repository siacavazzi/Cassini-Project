#!/bin/zsh
# build_each.sh CHECKOUT OUTDIR LIST [AT_ONCE] [PHASE_OVERRIDE]: each pass of LIST ("NAME phase" a line) made by a
# prebuild.py process of its own (its phase, --only the pass's frames, one thread), AT_ONCE processes side by side,
# into OUTDIR/cache with a private geometry copy. A process of its own per pass, so every build of a pass has the same
# history (a process that made other passes first can differ by a level in a few pixels of a level-matched mosaic).
# CPU seconds per pass in OUTDIR/times.txt
setopt NO_BG_NICE
D=~/cassini-build/deepopt
source $D/env.sh
WT=$1; OUT=$2; LIST=$3; AT=${4:-6}; PH=$5
mkdir -p $OUT/log $OUT/status $OUT/cache
[ -f $OUT/geometry.sqlite ] || cp $INP/geometry-usgs.sqlite $OUT/geometry.sqlite
export CASSINI_GEOMETRY_CACHE=$OUT/geometry.sqlite PYTHONHASHSEED=0
cd $WT
one() {
  local name=$1 phase=${PH:-$2}
  /usr/bin/time -l nice -n 19 $PY -u web/frames/prebuild.py $phase --cache $OUT/cache --status $OUT/status/$name-$phase --disk "" --live "" \
     --max-load 400 --min-free 20 --pause $OUT/pause --threads 1 --only $D/runs/ids/$name.txt > $OUT/log/$name-$phase.log 2> $OUT/log/$name-$phase.time
  local rc=$?
  local cpu=$(grep -E "^ *[0-9.]+ real" $OUT/log/$name-$phase.time | awk '{print $3 + $5}')
  local mem=$(grep "peak memory footprint" $OUT/log/$name-$phase.time | awk '{printf "%.0f", $1 / 1e6}')
  echo "$name $phase exit $rc cpu $cpu s peak $mem MB errors $(cat $OUT/status/$name-$phase/errors-*.jsonl 2>/dev/null | wc -l | tr -d ' ')" >> $OUT/times.txt
}
n=0
while read name phase; do
  [ -z "$name" ] && continue
  one $name $phase &
  n=$((n + 1))
  if [ $((n % AT)) -eq 0 ]; then wait; fi
done < $LIST
wait
