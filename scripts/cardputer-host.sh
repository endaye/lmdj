#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
build_root="$repo_root/build/core/cardputer-host"

fail() {
  echo "why: $1; remedy: $2" >&2
  exit 2
}

usage() {
  echo 'usage: scripts/cardputer-host.sh configure|build' >&2
  echo '       scripts/cardputer-host.sh test [dev|asan|tsan]' >&2
  echo 'Activate the selected EIM-managed ESP-IDF v6.1 environment first.' >&2
  echo 'This builds the B1 Cardputer test Product Build; it does not flash or release it.' >&2
}

[[ $# -gt 0 ]] || { usage; exit 64; }
action="$1"
shift
case "$action" in
  test)
    [[ $# -le 1 ]] || { usage; exit 64; }
    preset="${1:-dev}"
    case "$preset" in
      dev|asan|tsan) ;;
      *) usage; exit 64 ;;
    esac
    cd "$repo_root"
    cmake --preset "$preset"
    cmake --build --preset "$preset" --target lmdj_cardputer_audio_lifecycle_tests
    ctest --preset "$preset" --output-on-failure --no-tests=error -R '^platform\.cardputer\.'
    ;;
  configure|build)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    [[ -n "${IDF_PATH:-}" && -f "$IDF_PATH/tools/idf.py" ]] ||
      fail 'ESP-IDF is not activated' 'activate the selected EIM-managed ESP-IDF v6.1 environment'
    [[ -n "${IDF_PYTHON_ENV_PATH:-}" && -x "$IDF_PYTHON_ENV_PATH/bin/python" ]] ||
      fail 'ESP-IDF Python environment is unavailable' 'activate or repair the environment through EIM'
    sdk_revision="$(git -C "$IDF_PATH" rev-parse HEAD)" ||
      fail 'cannot identify the SDK revision' 'repair the selected SDK through EIM'
    [[ "$sdk_revision" == fff9895c82d744c7237be8847347bdd1b07c6643 ]] ||
      fail 'SDK revision differs from the selected Cardputer toolchain' 'select the pinned EIM v6.1 installation; audit upgrades separately'
    # Never follow a redirected build tree into another workspace or source.
    resolved_build_root="$("$IDF_PYTHON_ENV_PATH/bin/python" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$build_root")"
    [[ "$resolved_build_root" == "$build_root" ]] ||
      fail 'build path is redirected' 'use a real build/core/cardputer-host directory in this worktree'
    cd "$repo_root"
    idf=("$IDF_PYTHON_ENV_PATH/bin/python" "$IDF_PATH/tools/idf.py"
      -C "$repo_root/apps/cardputer-host" -B "$build_root"
      -D "SDKCONFIG=$build_root/sdkconfig")
    # Reconfigure for both actions so a cached header cannot silently win.
    "${idf[@]}" reconfigure
    if [[ "$action" == build ]]; then
      "${idf[@]}" build
    fi
    ;;
  *) usage; exit 64 ;;
esac
