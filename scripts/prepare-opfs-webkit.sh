#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--with-deps" ) ]]; then
  echo 'usage: bash scripts/prepare-opfs-webkit.sh [--with-deps]' >&2
  exit 64
fi
installer="$repo_root/tests/platform/web/opfs-browser"
workspace_browsers="$repo_root/build/toolchains/opfs-webkit"
# Never mutate the pinned test client's dependencies or shared browser cache.
npm --prefix "$installer" ci --ignore-scripts --no-audit --no-fund

if [[ -n "${LMDJ_BROWSER_CACHE_ROOT:-}" ]]; then
  # A self-hosted runner keeps this browser across jobs instead of downloading
  # about 100 MB into a workspace that checkout cleans (#2279). It gets its own
  # versioned directory beside the shared test-client cache, never inside it,
  # and the workspace path the consumers read becomes a link to it.
  version="$(node -p "require('$installer/node_modules/playwright/package.json').version")"
  cache_target="$LMDJ_BROWSER_CACHE_ROOT/opfs-webkit-$version"
  lock_file="$LMDJ_BROWSER_CACHE_ROOT/.install-opfs-webkit-$version.lock"
  mkdir -p "$cache_target"
  (umask 0007; touch "$lock_file")
  exec 9>"$lock_file"
  flock 9
  PLAYWRIGHT_BROWSERS_PATH="$cache_target" \
    node "$installer/node_modules/playwright/cli.js" install webkit "$@"
  flock -u 9
  mkdir -p "$(dirname "$workspace_browsers")"
  if [[ -e "$workspace_browsers" && ! -L "$workspace_browsers" ]]; then
    rm -rf -- "$workspace_browsers"
  fi
  ln -sfn "$cache_target" "$workspace_browsers"
else
  PLAYWRIGHT_BROWSERS_PATH="$workspace_browsers" \
    node "$installer/node_modules/playwright/cli.js" install webkit "$@"
fi
node "$repo_root/tests/platform/web/project_io/opfs_browser_environment.mjs"
