# Local API + Web Dev Command Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `scripts/dev.sh dev` so one Bash 3.2-compatible command preflights, starts, supervises, and stops the local LMDJ API and Web services together.

**Architecture:** Extend the existing repository-level Bash helper rather than adding a second launcher or a Node process-manager dependency. A shell regression test copies the helper into a synthetic repository tree, supplies fake API/Web/Demo executables, and verifies dependency failures plus process lifecycle without starting real Torch, Uvicorn, or Vite.

**Tech Stack:** Bash 3.2, Uvicorn, Vite, `curl`, existing per-package virtual environments.

## Global Constraints

- The public command is exactly `scripts/dev.sh dev`.
- Web is `http://localhost:5173`; API is `http://localhost:8000`.
- Bind both services to `127.0.0.1`.
- Keep API Jobs at the existing ignored default `apps/api/jobs/`.
- Never install or download dependencies from `dev`; fail before starting children and print exact recovery commands.
- Use only Bash 3.2-compatible process primitives; do not use `wait -n`.
- `Ctrl+C`, `SIGTERM`, `SIGHUP`, startup failure, or either child exiting must reap both children.
- Never kill an unrelated process that already occupies port 5173 or 8000.
- Do not add `concurrently`, a root `package.json`, custom ports, HTTPS, or deployment behavior.

## File Structure

- Modify `scripts/dev.sh`
  - Own the `dev` help entry, dependency preflight, readiness polling, child PID supervision, and signal cleanup.
- Create `scripts/tests/test_dev_command.sh`
  - Own deterministic shell-level regression coverage using a temporary fake repository and fake child services.

---

### Task 1: Add the combined local development command

**Files:**
- Modify: `scripts/dev.sh:5-43`
- Modify: `scripts/dev.sh:431-474`
- Create: `scripts/tests/test_dev_command.sh`

**Interfaces:**
- Consumes:
  - `apps/api/.venv/bin/python`
  - `apps/api/.venv/bin/uvicorn`
  - `apps/web/node_modules/.bin/vite`
  - `references/demos/lmdj-song-pipeline/.venv/bin/python`
  - `references/demos/lmdj-song-pipeline/.venv/bin/song-pipeline`
  - API readiness endpoint `GET /health`
- Produces:
  - CLI command `scripts/dev.sh dev`
  - Ready copy:

    ```text
    ==> LMDJ local dev ready
        Web: http://localhost:5173
        API: http://localhost:8000
    ```

  - Exit status `130` for `SIGINT`, `143` for `SIGTERM`, `129` for `SIGHUP`, and nonzero for dependency, readiness, port, or child-service failure.

- [ ] **Step 1: Write the failing shell regression test**

Create `scripts/tests/test_dev_command.sh` with the following complete test harness:

```bash
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
exit 0
EOF
cat >"$FIXTURE_ROOT/apps/api/.venv/bin/uvicorn" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$$" >"$FAKE_STATE_DIR/api.pid"
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

if "$DEV_SCRIPT" dev >"$STATE_DIR/missing-demo.log" 2>&1; then
  fail "dev accepted a missing Demo venv"
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
  [ -s "$STATE_DIR/api.pid" ] || fail "API child PID was not recorded"
  [ -s "$STATE_DIR/web.pid" ] || fail "Web child PID was not recorded"
}

start_dev "$STATE_DIR/sigint.log"
api_pid="$(cat "$STATE_DIR/api.pid")"
web_pid="$(cat "$STATE_DIR/web.pid")"
kill -INT "$DEV_PID"
set +e
wait "$DEV_PID"
dev_status=$?
set -e
DEV_PID=""
[ "$dev_status" -eq 130 ] || fail "SIGINT exit was $dev_status, expected 130"
wait_until_dead "$api_pid" || fail "API survived SIGINT cleanup"
wait_until_dead "$web_pid" || fail "Web survived SIGINT cleanup"

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
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
bash scripts/tests/test_dev_command.sh
```

Expected: FAIL at `help does not list dev` because the current helper has no `dev` entry or dispatch case.

- [ ] **Step 3: Add paths and help copy**

In `scripts/dev.sh`, add the two product paths beside the existing constants:

```bash
API="$ROOT/apps/api"
WEB="$ROOT/apps/web"
```

Add this exact help line before `all`:

```text
  dev                同时启动本地 API + Web（Ctrl+C 同时关闭）
```

- [ ] **Step 4: Implement dependency preflight**

Add these functions before `cmd_creator_smoke`:

```bash
print_api_dev_setup() {
  cat >&2 <<'EOF'
API 开发环境未就绪。运行：
  cd apps/api
  python3 -m venv .venv
  .venv/bin/pip install -e ../../packages/core-models
  .venv/bin/pip install -e ../../packages/patchify
  .venv/bin/pip install -e ../../workers/audio
  .venv/bin/pip install -e .
EOF
}

ensure_dev_dependencies() {
  if [ ! -x "$API/.venv/bin/python" ] || [ ! -x "$API/.venv/bin/uvicorn" ]; then
    print_api_dev_setup
    return 1
  fi
  if ! "$API/.venv/bin/python" -c \
    'import lmdj_api, lmdj_audio_worker, lmdj_patchify, lmdj_core_models' \
    >/dev/null 2>&1
  then
    print_api_dev_setup
    return 1
  fi

  if [ ! -x "$WEB/node_modules/.bin/vite" ] || ! command -v npm >/dev/null 2>&1; then
    echo "Web 开发环境未就绪。运行: cd apps/web && npm install" >&2
    return 1
  fi

  if [ ! -x "$DEMO/.venv/bin/python" ] \
    || [ ! -x "$DEMO/.venv/bin/song-pipeline" ] \
    || ! "$DEMO/.venv/bin/python" -c 'import torch, demucs' >/dev/null 2>&1
  then
    echo "Demo 开发环境未就绪。运行: scripts/dev.sh setup-demo" >&2
    return 1
  fi

  if ! command -v curl >/dev/null 2>&1; then
    echo "缺少 curl，无法检查本地服务就绪状态" >&2
    return 1
  fi
}
```

- [ ] **Step 5: Implement Bash 3.2-compatible child supervision**

Add the following globals and functions after the preflight:

```bash
DEV_API_PID=""
DEV_WEB_PID=""

cleanup_dev_children() {
  local exit_status=$?
  local child_pid
  trap - EXIT INT TERM HUP
  for child_pid in "$DEV_API_PID" "$DEV_WEB_PID"; do
    if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
      kill -TERM "$child_pid" 2>/dev/null || true
    fi
  done
  for child_pid in "$DEV_API_PID" "$DEV_WEB_PID"; do
    if [ -n "$child_pid" ]; then
      wait "$child_pid" 2>/dev/null || true
    fi
  done
  exit "$exit_status"
}

wait_for_dev_ready() {
  local deadline="$((SECONDS + 30))"
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! kill -0 "$DEV_API_PID" 2>/dev/null \
      || ! kill -0 "$DEV_WEB_PID" 2>/dev/null
    then
      echo "本地服务在就绪前退出" >&2
      return 1
    fi
    if curl --silent --fail --output /dev/null \
      http://127.0.0.1:8000/health \
      && curl --silent --fail --output /dev/null \
        http://127.0.0.1:5173/
    then
      return 0
    fi
    sleep 0.2
  done
  echo "本地服务在 30 秒内未就绪" >&2
  return 1
}

cmd_dev() {
  ensure_dev_dependencies

  trap cleanup_dev_children EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP

  (
    cd "$API"
    exec .venv/bin/uvicorn lmdj_api.app:app --host 127.0.0.1 --port 8000
  ) &
  DEV_API_PID=$!

  (
    cd "$WEB"
    exec npm run dev -- --host 127.0.0.1 --port 5173
  ) &
  DEV_WEB_PID=$!

  wait_for_dev_ready
  cat <<'EOF'
==> LMDJ local dev ready
    Web: http://localhost:5173
    API: http://localhost:8000
EOF

  while kill -0 "$DEV_API_PID" 2>/dev/null \
    && kill -0 "$DEV_WEB_PID" 2>/dev/null
  do
    sleep 0.2
  done

  local failed_service failed_pid failed_status
  if ! kill -0 "$DEV_API_PID" 2>/dev/null; then
    failed_service="API"
    failed_pid="$DEV_API_PID"
  else
    failed_service="Web"
    failed_pid="$DEV_WEB_PID"
  fi
  failed_status=1
  if wait "$failed_pid"; then
    failed_status=1
  else
    failed_status=$?
  fi
  echo "$failed_service 服务已退出，正在关闭本地开发环境" >&2
  return "$failed_status"
}
```

Add the dispatch case:

```bash
  dev)             cmd_dev ;;
```

- [ ] **Step 6: Run the focused RED/GREEN gate**

Run:

```bash
bash -n scripts/dev.sh
bash scripts/tests/test_dev_command.sh
```

Expected:

```text
local dev command shell tests: PASS
```

If the SIGINT assertion exposes Bash 3.2 signal inheritance differences, fix `cmd_dev` rather than weakening the test: the public contract requires exit 130 and both children reaped.

- [ ] **Step 7: Run existing regression gates**

Run:

```bash
bash scripts/tests/test_creator_smoke.sh
scripts/dev.sh test
git diff --check
```

Expected:

- `creator-smoke shell tests: PASS`
- Core Models: 7 passed
- Patchify: 18 passed
- `git diff --check`: no output

- [ ] **Step 8: Prepare this worktree for real local acceptance**

The current worktree intentionally has no `apps/api/.venv`. Create it explicitly; this is ignored local state and must not be committed:

```bash
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e ../../packages/core-models
.venv/bin/pip install -e ../../packages/patchify
.venv/bin/pip install -e ../../workers/audio
.venv/bin/pip install -e .
cd ../..
```

Before starting the new command, inspect listeners:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Stop only API/Web processes that this Codex task previously started. If a listener belongs to another user process, do not terminate it; report the port conflict.

- [ ] **Step 9: Run the real combined-service acceptance**

In one interactive terminal:

```bash
scripts/dev.sh dev
```

Expected ready output:

```text
==> LMDJ local dev ready
    Web: http://localhost:5173
    API: http://localhost:8000
```

From a second terminal:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:5173/
```

Expected: API returns `{"ok":true}` and Web returns HTTP 200.

Press `Ctrl+C` in the first terminal, then run:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Expected: both commands produce no listener rows.

- [ ] **Step 10: Commit the implementation atomically**

Inspect the exact task-local diff:

```bash
git status --short
git diff -- scripts/dev.sh scripts/tests/test_dev_command.sh
git diff --check
```

Stage and commit only the implementation and its test:

```bash
git add scripts/dev.sh scripts/tests/test_dev_command.sh
git commit -m "feat(dev): start API and Web together"
```

Verify the committed boundary:

```bash
git show --stat --oneline HEAD
git show --name-only --format= HEAD
git status --short --branch
```

Expected: exactly `scripts/dev.sh` and `scripts/tests/test_dev_command.sh` are committed, and the nonignored worktree is clean.
