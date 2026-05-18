#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=${ENV_FILE:-/etc/laumy-deploy.env}
LOCK_FILE=${LOCK_FILE:-/run/laumy-deploy.lock}
LOG_DIR=${LOG_DIR:-/var/log/laumy-deploy}

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

SITE_DIR=${SITE_DIR:-/srv/laumy-site}
CONTENT_DIR=${CONTENT_DIR:-/srv/laumy-notes-content}
SITE_BRANCH=${SITE_BRANCH:-main}
CONTENT_BRANCH=${CONTENT_BRANCH:-main}
DEPLOY_CMD=${DEPLOY_CMD:-"$SITE_DIR/scripts/deploy.sh"}
FORCE=${FORCE:-0}

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || {
  echo "Another deploy is running, exit."
  exit 0
}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

require_git_repo() {
  local dir=$1
  local name=$2

  if [[ ! -d "$dir/.git" ]]; then
    log "$name is not a git repository: $dir"
    log "Run the one-time clone step first."
    exit 2
  fi
}

update_repo() {
  local dir=$1
  local branch=$2
  local name=$3
  local before
  local after

  require_git_repo "$dir" "$name"

  before=$(git -C "$dir" rev-parse HEAD)
  git -C "$dir" fetch --prune origin "$branch"
  after=$(git -C "$dir" rev-parse "origin/$branch")

  if [[ "$before" != "$after" ]]; then
    log "$name changed: $before -> $after"
    git -C "$dir" reset --hard "origin/$branch"
    return 0
  fi

  log "$name unchanged: $before"
  return 1
}

main() {
  local changed=0

  update_repo "$CONTENT_DIR" "$CONTENT_BRANCH" "content" && changed=1 || true

  if [[ -d "$SITE_DIR/.git" ]]; then
    update_repo "$SITE_DIR" "$SITE_BRANCH" "site" && changed=1 || true
  else
    log "site is not managed by git, skip site pull: $SITE_DIR"
  fi

  if [[ "$changed" == 1 || "$FORCE" == 1 ]]; then
    log "start deploy"
    SITE_DIR="$SITE_DIR" CONTENT_DIR="$CONTENT_DIR" "$DEPLOY_CMD"
    log "deploy done"
  else
    log "no changes, skip deploy"
  fi
}

main "$@" 2>&1 | tee -a "$LOG_DIR/deploy.log"
