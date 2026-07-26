#!/usr/bin/env bash
set -euo pipefail

TARGET_SHA="${1:-}"
TAG="${2:-}"
NOTES_FILE="${3:-}"

if [[ ! "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: publish-staging-release.sh FULL_SHA vX.Y.Z CHANGELOG_FILE" >&2
  exit 2
fi
if [[ ! "$TAG" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "release Tag must use v<major>.<minor>.<patch>: $TAG" >&2
  exit 2
fi
if [ ! -f "$NOTES_FILE" ]; then
  echo "release notes file does not exist: $NOTES_FILE" >&2
  exit 2
fi
EXPECTED_ASSET="CHANGELOG-$TAG.md"
if [ "$(basename "$NOTES_FILE")" != "$EXPECTED_ASSET" ]; then
  echo "release notes must be named $EXPECTED_ASSET" >&2
  exit 2
fi

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_SERVER_URL:?GITHUB_SERVER_URL is required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

git cat-file -e "${TARGET_SHA}^{commit}"

remote_tag="$(git ls-remote --refs origin "refs/tags/$TAG")"
if [ -n "$remote_tag" ]; then
  remote_peeled="$(git ls-remote origin "refs/tags/$TAG^{}")"
  if [ -z "$remote_peeled" ]; then
    echo "remote product Tag $TAG must be annotated" >&2
    exit 1
  fi
  remote_sha="${remote_peeled%%[[:space:]]*}"
  if [ "$remote_sha" != "$TARGET_SHA" ]; then
    echo "remote Tag $TAG points to $remote_sha, expected $TARGET_SHA" >&2
    exit 1
  fi
  if ! git show-ref --verify --quiet "refs/tags/$TAG"; then
    git fetch --no-tags origin "refs/tags/$TAG:refs/tags/$TAG"
  fi
else
  if git show-ref --verify --quiet "refs/tags/$TAG"; then
    tagged_sha="$(git rev-parse "$TAG^{commit}")"
    if [ "$tagged_sha" != "$TARGET_SHA" ]; then
      echo "local Tag $TAG points to $tagged_sha, expected $TARGET_SHA" >&2
      exit 1
    fi
  else
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git tag -a "$TAG" "$TARGET_SHA" -m "Staging deployment $TAG

Workflow: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
  fi
  git push origin "refs/tags/$TAG"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RELEASE_BODY="$TMP/release-body.md"
ASSET_LIST="$TMP/assets.txt"

if gh release view "$TAG" --repo "$GITHUB_REPOSITORY" \
  --json body --template '{{.body}}' > "$RELEASE_BODY" 2>/dev/null; then
  cp "$RELEASE_BODY" "$NOTES_FILE"
else
  gh release create "$TAG" "$NOTES_FILE" \
    --repo "$GITHUB_REPOSITORY" --verify-tag \
    --title "$TAG" --notes-file "$NOTES_FILE"
fi

gh release view "$TAG" --repo "$GITHUB_REPOSITORY" \
  --json assets --jq '.assets[].name' > "$ASSET_LIST"
if grep -Fxq "$EXPECTED_ASSET" "$ASSET_LIST"; then
  DOWNLOAD_DIR="$TMP/download"
  mkdir -p "$DOWNLOAD_DIR"
  gh release download "$TAG" --repo "$GITHUB_REPOSITORY" \
    --pattern "$EXPECTED_ASSET" --dir "$DOWNLOAD_DIR"
  if ! cmp -s "$NOTES_FILE" "$DOWNLOAD_DIR/$EXPECTED_ASSET"; then
    echo "existing release asset $EXPECTED_ASSET differs from Release body" >&2
    exit 1
  fi
else
  gh release upload "$TAG" "$NOTES_FILE" --repo "$GITHUB_REPOSITORY"
fi

echo "published $TAG for $TARGET_SHA"
