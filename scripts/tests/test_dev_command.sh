#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_ROOT="$(mktemp -d)"
STATE_DIR="$FIXTURE_ROOT/state"
FAKE_BIN="$FIXTURE_ROOT/fake-bin"
DEV_PID=""

fail() {
  echo "test_dev_command: $*" >&2
  exit 1
}

process_is_alive() {
  kill -0 "$1" 2>/dev/null
}

wait_for_log() {
  local pattern="$1" log_file="$2"
  local attempt
  for attempt in $(seq 1 200); do
    grep -Fq "$pattern" "$log_file" 2>/dev/null && return 0
    [ -z "$DEV_PID" ] || process_is_alive "$DEV_PID" || break
    sleep 0.02
  done
  echo "missing log pattern: $pattern" >&2
  sed -n '1,200p' "$log_file" >&2 2>/dev/null || true
  return 1
}

wait_for_file() {
  local file="$1"
  local attempt
  for attempt in $(seq 1 200); do
    [ -s "$file" ] && return 0
    [ -z "$DEV_PID" ] || process_is_alive "$DEV_PID" || break
    sleep 0.02
  done
  return 1
}

wait_until_dead() {
  local pid="$1"
  local attempt
  for attempt in $(seq 1 200); do
    process_is_alive "$pid" || return 0
    sleep 0.02
  done
  return 1
}

cleanup() {
  local pid_file pid
  if [ -n "$DEV_PID" ] && process_is_alive "$DEV_PID"; then
    kill -TERM "$DEV_PID" 2>/dev/null || true
    wait "$DEV_PID" 2>/dev/null || true
  fi
  for pid_file in "$STATE_DIR/api.pid" "$STATE_DIR/web.pid"; do
    if [ -s "$pid_file" ]; then
      pid="$(cat "$pid_file")"
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$FIXTURE_ROOT"
}
trap cleanup EXIT

mkdir -p "$FIXTURE_ROOT/scripts" "$STATE_DIR" "$FAKE_BIN"
cp "$SOURCE_ROOT/scripts/dev.sh" "$FIXTURE_ROOT/scripts/dev.sh"
chmod +x "$FIXTURE_ROOT/scripts/dev.sh"
DEV_SCRIPT="$FIXTURE_ROOT/scripts/dev.sh"

help_output="$("$DEV_SCRIPT" --help)"
grep -Fq "dev" <<<"$help_output" || fail "help does not list dev"

if "$DEV_SCRIPT" dev >"$STATE_DIR/missing-api.log" 2>&1; then
  fail "dev accepted a missing API venv"
fi
grep -Fq "API 开发环境未就绪" "$STATE_DIR/missing-api.log"
grep -Fq "cd apps/api" "$STATE_DIR/missing-api.log"

mkdir -p "$FIXTURE_ROOT/apps/api/.venv/bin"
cat >"$FIXTURE_ROOT/apps/api/.venv/bin/python" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"numpy, soundfile, librosa, sklearn, pretty_midi"* ]] \
  && [ ! -f "$FAKE_STATE_DIR/material.ready" ]
then
  exit 1
fi
exit 0
EOF
cat >"$FIXTURE_ROOT/apps/api/.venv/bin/uvicorn" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$$" >"$FAKE_STATE_DIR/api.pid"
printf '%s\n' "${LMDJ_PIPELINE:-}" >"$FAKE_STATE_DIR/api.pipeline"
printf '%s\n' "${LMDJ_SEPARATOR_ID:-}" >"$FAKE_STATE_DIR/api.separator"
printf '%s\n' "${LMDJ_SEPARATOR_DEVICE:-}" >"$FAKE_STATE_DIR/api.device"
trap 'exit 7' TERM
trap 'exit 130' INT
trap 'exit 129' HUP
while :; do sleep 0.05; done
EOF
chmod +x \
  "$FIXTURE_ROOT/apps/api/.venv/bin/python" \
  "$FIXTURE_ROOT/apps/api/.venv/bin/uvicorn"

if "$DEV_SCRIPT" dev >"$STATE_DIR/missing-web.log" 2>&1; then
  fail "dev accepted missing Web dependencies"
fi
grep -Fq "Web 开发环境未就绪" "$STATE_DIR/missing-web.log"
grep -Fq "npm install" "$STATE_DIR/missing-web.log"

mkdir -p "$FIXTURE_ROOT/apps/web/node_modules/.bin"
cat >"$FIXTURE_ROOT/apps/web/node_modules/.bin/vite" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$FIXTURE_ROOT/apps/web/node_modules/.bin/vite"

mkdir -p \
  "$FIXTURE_ROOT/workers/audio/config" \
  "$FIXTURE_ROOT/workers/audio/.venv-sep-demucs/bin"
cat >"$FIXTURE_ROOT/workers/audio/config/separators.json" <<'EOF'
{
  "separators": [
    {
      "id": "htdemucs",
      "devices": ["cpu", "mps"],
      "command": ["workers/audio/.venv-sep-demucs/bin/python"]
    }
  ]
}
EOF
cat >"$FIXTURE_ROOT/workers/audio/.venv-sep-demucs/bin/python" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$FIXTURE_ROOT/workers/audio/.venv-sep-demucs/bin/python"

if FAKE_STATE_DIR="$STATE_DIR" \
  "$DEV_SCRIPT" dev >"$STATE_DIR/missing-material.log" 2>&1
then
  fail "dev accepted missing Material DSP dependencies"
fi
grep -Fq "Material 开发环境未就绪" "$STATE_DIR/missing-material.log"
grep -Fq "scripts/dev.sh setup-materials" "$STATE_DIR/missing-material.log"

cat >"$FAKE_BIN/npm" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$$" >"$FAKE_STATE_DIR/web.pid"
trap 'exit 0' TERM
trap 'exit 130' INT
trap 'exit 129' HUP
while :; do sleep 0.05; done
EOF
cat >"$FAKE_BIN/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$FAKE_BIN/npm" "$FAKE_BIN/curl"

start_dev() {
  local log_file="$1"
  rm -f "$STATE_DIR/api.pid" "$STATE_DIR/web.pid"
  PATH="$FAKE_BIN:$PATH" \
    FAKE_STATE_DIR="$STATE_DIR" \
    "$DEV_SCRIPT" dev >"$log_file" 2>&1 &
  DEV_PID=$!
  wait_for_log "==> LMDJ local dev ready" "$log_file"
  wait_for_file "$STATE_DIR/api.pid" \
    || fail "API child PID was not recorded"
  wait_for_file "$STATE_DIR/web.pid" \
    || fail "Web child PID was not recorded"
}

start_legacy_dev() {
  local log_file="$1"
  rm -f "$STATE_DIR/api.pid" "$STATE_DIR/web.pid"
  PATH="$FAKE_BIN:$PATH" \
    FAKE_STATE_DIR="$STATE_DIR" \
    LMDJ_PIPELINE=legacy \
    "$DEV_SCRIPT" dev >"$log_file" 2>&1 &
  DEV_PID=$!
  wait_for_log "==> LMDJ local dev ready" "$log_file"
  wait_for_file "$STATE_DIR/api.pid" \
    || fail "legacy API child PID was not recorded"
  wait_for_file "$STATE_DIR/web.pid" \
    || fail "legacy Web child PID was not recorded"
}

touch "$STATE_DIR/material.ready"
start_dev "$STATE_DIR/material-default.log"
grep -Fxq "materials-v1" "$STATE_DIR/api.pipeline"
grep -Fxq "htdemucs" "$STATE_DIR/api.separator"
grep -Fxq "mps" "$STATE_DIR/api.device"
grep -Fq "Pipeline: materials-v1" "$STATE_DIR/material-default.log"
grep -Fq "Separator: htdemucs" "$STATE_DIR/material-default.log"
grep -Fq "Device: mps" "$STATE_DIR/material-default.log"
api_pid="$(cat "$STATE_DIR/api.pid")"
web_pid="$(cat "$STATE_DIR/web.pid")"
kill -TERM "$DEV_PID"
set +e
wait "$DEV_PID"
dev_status=$?
set -e
DEV_PID=""
[ "$dev_status" -eq 143 ] \
  || fail "Material default SIGTERM exit was $dev_status, expected 143"
wait_until_dead "$api_pid" || fail "API survived Material default cleanup"
wait_until_dead "$web_pid" || fail "Web survived Material default cleanup"

if PATH="$FAKE_BIN:$PATH" \
  FAKE_STATE_DIR="$STATE_DIR" \
  LMDJ_PIPELINE=legacy \
  "$DEV_SCRIPT" dev >"$STATE_DIR/missing-demo.log" 2>&1
then
  fail "legacy dev accepted a missing Demo venv"
fi
grep -Fq "Demo 开发环境未就绪" "$STATE_DIR/missing-demo.log"
grep -Fq "scripts/dev.sh setup-demo" "$STATE_DIR/missing-demo.log"

mkdir -p "$FIXTURE_ROOT/references/demos/lmdj-song-pipeline/.venv/bin"
cat >"$FIXTURE_ROOT/references/demos/lmdj-song-pipeline/.venv/bin/python" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat >"$FIXTURE_ROOT/references/demos/lmdj-song-pipeline/.venv/bin/song-pipeline" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x \
  "$FIXTURE_ROOT/references/demos/lmdj-song-pipeline/.venv/bin/python" \
  "$FIXTURE_ROOT/references/demos/lmdj-song-pipeline/.venv/bin/song-pipeline"

start_legacy_dev "$STATE_DIR/legacy.log"
grep -Fxq "legacy" "$STATE_DIR/api.pipeline"
grep -Fxq "" "$STATE_DIR/api.separator"
grep -Fxq "" "$STATE_DIR/api.device"
grep -Fq "Pipeline: legacy" "$STATE_DIR/legacy.log"
grep -Fq "Separator: n/a" "$STATE_DIR/legacy.log"
grep -Fq "Device: n/a" "$STATE_DIR/legacy.log"
api_pid="$(cat "$STATE_DIR/api.pid")"
web_pid="$(cat "$STATE_DIR/web.pid")"
kill -TERM "$DEV_PID"
set +e
wait "$DEV_PID"
dev_status=$?
set -e
DEV_PID=""
[ "$dev_status" -eq 143 ] \
  || fail "Legacy SIGTERM exit was $dev_status, expected 143"
wait_until_dead "$api_pid" || fail "API survived Legacy cleanup"
wait_until_dead "$web_pid" || fail "Web survived Legacy cleanup"

rm -f "$STATE_DIR/api.pid" "$STATE_DIR/web.pid"
if LMDJ_PIPELINE=invalid \
  "$DEV_SCRIPT" dev >"$STATE_DIR/invalid.log" 2>&1
then
  fail "dev accepted invalid pipeline"
fi
grep -Fq \
  "LMDJ_PIPELINE must be one of: legacy, materials-v1" \
  "$STATE_DIR/invalid.log"
[ ! -e "$STATE_DIR/api.pid" ] || fail "invalid pipeline started API"
[ ! -e "$STATE_DIR/web.pid" ] || fail "invalid pipeline started Web"

# Signal-driven shutdown reaps both children.
#
# We assert this with SIGTERM and SIGHUP, not SIGINT. cmd_dev routes all three
# through the same EXIT-trap cleanup, so they exercise identical reaping code.
# SIGINT cannot be tested this way: Bash forces SIGINT (and SIGQUIT) to SIG_IGN
# for any process started asynchronously without job control, and a signal
# ignored on entry cannot be trapped. This test necessarily launches dev in the
# background, so a delivered SIGINT would be silently ignored regardless of
# cmd_dev's trap. A real terminal Ctrl+C differs — it signals the foreground
# process group, where SIGINT is not pre-ignored, so `trap 'exit 130' INT`
# fires. The SIGINT->130 path is verified by the interactive acceptance step,
# not here.
for signal_name in TERM HUP; do
  case "$signal_name" in
    TERM) expected_status=143 ;;
    HUP) expected_status=129 ;;
  esac
  start_dev "$STATE_DIR/sig-$signal_name.log"
  api_pid="$(cat "$STATE_DIR/api.pid")"
  web_pid="$(cat "$STATE_DIR/web.pid")"
  kill -"$signal_name" "$DEV_PID"
  set +e
  wait "$DEV_PID"
  dev_status=$?
  set -e
  DEV_PID=""
  [ "$dev_status" -eq "$expected_status" ] \
    || fail "SIG$signal_name exit was $dev_status, expected $expected_status"
  wait_until_dead "$api_pid" || fail "API survived SIG$signal_name cleanup"
  wait_until_dead "$web_pid" || fail "Web survived SIG$signal_name cleanup"
done

start_dev "$STATE_DIR/child-exit.log"
api_pid="$(cat "$STATE_DIR/api.pid")"
web_pid="$(cat "$STATE_DIR/web.pid")"
kill -TERM "$api_pid"
set +e
wait "$DEV_PID"
dev_status=$?
set -e
DEV_PID=""
[ "$dev_status" -ne 0 ] || fail "dev accepted an exited API child"
wait_until_dead "$api_pid" || fail "exited API was not reaped"
wait_until_dead "$web_pid" || fail "Web survived API failure"

echo "local dev command shell tests: PASS"
