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

if [[ ! -x "$repo_root/scripts/release.sh" ]]; then
  echo "stable release command is missing or not executable" >&2
  exit 1
fi
for command_name in prepare push-tag create-draft verify-draft publish-draft audit; do
  if ! grep -Eq "add_parser\(\"${command_name}\"\)" \
    "$repo_root/tools/release/cli.py"; then
    echo "stable release command is missing: $command_name" >&2
    exit 1
  fi
done
if [[ ! -f "$repo_root/.agents/skills/lmdj-release/SKILL.md" ]]; then
  echo "repo-local release skill is missing" >&2
  exit 1
fi

if [[ ! -x "$repo_root/scripts/web-runtime-host.sh" ]]; then
  echo "stable Web Runtime Host command is missing or not executable" >&2
  exit 1
fi
for command_name in configure build test proof serve clean; do
  if ! grep -Eq "^[[:space:]]*${command_name}\\)" \
    "$repo_root/scripts/web-runtime-host.sh"; then
    echo "stable Web Runtime Host command is missing: $command_name" >&2
    exit 1
  fi
done

coverage_artifact="$(
  find "$repo_root" \
    -path "$repo_root/build/core" -prune -o \
    -path "$repo_root/.worktrees" -prune -o \
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
