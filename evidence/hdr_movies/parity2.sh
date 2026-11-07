#!/bin/zsh
# parity2.sh: prebuild movies + mosaics for movie-ids.txt (3 passes) with CASSINI_HDR=0 and =1, timed
source /Volumes/SAM_IAC_PHOTO/cassini-work/hdr/env.sh
cd $W
for flag in ${=FLAGS:-0 1}; do
  C=$H/parity2-$flag; mkdir -p $C
  for ph in mosaics movies; do
    s=$(date +%s)
    CASSINI_HDR=$flag nice -n 10 $PY web/frames/prebuild.py $ph --cache $C --only $H/movie-ids.txt --threads 1 --live '' --pause $H/none.pause > $H/parity2-$flag-$ph.log 2>&1
    echo "hdr=$flag $ph rc=$? $(( $(date +%s) - s )) s" >> $H/parity2-times.txt
  done
done
echo DONE >> $H/parity2-times.txt
