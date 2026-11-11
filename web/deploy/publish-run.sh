#!/usr/bin/env bash
# The publish run after the full cache build (WP8 brief; WP10 runs it for real): WP2's tables and fullview phases and
# WP3's publisher, year by year, split across the Macs, then one run over the whole range that writes the manifest. It prints the
# manifest key for `deploy.sh --env staging switch --manifest KEY`; it never switches the Worker itself.
#
#   web/deploy/publish-run.sh --cache DIR --years 1997-2017 [--hosts "local mini"] [--to-dir MIRROR] [--dry-run]
#
# --hosts   where each year runs, round robin: "local" is this Mac, any other name is an ssh host with the repo at
#           $CASSINI_REPO_<host> (default ~/dev/Cassini-Project) and the cache at $CASSINI_CACHE_<host> (default --cache)
# --to-dir  publish to a local mirror instead of R2 (WP3's publish.py --to-dir); the default is R2, with the key pair
#           from ~/.cassini-cloudflare.env
# --state   the publisher's ledger folder (publish.py --state), the same for every run on a host; default the
#           publisher's own (~/.cassini-publish/BUCKET for R2). The final run skips, with no R2 request, every object
#           in this Mac's ledger; years another host published are checked against R2 (md5 and ETag) instead, so a
#           single host (the one with the cache) is the fastest split
# --dry-run print the commands only
# Each host's processes come from its free cores (CASSINI_WORKERS, else the cores not busy now), per the project's
# compute rule; BLAS threads are pinned to 1 because the parallelism is many processes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CACHE="" YEARS="" HOSTS="local" TODIR="" DRY=0 STATE=""
while [ $# -gt 0 ]; do case "$1" in
  --cache) CACHE="$2"; shift ;; --years) YEARS="$2"; shift ;; --hosts) HOSTS="$2"; shift ;;
  --to-dir) TODIR="$2"; shift ;; --state) STATE="$2"; shift ;; --dry-run) DRY=1 ;; *) echo "unknown $1" >&2; exit 2 ;; esac; shift; done
[ -n "$CACHE" ] && [ -n "$YEARS" ] || { echo "--cache and --years are needed" >&2; exit 2; }

# the pieces this run drives must exist at this commit (WP2, WP3)
need() { grep -q -- "$2" "$ROOT/$1" 2>/dev/null || { echo "$1 has no $2 yet ($3): nothing to run" >&2; [ "$DRY" = 1 ] || exit 2; }; }
need web/frames/prebuild.py '"tables"' WP2
need web/frames/prebuild.py '"fullview"' WP2
need web/frames/publish.py '--years' WP3
need web/frames/publish.py '--no-manifest' WP3

if [ -z "$TODIR" ]; then
  CREDS="${CASSINI_CLOUDFLARE_ENV:-$HOME/.cassini-cloudflare.env}"
  [ "$DRY" = 1 ] || { [ -f "$CREDS" ] || { echo "no $CREDS (R2 key pair)" >&2; exit 2; }; set -a; . "$CREDS"; set +a; }
  DEST="--to-r2"
else
  DEST="--to-dir $TODIR"
fi

[ -n "$STATE" ] && DEST="$DEST --state $STATE"
expand() { case "$1" in *-*) seq "${1%-*}" "${1#*-}" ;; *) tr ',' '\n' <<<"$1" ;; esac; }
read -r -a H <<<"$HOSTS"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOGDIR="${CASSINI_PUBLISH_LOGS:-$HOME/.cache/cassini-deploy/publish-$STAMP}"; mkdir -p "$LOGDIR"

job() {  # host year
  local host="$1" y="$2" repo cache
  local v="CASSINI_REPO_$host" c="CASSINI_CACHE_$host"
  repo="${!v:-~/dev/Cassini-Project}"; cache="${!c:-$CACHE}"
  [ "$host" = local ] && repo="$ROOT" && cache="$CACHE"
  local procs='${CASSINI_WORKERS:-$(python3 -c "import os; l=os.getloadavg()[0]; print(max(1, (os.cpu_count() or 2) - int(l + 0.5)))")}'
  local cmd="cd $repo && export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 && P=$procs && \
python web/frames/prebuild.py tables --cache $cache --years $y --procs \$P && \
python web/frames/prebuild.py fullview --cache $cache --years $y --procs \$P && \
python web/frames/publish.py --cache $cache --years $y --no-manifest --workers \$P $DEST"
  if [ "$DRY" = 1 ]; then echo "[$host] $cmd"; return; fi
  if [ "$host" = local ]; then bash -c "$cmd"; else ssh "$host" "$cmd"; fi >"$LOGDIR/$y-$host.log" 2>&1 \
    && echo "year $y on $host: done" || { echo "year $y on $host: FAILED (see $LOGDIR/$y-$host.log)"; return 1; }
}

i=0; pids=()
for y in $(expand "$YEARS"); do
  host="${H[$((i % ${#H[@]}))]}"; i=$((i + 1))
  # one year per host at a time; each year's job uses all that host's free cores
  if [ "$DRY" = 1 ]; then job "$host" "$y"; continue; fi
  while [ "$(jobs -rp | wc -l)" -ge "${#H[@]}" ]; do wait -n || true; done
  job "$host" "$y" & pids+=($!)
done
fail=0; for p in "${pids[@]:-}"; do [ -n "$p" ] && { wait "$p" || fail=1; }; done
[ "$fail" = 0 ] || { echo "some years failed: no manifest written; rerun them (the publisher skips what is up)" >&2; exit 1; }

# every year is up: one run over the whole range, from this Mac. It skips every object already up (ledger in --state,
# else md5 against the ETag) and is the one run whose published.json covers every year, so its manifest (uploaded last,
# its key alone on the last line) lists the whole range. --manifest-only would build the manifest from the last
# finished run only, which here is a single year.
FINAL="python web/frames/publish.py --cache $CACHE --years $YEARS $DEST"
if [ "$DRY" = 1 ]; then echo "[local] $FINAL"; exit 0; fi
KEY="$(cd "$ROOT" && $FINAL | tail -1)"
case "$KEY" in manifest/*.json) ;; *) echo "the final run wrote no manifest (last line: $KEY)" >&2; exit 1 ;; esac
echo "published; switch with: web/deploy/deploy.sh --env staging switch --manifest $KEY"
