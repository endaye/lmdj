# Local Material Pipeline Dev Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/dev.sh dev` start the local Material Pipeline by default, provide an idempotent Material environment setup command, and keep the production API default unchanged.

**Architecture:** The application-level `runner_from_env()` continues to default to `legacy`. The local shell boundary resolves an unset pipeline to `materials-v1`, validates only the selected pipeline's dependencies, and exports the resolved pipeline/Separator/Device to the API child. A new setup command installs Material DSP dependencies into the API venv and reuses the isolated HT Demucs runner setup.

**Tech Stack:** Bash, Python venv/pip editable installs, Python standard-library JSON, existing Separator registry, shell fixture tests.

## Global Constraints

- Do not change `apps/api/lmdj_api/app.py::runner_from_env()`; an unset production environment must still select `legacy`.
- `scripts/dev.sh dev` defaults locally to `materials-v1`.
- `LMDJ_PIPELINE=legacy scripts/dev.sh dev` remains supported.
- Local Material defaults are `LMDJ_SEPARATOR_ID=htdemucs` and `LMDJ_SEPARATOR_DEVICE=mps`.
- Explicit user values override local defaults.
- Material startup must not require the frozen demo venv.
- Legacy startup must not require Material DSP or a Separator runner venv.
- There is no silent Material-to-legacy fallback.
- `setup-materials` prepares dependencies only; it never starts or restarts services.
- Keep `AGENTS.md` and `CLAUDE.md` synchronized for shared command guidance.
- Every implementation task gets its own Conventional Commit.

---

## File Map

- Modify `scripts/dev.sh`
  - Own `setup-materials`.
  - Resolve local runtime selection.
  - Validate selected-pipeline dependencies.
  - Export runtime identity to the API child.
  - Print the selected runtime at readiness.
- Create `scripts/tests/test_setup_materials.sh`
  - Prove setup command ordering, idempotent entry, import verification, and failure propagation without downloading Demucs.
- Modify `scripts/tests/test_dev_command.sh`
  - Prove Material local defaults, legacy override, preflight routing, child environment propagation, readiness output, and existing process cleanup.
- Modify `README.md`
  - Add the local Material setup and startup workflow.
- Modify `AGENTS.md`
  - Add `setup-materials` and clarify local versus production defaults.
- Modify `CLAUDE.md`
  - Mirror the `AGENTS.md` command guidance exactly.
- Modify `docs/superpowers/2026-07-10-status-and-backlog.md`
  - Record that PR #35 is merged and local `dev` now defaults to Material while production remains explicit legacy.

---

### Task 1: Add the idempotent Material environment setup command

**Files:**
- Create: `scripts/tests/test_setup_materials.sh`
- Modify: `scripts/dev.sh:21-45`
- Modify: `scripts/dev.sh:117-159`
- Modify: `scripts/dev.sh:440-462`
- Modify: `scripts/dev.sh:591-615`

**Interfaces:**
- Produces: `cmd_setup_materials() -> shell exit status`
- Produces: `install_api_material_dependencies() -> shell exit status`
- Reuses: `cmd_setup_sep_demucs() -> shell exit status`
- CLI: `scripts/dev.sh setup-materials`

- [ ] **Step 1: Write the failing setup fixture test**

Create `scripts/tests/test_setup_materials.sh` with a copied `dev.sh`, a fake
`python3 -m venv`, and fake pip executables that append their arguments to a
log. The test must assert the Material setup command is advertised, installs
the four editable boundaries in order, invokes the Demucs constraints, and
propagates pip failure:

```bash
#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_ROOT="$(mktemp -d)"
FAKE_BIN="$FIXTURE_ROOT/fake-bin"
STATE_DIR="$FIXTURE_ROOT/state"
trap 'rm -rf "$FIXTURE_ROOT"' EXIT

mkdir -p \
  "$FIXTURE_ROOT/scripts" \
  "$FIXTURE_ROOT/apps/api" \
  "$FIXTURE_ROOT/apps/web" \
  "$FIXTURE_ROOT/packages/core-models" \
  "$FIXTURE_ROOT/packages/patchify" \
  "$FIXTURE_ROOT/workers/audio/config" \
  "$FAKE_BIN" \
  "$STATE_DIR"
cp "$SOURCE_ROOT/scripts/dev.sh" "$FIXTURE_ROOT/scripts/dev.sh"
cp "$SOURCE_ROOT/workers/audio/config/parity-constraints.txt" \
  "$FIXTURE_ROOT/workers/audio/config/parity-constraints.txt"
cp "$SOURCE_ROOT/workers/audio/config/runner-demucs-constraints.txt" \
  "$FIXTURE_ROOT/workers/audio/config/runner-demucs-constraints.txt"
chmod +x "$FIXTURE_ROOT/scripts/dev.sh"

cat >"$FAKE_BIN/python3" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]
venv="$3"
mkdir -p "$venv/bin"
cat >"$venv/bin/python" <<'PY'
#!/usr/bin/env bash
exit 0
PY
cat >"$venv/bin/pip" <<'PIP'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_SETUP_LOG"
if [ -n "${FAKE_PIP_FAIL_ON:-}" ] && [[ "$*" == *"$FAKE_PIP_FAIL_ON"* ]]; then
  exit 23
fi
exit 0
PIP
chmod +x "$venv/bin/python" "$venv/bin/pip"
EOF
chmod +x "$FAKE_BIN/python3"

help_output="$("$FIXTURE_ROOT/scripts/dev.sh" --help)"
grep -Fq "setup-materials" <<<"$help_output"

FAKE_SETUP_LOG="$STATE_DIR/pip.log" \
PATH="$FAKE_BIN:$PATH" \
  "$FIXTURE_ROOT/scripts/dev.sh" setup-materials

install_count="$(wc -l <"$STATE_DIR/pip.log" | tr -d ' ')"
[ "$install_count" -eq 7 ]
install_1="$(sed -n '1p' "$STATE_DIR/pip.log")"
install_2="$(sed -n '2p' "$STATE_DIR/pip.log")"
install_3="$(sed -n '3p' "$STATE_DIR/pip.log")"
install_4="$(sed -n '4p' "$STATE_DIR/pip.log")"
install_5="$(sed -n '5p' "$STATE_DIR/pip.log")"
install_6="$(sed -n '6p' "$STATE_DIR/pip.log")"
install_7="$(sed -n '7p' "$STATE_DIR/pip.log")"
[[ "$install_1" == *"packages/core-models"* ]]
[[ "$install_2" == *"packages/patchify"* ]]
[[ "$install_3" == *"workers/audio[pfs]"* ]]
[[ "$install_3" == *"parity-constraints.txt"* ]]
[[ "$install_4" == *"apps/api"* ]]
[[ "$install_5" == *"packages/core-models"* ]]
[[ "$install_6" == *"packages/patchify"* ]]
[[ "$install_7" == *"demucs soundfile"* ]]
[[ "$install_7" == *"runner-demucs-constraints.txt"* ]]

if FAKE_SETUP_LOG="$STATE_DIR/failing-pip.log" \
  FAKE_PIP_FAIL_ON="workers/audio[pfs]" \
  PATH="$FAKE_BIN:$PATH" \
  "$FIXTURE_ROOT/scripts/dev.sh" setup-materials
then
  echo "setup-materials ignored a pip failure" >&2
  exit 1
fi

echo "material setup shell tests: PASS"
```

- [ ] **Step 2: Run the setup test to verify it fails**

Run:

```bash
bash scripts/tests/test_setup_materials.sh
```

Expected: FAIL because `setup-materials` is absent from help and command dispatch.

- [ ] **Step 3: Add the setup implementation**

Add the help entry:

```bash
  setup-materials    创建/补齐本地 Material API DSP + HT Demucs runner 环境
```

Add the focused API installer before `cmd_setup_pfs`:

```bash
install_api_material_dependencies() {
  if [ ! -x "$API/.venv/bin/python" ]; then
    echo "==> 创建 API venv"
    python3 -m venv "$API/.venv"
  fi
  "$API/.venv/bin/pip" -q install -e "$CORE" -c "$CONSTRAINTS"
  "$API/.venv/bin/pip" -q install -e "$PATCHIFY" -c "$CONSTRAINTS"
  "$API/.venv/bin/pip" -q install -e "$WORKER[pfs]" -c "$CONSTRAINTS"
  "$API/.venv/bin/pip" -q install -e "$API"
  "$API/.venv/bin/python" -c \
    'import numpy, soundfile, librosa, sklearn, pretty_midi; from lmdj_audio_worker.creator_runner import CreatorPipelineRunner'
}

cmd_setup_materials() {
  install_api_material_dependencies
  cmd_setup_sep_demucs
  [ -x "$SEP_DEMUCS_VENV/bin/python" ] || {
    echo "HT Demucs runner 环境未就绪" >&2
    return 1
  }
  echo "==> Material 本地环境就绪"
}
```

Add dispatch before `setup-demo`:

```bash
  setup-materials)  cmd_setup_materials ;;
```

- [ ] **Step 4: Run the focused setup test**

Run:

```bash
bash scripts/tests/test_setup_materials.sh
```

Expected:

```text
material setup shell tests: PASS
```

- [ ] **Step 5: Run shell syntax validation**

Run:

```bash
bash -n scripts/dev.sh scripts/tests/test_setup_materials.sh
```

Expected: exit 0 with no output.

- [ ] **Step 6: Commit Task 1**

```bash
git add scripts/dev.sh scripts/tests/test_setup_materials.sh
git commit -m "feat(dev): add material environment setup"
```

---

### Task 2: Make local dev pipeline-aware and default to Material

**Files:**
- Modify: `scripts/tests/test_dev_command.sh`
- Modify: `scripts/dev.sh:117-251`

**Interfaces:**
- Produces: `configure_dev_runtime() -> shell exit status`
- Produces globals:
  - `DEV_PIPELINE: "materials-v1" | "legacy"`
  - `DEV_SEPARATOR_ID: string`
  - `DEV_SEPARATOR_DEVICE: "cpu" | "mps"`
- Consumes: `workers/audio/config/separators.json`
- Calls: `ensure_dev_dependencies() -> shell exit status`

- [ ] **Step 1: Rewrite the fixture's fake API Python to expose Material readiness**

In `scripts/tests/test_dev_command.sh`, replace the always-success fake API
Python with a script that fails Material imports until the fixture creates a
marker:

```bash
cat >"$FIXTURE_ROOT/apps/api/.venv/bin/python" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"numpy, soundfile, librosa, sklearn, pretty_midi"* ]] \
  && [ ! -f "$FAKE_STATE_DIR/material.ready" ]
then
  exit 1
fi
exit 0
EOF
```

Create a minimal registry and fake runner:

```bash
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
```

- [ ] **Step 2: Add failing assertions for Material defaults and legacy override**

Before creating `material.ready`, assert default startup fails with the focused
setup instruction:

```bash
if FAKE_STATE_DIR="$STATE_DIR" \
  "$DEV_SCRIPT" dev >"$STATE_DIR/missing-material.log" 2>&1
then
  fail "dev accepted missing Material DSP dependencies"
fi
grep -Fq "Material 开发环境未就绪" "$STATE_DIR/missing-material.log"
grep -Fq "scripts/dev.sh setup-materials" "$STATE_DIR/missing-material.log"
```

After creating the marker, remove the demo fixture from the default path and
assert Material startup succeeds. Capture the API child environment by adding
these lines to the fake uvicorn:

```bash
printf '%s\n' "${LMDJ_PIPELINE:-}" >"$FAKE_STATE_DIR/api.pipeline"
printf '%s\n' "${LMDJ_SEPARATOR_ID:-}" >"$FAKE_STATE_DIR/api.separator"
printf '%s\n' "${LMDJ_SEPARATOR_DEVICE:-}" >"$FAKE_STATE_DIR/api.device"
```

Then assert:

```bash
touch "$STATE_DIR/material.ready"
start_dev "$STATE_DIR/material-default.log"
grep -Fxq "materials-v1" "$STATE_DIR/api.pipeline"
grep -Fxq "htdemucs" "$STATE_DIR/api.separator"
grep -Fxq "mps" "$STATE_DIR/api.device"
grep -Fq "Pipeline: materials-v1" "$STATE_DIR/material-default.log"
grep -Fq "Separator: htdemucs" "$STATE_DIR/material-default.log"
grep -Fq "Device: mps" "$STATE_DIR/material-default.log"
```

Add a legacy start helper:

```bash
start_legacy_dev() {
  local log_file="$1"
  rm -f "$STATE_DIR/api.pid" "$STATE_DIR/web.pid"
  PATH="$FAKE_BIN:$PATH" \
    FAKE_STATE_DIR="$STATE_DIR" \
    LMDJ_PIPELINE=legacy \
    "$DEV_SCRIPT" dev >"$log_file" 2>&1 &
  DEV_PID=$!
  wait_for_log "==> LMDJ local dev ready" "$log_file"
}
```

Assert legacy fails without the demo venv, succeeds once the demo fixture is
created, and prints `Pipeline: legacy`. Assert an invalid pipeline fails before
either child PID is written:

```bash
if LMDJ_PIPELINE=invalid "$DEV_SCRIPT" dev >"$STATE_DIR/invalid.log" 2>&1; then
  fail "dev accepted invalid pipeline"
fi
grep -Fq "LMDJ_PIPELINE must be one of: legacy, materials-v1" "$STATE_DIR/invalid.log"
```

- [ ] **Step 3: Run the dev test to verify the new assertions fail**

Run:

```bash
bash scripts/tests/test_dev_command.sh
```

Expected: FAIL because default startup still selects application-level legacy
and the current preflight always requires the demo venv.

- [ ] **Step 4: Implement local runtime selection**

Add globals and configuration before `ensure_dev_dependencies`:

```bash
DEV_PIPELINE=""
DEV_SEPARATOR_ID=""
DEV_SEPARATOR_DEVICE=""

configure_dev_runtime() {
  DEV_PIPELINE="${LMDJ_PIPELINE:-materials-v1}"
  case "$DEV_PIPELINE" in
    materials-v1)
      DEV_SEPARATOR_ID="${LMDJ_SEPARATOR_ID:-htdemucs}"
      DEV_SEPARATOR_DEVICE="${LMDJ_SEPARATOR_DEVICE:-mps}"
      ;;
    legacy)
      DEV_SEPARATOR_ID=""
      DEV_SEPARATOR_DEVICE=""
      ;;
    *)
      echo "LMDJ_PIPELINE must be one of: legacy, materials-v1" >&2
      return 1
      ;;
  esac
}
```

Add a standard-library registry probe:

```bash
material_runner_path() {
  python3 - "$ROOT" "$DEV_SEPARATOR_ID" "$DEV_SEPARATOR_DEVICE" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
separator_id = sys.argv[2]
device = sys.argv[3]
registry = json.loads(
    (root / "workers/audio/config/separators.json").read_text()
)
entries = {
    entry["id"]: entry
    for entry in registry.get("separators", [])
    if isinstance(entry, dict) and isinstance(entry.get("id"), str)
}
if separator_id not in entries:
    raise SystemExit(
        f"unknown LMDJ separator {separator_id!r}; available: {sorted(entries)}"
    )
entry = entries[separator_id]
if device not in entry.get("devices", []):
    raise SystemExit(
        f"separator {separator_id!r} does not support {device!r}"
    )
command = entry.get("command")
if not isinstance(command, list) or not command:
    raise SystemExit(f"separator {separator_id!r} has no command")
runner = pathlib.Path(command[0])
print(runner if runner.is_absolute() else root / runner)
PY
}
```

Split the selected-pipeline checks:

```bash
ensure_material_dev_dependencies() {
  if ! "$API/.venv/bin/python" -c \
    'import numpy, soundfile, librosa, sklearn, pretty_midi; from lmdj_audio_worker.creator_runner import CreatorPipelineRunner' \
    >/dev/null 2>&1
  then
    echo "Material 开发环境未就绪。运行: scripts/dev.sh setup-materials" >&2
    return 1
  fi
  local runner_path
  runner_path="$(material_runner_path)" || return 1
  if [ ! -x "$runner_path" ]; then
    echo "Material Separator 未就绪。运行: scripts/dev.sh setup-materials" >&2
    return 1
  fi
}

ensure_legacy_dev_dependencies() {
  if [ ! -x "$DEMO/.venv/bin/python" ] \
    || [ ! -x "$DEMO/.venv/bin/song-pipeline" ] \
    || ! "$DEMO/.venv/bin/python" -c 'import torch, demucs' >/dev/null 2>&1
  then
    echo "Demo 开发环境未就绪。运行: scripts/dev.sh setup-demo" >&2
    return 1
  fi
}
```

Keep the API/Web/curl checks in `ensure_dev_dependencies`, then dispatch:

```bash
case "$DEV_PIPELINE" in
  materials-v1) ensure_material_dev_dependencies ;;
  legacy) ensure_legacy_dev_dependencies ;;
esac
```

- [ ] **Step 5: Export the resolved runtime to the API child**

At the start of `cmd_dev`:

```bash
configure_dev_runtime
ensure_dev_dependencies
```

Replace the API child with:

```bash
(
  cd "$API"
  export LMDJ_PIPELINE="$DEV_PIPELINE"
  if [ "$DEV_PIPELINE" = "materials-v1" ]; then
    export LMDJ_SEPARATOR_ID="$DEV_SEPARATOR_ID"
    export LMDJ_SEPARATOR_DEVICE="$DEV_SEPARATOR_DEVICE"
  else
    unset LMDJ_SEPARATOR_ID LMDJ_SEPARATOR_DEVICE
  fi
  exec .venv/bin/uvicorn lmdj_api.app:app --host 127.0.0.1 --port 8000
) &
```

Replace the ready heredoc with explicit output:

```bash
echo "==> LMDJ local dev ready"
echo "    Web: http://localhost:5173"
echo "    API: http://localhost:8000"
echo "    Pipeline: $DEV_PIPELINE"
if [ "$DEV_PIPELINE" = "materials-v1" ]; then
  echo "    Separator: $DEV_SEPARATOR_ID"
  echo "    Device: $DEV_SEPARATOR_DEVICE"
else
  echo "    Separator: n/a"
  echo "    Device: n/a"
fi
```

- [ ] **Step 6: Run the focused dev test**

Run:

```bash
bash scripts/tests/test_dev_command.sh
```

Expected:

```text
local dev command shell tests: PASS
```

- [ ] **Step 7: Run the existing Creator smoke fixture**

Run:

```bash
bash scripts/tests/test_creator_smoke.sh
```

Expected:

```text
creator-smoke shell tests: PASS
```

- [ ] **Step 8: Commit Task 2**

```bash
git add scripts/dev.sh scripts/tests/test_dev_command.sh
git commit -m "feat(dev): default local startup to materials"
```

---

### Task 3: Document the local/production boundary and run the full gate

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/2026-07-10-status-and-backlog.md`

**Interfaces:**
- Documents CLI: `scripts/dev.sh setup-materials`
- Documents CLI: `scripts/dev.sh dev`
- Documents override: `LMDJ_PIPELINE=legacy scripts/dev.sh dev`

- [ ] **Step 1: Update README commands**

Add:

```markdown
scripts/dev.sh setup-materials       # 本地 Material DSP + HT Demucs runner
scripts/dev.sh dev                   # 本地默认 materials-v1；同时启动 API + Web
LMDJ_PIPELINE=legacy scripts/dev.sh dev  # 显式回到冻结 demo 链
```

Replace the statement that app API/Web development always needs
`setup-demo`. Explain that default local Material development needs
`setup-materials`, while explicit legacy needs `setup-demo`.

- [ ] **Step 2: Update AGENTS and CLAUDE together**

Add the same command entries to both files:

```markdown
scripts/dev.sh setup-materials  # local Material DSP + HT Demucs runner
scripts/dev.sh dev              # local default: materials-v1 API + Web
LMDJ_PIPELINE=legacy scripts/dev.sh dev  # explicit legacy local chain
```

Replace:

```markdown
App API + web end-to-end (needs `scripts/dev.sh setup-demo` first):
```

with:

```markdown
Local App API + Web defaults to `materials-v1` and needs
`scripts/dev.sh setup-materials` first. Production/unset API configuration
still defaults to `legacy`; use `LMDJ_PIPELINE=legacy scripts/dev.sh dev`
for the frozen local demo chain.
```

After editing, verify the shared passages are identical:

```bash
diff \
  <(sed -n '75,130p' AGENTS.md) \
  <(sed -n '75,130p' CLAUDE.md)
```

Expected: exit 0.

- [ ] **Step 3: Correct the status/backlog record**

Change the stale integration wording to state:

```markdown
## Material Pipeline v1 实现（2026-07-26，已合并 main）

PR #35 已合并 `lmdj.materials.v1`、Material Extractor、固定槽
Patchify、`CreatorPipelineRunner` 和队列集成。生产 API 在未显式设置时仍默认
`legacy`；`scripts/dev.sh dev` 仅在本地开发边界默认
`materials-v1 / htdemucs / mps`。
```

Keep the real release-evidence gates and do not claim production promotion.

- [ ] **Step 4: Run all shell gates**

Run:

```bash
bash -n scripts/dev.sh \
  scripts/tests/test_setup_materials.sh \
  scripts/tests/test_dev_command.sh \
  scripts/tests/test_creator_smoke.sh
bash scripts/tests/test_setup_materials.sh
bash scripts/tests/test_dev_command.sh
bash scripts/tests/test_creator_smoke.sh
```

Expected: syntax check exit 0 and all three tests print `PASS`.

- [ ] **Step 5: Run package regression tests**

Run:

```bash
scripts/dev.sh test
```

Expected:

```text
core-models: 18 passed
patchify: 23 passed
```

- [ ] **Step 6: Verify task-local diff scope**

Run:

```bash
git diff --check
git status --short
```

Expected changed files only:

```text
README.md
AGENTS.md
CLAUDE.md
docs/superpowers/2026-07-10-status-and-backlog.md
```

plus the already committed Task 1/Task 2 files absent from the unstaged list.

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  README.md \
  AGENTS.md \
  CLAUDE.md \
  docs/superpowers/2026-07-10-status-and-backlog.md
git commit -m "docs(dev): document material local startup"
```

---

## Post-Implementation Handoff

After all three commits exist and the branch is clean:

1. Inspect `git log origin/main..HEAD` and the committed file list.
2. Request separate authorization to push, open a PR, and merge; automatic
   commits do not grant publication permission.
3. After the PR is merged and local `main` is synchronized, run:

   ```bash
   scripts/dev.sh setup-materials
   ```

4. Verify without starting services:

   ```bash
   apps/api/.venv/bin/python -c \
     'import numpy, soundfile, librosa, sklearn, pretty_midi; from lmdj_audio_worker.creator_runner import CreatorPipelineRunner; print("api-material-dsp: ready")'
   test -x workers/audio/.venv-sep-demucs/bin/python
   ```

5. Do not restart the currently running API/Web processes. The user then stops
   the old local process and runs:

   ```bash
   scripts/dev.sh dev
   ```

6. The startup banner must show:

   ```text
   Pipeline: materials-v1
   Separator: htdemucs
   Device: mps
   ```

7. Existing legacy Jobs remain legacy. Upload a new submission to exercise the
   Material Pipeline.
