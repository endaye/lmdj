#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/deploy-server.yml"
CI_WORKFLOW="$ROOT/.github/workflows/ci.yml"

line_number() {
  grep -n -F "$1" "$WORKFLOW" | head -n 1 | cut -d: -f1
}

assert_order() {
  local before="$1" after="$2" before_line after_line
  before_line="$(line_number "$before")"
  after_line="$(line_number "$after")"
  if [ -z "$before_line" ] || [ -z "$after_line" ] || [ "$before_line" -ge "$after_line" ]; then
    echo "workflow step order is invalid: $before must precede $after" >&2
    exit 1
  fi
}

grep -Fq '      contents: write' "$WORKFLOW" || {
  echo "deploy job must grant contents: write for immutable Tags and Releases" >&2
  exit 1
}

grep -Fq '      actions: read' "$WORKFLOW" || {
  echo "deploy job must retain actions: read for CI verification" >&2
  exit 1
}

grep -Fq 'git show origin/main:scripts/deploy/activate-release.sh > "$RUNNER_TEMP/activate-release.sh"' "$WORKFLOW" || {
  echo "deploy workflow must stage the activation controller from current main" >&2
  exit 1
}

grep -Fq 'git show origin/main:scripts/release/release_version.py > "$RUNNER_TEMP/release_version.py"' "$WORKFLOW" || {
  echo "deploy workflow must stage the version controller from current main" >&2
  exit 1
}

grep -Fq 'git show origin/main:scripts/release/publish-staging-release.sh > "$RUNNER_TEMP/publish-staging-release.sh"' "$WORKFLOW" || {
  echo "deploy workflow must stage the publisher from current main" >&2
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

grep -Fq '      - name: Plan staging version' "$WORKFLOW" || {
  echo "deploy workflow must plan the product version before building artifacts" >&2
  exit 1
}

grep -Fq -- '--mode plan' "$WORKFLOW" || {
  echo "deploy workflow must use the metadata-free release plan mode" >&2
  exit 1
}

grep -Fq 'VITE_PRODUCT_VERSION: ${{ steps.version.outputs.tag }}' "$WORKFLOW" || {
  echo "web build must receive the planned product version" >&2
  exit 1
}

grep -Fq 'VITE_BUILD_REVISION: ${{ steps.target.outputs.sha }}' "$WORKFLOW" || {
  echo "web build must receive the full target revision" >&2
  exit 1
}

grep -Fq -- '--build-arg "LMDJ_PRODUCT_VERSION=$PRODUCT_VERSION"' "$WORKFLOW" || {
  echo "server image must receive the planned product version" >&2
  exit 1
}

grep -Fq -- '--build-arg "LMDJ_BUILD_REVISION=$TARGET_SHA"' "$WORKFLOW" || {
  echo "server image must receive the full target revision" >&2
  exit 1
}

grep -Fq -- '--tag "lmdj-app:$TARGET_SHA" .' "$WORKFLOW" || {
  echo "deploy workflow must build the server image on the GitHub runner" >&2
  exit 1
}

grep -Fq 'docker tag caddy:2 "lmdj-caddy:$TARGET_SHA"' "$WORKFLOW" || {
  echo "deploy workflow must give Caddy an immutable release tag" >&2
  exit 1
}

grep -Fq 'docker save "lmdj-app:$TARGET_SHA" "lmdj-caddy:$TARGET_SHA"' "$WORKFLOW" || {
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

grep -Fq '      - name: Verify staging revision' "$WORKFLOW" || {
  echo "deploy workflow must verify DEPLOYED_REVISION after activation" >&2
  exit 1
}

grep -Fq '"cat '\''$DEPLOY_PATH/DEPLOYED_REVISION'\''"' "$WORKFLOW" || {
  echo "revision verification must read the deployed server revision" >&2
  exit 1
}

grep -Fq '      - name: Prepare staging release' "$WORKFLOW" || {
  echo "deploy workflow must prepare the product version and Changelog" >&2
  exit 1
}

grep -Fq 'python3 "$RUNNER_TEMP/release_version.py"' "$WORKFLOW" || {
  echo "deploy workflow must run the current-main version controller" >&2
  exit 1
}

grep -Fq -- '--mode render' "$WORKFLOW" || {
  echo "deploy workflow must render release metadata after staging activation" >&2
  exit 1
}

grep -Fq -- '--expected-tag "$EXPECTED_TAG"' "$WORKFLOW" || {
  echo "release rendering must reject drift from the version embedded at build time" >&2
  exit 1
}

grep -Fq '      - name: Publish staging release' "$WORKFLOW" || {
  echo "deploy workflow must publish the immutable Tag and Release" >&2
  exit 1
}

grep -Fq '"$RUNNER_TEMP/publish-staging-release.sh"' "$WORKFLOW" || {
  echo "deploy workflow must run the current-main release publisher" >&2
  exit 1
}

assert_order '      - name: Plan staging version' '      - name: Build web'
assert_order '      - name: Plan staging version' '      - name: Build server images'
assert_order '      - name: Activate staging release' '      - name: Verify staging revision'
assert_order '      - name: Verify staging revision' '      - name: Prepare staging release'
assert_order '      - name: Prepare staging release' '      - name: Publish staging release'

if grep -Eq 'git (push .*--force|tag -f|commit|push origin main)' "$WORKFLOW"; then
  echo "deploy workflow must not rewrite Tags or commit directly to main" >&2
  exit 1
fi

grep -Fq 'bash scripts/release/tests/test-release-versioning.sh' "$CI_WORKFLOW" || {
  echo "deploy-config CI must run the release-versioning suite" >&2
  exit 1
}

grep -Fq 'ARG LMDJ_PRODUCT_VERSION' "$ROOT/Dockerfile" || {
  echo "Dockerfile must accept the product version build argument" >&2
  exit 1
}

grep -Fq 'ARG LMDJ_BUILD_REVISION' "$ROOT/Dockerfile" || {
  echo "Dockerfile must accept the build revision argument" >&2
  exit 1
}

grep -Fq 'LMDJ_PRODUCT_VERSION=$LMDJ_PRODUCT_VERSION' "$ROOT/Dockerfile" || {
  echo "Dockerfile must preserve the product version in the runtime image" >&2
  exit 1
}

grep -Fq 'LMDJ_BUILD_REVISION=$LMDJ_BUILD_REVISION' "$ROOT/Dockerfile" || {
  echo "Dockerfile must preserve the build revision in the runtime image" >&2
  exit 1
}

echo "deploy-workflow tests passed"
