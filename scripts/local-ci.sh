#!/usr/bin/env bash
# Run the CI lanes this working tree selects, on this machine.
#
# The pre-flight is advisory. It reuses scripts/ci/change_scope.py so it
# cannot select a different lane set than CI, and it reports
# not-runnable-here rather than pass for lanes this platform cannot execute.
# `PR Gate` remains the single aggregate decision; a green local run
# authorizes no push, Pull Request, merge, or later state transition.
#
# Usage:
#   scripts/local-ci.sh                     # run every selected lane
#   scripts/local-ci.sh --list              # resolve the plan without running
#   scripts/local-ci.sh --lanes docs_static # restrict to named lanes
#   scripts/local-ci.sh --no-cache          # ignore cached lane verdicts
#   scripts/local-ci.sh --install-hook      # install the pre-push hook
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

python_bin=""
for candidate in python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo "local-ci error: python3 is required" >&2
  exit 2
fi

exec "$python_bin" "$repo_root/scripts/ci/local_preflight.py" "$@"
