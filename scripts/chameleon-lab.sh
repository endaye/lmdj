#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
lab_root="$repo_root/demos/chameleon-lab"

usage() {
  cat <<'EOF'
usage:
  scripts/chameleon-lab.sh test
  scripts/chameleon-lab.sh serve [--port PORT]
EOF
}

[[ $# -ge 1 ]] || {
  usage
  exit 64
}

command_name="$1"
shift

case "$command_name" in
  test)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    npm --prefix "$lab_root" test
    python3 "$lab_root/test/server_test.py"
    ;;
  serve)
    port=4175
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --port)
          [[ $# -ge 2 ]] || {
            usage
            exit 64
          }
          port="$2"
          shift 2
          ;;
        --port=*)
          port="${1#--port=}"
          shift
          ;;
        *)
          usage
          exit 64
          ;;
      esac
    done
    exec python3 "$lab_root/server.py" --port "$port"
    ;;
  *)
    usage
    exit 64
    ;;
esac
