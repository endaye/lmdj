#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_ROOT="$(mktemp -d)"
FAKE_BIN="$FIXTURE_ROOT/fake-bin"
STATE_DIR="$FIXTURE_ROOT/state"
REAL_PYTHON3="$(command -v python3)"
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
chmod +x "$FIXTURE_ROOT/scripts/dev.sh"

cat >"$FAKE_BIN/python3" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" != "-m" ] || [ "${2:-}" != "venv" ]; then
  exec "$REAL_PYTHON3" "$@"
fi
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
REAL_PYTHON3="$REAL_PYTHON3" \
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
  REAL_PYTHON3="$REAL_PYTHON3" \
  PATH="$FAKE_BIN:$PATH" \
  "$FIXTURE_ROOT/scripts/dev.sh" setup-materials
then
  echo "setup-materials ignored a pip failure" >&2
  exit 1
fi

cat >"$FIXTURE_ROOT/workers/audio/config/separators.json" <<'EOF'
{
  "separators": [
    {
      "id": "htdemucs",
      "devices": ["cpu", "mps"],
      "command": ["workers/audio/custom-default-runner/bin/python"]
    }
  ]
}
EOF
if FAKE_SETUP_LOG="$STATE_DIR/missing-registry-runner.log" \
  REAL_PYTHON3="$REAL_PYTHON3" \
  PATH="$FAKE_BIN:$PATH" \
  "$FIXTURE_ROOT/scripts/dev.sh" setup-materials \
  >"$STATE_DIR/missing-registry-runner.out" 2>&1
then
  echo "setup-materials ignored the default registry runner path" >&2
  exit 1
fi
grep -Fq "registry" "$STATE_DIR/missing-registry-runner.out"

echo "material setup shell tests: PASS"
