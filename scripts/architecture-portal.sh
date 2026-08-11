#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
portal_root="$repo_root/apps/architecture-portal"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/architecture-portal.sh install
  scripts/architecture-portal.sh dev
  scripts/architecture-portal.sh build
  scripts/architecture-portal.sh check
  scripts/architecture-portal.sh version PRODUCT_BUILD [CHANNEL]
  scripts/architecture-portal.sh witness PRODUCT_BUILD INTRODUCING_REVISION
  scripts/architecture-portal.sh smoke BASE_URL
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 64
fi

command_name="$1"
shift
cd "$portal_root"

case "$command_name" in
  install)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    exec npm ci
    ;;
  dev)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    exec npm run start
    ;;
  build)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    exec npm run build
    ;;
  check)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    exec npm run check
    ;;
  version)
    [[ $# -ge 1 && $# -le 2 ]] || { usage; exit 64; }
    exec node scripts/version-docs.mjs "$@"
    ;;
  witness)
    [[ $# -eq 2 ]] || { usage; exit 64; }
    exec node scripts/create-squash-witness.mjs "$@"
    ;;
  smoke)
    [[ $# -eq 1 ]] || { usage; exit 64; }
    exec node scripts/smoke.mjs "$1"
    ;;
  *)
    usage
    exit 64
    ;;
esac
