#!/usr/bin/env bash
set -euo pipefail
demo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo_build="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-observation.XXXXXX")"
printf 'Retained build directory: %s\n' "$demo_build"
python3 "$demo_root/model.py"
flags=(-std=c++20 -O2 -g -Wall -Wextra -Wpedantic -Werror -pthread)
case "${1:-normal}" in
  normal) ;;
  tsan) flags+=(-fsanitize=thread -fno-omit-frame-pointer) ;;
  *) echo 'usage: bash run.sh [normal|tsan]' >&2; exit 2 ;;
esac
"${CXX:-c++}" "${flags[@]}" "$demo_root/test.cpp" -o "$demo_build/observation-test"
"$demo_build/observation-test"
