#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--with-deps" ) ]]; then
  echo 'usage: bash scripts/prepare-opfs-webkit.sh [--with-deps]' >&2
  exit 64
fi
installer="$repo_root/tests/platform/web/opfs-browser"
# Never mutate the pinned test client's dependencies or shared browser cache.
npm --prefix "$installer" ci --ignore-scripts --no-audit --no-fund
PLAYWRIGHT_BROWSERS_PATH="$repo_root/build/toolchains/opfs-webkit" \
  node "$installer/node_modules/playwright/cli.js" install webkit "$@"
node "$repo_root/tests/platform/web/project_io/opfs_browser_environment.mjs"
