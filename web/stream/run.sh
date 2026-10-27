#!/bin/bash
# Keeps the stream running: starts stream.mjs at low priority and starts it again whenever it stops on its own.
#   web/stream/run.sh --out /path/hls/index.m3u8 [more stream.mjs options]
# Run it in tmux (tmux new -d -s stream 'web/stream/run.sh ...'); Ctrl-C or `tmux kill-session -t stream` ends it.
#
# STREAM_PRIORITY  normal (default): no clamp. The rig needs about half a core at 720p, and macOS slows the page's
#                  own animation at any lower QoS (measured on the Mini 2026-10-27: 60 fps at normal, 14-22 at utility);
#                  utility: utility QoS and nice 10; background: taskpolicy -b and nice 20 (3 to 8 fps under a pre-build).
# STREAM_STATE     where logs, stats.jsonl and Chrome's profile live (default ~/server/stream).
# STREAM_URL       the page (default the live site in ambient mode, live clock).
set -u
here=$(cd "$(dirname "$0")" && pwd)
state=${STREAM_STATE:-$HOME/server/stream}
url=${STREAM_URL:-http://127.0.0.1:8765/?ambient=live}
mkdir -p "$state"
case "${STREAM_PRIORITY:-normal}" in
  background) if command -v taskpolicy >/dev/null; then wrap=(taskpolicy -b nice -n 20); else wrap=(nice -n 19); fi ;;
  utility)    if command -v taskpolicy >/dev/null; then wrap=(taskpolicy -c utility nice -n 10); else wrap=(nice -n 10); fi ;;
  *)          wrap=() ;;
esac
trap 'kill -TERM "$child" 2>/dev/null; wait "$child"; exit 0' INT TERM HUP
fast=0
while :; do
  started=$(date +%s)
  echo "$(date -u +%FT%TZ) starting (${STREAM_PRIORITY:-normal} priority) $url" | tee -a "$state/restarts.log"
  ${wrap[@]+"${wrap[@]}"} node "$here/stream.mjs" --url "$url" --state "$state" "$@" >>"$state/stream.log" 2>&1 &
  child=$!
  wait "$child"; code=$?
  echo "$(date -u +%FT%TZ) stopped with code $code after $(( $(date +%s) - started )) s" | tee -a "$state/restarts.log"
  [ "$code" -eq 0 ] && exit 0                     # asked to stop, or a --duration run finished
  # memory short (8) or far behind real time for ten minutes (7): give the Mini ten minutes
  if [ "$code" -eq 8 ] || [ "$code" -eq 7 ]; then sleep 600; continue; fi
  # quick crashes back off up to five minutes; a stream that ran a while restarts at once
  if [ $(( $(date +%s) - started )) -lt 120 ]; then fast=$(( fast + 1 )); else fast=0; fi
  # ten quick failures in a row is a setup problem, not a hiccup: stop rather than loop forever
  if [ "$fast" -ge 10 ]; then echo "$(date -u +%FT%TZ) giving up after 10 quick failures; see $state/stream.log" | tee -a "$state/restarts.log"; exit 1; fi
  wait_s=$(( fast == 0 ? 5 : (fast > 6 ? 300 : 5 * 2 ** fast) ))
  sleep "$wait_s"
done
