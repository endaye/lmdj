#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for retired_path in \
  apps/api \
  apps/web \
  packages/core-models \
  packages/patchify \
  workers/audio \
  workers/generation \
  workers/render \
  scripts/dev.sh \
  scripts/deploy \
  scripts/release \
  scripts/tests \
  .dockerignore \
  Dockerfile \
  Caddyfile \
  compose.yml \
  compose.smoke.yml \
  .env.example \
  .github/workflows/deploy-server.yml
do
  if [[ -e "$repo_root/$retired_path" ]]; then
    echo "retired active path still exists: $retired_path" >&2
    exit 1
  fi
done

grep -Eq 'New Headless Core' "$repo_root/README.md"
grep -Eq 'lmdj.patch.v1.*must not' "$repo_root/AGENTS.md"
grep -Eq 'docs/governance/version-management.md' "$repo_root/AGENTS.md"
cmp "$repo_root/AGENTS.md" "$repo_root/CLAUDE.md"

coverage_artifact="$(
  find "$repo_root" \
    -path "$repo_root/build/core" -prune -o \
    -type f \
    \( \
      -name '*.profraw' -o \
      -name '*.profdata' -o \
      -name 'coverage-objects.txt' -o \
      -path '*/coverage/summary.json' -o \
      -path '*/coverage/report.txt' \
    \) \
    -print \
    -quit
)"
if [[ -n "$coverage_artifact" ]]; then
  echo \
    "coverage artifact exists outside build/core: ${coverage_artifact#"$repo_root/"}" \
    >&2
  exit 1
fi
