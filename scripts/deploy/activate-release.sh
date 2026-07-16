#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
DEPLOY_PATH="${2:-}"
if [ -z "$ARCHIVE" ] || [ -z "$DEPLOY_PATH" ]; then
  echo "usage: activate-release.sh RELEASE_TAR DEPLOY_PATH" >&2
  exit 2
fi
test -f "$ARCHIVE"
test -f "$DEPLOY_PATH/shared/.env"

SHA="$(tar -xOf "$ARCHIVE" ./REVISION | tr -d '\r\n')"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "archive REVISION is not a full commit SHA" >&2
  exit 1
fi

RELEASES="$DEPLOY_PATH/releases"
RELEASE="$RELEASES/$SHA"
CURRENT="$DEPLOY_PATH/current"
PREVIOUS=""
mkdir -p "$RELEASES" "$RELEASE"
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink "$CURRENT")"; fi

replace_symlink() {
  local source="$1" target="$2"
  if mv --help 2>&1 | grep -q -- '--no-target-directory'; then
    mv -Tf "$source" "$target"
  else
    mv -fh "$source" "$target"
  fi
}

rm -rf "$RELEASE"
mkdir -p "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
test "$(cat "$RELEASE/REVISION")" = "$SHA"
test -f "$RELEASE/compose.yml"
test -f "$RELEASE/compose.smoke.yml"
DOMAIN="$(sed -n 's/^LMDJ_DOMAIN=//p' "$DEPLOY_PATH/shared/.env" | tail -n 1)"
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "LMDJ_DOMAIN must be a hostname without scheme or path" >&2
  exit 1
fi

smoke_down() {
  docker compose -p lmdj-smoke \
    --env-file "$DEPLOY_PATH/shared/.env" \
    -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
    down -v --remove-orphans >/dev/null 2>&1 || true
}
trap smoke_down EXIT
smoke_down
docker compose -p lmdj-smoke \
  --env-file "$DEPLOY_PATH/shared/.env" \
  -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
  up -d --build app
curl --fail --silent --show-error --retry 12 --retry-delay 5 \
  --retry-connrefused --retry-all-errors \
  http://127.0.0.1:18000/health >/dev/null
smoke_down
trap - EXIT

rm -f "$DEPLOY_PATH/current.next"
ln -s "$RELEASE" "$DEPLOY_PATH/current.next"
replace_symlink "$DEPLOY_PATH/current.next" "$CURRENT"

if ! (
  cd "$CURRENT" &&
  docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" up -d --build &&
  docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" exec -T app \
    /opt/app-venv/bin/python -c \
    'import json, urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/health"))["ok"] is True' &&
  curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --retry-all-errors \
    --insecure --resolve "$DOMAIN:443:127.0.0.1" \
    "https://$DOMAIN/" >/dev/null &&
  curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --retry-all-errors \
    --insecure --resolve "$DOMAIN:443:127.0.0.1" \
    "https://$DOMAIN/api/health" >/dev/null
); then
  (
    cd "$CURRENT"
    docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" logs --tail 100
  ) || true
  if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
    rm -f "$DEPLOY_PATH/current.rollback"
    ln -s "$PREVIOUS" "$DEPLOY_PATH/current.rollback"
    replace_symlink "$DEPLOY_PATH/current.rollback" "$CURRENT"
    (
      cd "$CURRENT"
      docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" up -d --build
    )
  else
    (
      cd "$CURRENT"
      docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" down --remove-orphans
    ) || true
    rm -f "$CURRENT"
  fi
  exit 1
fi

printf '%s\n' "$SHA" > "$DEPLOY_PATH/DEPLOYED_REVISION"
echo "deployed $SHA"
