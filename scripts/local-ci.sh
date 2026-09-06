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
#   scripts/local-ci.sh --pr-body body.md   # also check the PR body declaration
#   scripts/local-ci.sh --install-hook      # install the pre-push hook
#
# --pr-body runs CI's own check-doc-impact.mjs against a Pull Request body
# file. The declaration verdict prints before any lane output, so a malformed
# `Documentation impact:` line is visible before the Pull Request exists --
# but every selected lane still runs afterwards; there is no declaration-only
# mode. It is never cached, and it reports not-applicable when the portal lane
# is not selected, because that is the only condition under which CI checks
# the declaration.
#
# Before classifying, the entry point compares the local `origin/main` ref to
# the remote's `main`. The classifier resolves its merge base against the
# local ref and never fetches, so a ref that is days old classifies against a
# days-old base without saying so -- which is how a real control-plane defect
# was once reproduced, fixed upstream already, against a checkout nobody had
# refreshed (.agents/pitfalls/stale-push-verification-under-concurrent-sessions.md).
# The comparison is a notice, never a failure: an offline machine, or one
# where `origin` is not the integration remote, is not wrong to run a
# pre-flight.
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

# stale-base notice. `ls-remote` is one round trip and is bounded so a dead
# network cannot stall the pre-flight; every failure path falls through
# silently because a notice that can fail the run is a gate, and this is not.
# The bound is Python's, not GNU `timeout`: stock macOS does not ship
# `timeout`, and a missing binary here would fail open -- the notice would
# never print on exactly the machines this repository treats as normal.
local_main="$(git -C "$repo_root" rev-parse --verify --quiet origin/main 2>/dev/null || true)"
remote_main="$("$python_bin" - "$repo_root" <<'PYEOF' 2>/dev/null || true
import subprocess, sys
try:
    out = subprocess.run(
        ["git", "-C", sys.argv[1], "ls-remote", "--heads", "origin", "refs/heads/main"],
        capture_output=True, text=True, timeout=5, check=False,
    ).stdout
    print(out.split("\t", 1)[0] if out else "", end="")
except Exception:
    pass
PYEOF
)"
if [[ -n "$local_main" && -n "$remote_main" && "$local_main" != "$remote_main" ]]; then
  echo "pre-flight: stale-base -- local origin/main is ${local_main:0:9}, remote main is ${remote_main:0:9};" >&2
  echo "  this classification uses the local ref. Run 'git fetch origin' and rerun before trusting it." >&2
fi

exec "$python_bin" "$repo_root/scripts/ci/local_preflight.py" "$@"
