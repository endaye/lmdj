#!/usr/bin/env bash
# Run the installed PR-Agent engine on the review host as the current CI runner
# account. Every argument is passed to the engine (`--witness`, or `--input
# FILE`); the result JSON is written to stdout.
#
# The installation is root-owned and read-only under $PR_AGENT_INSTALL_ROOT;
# the shared budget ledger and engine working directory are writable by the
# runner accounts through the ACLs that install.sh applies. umask 002 keeps
# ledger files group/ACL writable so every runner account appends to the same
# ledger instead of each starting its own budget.
set -euo pipefail

INSTALL_ROOT=${PR_AGENT_INSTALL_ROOT:-/var/lib/lmdj/pr-agent}
current="$INSTALL_ROOT/current"
if [[ ! -L "$current" ]]; then
  echo "why: no PR-Agent release is installed at $current; remedy: run scripts/ci/pr-agent/install.sh on the review host" >&2
  exit 2
fi
release=$(readlink -f "$current")
for required in "$release/pr_agent_review.py" "$release/runtime.toml" "$release/vendor" "$release/pr_agent"; do
  if [[ ! -e "$required" ]]; then
    echo "why: installed PR-Agent release is incomplete ($required missing); remedy: reinstall with scripts/ci/pr-agent/install.sh" >&2
    exit 2
  fi
done

umask 002
export PYTHONPATH="$release/vendor:$release"
export PYTHONDONTWRITEBYTECODE=1
export LITELLM_LOCAL_MODEL_COST_MAP=true
exec /usr/bin/python3.12 -s "$release/pr_agent_review.py" \
  --config "$release/runtime.toml" \
  --engine-cwd "$INSTALL_ROOT/engine" \
  --ledger "$INSTALL_ROOT/engine-state/ledger.jsonl" \
  "$@"
