#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
build_root="$repo_root/build/web"
toolchain_root="$build_root/toolchain"
cmake_root="$toolchain_root/cmake"
web_test_root="$repo_root/tests/platform/web"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/web-toolchain-conformance.sh configure
  scripts/web-toolchain-conformance.sh build
  scripts/web-toolchain-conformance.sh serve [--port PORT]
  scripts/web-toolchain-conformance.sh proof
  scripts/web-toolchain-conformance.sh clean
EOF
}

activate_toolchain() {
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
    python3 "$web_test_root/toolchain/toolchain_identity_test.py"
    npm --prefix "$web_test_root" test -- \
      --project=chromium \
      "$web_test_root/toolchain/toolchain_conformance.spec.mjs"
    npm --prefix "$web_test_root" test -- \
      --project=webkit \
      "$web_test_root/toolchain/toolchain_conformance.spec.mjs"
    product_status="$(git status --short --untracked-files=all -- apps packages products)"
    if [[ -n "$product_status" ]]; then
      echo "web toolchain error: Product source changed during Task 0" >&2
      echo "$product_status" >&2
      exit 2
    fi
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
