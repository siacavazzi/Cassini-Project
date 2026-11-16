#!/bin/zsh
# deepopt thread: the grown-mosaic fix (finding 18, work-grown = main + the fix) through the pre-build: the two
# toss-up passes in main's order, the four mosaic passes, and the toss-up passes with #503 too (work-grown503);
# compared with main's and #503's builds. Run under one slot
D=~/cassini-build/deepopt; source $D/env.sh
G=$D/runs/grown; B=$D/bench/build_each.sh; T=$D/runs/toss2
rm -rf $G; mkdir -p $G
$B $D/work-grown $G/g18 $D/runs/passes_toss2.txt 1
$B $D/work-grown503 $G/both $D/runs/passes_toss2.txt 1
$B $D/work-grown $G/g18 $D/runs/passes4m.txt 1
cd $D
nice -n 19 $PY bench/cmp_pixels.py $T/fix/cache $G/both/cache runs/names_toss2.txt > $G/both-vs-503.md 2>&1
nice -n 19 $PY bench/cmp_pixels.py $T/fix/cache $G/g18/cache runs/names_toss2.txt > $G/g18-vs-503.md 2>&1
nice -n 19 $PY bench/cmp_pixels.py $T/main/cache $G/g18/cache runs/names_toss2.txt > $G/g18-vs-main.md 2>&1
nice -n 19 $PY bench/cmp_pixels.py runs/v2/main/cache $G/g18/cache runs/names4m.txt > $G/mosaics-vs-main.md 2>&1
quiet() { grep -v "number of lines\|^\[\|^[0-9.]*$" }
for P in SATURN_ISS_108RI_MNRNGSHAD005_PRIME_N_0 ENCELADUS_ISS_088EN_SECLNX001_CIRS_N_1; do
  for v in g18 both; do
    cp -cR $G/$v/cache $G/$v-check-$P; cp $G/$v/geometry.sqlite $G/$v-check-$P.sqlite
    ( cd $D/dev && WT=$D/work-grown CASSINI_GEOMETRY_CACHE=$G/$v-check-$P.sqlite PYTHONHASHSEED=0 nice -n 19 $PY $D/bench/tossup_check.py $G/$v-check-$P $P 2>&1 | quiet > $G/check-$v-$P.txt )
  done
  # the finished view and three on the way: #503's build (left) against main's order with the fix (middle)
  cp -cR $T/fix/cache $G/a-sheet-$P; cp -cR $G/g18/cache $G/b-sheet-$P; cp $G/g18/geometry.sqlite $G/sheet-$P.sqlite
  ( cd $D/work-grown && WT=$D/work-grown CASSINI_GEOMETRY_CACHE=$G/sheet-$P.sqlite PYTHONHASHSEED=0 nice -n 19 $PY $D/bench/tossup_sheet.py $G/a-sheet-$P $G/b-sheet-$P $P $G/sheet-$P 2>&1 | quiet > $G/sheet-$P.log )
done
echo GROWN DONE > $G/done.txt
