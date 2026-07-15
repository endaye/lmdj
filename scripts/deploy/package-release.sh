#!/usr/bin/env bash
set -euo pipefail

ROOT="${LMDJ_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SHA="${1:-}"
OUTPUT="${2:-}"

if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: package-release.sh FULL_SHA OUTPUT_TAR" >&2
  exit 2
fi
if [ -z "$OUTPUT" ]; then
  echo "usage: package-release.sh FULL_SHA OUTPUT_TAR" >&2
  exit 2
fi
git -C "$ROOT" cat-file -e "${SHA}^{commit}"
test -f "$ROOT/apps/web/dist/index.html" || {
  echo "apps/web/dist/index.html is missing; build the web app first" >&2
  exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$ROOT" archive "$SHA" | tar -x -C "$TMP"
mkdir -p "$TMP/apps/web"
cp -R "$ROOT/apps/web/dist" "$TMP/apps/web/dist"
printf '%s\n' "$SHA" > "$TMP/REVISION"
mkdir -p "$(dirname "$OUTPUT")"
tar -C "$TMP" -czf "$OUTPUT" .
