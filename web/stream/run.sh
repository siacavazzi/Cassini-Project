#!/bin/bash
# Keeps the stream running: starts stream.mjs at low priority and starts it again whenever it stops on its own.
#   web/stream/run.sh --out /path/hls/index.m3u8 [more stream.mjs options]
# Run it in tmux (tmux new -d -s stream 'web/stream/run.sh ...'); Ctrl-C or `tmux kill-session -t stream` ends it.
#
# STREAM_PRIORITY  background (default): macOS background QoS (taskpolicy -b, mostly the efficiency cores, throttled
#                  disk) and nice 20, so builds and servers always come first and the stream gets what is left;
#                  utility: a step up, for when the stream stutters and the Mini has room; normal: no clamp.
# STREAM_STATE     where logs, stats.jsonl and Chrome's profile live (default ~/server/stream).
# STREAM_URL       the page (default the live site in ambient mode, live clock).
set -u
here=$(cd "$(dirname "$0")" && pwd)
state=${STREAM_STATE:-$HOME/server/stream}
url=${STREAM_URL:-http://127.0.0.1:8765/?ambient=live}
mkdir -p "$state"
case "${STREAM_PRIORITY:-background}" in
  background) if command -v taskpolicy >/dev/null; then wrap=(taskpolicy -b nice -n 20); else wrap=(nice -n 19); fi ;;
  utility)    if command -v taskpolicy >/dev/null; then wrap=(taskpolicy -c utility nice -n 10); else wrap=(nice -n 10); fi ;;
  *)          wrap=() ;;
esac
trap 'kill -TERM "$child" 2>/dev/null; wait "$child"; exit 0' INT TERM
fast=0
while :; do
  started=$(date +%s)
  echo "$(date -u +%FT%TZ) starting (${STREAM_PRIORITY:-background} priority) $url" | tee -a "$state/restarts.log"
  "${wrap[@]}" node "$here/stream.mjs" --url "$url" --state "$state" "$@" >>"$state/stream.log" 2>&1 &
  child=$!
  wait "$child"; code=$?
  echo "$(date -u +%FT%TZ) stopped with code $code after $(( $(date +%s) - started )) s" | tee -a "$state/restarts.log"
  [ "$code" -eq 0 ] && exit 0                     # asked to stop, or a --duration run finished
  if [ "$code" -eq 8 ]; then sleep 600; continue; fi  # memory was short: give the Mini ten minutes
  # quick crashes back off up to five minutes; a stream that ran a while restarts at once
  if [ $(( $(date +%s) - started )) -lt 120 ]; then fast=$(( fast + 1 )); else fast=0; fi
  wait_s=$(( fast == 0 ? 5 : (fast > 6 ? 300 : 5 * 2 ** fast) ))
  sleep "$wait_s"
done
