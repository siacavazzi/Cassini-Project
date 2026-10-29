#!/bin/bash
# Spot check round 2 (single frames): fetch each frame from the 8861 preview (new) and the live 8765 (old),
# keep PNGs in $OUT/png, push full-size JPEGs to the branch scratch/qc2-frames every 40 frames.
# usage: bash run.sh ids.txt ~/Documents/qc2-frames
set -u
IDS=$1; OUT=$2; HERE=$(cd "$(dirname "$0")" && pwd)
PY=~/dev/Cassini-Project/.venv/bin/python
mkdir -p "$OUT/png" "$OUT/hdr" "$OUT/git/jpg"
if [ ! -d "$OUT/git/.git" ]; then
  git init -q "$OUT/git" && git -C "$OUT/git" checkout -q -b qc2
  git -C "$OUT/git" remote add origin "$(git -C ~/dev/Cassini-Project remote get-url origin)"
fi
push() {
  cp "$OUT/codes.tsv" "$OUT/git/"; mkdir -p "$OUT/git/hdr"; cp "$OUT"/hdr/*.txt "$OUT/git/hdr/" 2>/dev/null
  git -C "$OUT/git" add -A && git -C "$OUT/git" commit -qm "qc2 frames: $1" && git -C "$OUT/git" push -q origin HEAD:refs/heads/scratch/qc2-frames
  echo "pushed $1"
}
n=0
while read -r id; do
  for v in new ctr old oldctr raw; do
    case $v in
      new)    url="http://127.0.0.1:8861/frames/processed/$id.webp?size=full&format=png";;
      ctr)    url="http://127.0.0.1:8861/frames/processed/$id.webp?size=full&format=png&center=1";;
      old)    url="http://127.0.0.1:8765/frames/processed/$id.webp?size=full&format=png";;
      oldctr) url="http://127.0.0.1:8765/frames/processed/$id.webp?size=full&format=png&center=1";;
      raw)    url="http://127.0.0.1:8861/frames/$id.webp?size=full&format=png";;
    esac
    f="$OUT/png/${id}__$v.png"
    [ -s "$f" ] && continue
    code=000
    for try in 1 2 3 4 5 6 7 8; do
      code=$(curl -s -m 900 -D "$OUT/hdr/${id}__$v.txt" -o "$f.part" -w '%{http_code}' "$url")
      [ "$code" = 503 ] && { sleep 6; continue; }
      break
    done
    printf '%s\t%s\t%s\t%s\n' "$id" "$v" "$code" "$(date -u +%H:%M:%S)" >> "$OUT/codes.tsv"
    if [ "$code" = 200 ]; then mv "$f.part" "$f"; else rm -f "$f.part"; fi
  done
  "$PY" "$HERE/tojpg.py" "$OUT/png" "$OUT/git/jpg" "$id"
  n=$((n+1))
  [ $((n % 40)) = 0 ] && push "$n"
done < "$IDS"
push "all $n"
echo DONE
