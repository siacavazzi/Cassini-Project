#!/bin/zsh
# parity.sh: prebuild composites + processed for parity-ids.txt with CASSINI_HDR=0 and =1, timed
source /Volumes/SAM_IAC_PHOTO/cassini-work/hdr/env.sh
cd $W
for flag in ${FLAGS:-0 1}; do
  C=$H/parity-$flag; mkdir -p $C
  for ph in composites processed; do
    s=$(date +%s)
    CASSINI_HDR=$flag $PY web/frames/prebuild.py $ph --cache $C --only $H/parity-ids.txt --threads 1 --live '' --pause $H/none.pause > $H/parity-$flag-$ph.log 2>&1
    echo "hdr=$flag $ph rc=$? $(( $(date +%s) - s )) s" >> $H/parity-times.txt
  done
done
echo DONE >> $H/parity-times.txt
