#!/usr/bin/env bash
# Deploys the public site (WP8): the page and its replay data to Cloudflare Pages, the frames Worker in front of R2,
# the switch of the Worker's MANIFEST_KEY to a finished publish, and the rollback. See web/deploy/README.md.
#
#   web/deploy/deploy.sh --local      COMMAND ...   wrangler dev and a local mirror; touches nothing on Cloudflare
#   web/deploy/deploy.sh --env staging COMMAND ...  staging.<domain>, locked behind Cloudflare Access
#   web/deploy/deploy.sh --env production --sams-go COMMAND ...   only after Sam's go (G4)
#
# Commands:
#   preflight                      tools, credentials file, token, bucket private, staging lock
#   build --data DIR [--out DIR]   the public site from a clean worktree at HEAD, measured against Pages' limits
#   pages --site DIR               upload a built site to Pages (local: serve it with wrangler pages dev)
#   switch --manifest KEY          deploy the Worker with MANIFEST_KEY=KEY, after checking the manifest is published
#   rollback [--pages]             back to the switch before the last (the Worker version, and with --pages the site)
#   status                         the switch history and what answers now
#   all --data DIR --manifest KEY  preflight, build, pages, switch
#   stop                           local only: stop the local servers
#   --mirror DIR                   local only: load this mirror into the local R2 first (WP3's publish.py --to-dir)
#
# Credentials come only from ~/.cassini-cloudflare.env (cloudflare.env.example), mode 600, never printed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="${PYTHON:-python3}"
CF() { "$PY" "$HERE/cf.py" "$@"; }
set -a; . "$HERE/site.env"; set +a

ENV="" SAMS_GO=0 MIRROR="" CMD=""
DATA="" OUT="" SITE="" MANIFEST="" WITH_PAGES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --local) ENV=local ;;
    --env) ENV="$2"; shift ;;
    --sams-go) SAMS_GO=1 ;;
    --mirror) MIRROR="$2"; shift ;;
    --data) DATA="$2"; shift ;;
    --out) OUT="$2"; shift ;;
    --site) SITE="$2"; shift ;;
    --manifest) MANIFEST="$2"; shift ;;
    --pages) WITH_PAGES=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) [ -z "$CMD" ] && CMD="$1" || { echo "one command at a time ($CMD, $1)" >&2; exit 2; } ;;
  esac
  shift
done
case "$ENV" in local|staging|production) ;; *) echo "say --local or --env staging|production" >&2; exit 2 ;; esac
[ -n "$CMD" ] || { echo "no command (deploy.sh --help)" >&2; exit 2; }
if [ "$ENV" = production ] && [ "$SAMS_GO" != 1 ]; then
  echo "production makes the site public: only on Sam's own go (G4), then add --sams-go" >&2; exit 2
fi

STATE="${CASSINI_DEPLOY_STATE:-$HOME/.cache/cassini-deploy}/$ENV"
mkdir -p "$STATE"
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$STATE/deploy.log"; }

# ---------- wrangler, pinned, in a tools folder outside the repo ----------
TOOLS="${CASSINI_DEPLOY_TOOLS:-$HOME/.cache/cassini-deploy/wrangler-$WRANGLER_VERSION}"
WR="$TOOLS/node_modules/.bin/wrangler"
if [ ! -x "$WR" ]; then
  log "installing wrangler $WRANGLER_VERSION into $TOOLS"
  mkdir -p "$TOOLS" && (cd "$TOOLS" && npm init -y >/dev/null && npm install --silent "wrangler@$WRANGLER_VERSION" >/dev/null)
fi
export WRANGLER_MODULE="$TOOLS/node_modules/wrangler/wrangler-dist/cli.js"
export WRANGLER_SEND_METRICS=false

# ---------- the Worker's code ----------
WORKER_MAIN="${WORKER_MAIN:-$ROOT/web/worker/src/index.mjs}"
if [ ! -f "$WORKER_MAIN" ]; then
  if [ "$ENV" = local ]; then
    WORKER_MAIN="$HERE/stub/worker.mjs"
    log "note: no web/worker/ yet (WP4); the local dry run uses the stand-in $WORKER_MAIN"
  elif [ "$CMD" = switch ] || [ "$CMD" = all ]; then
    echo "no Worker at $WORKER_MAIN (WP4): nothing to deploy" >&2; exit 2
  fi
fi
case "$WORKER_MAIN" in */deploy/stub/*) [ "$ENV" = local ] || { echo "the stand-in Worker is for --local only" >&2; exit 2; } ;; esac

# ---------- credentials (staging and production) ----------
CREDS="${CASSINI_CLOUDFLARE_ENV:-$HOME/.cassini-cloudflare.env}"
load_creds() {
  [ -f "$CREDS" ] || { echo "no $CREDS: fill web/deploy/cloudflare.env.example and chmod 600 it" >&2; exit 2; }
  "$PY" -c 'import os,sys; sys.exit(1 if os.stat(sys.argv[1]).st_mode & 0o077 else 0)' "$CREDS" \
    || { echo "$CREDS can be read by other users: chmod 600 it first" >&2; exit 2; }
  set -a; . "$CREDS"; set +a
  for v in CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID; do
    [ -n "${!v:-}" ] || { echo "$v is empty in $CREDS" >&2; exit 2; }
  done
}
[ "$ENV" = local ] || load_creds

HOST=""; PROJECT=""
case "$ENV" in
  staging) HOST="$STAGING_HOST"; PROJECT="$PAGES_PROJECT_STAGING" ;;
  production) HOST="$PRODUCTION_HOST"; PROJECT="$PAGES_PROJECT_PRODUCTION" ;;
esac
COMMIT="$(git -C "$ROOT" rev-parse HEAD)"

# ---------- the switch history: R2 deploy/<env>/history.json (local: a file) ----------
HIST="$STATE/history.json"
hist_pull() { [ "$ENV" = local ] && return 0
  "$WR" r2 object get "$R2_BUCKET_NAME/deploy/$ENV/history.json" --remote --file "$HIST" >/dev/null 2>&1 || : ; }
hist_push() { [ "$ENV" = local ] && return 0
  "$WR" r2 object put "$R2_BUCKET_NAME/deploy/$ENV/history.json" --remote --file "$HIST" --content-type application/json >/dev/null; }

# ---------- local servers ----------
local_stop() {
  for p in worker pages; do
    if [ -f "$STATE/$p.pid" ]; then kill "$(cat "$STATE/$p.pid")" 2>/dev/null || :; rm -f "$STATE/$p.pid"; fi
  done
}
wait_http() {  # url, seconds
  for _ in $(seq 1 "$2"); do curl -fsS -o /dev/null "$1" 2>/dev/null && return 0; sleep 1; done
  echo "nothing answers at $1 (see $STATE/*.out)" >&2; return 1
}
local_worker() {  # manifest key
  local cfg="$STATE/config"
  CF render --env local --manifest "$1" --main "$WORKER_MAIN" --out "$cfg" >/dev/null
  if [ -n "$MIRROR" ]; then node "$HERE/local_r2.mjs" --config "$cfg/wrangler.toml" --persist "$STATE/r2/v3" --mirror "$MIRROR" 2>>"$STATE/worker.out" | tee -a "$STATE/deploy.log"; MIRROR=""; fi
  [ -f "$STATE/worker.pid" ] && { kill "$(cat "$STATE/worker.pid")" 2>/dev/null || :; sleep 1; }
  (cd "$cfg" || exit 1; exec "$WR" dev --config "$cfg/wrangler.toml" --local --ip 127.0.0.1 --port "$LOCAL_WORKER_PORT" \
     --persist-to "$STATE/r2" --show-interactive-dev-session=false </dev/null >"$STATE/worker.out" 2>&1) &
  echo $! >"$STATE/worker.pid"
  wait_http "http://127.0.0.1:$LOCAL_WORKER_PORT/health" 90
}

# ---------- commands ----------
preflight() {
  command -v node >/dev/null || { echo "node is needed" >&2; exit 2; }
  "$WR" --version >/dev/null
  CF manifest-check "$ROOT/web/public/manifest.schema.json" >/dev/null 2>&1 || :   # schema readable
  if [ "$ENV" = local ]; then log "preflight local: wrangler $("$WR" --version | tail -1), worker $WORKER_MAIN"; return; fi
  log "preflight $ENV: token"
  "$WR" whoami 2>&1 | grep -qi "account" || { echo "the token is not accepted (wrangler whoami)" >&2; exit 2; }
  log "preflight $ENV: bucket $R2_BUCKET_NAME is private"
  "$WR" r2 bucket info "$R2_BUCKET_NAME" >/dev/null || { echo "no bucket $R2_BUCKET_NAME" >&2; exit 2; }
  if "$WR" r2 bucket dev-url get "$R2_BUCKET_NAME" 2>&1 | grep -qiE "is enabled|https://pub-"; then
    echo "the bucket's r2.dev URL is ON: turn it off before deploying" >&2; exit 2; fi
  if "$WR" r2 bucket domain list "$R2_BUCKET_NAME" 2>&1 | grep -qiE "domain:|enabled: *(yes|true)"; then
    echo "the bucket has a custom domain: the bucket must stay private" >&2; exit 2; fi
  if [ "$ENV" = staging ]; then
    log "preflight staging: Access app"
    CF access --env staging >/dev/null
  fi
  log "preflight $ENV: ok"
}

build() {
  [ -n "$DATA" ] || DATA="$ROOT/web/replay/data"
  [ -n "$OUT" ] || OUT="$STATE/site-$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT:0:7}"
  log "build $ENV from $COMMIT, data $DATA -> $OUT"
  CF build --data "$DATA" --out "$OUT" --env "$ENV" | tee "$OUT.build.txt"
  CF measure "$OUT" --json "$OUT.measure.json" >/dev/null || { echo "the site does not fit Pages' limits ($OUT.measure.json)" >&2; exit 1; }
  SITE="$OUT"
  echo "$OUT" >"$STATE/last-site"
}

pages() {
  [ -n "$SITE" ] || SITE="$(cat "$STATE/last-site" 2>/dev/null || :)"
  [ -f "$SITE/.build.json" ] || { echo "--site must be a folder deploy.sh build made" >&2; exit 2; }
  "$PY" -c 'import json,sys; b=json.load(open(sys.argv[1])); sys.exit(0 if b["env"]==sys.argv[2] else 1)' "$SITE/.build.json" "$ENV" \
    || { echo "$SITE was built for another environment" >&2; exit 2; }
  if [ "$ENV" = local ]; then
    [ -f "$STATE/pages.pid" ] && { kill "$(cat "$STATE/pages.pid")" 2>/dev/null || :; sleep 1; }
    "$WR" pages dev "$SITE" --ip 127.0.0.1 --port "$LOCAL_PAGES_PORT" </dev/null >"$STATE/pages.out" 2>&1 &
    echo $! >"$STATE/pages.pid"
    wait_http "http://127.0.0.1:$LOCAL_PAGES_PORT/robots.txt" 60
    log "pages local: http://127.0.0.1:$LOCAL_PAGES_PORT/?frames=http://127.0.0.1:$LOCAL_WORKER_PORT"
    return
  fi
  if ! "$WR" pages project list 2>/dev/null | grep -q " $PROJECT "; then
    log "pages: making project $PROJECT"
    "$WR" pages project create "$PROJECT" --production-branch main
  fi
  # the lock goes on before anything is uploaded, and before the host has a DNS record
  [ "$ENV" = staging ] && CF access --env staging --apply
  log "pages $ENV: uploading $SITE"
  "$WR" pages deploy "$SITE" --project-name "$PROJECT" --branch main --commit-hash "$COMMIT" \
    --commit-message "deploy.sh $ENV $(date -u +%FT%TZ)" | tee -a "$STATE/deploy.log"
  CF pages-domain --env "$ENV" --apply
  [ "$ENV" = staging ] && CF check-lock "https://$HOST/" "https://$HOST/data/mission.json" "https://$PROJECT.pages.dev/"
  "$PY" -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])' <<<"$(CF pages-deployments --env "$ENV")" >"$STATE/last-pages"
}

switch() {
  [ -n "$MANIFEST" ] || { echo "--manifest manifest/<publish_id>.json is needed" >&2; exit 2; }
  local m="$STATE/manifest-check.json"
  if [ "$ENV" = local ]; then
    if [ -n "$MIRROR" ]; then cp "$MIRROR/$MANIFEST" "$m"; fi
  else
    "$WR" r2 object get "$R2_BUCKET_NAME/$MANIFEST" --remote --file "$m" >/dev/null \
      || { echo "$MANIFEST is not in the bucket: a publish uploads it last, so it is not finished" >&2; exit 2; }
  fi
  [ -f "$m" ] && CF manifest-check "$m"
  hist_pull
  if [ "$ENV" = local ]; then
    local_worker "$MANIFEST"
    local got; got="$(curl -fsS -D - -o /dev/null "http://127.0.0.1:$LOCAL_WORKER_PORT/version.json" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-manifest"{print $2}')"
    log "switch local: MANIFEST_KEY=$MANIFEST, the Worker answers publish ${got:-?}"
    CF history "$HIST" add "when=$(date -u +%FT%TZ)" "env=local" "manifest=$MANIFEST" "worker_version=local" "commit=$COMMIT" >/dev/null
    return
  fi
  local cfg="$STATE/config"
  CF render --env "$ENV" --manifest "$MANIFEST" --main "$WORKER_MAIN" --out "$cfg" >/dev/null
  log "switch $ENV: deploying the Worker with MANIFEST_KEY=$MANIFEST"
  local out; out="$("$WR" deploy --config "$cfg/wrangler.toml" --env "$ENV" --message "MANIFEST_KEY=$MANIFEST" 2>&1 | tee -a "$STATE/deploy.log")"
  local ver; ver="$(grep -oiE 'Version ID: *[0-9a-f-]{36}' <<<"$out" | grep -oE '[0-9a-f-]{36}' | tail -1)"
  [ -n "$ver" ] || { echo "no Worker version in wrangler's answer" >&2; exit 1; }
  [ "$ENV" = staging ] && CF check-lock "https://$HOST/health" "https://$HOST/version.json"
  CF history "$HIST" add "when=$(date -u +%FT%TZ)" "env=$ENV" "manifest=$MANIFEST" "worker_version=$ver" \
    "pages_deployment=$(cat "$STATE/last-pages" 2>/dev/null || :)" "commit=$COMMIT" >/dev/null
  hist_push
  log "switch $ENV: Worker version $ver answers $MANIFEST"
}

rollback() {
  hist_pull
  local prev; prev="$(CF history "$HIST" previous)"
  [ "$prev" != "{}" ] || { echo "nothing to roll back to (history $HIST)" >&2; exit 2; }
  local pm pv pp
  pm="$("$PY" -c 'import json,sys; print(json.loads(sys.argv[1]).get("manifest",""))' "$prev")"
  pv="$("$PY" -c 'import json,sys; print(json.loads(sys.argv[1]).get("worker_version",""))' "$prev")"
  pp="$("$PY" -c 'import json,sys; print(json.loads(sys.argv[1]).get("pages_deployment",""))' "$prev")"
  if [ "$ENV" = local ]; then
    local_worker "$pm"
    log "rollback local: MANIFEST_KEY back to $pm"
  else
    log "rollback $ENV: Worker back to version $pv ($pm)"
    "$WR" rollback "$pv" --name "$WORKER_NAME-$ENV" --message "deploy.sh rollback to $pm" --yes | tee -a "$STATE/deploy.log"
    if [ "$WITH_PAGES" = 1 ] && [ -n "$pp" ]; then CF pages-rollback --env "$ENV" --to "$pp" --apply; fi
    [ "$ENV" = staging ] && CF check-lock "https://$HOST/" "https://$HOST/health"
  fi
  CF history "$HIST" add "when=$(date -u +%FT%TZ)" "env=$ENV" "manifest=$pm" "worker_version=$pv" "pages_deployment=$pp" \
    "commit=$COMMIT" "rollback=1" >/dev/null
  hist_push
}

status() {
  hist_pull
  echo "history ($HIST):"; "$PY" -c 'import json,sys
for e in (json.load(open(sys.argv[1])) if __import__("os").path.exists(sys.argv[1]) else []): print(" ", e.get("when"), e.get("manifest"), e.get("worker_version"), "rollback" if e.get("rollback") else "")' "$HIST"
  if [ "$ENV" = local ]; then
    curl -fsS -D - -o /dev/null "http://127.0.0.1:$LOCAL_WORKER_PORT/version.json" 2>/dev/null | grep -i x-manifest || echo "  local Worker not running"
  else
    "$WR" deployments list --name "$WORKER_NAME-$ENV" 2>/dev/null | tail -12
  fi
}

case "$CMD" in
  preflight) preflight ;;
  build) build ;;
  pages) pages ;;
  switch) switch ;;
  rollback) rollback ;;
  status) status ;;
  all) preflight; build; pages; switch ;;
  stop) [ "$ENV" = local ] && local_stop ;;
  *) echo "unknown command $CMD" >&2; exit 2 ;;
esac
