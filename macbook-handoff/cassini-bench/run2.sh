#!/bin/zsh
# usage: run2.sh <tag> [env assignments...]   (runs in new/, output must be empty)
cd ~/Development/cassini-bench/new; tag=$1; shift
swap() { sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}'; }
s0=$(swap); echo "swap before: $s0 MB"
mkdir -p output
( /usr/bin/time -l env PYTHONUNBUFFERED=1 CASSINI_DATA=/Volumes/LaCie/cassiniprojectJAN05.zip "$@" ~/Development/Cassini-Project/.venv/bin/python main.py 2> time2_$tag.txt \
  | while IFS= read -r l; do echo "[$SECONDS s] $l"; done > log2_$tag.txt ) &
job=$!; peak=$s0; killed=0; SECONDS=0
while kill -0 $job 2>/dev/null; do
  s=$(swap); (( s > peak )) && peak=$s
  if (( s - s0 > 2048 )); then echo "swap +$((s - s0)) MB, killing"; pkill -f "Cassini-Project/.venv/bin/python"; killed=1; fi
  sleep 2
done
echo "swap after: $(swap) MB, peak during run: $peak MB, killed=$killed"
grep -E "real|maximum resident" time2_$tag.txt
echo "frames: $(ls output/*/ | wc -l)"
mv output output2_$tag
