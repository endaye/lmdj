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
printf 'docker %s\n' "$*" >> "$DEPLOY_TEST_LOG"
if [ "${DEPLOY_TEST_DOCKER_FAIL_EXEC:-0}" = "1" ] && [[ "$*" == *" exec -T app "* ]]; then
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
exit 0
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
  printf 'services: {app: {image: test}, caddy: {image: test}}\n' > "$root/compose.yml"
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

"$ACTIVATE_SCRIPT" "$TMP/one.tar.gz" "$DEPLOY_PATH"
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA1"
grep -q 'lmdj-smoke' "$DEPLOY_TEST_LOG"
grep -q -- '-p lmdj ' "$DEPLOY_TEST_LOG"
if grep '^curl ' "$DEPLOY_TEST_LOG" | grep -vq -- '--retry-all-errors'; then
  echo "health checks must retry transient curl errors" >&2
  exit 1
fi

: > "$DEPLOY_TEST_LOG"
export DEPLOY_TEST_DOCKER_EXEC_COUNT_FILE="$TMP/docker-exec-count"
rm -f "$DEPLOY_TEST_DOCKER_EXEC_COUNT_FILE"
DEPLOY_TEST_DOCKER_FAIL_EXEC_COUNT=1 \
  "$ACTIVATE_SCRIPT" "$TMP/two.tar.gz" "$DEPLOY_PATH"
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA2"
test "$(grep -c 'docker .* exec -T app ' "$DEPLOY_TEST_LOG")" -ge 2

: > "$DEPLOY_TEST_LOG"
if DEPLOY_TEST_DOCKER_FAIL_EXEC=1 "$ACTIVATE_SCRIPT" "$TMP/one.tar.gz" "$DEPLOY_PATH"; then
  echo "failed health check unexpectedly succeeded" >&2
  exit 1
fi
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA2"

echo "activate-release tests passed"
