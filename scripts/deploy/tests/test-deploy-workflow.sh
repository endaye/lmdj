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

grep -Fq 'docker build --tag "lmdj-app:$TARGET_SHA" .' "$WORKFLOW" || {
  echo "deploy workflow must build the server image on the GitHub runner" >&2
  exit 1
}

grep -Fq 'docker save "lmdj-app:$TARGET_SHA" caddy:2' "$WORKFLOW" || {
  echo "deploy workflow must bundle every server image for offline loading" >&2
  exit 1
}

grep -Fq 'scp "$RUNNER_TEMP/lmdj-images-$TARGET_SHA.tar.gz"' "$WORKFLOW" || {
  echo "deploy workflow must upload the prebuilt image bundle" >&2
  exit 1
}

grep -Fq 'lmdj-images-$TARGET_SHA.tar.gz' "$WORKFLOW" || {
  echo "deploy workflow must pass the image bundle to the activation controller" >&2
  exit 1
}

grep -Fq 'image: lmdj-app:${LMDJ_IMAGE_TAG:-latest}' "$ROOT/compose.yml" || {
  echo "compose must select the release-tagged prebuilt app image" >&2
  exit 1
}

echo "deploy-workflow tests passed"
