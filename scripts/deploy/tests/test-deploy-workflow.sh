#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/deploy-server.yml"

grep -Fq 'git show origin/main:scripts/deploy/activate-release.sh > "$RUNNER_TEMP/activate-release.sh"' "$WORKFLOW" || {
  echo "deploy workflow must stage the activation controller from current main" >&2
  exit 1
}

grep -Fq 'scp "$RUNNER_TEMP/activate-release.sh"' "$WORKFLOW" || {
  echo "deploy workflow must upload the staged main activation controller" >&2
  exit 1
}

if grep -Fq 'scp scripts/deploy/activate-release.sh' "$WORKFLOW"; then
  echo "deploy workflow must not upload the rollback target's activation controller" >&2
  exit 1
fi

echo "deploy-workflow tests passed"
