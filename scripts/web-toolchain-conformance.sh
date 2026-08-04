#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
build_root="$repo_root/build/web"
toolchain_root="$build_root/toolchain"
cmake_root="$toolchain_root/cmake"
project_io_root="$toolchain_root/project_io"
project_io_cmake_root="$project_io_root/cmake"
formal_audio_root="$toolchain_root/formal-audio"
audio_runtime_root="$build_root/audio-runtime"
audio_runtime_cmake_root="$audio_runtime_root/cmake"
web_test_root="$repo_root/tests/platform/web"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/web-toolchain-conformance.sh configure
  scripts/web-toolchain-conformance.sh build
  scripts/web-toolchain-conformance.sh build-project-io
  scripts/web-toolchain-conformance.sh build-audio-runtime
  scripts/web-toolchain-conformance.sh serve [--port PORT]
  scripts/web-toolchain-conformance.sh proof
  scripts/web-toolchain-conformance.sh clean
EOF
}

activate_toolchain() {
  if [[ -z "${EMSDK:-}" && -f "$repo_root/build/toolchains/emsdk/emsdk_env.sh" ]]; then
    EMSDK="$repo_root/build/toolchains/emsdk"
    export EMSDK
  fi
  if [[ -z "${EMSDK:-}" ]]; then
    echo "web toolchain error: EMSDK is not set" >&2
    exit 2
  fi
  if [[ ! -f "$EMSDK/emsdk_env.sh" ]]; then
    echo "web toolchain error: missing EMSDK environment: $EMSDK/emsdk_env.sh" >&2
    exit 2
  fi
  export EMSDK_QUIET=1
  # shellcheck disable=SC1090
  source "$EMSDK/emsdk_env.sh" >/dev/null
  if [[ -n "${EMSDK_NODE:-}" ]]; then
    emsdk_node_dir="$(dirname "$EMSDK_NODE")"
    PATH="$emsdk_node_dir:$PATH"
    export PATH
  fi
  for required_command in emcc emcmake cmake python3 node npm; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
      echo "web toolchain error: missing command: $required_command" >&2
      exit 2
    fi
  done
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  if [[ "$node_major" != "22" ]]; then
    echo "web toolchain error: Node 22 is required, got $(node --version)" >&2
    exit 2
  fi
}

configure_fixture() {
  activate_toolchain
  python3 "$repo_root/tools/web-runtime/verify_emscripten.py"
  emcmake cmake \
    -S "$web_test_root/toolchain" \
    -B "$cmake_root" \
    -DCMAKE_BUILD_TYPE=Release
}

build_fixture() {
  activate_toolchain
  if [[ ! -f "$cmake_root/CMakeCache.txt" ]]; then
    configure_fixture
  fi
  cmake --build "$cmake_root" --parallel
}

build_project_io() {
  activate_toolchain
  if [[ ! -f "$project_io_cmake_root/CMakeCache.txt" ]]; then
    emcmake cmake \
      -S "$web_test_root/project_io" \
      -B "$project_io_cmake_root" \
      -DCMAKE_BUILD_TYPE=Release
  fi
  cmake --build "$project_io_cmake_root" --parallel
  local production_js="$project_io_root/project_io_web_production_link.js"
  if [[ ! -f "$production_js" ]]; then
    echo "web toolchain error: production Project I/O link output is missing" >&2
    exit 2
  fi
  if grep -Eq 'test-fault|LmdjOpfsTest|lmdj_opfs_(create_immutable|replace_complete|append_durable)_test|(append_flush|immutable_write)_count' "$production_js"; then
    echo "web toolchain error: production Project I/O link contains test hooks" >&2
    exit 2
  fi
}

build_audio_runtime() {
  activate_toolchain
  cmake -E remove_directory "$audio_runtime_root"
  cmake -E remove_directory "$formal_audio_root"
  emcmake cmake \
    -S "$repo_root" \
    -B "$audio_runtime_cmake_root" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF \
    -DLMDJ_WEB_AUDIO_CONFORMANCE=ON \
    -DLMDJ_WEB_AUDIO_OUTPUT_DIR="$formal_audio_root"
  cmake --build "$audio_runtime_cmake_root" \
    --target lmdj_web_runtime_host \
    --parallel
  local expected_artifacts=(
    lmdj-web-runtime-host.html
    lmdj-web-runtime-host.js
    lmdj-web-runtime-host.wasm
  )
  local actual_artifacts=()
  while IFS= read -r artifact; do
    actual_artifacts+=("$(basename "$artifact")")
  done < <(find "$formal_audio_root" -mindepth 1 -maxdepth 1 -print | sort)
  if [[ "${actual_artifacts[*]}" != "${expected_artifacts[*]}" ]]; then
    echo "web toolchain error: formal audio artifacts are not the exact three-file set" >&2
    printf '  %s\n' "${actual_artifacts[@]}" >&2
    exit 2
  fi
}

clean_fixture() {
  if [[ -z "$repo_root" || "$repo_root" == "/" ]]; then
    echo "web toolchain error: unsafe repository root" >&2
    exit 2
  fi
  if [[ "$build_root" != "$repo_root/build/web" ]]; then
    echo "web toolchain error: unexpected build path: $build_root" >&2
    exit 2
  fi
  cmake -E remove_directory "$build_root"
}

[[ $# -ge 1 ]] || {
  usage
  exit 64
}

command_name="$1"
shift
cd "$repo_root"

case "$command_name" in
  configure)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    configure_fixture
    ;;
  build)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    build_fixture
    ;;
  build-project-io)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    build_project_io
    ;;
  build-audio-runtime)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    build_audio_runtime
    ;;
  serve)
    if [[ $# -ne 0 && ( $# -ne 2 || "$1" != "--port" ) ]]; then
      usage
      exit 64
    fi
    if [[ ! -f "$toolchain_root/probe.html" ]]; then
      echo "web toolchain error: build the fixture before serving" >&2
      exit 2
    fi
    exec python3 "$web_test_root/toolchain/server.py" \
      --root "$toolchain_root" \
      "$@"
    ;;
  proof)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    activate_toolchain
    if [[ ! -f "$web_test_root/node_modules/@playwright/test/package.json" ]]; then
      echo "web toolchain error: run npm ci before proof" >&2
      exit 2
    fi
    installed_playwright="$(
      node -p \
        "require('$web_test_root/node_modules/@playwright/test/package.json').version"
    )"
    if [[ "$installed_playwright" != "1.62.1" ]]; then
      echo \
        "web toolchain error: Playwright 1.62.1 is required, got $installed_playwright" \
        >&2
      exit 2
    fi
    export npm_config_offline=true
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
    clean_fixture
    python3 "$web_test_root/toolchain/toolchain_identity_test.py"
    configure_fixture
    build_fixture
    build_project_io
    build_audio_runtime
    python3 "$web_test_root/toolchain/toolchain_identity_test.py"
    npm --prefix "$web_test_root" test -- \
      --project=chromium \
      "$web_test_root/toolchain/toolchain_conformance.spec.mjs"
    npm --prefix "$web_test_root" test -- \
      --project=webkit \
      "$web_test_root/toolchain/toolchain_conformance.spec.mjs"
    npm --prefix "$web_test_root" test -- \
      --project=chromium \
      "$web_test_root/project_io/project_io_web_conformance.spec.mjs"
    npm --prefix "$web_test_root" test -- \
      --project=webkit \
      "$web_test_root/project_io/project_io_web_conformance.spec.mjs"
    npm --prefix "$web_test_root" test -- \
      --project=chromium \
      "$web_test_root/audio/realtime_audio_worklet.spec.mjs"
    echo "Web Toolchain Conformance Proof: PASS"
    ;;
  clean)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    clean_fixture
    ;;
  *)
    echo "unknown Web toolchain command: $command_name" >&2
    usage
    exit 64
    ;;
esac
