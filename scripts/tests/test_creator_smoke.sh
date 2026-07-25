#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
PORT_FILE="$TMP_DIR/port"
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

python3 "$ROOT/scripts/tests/creator_smoke_server.py" "$PORT_FILE" &
SERVER_PID=$!
for _ in $(seq 1 100); do
  [ -s "$PORT_FILE" ] && break
  sleep 0.02
done
[ -s "$PORT_FILE" ] || { echo "fixture server did not start" >&2; exit 1; }
BASE_URL="http://127.0.0.1:$(cat "$PORT_FILE")"

for name in \
  success contract-fail scene-contract-fail http-fail nondeterministic \
  generating failed cancelled unknown-state hanging
do
  printf 'RIFF fixture WAVE' > "$TMP_DIR/$name.wav"
done

output="$(
  LMDJ_API_BASE_URL="$BASE_URL" \
    "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/success.wav"
)"
grep -Eq '^job_id: job-smoke$' <<<"$output"
grep -Eq '^patch_id: .+$' <<<"$output"
grep -Eq '^pads: 16$' <<<"$output"
grep -Eq '^export_sha256_a: [0-9a-f]{64}$' <<<"$output"
grep -Eq '^export_sha256_b: [0-9a-f]{64}$' <<<"$output"
grep -Eq '^deterministic: yes$' <<<"$output"

generating_output="$(
  LMDJ_API_BASE_URL="$BASE_URL" \
    LMDJ_CREATOR_SMOKE_POLL_INTERVAL_SECONDS=0 \
    "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/generating.wav"
)"
grep -Eq '^job_id: generating$' <<<"$generating_output"
grep -Eq '^deterministic: yes$' <<<"$generating_output"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/contract-fail.wav" \
  >"$TMP_DIR/contract-fail.log" 2>&1
then
  echo "creator-smoke accepted an invalid 15-Pad contract" >&2
  exit 1
fi
grep -q "ValidationError" "$TMP_DIR/contract-fail.log"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/scene-contract-fail.wav" \
  >"$TMP_DIR/scene-contract-fail.log" 2>&1
then
  echo "creator-smoke accepted an invalid Scene Pad coverage" >&2
  exit 1
fi
grep -q "ValidationError" "$TMP_DIR/scene-contract-fail.log"
grep -Fq "On instance['scenes']" "$TMP_DIR/scene-contract-fail.log"
grep -q "pad_indexes" "$TMP_DIR/scene-contract-fail.log"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/failed.wav" \
  >"$TMP_DIR/failed.log" 2>&1
then
  echo "creator-smoke accepted a failed Job" >&2
  exit 1
fi
grep -q "Creator job failed" "$TMP_DIR/failed.log"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/cancelled.wav" \
  >"$TMP_DIR/cancelled.log" 2>&1
then
  echo "creator-smoke accepted a cancelled Job" >&2
  exit 1
fi
grep -q "Creator job cancelled" "$TMP_DIR/cancelled.log"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/unknown-state.wav" \
  >"$TMP_DIR/unknown-state.log" 2>&1
then
  echo "creator-smoke accepted an unknown Job state" >&2
  exit 1
fi
grep -q "Unknown Creator job state: mystery" "$TMP_DIR/unknown-state.log"

hang_started_at="$(date +%s)"
if LMDJ_API_BASE_URL="$BASE_URL" \
  LMDJ_CREATOR_SMOKE_CONNECT_TIMEOUT_SECONDS=1 \
  LMDJ_CREATOR_SMOKE_REQUEST_TIMEOUT_SECONDS=1 \
  LMDJ_CREATOR_SMOKE_TIMEOUT_SECONDS=2 \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/hanging.wav" \
  >"$TMP_DIR/hanging.log" 2>&1
then
  echo "creator-smoke accepted a hanging status response" >&2
  exit 1
fi
hang_elapsed="$(( $(date +%s) - hang_started_at ))"
[ "$hang_elapsed" -lt 4 ] || {
  echo "creator-smoke exceeded its hanging-request timeout" >&2
  exit 1
}
grep -Eq "timed out|curl: \\(28\\)" "$TMP_DIR/hanging.log"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/http-fail.wav" \
  >"$TMP_DIR/http-fail.log" 2>&1
then
  echo "creator-smoke ignored an HTTP 500 response" >&2
  exit 1
fi
grep -q "curl: (22)" "$TMP_DIR/http-fail.log"

if LMDJ_API_BASE_URL="$BASE_URL" \
  "$ROOT/scripts/dev.sh" creator-smoke "$TMP_DIR/nondeterministic.wav" \
  >"$TMP_DIR/nondeterministic.log" 2>&1
then
  echo "creator-smoke accepted non-deterministic exports" >&2
  exit 1
fi
grep -q "not deterministic" "$TMP_DIR/nondeterministic.log"

echo "creator-smoke shell tests: PASS"
