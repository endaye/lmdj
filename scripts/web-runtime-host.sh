#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
expected_build_root="$repo_root/build/web/host"
build_root="${LMDJ_WEB_HOST_BUILD_ROOT:-$expected_build_root}"
resolved_build_root="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$build_root")"
if [[ "$resolved_build_root" != "$expected_build_root" ]]; then
  echo "Web Runtime Host error: unsafe build root: $resolved_build_root" >&2
  exit 2
fi
cmake_root="$build_root/cmake"
runtime_root="$build_root/runtime"
dist_root="$build_root/dist"
identity_path="$repo_root/build/web/toolchain/toolchain-identity.json"
web_test_root="$repo_root/tests/platform/web"
proof_root=""

cleanup_proof_root() {
  if [[ -z "$proof_root" ]]; then
    return
  fi
  case "$proof_root" in
    "${TMPDIR:-/tmp}"/lmdj-web-host-proof.*)
      cmake -E remove_directory "$proof_root"
      ;;
    *)
      echo "Web Runtime Host error: unsafe proof cleanup path: $proof_root" >&2
      return 2
      ;;
  esac
}

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/web-runtime-host.sh configure
  scripts/web-runtime-host.sh build
  scripts/web-runtime-host.sh test
  scripts/web-runtime-host.sh proof
  scripts/web-runtime-host.sh serve [--port PORT]
  scripts/web-runtime-host.sh clean
EOF
}

activate_toolchain() {
  if [[ -z "${EMSDK:-}" && -f "$repo_root/build/toolchains/emsdk/emsdk_env.sh" ]]; then
    EMSDK="$repo_root/build/toolchains/emsdk"
    export EMSDK
  fi
  if [[ -z "${EMSDK:-}" || ! -f "$EMSDK/emsdk_env.sh" ]]; then
    echo "Web Runtime Host error: EMSDK is not configured" >&2
    exit 2
  fi
  export EMSDK_QUIET=1
  # shellcheck disable=SC1090
  source "$EMSDK/emsdk_env.sh" >/dev/null
  if [[ -n "${EMSDK_NODE:-}" ]]; then
    PATH="$(dirname "$EMSDK_NODE"):$PATH"
    export PATH
  fi
  for required_command in emcc emcmake cmake python3 node npm; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
      echo "Web Runtime Host error: missing command: $required_command" >&2
      exit 2
    fi
  done
  if [[ "$(node -p 'process.versions.node.split(".")[0]')" != "22" ]]; then
    echo "Web Runtime Host error: Node 22 is required, got $(node --version)" >&2
    exit 2
  fi
}

require_playwright() {
  if [[ ! -f "$web_test_root/node_modules/@playwright/test/package.json" ]]; then
    echo "Web Runtime Host error: run npm ci in tests/platform/web" >&2
    exit 2
  fi
  local installed
  installed="$(node -p "require('$web_test_root/node_modules/@playwright/test/package.json').version")"
  if [[ "$installed" != "1.62.1" ]]; then
    echo "Web Runtime Host error: Playwright 1.62.1 is required, got $installed" >&2
    exit 2
  fi
}

configure_host() {
  activate_toolchain
  python3 "$repo_root/tools/web-runtime/verify_emscripten.py"
  cmake -E make_directory "$runtime_root"
  emcmake cmake \
    -S "$repo_root" \
    -B "$cmake_root" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF \
    -DLMDJ_WEB_AUDIO_CONFORMANCE=OFF \
    -DLMDJ_WEB_AUDIO_OUTPUT_DIR="$runtime_root"
}

package_host() {
  python3 "$repo_root/apps/web-runtime-host/tools/package.py" \
    --repo-root "$repo_root" \
    --runtime-root "$runtime_root" \
    --identity "$identity_path" \
    --dist-root "$dist_root"
}

build_host() {
  activate_toolchain
  if [[ ! -f "$cmake_root/CMakeCache.txt" ]]; then
    configure_host
  else
    python3 "$repo_root/tools/web-runtime/verify_emscripten.py"
  fi
  cmake --build "$cmake_root" --target lmdj_web_runtime_host --parallel
  package_host
}

run_browser_gate() {
  local selected_dist="$1"
  local port="${LMDJ_WEB_HOST_PORT:-4175}"
  local log_path="$build_root/proof-server.log"
  require_playwright
  cmake -E make_directory "$repo_root/build/web/toolchain"
  python3 "$repo_root/apps/web-runtime-host/tools/server.py" \
    --root "$selected_dist" \
    --port "$port" >"$log_path" 2>&1 &
  local server_pid=$!
  local ready=0
  for _ in {1..100}; do
    if python3 -c \
      'import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=0.2).read()' \
      "http://127.0.0.1:$port/index.html" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
      break
    fi
    sleep 0.05
  done
  if [[ "$ready" != "1" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
    echo "Web Runtime Host error: proof server did not become ready" >&2
    sed -n '1,120p' "$log_path" >&2 || true
    exit 2
  fi
  local status=0
  LMDJ_WEB_HOST_BASE_URL="http://127.0.0.1:$port" \
    npm --prefix "$web_test_root" test -- \
      --project=chromium \
      host/web_runtime_host_manifest_gate.spec.mjs || status=$?
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  return "$status"
}

run_nonbrowser_tests() {
  activate_toolchain
  python3 "$repo_root/apps/web-runtime-host/test/package_test.py"
  python3 "$repo_root/apps/web-runtime-host/test/server_test.py"
  node --test "$repo_root"/apps/web-runtime-host/test/*.test.mjs
  "$repo_root/scripts/core.sh" configure dev
  "$repo_root/scripts/core.sh" build dev
  ctest \
    --test-dir "$repo_root/build/core/dev" \
    --output-on-failure \
    -R '^host\.web_(control_runtime|realtime_session|manifest_gate)$'
}

test_host() {
  if [[ ! -d "$dist_root" ]]; then
    echo "Web Runtime Host error: build the Host before testing" >&2
    exit 2
  fi
  run_nonbrowser_tests
  python3 "$repo_root/apps/web-runtime-host/test/distribution_test.py"
  run_browser_gate "$dist_root"
  echo "Web Runtime Host tests: PASS"
}

proof_host() {
  activate_toolchain
  require_playwright
  export npm_config_offline=true
  export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
  export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
  unset NODE_PATH || true
  unset PYTHONPATH || true
  clean_host
  configure_host
  build_host
  run_nonbrowser_tests
  proof_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-web-host-proof.XXXXXX")"
  trap cleanup_proof_root EXIT
  cmake -E copy_directory "$dist_root" "$proof_root/dist"
  LMDJ_WEB_HOST_DIST_ROOT="$proof_root/dist" \
    python3 "$repo_root/apps/web-runtime-host/test/distribution_test.py"
  run_browser_gate "$proof_root/dist"
  echo "Web Runtime Host Proof: PASS"
}

clean_host() {
  if [[ "$resolved_build_root" != "$expected_build_root" || -z "$resolved_build_root" ]]; then
    echo "Web Runtime Host error: unsafe clean path: $resolved_build_root" >&2
    exit 2
  fi
  cmake -E remove_directory "$resolved_build_root"
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
    [[ $# -eq 0 ]] || { usage; exit 64; }
    configure_host
    ;;
  build)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    build_host
    ;;
  test)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    test_host
    ;;
  proof)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    proof_host
    ;;
  serve)
    if [[ $# -ne 0 && ( $# -ne 2 || "$1" != "--port" ) ]]; then
      usage
      exit 64
    fi
    [[ -d "$dist_root" ]] || {
      echo "Web Runtime Host error: build the Host before serving" >&2
      exit 2
    }
    exec python3 "$repo_root/apps/web-runtime-host/tools/server.py" \
      --root "$dist_root" "$@"
    ;;
  clean)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    clean_host
    ;;
  *)
    echo "unknown Web Runtime Host command: $command_name" >&2
    usage
    exit 64
    ;;
esac
