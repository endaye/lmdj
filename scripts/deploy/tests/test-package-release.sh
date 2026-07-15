#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/package-release.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

REPO="$TMP/repo"
mkdir -p "$REPO/apps/web/dist"
git -C "$REPO" init -q
git -C "$REPO" config user.name test
git -C "$REPO" config user.email test@example.com
printf 'tracked\n' > "$REPO/tracked.txt"
git -C "$REPO" add tracked.txt
git -C "$REPO" commit -qm init
SHA="$(git -C "$REPO" rev-parse HEAD)"
printf '<!doctype html>\n' > "$REPO/apps/web/dist/index.html"

ARCHIVE="$TMP/release.tar.gz"
LMDJ_ROOT="$REPO" "$PACKAGE_SCRIPT" "$SHA" "$ARCHIVE"

mkdir "$TMP/unpacked"
tar -xzf "$ARCHIVE" -C "$TMP/unpacked"
test "$(cat "$TMP/unpacked/REVISION")" = "$SHA"
test "$(cat "$TMP/unpacked/tracked.txt")" = "tracked"
test "$(cat "$TMP/unpacked/apps/web/dist/index.html")" = "<!doctype html>"

if LMDJ_ROOT="$REPO" "$PACKAGE_SCRIPT" not-a-sha "$TMP/bad.tar.gz" 2>/dev/null; then
  echo "invalid SHA unexpectedly succeeded" >&2
  exit 1
fi

echo "package-release tests passed"
