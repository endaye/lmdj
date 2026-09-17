#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
portal_root="$repo_root/apps/docs-site"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/docs-site.sh install
  scripts/docs-site.sh dev
  scripts/docs-site.sh build
  scripts/docs-site.sh check
  scripts/docs-site.sh version PRODUCT_BUILD [CHANNEL]
  scripts/docs-site.sh resume-version PRODUCT_BUILD CHANNEL SOURCE_SHA
  scripts/docs-site.sh witness PRODUCT_BUILD [INTRODUCING_REVISION]
  scripts/docs-site.sh verify-witness PRODUCT_BUILD INTRODUCING_REVISION
  scripts/docs-site.sh smoke BASE_URL
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
    [[ $# -ge 1 && $# -le 2 ]] || { usage; exit 64; }
    exec node scripts/create-squash-witness.mjs "$@"
    ;;
  verify-witness)
    [[ $# -eq 2 ]] || { usage; exit 64; }
    exec node scripts/verify-squash-witness.mjs "$@"
    ;;
  resume-version)
    [[ $# -eq 3 ]] || { usage; exit 64; }
    exec node scripts/resume-version.mjs "$@"
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
