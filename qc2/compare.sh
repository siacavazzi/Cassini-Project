#!/bin/bash
# Colour softness before/after: the same movie frames from live 8765 (old code) and preview 8861 (main d4d9ecc),
# page defaults, color=1 and color=0. Report only: reads HTTP, writes under the gallery and the qc2 worktree.
set -u
OUT=~/dev/Cassini-Project/web/cassini-os/quality-check2/movies/compare
WT=~/Documents/qc2-movies-git
mkdir -p "$OUT"
IDS="N1677190045_1 N1677190133_1 N1677190221_1 N1677190309_1 N1677192549_1 N1677206605_1 N1519422341_1 N1519422360_1 N1519422390_1 N1519422428_1 N1519422454_1 N1519422759_1 N1640775312_1 N1640775367_1 N1640777023_1"
for port in 8765 8861; do
  for c in 1 0; do
    for id in $IDS; do
      f="$OUT/${port}_c${c}_${id}.webp"
      [ -s "$f" ] && continue
      for try in $(seq 1 60); do
        code=$(curl -s -o "$f" -w '%{http_code}' --max-time 240 "http://127.0.0.1:${port}/frames/movie/${id}.webp?size=512&color=${c}&trail=0&laps=1&exposure=8")
        [ "$code" = 200 ] && break
        rm -f "$f"; [ "$code" = 503 ] || { echo "$port $id c$c HTTP $code"; break; }
        sleep 4
      done
    done
  done
done
ls "$OUT" | wc -l
if [ ! -d "$WT" ]; then
  git -C ~/dev/Cassini-Project fetch -q origin claude/project-thread-7aaoos
  git -C ~/dev/Cassini-Project worktree add -q --detach "$WT" FETCH_HEAD
fi
cd "$WT" && git fetch -q origin claude/project-thread-7aaoos && git checkout -q --detach FETCH_HEAD
mkdir -p qc2/compare && cp "$OUT"/*.webp qc2/compare/
git add qc2/compare && git commit -qm "qc2 movies: colour softness 8765 vs 8861 frames" && \
  for k in 1 2 3 4; do git push -q origin HEAD:claude/project-thread-7aaoos && break; sleep $((2**k)); done
echo DONE
