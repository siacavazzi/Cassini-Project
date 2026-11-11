#!/usr/bin/env bash
# WP8's local dry run (brief: "deploys, switches and rolls back against the mirror and wrangler dev"). Builds the
# site, serves it with wrangler pages dev, loads a mirror into the local R2, switches the Worker to publish A, then
# B, rolls back, and records what /version.json, /health and a picture answer after each step. Nothing on Cloudflare.
#
#   web/deploy/dry_run.sh --data REPLAY_DATA [--mirror DIR --a KEY --b KEY] [--out LOG]
# With no --mirror it makes the test mirror (make_test_mirror.py) and uses its two publishes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/site.env"
DATA="" MIRROR="" A="" B="" OUT=""
while [ $# -gt 0 ]; do case "$1" in
  --data) DATA="$2"; shift ;; --mirror) MIRROR="$2"; shift ;; --a) A="$2"; shift ;; --b) B="$2"; shift ;;
  --out) OUT="$2"; shift ;; *) echo "unknown $1" >&2; exit 2 ;; esac; shift; done
[ -n "$DATA" ] || { echo "--data is needed (built replay data)" >&2; exit 2; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cassini-dry-run.XXXXXX")"
export CASSINI_DEPLOY_STATE="$WORK/state"
OUT="${OUT:-$WORK/dry-run.log}"
if [ -z "$MIRROR" ]; then
  MIRROR="$WORK/mirror"
  { read -r A; read -r B; } < <(python3 "$HERE/make_test_mirror.py" "$MIRROR")
fi
D="$HERE/deploy.sh --local"
W="http://127.0.0.1:$LOCAL_WORKER_PORT"
pic="/frames/N1500060789_2.webp"
probe() {  # step name
  local v h p
  v="$(curl -fsS "$W/version.json")"
  h="$(curl -fsS -D - -o /dev/null "$W/health" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-manifest"{print $2}')"
  p="$(curl -sS -o /dev/null -w '%{http_code} %{size_download}B' -D - "$W$pic" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-key"{k=$2} END{print k}')"
  printf '%-22s health->%s  version.json %s  %s key %s  refused /flags/: %s\n' "$1" "$h" "$v" "$pic" "$p" \
    "$(curl -s -o /dev/null -w '%{http_code}' "$W/flags/")" | tee -a "$OUT"
}
trap '$D stop >/dev/null 2>&1 || :' EXIT
echo "dry run $(date -u +%FT%TZ) at $(git -C "$HERE" rev-parse --short HEAD); mirror $MIRROR" | tee "$OUT"
$D build --data "$DATA" --out "$WORK/site" | tail -3 | tee -a "$OUT"
$D pages --site "$WORK/site" | tee -a "$OUT"
curl -fsS -o /dev/null -w "pages: index.html %{http_code} %{size_download}B\n" "http://127.0.0.1:$LOCAL_PAGES_PORT/" | tee -a "$OUT"
$D switch --mirror "$MIRROR" --manifest "$A" | tail -1 | tee -a "$OUT"; probe "deploy A"
$D switch --manifest "$B" | tail -1 | tee -a "$OUT"; probe "switch to B"
$D rollback | tail -1 | tee -a "$OUT"; probe "rollback"
$D status | tee -a "$OUT"
echo "log: $OUT"
