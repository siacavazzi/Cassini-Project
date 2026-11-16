#!/bin/zsh
# deepopt thread: the full-view pair on PR 482's newest commit (d0490078) and the fix merged up to it (d6a06f10), on
# the MacBook's main mosaics build (runs/v2/main); run under one slot
D=~/cassini-build/deepopt; source $D/env.sh
F=$D/runs/full2; B=$D/bench/build_each.sh
rm -rf $F; mkdir -p $F/full482b
cp -cR $D/runs/v2/main/cache $F/full482b/cache && cp $D/runs/v2/main/geometry.sqlite $F/full482b/geometry.sqlite
$B $D/base-full2 $F/full482b $D/runs/passes4m.txt 1 fullview
$B $D/work-full $F/fullnewb $D/runs/passes4m.txt 1
( cd $D && nice -n 19 $PY bench/cmp_items.py $F/full482b/cache $F/fullnewb/cache $D/runs/names4m.txt > $F/cmp-b.txt 2>&1; echo "exit $?" >> $F/cmp-b.txt )
( cd $D && $PY bench/full_table.py $D/runs/v2/main $F/full482b $F/fullnewb $D/runs/passes4m.txt > $F/table.md 2>&1 )
$B $D/work-full $F/fullnewb $D/runs/passes4m.txt 1 fullview
echo FULL2 DONE > $F/done.txt
