#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_root="$repo_root/build/core"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/core.sh configure [dev|release|asan]
  scripts/core.sh build [dev|release|asan]
  scripts/core.sh test [dev|release|asan]
  scripts/core.sh proof
  scripts/core.sh clean
EOF
}

require_preset() {
  case "$1" in
    dev|release|asan)
      ;;
    *)
      echo "unsupported Core preset: $1" >&2
      usage
      exit 64
      ;;
  esac
}

if [[ $# -lt 1 ]]; then
  usage
  exit 64
fi

command_name="$1"
shift

cd "$repo_root"

case "$command_name" in
  configure)
    [[ $# -eq 1 ]] || {
      usage
      exit 64
    }
    require_preset "$1"
    cmake --preset "$1"
    ;;
  build)
    [[ $# -eq 1 ]] || {
      usage
      exit 64
    }
    require_preset "$1"
    cmake --build --preset "$1"
    ;;
  test)
    [[ $# -eq 1 ]] || {
      usage
      exit 64
    }
    require_preset "$1"
    ctest --preset "$1"
    ;;
  proof)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    echo "Headless Core Proof is unavailable before Product Assembly." >&2
    exit 2
    ;;
  clean)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    if [[ -z "$repo_root" || "$repo_root" == "/" ]]; then
      echo "refusing to clean from an unsafe repository root" >&2
      exit 2
    fi
    if [[ "$build_root" != "$repo_root/build/core" ]]; then
      echo "refusing to clean an unexpected build path: $build_root" >&2
      exit 2
    fi
    cmake -E remove_directory "$build_root"
    ;;
  *)
    echo "unknown Core command: $command_name" >&2
    usage
    exit 64
    ;;
esac
