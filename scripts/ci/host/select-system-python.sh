#!/usr/bin/env bash
# Select a host interpreter that survives the release executor's environment.
# Usage: bash scripts/ci/host/select-system-python.sh [/absolute/python3]
set -euo pipefail

python_executable="${1:-/usr/bin/python3}"
if [[ $# -gt 1 || "$python_executable" != /* || ! -x "$python_executable" ]]; then
  echo 'why: an executable absolute system Python path is required; remedy: provision /usr/bin/python3 (3.11+) or pass its absolute host path' >&2
  exit 1
fi

python_bin="$(mktemp -d "${RUNNER_TEMP:?}/lmdj-system-python.XXXXXX")"
trap 'rm -rf -- "$python_bin"' EXIT
ln -s "$python_executable" "$python_bin/python3"
ln -s "$python_executable" "$python_bin/python"

# Probe both resolution by name and the sys.executable spawn used by release
# validators. Do not forward LD_LIBRARY_PATH, PYTHONHOME or any parent state.
if ! env -i PATH="$python_bin:/usr/bin:/bin" python3 - <<'PY'
import json
import os
import subprocess
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
child = subprocess.run(
    [sys.executable, "-c", "import sys; print(sys.version)"],
    env={"PATH": os.environ["PATH"]},
    check=True, capture_output=True, text=True,
)
print(json.dumps({"python": os.path.realpath(sys.executable),
                  "version": sys.version, "sanitized_child": child.stdout.strip()}))
PY
then
  echo 'why: system Python cannot run a Python 3.11+ parent and child without loader variables; remedy: repair the host Python installation, never forward loader variables into sanitized children' >&2
  exit 1
fi

printf '%s\n' "$python_bin" >>"${GITHUB_PATH:?}"
trap - EXIT
