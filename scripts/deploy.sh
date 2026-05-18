#!/usr/bin/env bash
set -euo pipefail

SITE_DIR=${SITE_DIR:-/srv/laumy-site}
CONTENT_DIR=${CONTENT_DIR:-/srv/laumy-notes-content}
WWW_DIR=${WWW_DIR:-/var/www/laumy-static}
SHARED_DIR=${SHARED_DIR:-$WWW_DIR/shared}
POST_ASSETS_DIR=${POST_ASSETS_DIR:-$SHARED_DIR/assets/posts}
PROTECTED_NGINX_INCLUDE=${PROTECTED_NGINX_INCLUDE:-$SITE_DIR/deploy/generated/protected-routes.conf}
PROTECTED_AUTH_FILE=${PROTECTED_AUTH_FILE:-/etc/nginx/laumy-private.htpasswd}
KEEP_RELEASES=${KEEP_RELEASES:-3}
STAMP=$(date +%Y%m%d-%H%M%S)
RELEASE="$WWW_DIR/releases/$STAMP"

cd "$SITE_DIR"

mkdir -p "$WWW_DIR/releases" "$SHARED_DIR/assets"

if [[ -d "$SITE_DIR/static/assets/posts" ]]; then
  mkdir -p "$(dirname "$POST_ASSETS_DIR")"
  if [[ ! -d "$POST_ASSETS_DIR" ]]; then
    mv "$SITE_DIR/static/assets/posts" "$POST_ASSETS_DIR"
  else
    rsync -a --ignore-existing "$SITE_DIR/static/assets/posts/" "$POST_ASSETS_DIR/"
    rm -rf "$SITE_DIR/static/assets/posts"
  fi
fi

python3 scripts/build_content.py "$CONTENT_DIR" \
  --site "$SITE_DIR" \
  --assets-output "$POST_ASSETS_DIR" \
  --protected-nginx-output "$PROTECTED_NGINX_INCLUDE" \
  --protected-auth-file "$PROTECTED_AUTH_FILE" \
  --protected-assets-root "$SHARED_DIR"
hugo --source "$SITE_DIR" --destination "$RELEASE" --minify
ln -sfn "$RELEASE" "$WWW_DIR/current"

if [[ "${RELOAD_NGINX:-1}" == "1" ]] && [[ "$(id -u)" -eq 0 ]] && command -v nginx >/dev/null 2>&1 && systemctl is-active --quiet nginx; then
  nginx -t
  systemctl reload nginx
fi

mapfile -t releases < <(find "$WWW_DIR/releases" -mindepth 1 -maxdepth 1 -type d | sort -r)
for old_release in "${releases[@]:$KEEP_RELEASES}"; do
  rm -rf "$old_release"
done

echo "Published $RELEASE"
