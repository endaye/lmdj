#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
DEPLOY_PATH="${2:-}"
IMAGE_ARCHIVE="${3:-}"
if [ -z "$ARCHIVE" ] || [ -z "$DEPLOY_PATH" ] || [ -z "$IMAGE_ARCHIVE" ]; then
  echo "usage: activate-release.sh RELEASE_TAR DEPLOY_PATH IMAGE_TAR" >&2
  exit 2
fi
test -f "$ARCHIVE"
test -f "$IMAGE_ARCHIVE"
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
PREVIOUS_SHA=""
DEPLOY_SUCCEEDED=0
IMAGE_LOADED=0
SMOKE_ACTIVE=0
mkdir -p "$RELEASES" "$RELEASE"
if [ -L "$CURRENT" ]; then
  PREVIOUS="$(readlink "$CURRENT")"
  PREVIOUS_SHA="$(basename "$PREVIOUS")"
fi

cleanup_on_exit() {
  if [ "$SMOKE_ACTIVE" = "1" ]; then
    smoke_down
  fi
  rm -f "$ARCHIVE" "$IMAGE_ARCHIVE"
  if [ "$DEPLOY_SUCCEEDED" != "1" ] && [ "$IMAGE_LOADED" = "1" ] \
    && [ "$SHA" != "$PREVIOUS_SHA" ]; then
    docker image rm "lmdj-app:$SHA" || true
    docker image rm "lmdj-caddy:$SHA" || true
  fi
}
trap cleanup_on_exit EXIT

replace_symlink() {
  local source="$1" target="$2"
  if mv --help 2>&1 | grep -q -- '--no-target-directory'; then
    mv -Tf "$source" "$target"
  else
    mv -fh "$source" "$target"
  fi
}

write_image_override() {
  local release="$1" sha="$2"
  cat > "$release/compose.images.yml" <<EOF
services:
  app:
    image: lmdj-app:$sha
    pull_policy: never
  caddy:
    image: lmdj-caddy:$sha
    pull_policy: never
EOF
}

preserve_previous_images() {
  local service repository container image
  if [ -z "$PREVIOUS_SHA" ]; then
    return
  fi
  for service in app caddy; do
    case "$service" in
      app) repository="lmdj-app" ;;
      caddy) repository="lmdj-caddy" ;;
    esac
    container="$(
      docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
        -f "$PREVIOUS/compose.yml" ps -q "$service"
    )"
    if [ -z "$container" ]; then
      echo "cannot preserve previous $service image: running container not found" >&2
      return 1
    fi
    image="$(docker inspect --format '{{.Image}}' "$container")"
    if [[ ! "$image" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "cannot preserve previous $service image: invalid image ID" >&2
      return 1
    fi
    docker tag "$image" "$repository:$PREVIOUS_SHA"
  done
}

cleanup_release_images() {
  local reference repository tag
  while IFS= read -r reference; do
    repository="${reference%%:*}"
    tag="${reference#*:}"
    case "$repository" in
      lmdj-app|lmdj-caddy) ;;
      *) continue ;;
    esac
    if [[ ! "$tag" =~ ^[0-9a-f]{40}$ ]]; then
      continue
    fi
    if [ "$tag" = "$SHA" ] || { [ -n "$PREVIOUS_SHA" ] && [ "$tag" = "$PREVIOUS_SHA" ]; }; then
      continue
    fi
    docker image rm "$reference" || true
  done < <(docker image ls --format '{{.Repository}}:{{.Tag}}')
  docker image prune -f >/dev/null
}

wait_for_app_health() {
  local attempt
  for attempt in {1..12}; do
    if docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
      -f "$CURRENT/compose.yml" -f "$CURRENT/compose.images.yml" \
      exec -T app \
      /opt/app-venv/bin/python -c \
      'import json, urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/health"))["ok"] is True'; then
      return 0
    fi
    if [ "$attempt" -eq 12 ]; then
      return 1
    fi
    sleep 5
  done
}

wait_for_smoke_health() {
  local attempt
  for attempt in {1..12}; do
    if docker compose -p lmdj-smoke \
      --env-file "$DEPLOY_PATH/shared/.env" \
      -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
      -f "$RELEASE/compose.images.yml" \
      exec -T app \
      /opt/app-venv/bin/python -c \
      'import json, urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/health"))["ok"] is True'; then
      return 0
    fi
    if [ "$attempt" -eq 12 ]; then
      return 1
    fi
    sleep 5
  done
}

wait_for_caddy_health() {
  local attempt
  for attempt in {1..12}; do
    if docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
      -f "$CURRENT/compose.yml" -f "$CURRENT/compose.images.yml" \
      exec -T -e "LMDJ_HEALTH_DOMAIN=$DOMAIN" app \
      /opt/app-venv/bin/python -c \
      'import json, os, socket, ssl, urllib.request; domain=os.environ["LMDJ_HEALTH_DOMAIN"]; resolve=socket.getaddrinfo; socket.getaddrinfo=lambda host, port, *args, **kwargs: resolve("caddy" if host == domain else host, port, *args, **kwargs); ctx=ssl._create_unverified_context(); home=urllib.request.Request(f"https://{domain}/"); health=urllib.request.Request(f"https://{domain}/api/health"); assert urllib.request.urlopen(home, context=ctx, timeout=10).status == 200; assert json.load(urllib.request.urlopen(health, context=ctx, timeout=10))["ok"] is True'; then
      return 0
    fi
    if [ "$attempt" -eq 12 ]; then
      return 1
    fi
    sleep 5
  done
}

rm -rf "$RELEASE"
mkdir -p "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
test "$(cat "$RELEASE/REVISION")" = "$SHA"
test -f "$RELEASE/compose.yml"
test -f "$RELEASE/compose.smoke.yml"
write_image_override "$RELEASE" "$SHA"
if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
  write_image_override "$PREVIOUS" "$PREVIOUS_SHA"
fi
DOMAIN="$(sed -n 's/^LMDJ_DOMAIN=//p' "$DEPLOY_PATH/shared/.env" | tail -n 1)"
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "LMDJ_DOMAIN must be a hostname without scheme or path" >&2
  exit 1
fi
export LMDJ_IMAGE_TAG="$SHA"
preserve_previous_images
docker load -i "$IMAGE_ARCHIVE"
IMAGE_LOADED=1

smoke_down() {
  docker compose -p lmdj-smoke \
    --env-file "$DEPLOY_PATH/shared/.env" \
    -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
    -f "$RELEASE/compose.images.yml" \
    down -v --remove-orphans >/dev/null 2>&1 || true
}
SMOKE_ACTIVE=1
smoke_down
docker compose -p lmdj-smoke \
  --env-file "$DEPLOY_PATH/shared/.env" \
  -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
  -f "$RELEASE/compose.images.yml" \
  up -d --no-build app
wait_for_smoke_health
smoke_down
SMOKE_ACTIVE=0

rm -f "$DEPLOY_PATH/current.next"
ln -s "$RELEASE" "$DEPLOY_PATH/current.next"
replace_symlink "$DEPLOY_PATH/current.next" "$CURRENT"

if ! (
  cd "$CURRENT" &&
  docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
    -f "$CURRENT/compose.yml" -f "$CURRENT/compose.images.yml" \
    up -d --no-build --force-recreate &&
  wait_for_app_health &&
  wait_for_caddy_health
); then
  (
    cd "$CURRENT"
    docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
      -f "$CURRENT/compose.yml" -f "$CURRENT/compose.images.yml" \
      logs --tail 100
  ) || true
  if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
    rm -f "$DEPLOY_PATH/current.rollback"
    ln -s "$PREVIOUS" "$DEPLOY_PATH/current.rollback"
    replace_symlink "$DEPLOY_PATH/current.rollback" "$CURRENT"
    (
      cd "$CURRENT"
      LMDJ_IMAGE_TAG="$(basename "$PREVIOUS")" \
        docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
        -f "$CURRENT/compose.yml" -f "$CURRENT/compose.images.yml" \
        up -d --no-build --force-recreate
    )
  else
    (
      cd "$CURRENT"
      docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" \
        -f "$CURRENT/compose.yml" -f "$CURRENT/compose.images.yml" \
        down --remove-orphans
    ) || true
    rm -f "$CURRENT"
  fi
  exit 1
fi

DEPLOY_SUCCEEDED=1
printf '%s\n' "$SHA" > "$DEPLOY_PATH/DEPLOYED_REVISION"
find "$DEPLOY_PATH/incoming" -maxdepth 1 -type f -name '*.tar.gz' -delete
cleanup_release_images
echo "deployed $SHA"
