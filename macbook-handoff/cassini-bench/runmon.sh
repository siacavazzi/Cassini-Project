#!/bin/zsh
# usage: runmon.sh <dir> <tag> [env assignments...]
cd $1; tag=$2; shift 2
( while true; do ps -A -o rss=,command= | grep "[C]assini-Project/.venv/bin/python" | awk "{s+=\$1} END {print s/1024 \" MB\"}"; date +%T; sysctl -n vm.swapusage; sleep 5; done ) > mem_$tag.txt 2>&1 &
mon=$!
/usr/bin/time -l env CASSINI_DATA=/Volumes/LaCie/cassiniprojectJAN05.zip "$@" ~/Development/Cassini-Project/.venv/bin/python main.py > log_$tag.txt 2> time_$tag.txt
echo "exit $?"
kill $mon
grep -E "real|maximum resident" time_$tag.txt
ls output/*/ | wc -l
