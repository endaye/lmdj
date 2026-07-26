#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTIVATE_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/activate-release.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_BIN="$TMP/bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/docker" <<'EOF'
#!/usr/bin/env bash
printf 'docker_buildkit=%s\n' "${DOCKER_BUILDKIT:-unset}" >> "$DEPLOY_TEST_LOG"
printf 'lmdj_image_tag=%s\n' "${LMDJ_IMAGE_TAG:-unset}" >> "$DEPLOY_TEST_LOG"
printf 'docker %s\n' "$*" >> "$DEPLOY_TEST_LOG"
if [ "$*" = "image ls --format {{.Repository}}:{{.Tag}}" ]; then
  printf '%s\n' \
    'lmdj-app:1111111111111111111111111111111111111111' \
    'lmdj-app:2222222222222222222222222222222222222222' \
    'lmdj-app:0000000000000000000000000000000000000000' \
    'lmdj-caddy:1111111111111111111111111111111111111111' \
    'lmdj-caddy:2222222222222222222222222222222222222222' \
    'lmdj-caddy:0000000000000000000000000000000000000000'
  exit 0
fi
if [[ "$*" == compose\ -p\ lmdj\ *" ps -q app" ]]; then
  if [ "${DEPLOY_TEST_MISSING_RUNNING_CONTAINER:-0}" != "1" ]; then
    printf 'running-app-container\n'
  fi
  exit 0
fi
if [[ "$*" == compose\ -p\ lmdj\ *" ps -q caddy" ]]; then
  if [ "${DEPLOY_TEST_MISSING_RUNNING_CONTAINER:-0}" != "1" ]; then
    printf 'running-caddy-container\n'
  fi
  exit 0
fi
if [ "$*" = "inspect --format {{.Image}} running-app-container" ]; then
  printf 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n'
  exit 0
fi
if [ "$*" = "inspect --format {{.Image}} running-caddy-container" ]; then
  printf 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n'
  exit 0
fi
if [ "${DEPLOY_TEST_DOCKER_FAIL_EXEC:-0}" = "1" ] \
  && [[ "$*" == compose\ -p\ lmdj\ *" exec -T app "* ]]; then
  exit 1
fi
if [ "${DEPLOY_TEST_DOCKER_FAIL_CADDY_HEALTH:-0}" = "1" ] \
  && [[ "$*" == compose\ -p\ lmdj\ *" exec -T -e LMDJ_HEALTH_DOMAIN="* ]]; then
  exit 1
fi
if [[ "$*" == *" exec -T app "* ]] && [ "${DEPLOY_TEST_DOCKER_FAIL_EXEC_COUNT:-0}" -gt 0 ]; then
  count_file="${DEPLOY_TEST_DOCKER_EXEC_COUNT_FILE:?}"
  count="$(cat "$count_file" 2>/dev/null || printf '0')"
  count=$((count + 1))
  printf '%s\n' "$count" > "$count_file"
  if [ "$count" -le "$DEPLOY_TEST_DOCKER_FAIL_EXEC_COUNT" ]; then
    exit 1
  fi
fi
exit 0
EOF
cat > "$FAKE_BIN/curl" <<'EOF'
#!/usr/bin/env bash
printf 'curl %s\n' "$*" >> "$DEPLOY_TEST_LOG"
exit 127
EOF
chmod +x "$FAKE_BIN/docker" "$FAKE_BIN/curl"
cat > "$FAKE_BIN/sleep" <<'EOF'
#!/usr/bin/env bash
printf 'sleep %s\n' "$*" >> "$DEPLOY_TEST_LOG"
EOF
chmod +x "$FAKE_BIN/sleep"

make_archive() {
  local sha="$1" output="$2" root
  root="$TMP/archive-$sha"
  mkdir -p "$root"
  printf '%s\n' "$sha" > "$root/REVISION"
  printf 'services: {app: {build: .}, caddy: {image: caddy:2}}\n' > "$root/compose.yml"
  printf 'services: {app: {ports: ["127.0.0.1:18000:8000"]}}\n' > "$root/compose.smoke.yml"
  printf 'test\n' > "$root/Caddyfile"
  tar -C "$root" -czf "$output" .
}

DEPLOY_PATH="$TMP/deploy"
mkdir -p "$DEPLOY_PATH/shared"
printf 'LMDJ_DOMAIN=staging.example.com\n' > "$DEPLOY_PATH/shared/.env"
export DEPLOY_TEST_LOG="$TMP/deploy.log"
export PATH="$FAKE_BIN:$PATH"

SHA1="1111111111111111111111111111111111111111"
SHA2="2222222222222222222222222222222222222222"
make_archive "$SHA1" "$TMP/one.tar.gz"
make_archive "$SHA2" "$TMP/two.tar.gz"
make_archive "$SHA1" "$TMP/one-fail.tar.gz"
make_archive "$SHA1" "$TMP/one-caddy-fail.tar.gz"
printf 'prebuilt image bundle\n' > "$TMP/images-one.tar.gz"
printf 'prebuilt image bundle\n' > "$TMP/images-two.tar.gz"
printf 'prebuilt image bundle\n' > "$TMP/images-fail.tar.gz"
printf 'prebuilt image bundle\n' > "$TMP/images-caddy-fail.tar.gz"
mkdir -p "$DEPLOY_PATH/incoming"
printf 'stale\n' > "$DEPLOY_PATH/incoming/stale.tar.gz"

"$ACTIVATE_SCRIPT" "$TMP/one.tar.gz" "$DEPLOY_PATH" "$TMP/images-one.tar.gz"
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA1"
test ! -e "$TMP/one.tar.gz"
test ! -e "$TMP/images-one.tar.gz"
test ! -e "$DEPLOY_PATH/incoming/stale.tar.gz"
grep -q "image: lmdj-app:$SHA1" "$DEPLOY_PATH/releases/$SHA1/compose.images.yml"
grep -q "image: lmdj-caddy:$SHA1" "$DEPLOY_PATH/releases/$SHA1/compose.images.yml"
grep -q 'pull_policy: never' "$DEPLOY_PATH/releases/$SHA1/compose.images.yml"
grep -q 'lmdj-smoke' "$DEPLOY_TEST_LOG"
grep -q -- '-p lmdj ' "$DEPLOY_TEST_LOG"
grep -q 'docker load -i .*images-one.tar.gz' "$DEPLOY_TEST_LOG" || {
  echo "activation must load the prebuilt image bundle" >&2
  exit 1
}
grep -q "docker compose -p lmdj-smoke .*compose.images.yml .*up -d --no-build app" \
  "$DEPLOY_TEST_LOG" || {
  echo "smoke must use the controller-owned immutable image override" >&2
  exit 1
}
grep -q 'docker compose -p lmdj .* up -d --no-build --force-recreate' "$DEPLOY_TEST_LOG" || {
  echo "activation must recreate services without building on the server" >&2
  exit 1
}
if grep '^docker ' "$DEPLOY_TEST_LOG" | grep -Eq -- ' compose .*--build| build '; then
  echo "activation must not build images on the server" >&2
  exit 1
fi
if grep '^lmdj_image_tag=' "$DEPLOY_TEST_LOG" | grep -vq "^lmdj_image_tag=$SHA1$"; then
  echo "activation must select the image tagged for the release SHA" >&2
  exit 1
fi
if grep -q '^curl ' "$DEPLOY_TEST_LOG"; then
  echo "activation must not depend on host curl" >&2
  exit 1
fi
grep -q 'docker compose -p lmdj-smoke .* exec -T app .*127.0.0.1:8000/health' \
  "$DEPLOY_TEST_LOG" || {
  echo "smoke health check must run inside the app container" >&2
  exit 1
}
grep -q 'docker compose -p lmdj .* exec -T -e LMDJ_HEALTH_DOMAIN=staging.example.com app ' \
  "$DEPLOY_TEST_LOG" || {
  echo "Caddy health check must run inside the app container" >&2
  exit 1
}
grep -Fq 'home=urllib.request.Request("https://caddy/", headers={"Host": domain})' \
  "$DEPLOY_TEST_LOG"
grep -Fq 'health=urllib.request.Request("https://caddy/api/health", headers={"Host": domain})' \
  "$DEPLOY_TEST_LOG"

: > "$DEPLOY_TEST_LOG"
export DEPLOY_TEST_DOCKER_EXEC_COUNT_FILE="$TMP/docker-exec-count"
rm -f "$DEPLOY_TEST_DOCKER_EXEC_COUNT_FILE"
DEPLOY_TEST_DOCKER_FAIL_EXEC_COUNT=1 \
  "$ACTIVATE_SCRIPT" "$TMP/two.tar.gz" "$DEPLOY_PATH" "$TMP/images-two.tar.gz"
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA2"
test ! -e "$TMP/two.tar.gz"
test ! -e "$TMP/images-two.tar.gz"
test "$(grep -c 'docker .* exec -T app ' "$DEPLOY_TEST_LOG")" -ge 2
grep -q "docker tag sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa lmdj-app:$SHA1" \
  "$DEPLOY_TEST_LOG"
grep -q "docker tag sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb lmdj-caddy:$SHA1" \
  "$DEPLOY_TEST_LOG"
grep -q 'docker image rm lmdj-app:0000000000000000000000000000000000000000' \
  "$DEPLOY_TEST_LOG"
grep -q 'docker image rm lmdj-caddy:0000000000000000000000000000000000000000' \
  "$DEPLOY_TEST_LOG"

: > "$DEPLOY_TEST_LOG"
if DEPLOY_TEST_DOCKER_FAIL_EXEC=1 \
  "$ACTIVATE_SCRIPT" "$TMP/one-fail.tar.gz" "$DEPLOY_PATH" "$TMP/images-fail.tar.gz"; then
  echo "failed health check unexpectedly succeeded" >&2
  exit 1
fi
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA2"
test ! -e "$TMP/one-fail.tar.gz"
test ! -e "$TMP/images-fail.tar.gz"
grep -q "docker image rm lmdj-app:$SHA1" "$DEPLOY_TEST_LOG"
grep -q "docker image rm lmdj-caddy:$SHA1" "$DEPLOY_TEST_LOG"
grep -q "image: lmdj-app:$SHA2" "$DEPLOY_PATH/releases/$SHA2/compose.images.yml"
grep -q "image: lmdj-caddy:$SHA2" "$DEPLOY_PATH/releases/$SHA2/compose.images.yml"
test "$(grep -c 'docker compose -p lmdj .* up -d --no-build --force-recreate' "$DEPLOY_TEST_LOG")" -ge 2 || {
  echo "rollback must recreate services without building on the server" >&2
  exit 1
}

: > "$DEPLOY_TEST_LOG"
if DEPLOY_TEST_DOCKER_FAIL_CADDY_HEALTH=1 \
  "$ACTIVATE_SCRIPT" "$TMP/one-caddy-fail.tar.gz" "$DEPLOY_PATH" \
  "$TMP/images-caddy-fail.tar.gz"; then
  echo "failed Caddy health check unexpectedly succeeded" >&2
  exit 1
fi
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA2"
test ! -e "$TMP/one-caddy-fail.tar.gz"
test ! -e "$TMP/images-caddy-fail.tar.gz"
grep -q "docker image rm lmdj-app:$SHA1" "$DEPLOY_TEST_LOG"
grep -q "docker image rm lmdj-caddy:$SHA1" "$DEPLOY_TEST_LOG"
test "$(grep -c 'docker compose -p lmdj .* up -d --no-build --force-recreate' "$DEPLOY_TEST_LOG")" -ge 2 || {
  echo "Caddy health failure must recreate the previous release" >&2
  exit 1
}

make_archive "$SHA1" "$TMP/missing-running.tar.gz"
printf 'prebuilt image bundle\n' > "$TMP/images-missing-running.tar.gz"
if DEPLOY_TEST_MISSING_RUNNING_CONTAINER=1 \
  "$ACTIVATE_SCRIPT" "$TMP/missing-running.tar.gz" "$DEPLOY_PATH" \
  "$TMP/images-missing-running.tar.gz"; then
  echo "activation without previous running images unexpectedly succeeded" >&2
  exit 1
fi
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA2"

echo "activate-release tests passed"
