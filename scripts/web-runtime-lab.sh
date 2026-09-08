#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
lab_root="$repo_root/demos/web-runtime-lab"

usage() {
  cat <<'EOF'
usage:
  scripts/web-runtime-lab.sh test
  scripts/web-runtime-lab.sh evaluate EVIDENCE.json
  scripts/web-runtime-lab.sh prepare ROW_KEY REPORT.json \
    --os-version VERSION \
    --browser-version VERSION
  scripts/web-runtime-lab.sh serve [--port PORT]
  scripts/web-runtime-lab.sh serve-lan \
    --bind ADDRESS \
    --cert-file CERTIFICATE \
    --key-file PRIVATE_KEY \
    [--port PORT]
EOF
}

has_option() {
  local expected="$1"
  shift
  local argument
  for argument in "$@"; do
    if [[ "$argument" == "$expected" || "$argument" == "$expected="* ]]; then
      return 0
    fi
  done
  return 1
}

[[ $# -ge 1 ]] || {
  usage
  exit 64
}

command_name="$1"
shift

cd "$repo_root"

case "$command_name" in
  test)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    npm --prefix "$lab_root" test
    python3 "$lab_root/test/server_test.py"
    if [[ -f "$lab_root/test/active_tree_test.py" ]]; then
      python3 "$lab_root/test/active_tree_test.py"
    fi
    ;;
  evaluate)
    [[ $# -eq 1 ]] || {
      usage
      exit 64
    }
    node "$lab_root/src/evaluate-physical-evidence.mjs" "$1"
    ;;
  prepare)
    node "$lab_root/src/prepare-physical-evidence.mjs" "$@"
    ;;
  serve)
    python3 "$lab_root/server.py" --bind 127.0.0.1 "$@"
    ;;
  serve-lan)
    for required in --bind --cert-file --key-file; do
      if ! has_option "$required" "$@"; then
        echo "web runtime lab error: serve-lan requires $required" >&2
        exit 64
      fi
    done
    python3 "$lab_root/server.py" "$@"
    ;;
  *)
    echo "unknown Web Runtime Lab command: $command_name" >&2
    usage
    exit 64
    ;;
esac
