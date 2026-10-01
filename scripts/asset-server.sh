#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "${1:-check}" in
  check)
    python3 "$repo_root/tools/asset-server/kit.py" --check
    python3 "$repo_root/tools/asset-server/kit_test.py"
    node --test "$repo_root/tools/asset-server/worker.test.mjs"
    ;;
  deploy)
    "$0" check
    : "${LMDJ_WRANGLER:?Set LMDJ_WRANGLER to the installed pinned Wrangler executable}"
    "$LMDJ_WRANGLER" deploy --config "$repo_root/tools/asset-server/wrangler.json"
    ;;
  verify-live)
    python3 "$repo_root/tools/asset-server/kit_test.py" --live "${2:?Supply the deployed asset origin}"
    ;;
  *) echo "Usage: scripts/asset-server.sh [check|deploy|verify-live ORIGIN]" >&2; exit 64 ;;
esac
