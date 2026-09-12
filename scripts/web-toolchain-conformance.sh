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
proof_server_pid=""
proof_server_ready_root=""
proof_server_base_url=""

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

run_cmake_build() {
  local build_directory="$1"
  shift
  local parallel_args=(--parallel)
  if [[ -n "${CMAKE_BUILD_PARALLEL_LEVEL:-}" ]]; then
    parallel_args+=("$CMAKE_BUILD_PARALLEL_LEVEL")
  fi
  cmake --build "$build_directory" "$@" "${parallel_args[@]}"
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
  run_cmake_build "$cmake_root"
}

build_project_io() {
  activate_toolchain
  if [[ ! -f "$project_io_cmake_root/CMakeCache.txt" ]]; then
    emcmake cmake \
      -S "$web_test_root/project_io" \
      -B "$project_io_cmake_root" \
      -DCMAKE_BUILD_TYPE=Release
  fi
  run_cmake_build "$project_io_cmake_root"
  local production_js="$project_io_root/project_io_web_production_link.js"
  if [[ ! -f "$production_js" ]]; then
    echo "web toolchain error: production Project I/O link output is missing" >&2
    exit 2
  fi
  if grep -Eq 'test-fault|LmdjOpfsTest|lmdj_opfs_(create_immutable|replace_complete|append_durable|publish_directory_if_absent)_test|(append_flush|immutable_write)_count|publication_max_chunk_bytes' "$production_js"; then
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
  run_cmake_build "$audio_runtime_cmake_root" \
    --target lmdj_web_runtime_host
  local expected_artifacts=(
    lmdj-web-runtime.html
    lmdj-web-runtime.js
    lmdj-web-runtime.wasm
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

cleanup_proof_server() {
  if [[ -n "$proof_server_pid" ]]; then
    kill "$proof_server_pid" 2>/dev/null || true
    wait "$proof_server_pid" 2>/dev/null || true
    proof_server_pid=""
  fi
  if [[ -n "$proof_server_ready_root" ]]; then
    rm -rf "$proof_server_ready_root"
    proof_server_ready_root=""
  fi
  proof_server_base_url=""
}

# The Proof owns the server its browsers drive. Port 0 makes the kernel hand
# this run a private ephemeral port, so two runner services on one host can
# never contend for a fixed one, and a server leaked by a crashed lane can
# neither be collided with nor silently answer this lane's requests: the port
# is read back from this child's own handshake file and the health response on
# it must identify this service.
start_proof_server() {
  local log_path="$build_root/toolchain-proof-server.log"
  local port_file
  local port=""
  cleanup_proof_server
  cmake -E make_directory "$build_root"
  proof_server_ready_root="$(
    mktemp -d "${TMPDIR:-/tmp}/lmdj-web-toolchain-server.XXXXXX"
  )"
  port_file="$proof_server_ready_root/port"
  python3 "$web_test_root/toolchain/server.py" \
    --root "$toolchain_root" \
    --port 0 \
    --write-port "$port_file" >"$log_path" 2>&1 &
  proof_server_pid=$!
  trap cleanup_proof_server EXIT
  for _ in {1..200}; do
    if [[ -s "$port_file" ]] && port="$(python3 - "$port_file" <<'PY'
import pathlib
import sys

try:
    encoded = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    value = int(encoded)
except (OSError, UnicodeDecodeError, ValueError):
    raise SystemExit(1)
if encoded != f"{value}\n" or value < 1 or value > 65_535:
    raise SystemExit(1)
print(value)
PY
    )"; then
      break
    fi
    kill -0 "$proof_server_pid" 2>/dev/null || break
    sleep 0.05
  done
  if [[ -z "$port" ]] || ! kill -0 "$proof_server_pid" 2>/dev/null; then
    echo "web toolchain error: proof server did not become ready" >&2
    sed -n '1,120p' "$log_path" >&2 || true
    return 2
  fi
  if ! python3 - "http://127.0.0.1:$port/health.json" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=0.5) as response:
    payload = json.load(response)
if payload != {"ok": True, "service": "web-toolchain-conformance"}:
    raise SystemExit(1)
PY
  then
    echo "web toolchain error: owned proof server is unreachable" >&2
    sed -n '1,120p' "$log_path" >&2 || true
    return 2
  fi
  proof_server_base_url="http://127.0.0.1:$port"
}

# Playwright clears outputDir at the start of every run, so each invocation
# needs its own results slot or the last one destroys every earlier trace.
run_proof_specs() {
  local slot="$1"
  shift
  LMDJ_WEB_RESULTS_SLOT="$slot" \
    LMDJ_WEB_HOST_EXTERNAL_SERVER=1 \
    LMDJ_WEB_HOST_BASE_URL="$proof_server_base_url" \
    npm --prefix "$web_test_root" test -- "$@"
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
    LMDJ_WEBKIT_OPFS_EXECUTABLE="$(node "$web_test_root/project_io/opfs_browser_environment.mjs")"
    export LMDJ_WEBKIT_OPFS_EXECUTABLE
    export npm_config_offline=true
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
    clean_fixture
    python3 "$web_test_root/toolchain/server_test.py"
    python3 "$web_test_root/toolchain/toolchain_identity_test.py"
    python3 "$web_test_root/project_io/project_io_web_timeout_policy_test.py"
    node --test "$web_test_root/project_io/opfs_writer_error_test.mjs"
    node --test "$web_test_root/project_io/opfs_browser_environment_test.mjs"
    configure_fixture
    build_fixture
    build_project_io
    build_audio_runtime
    python3 "$web_test_root/toolchain/toolchain_identity_test.py"
    start_proof_server
    run_proof_specs toolchain-chromium \
      --project=chromium \
      "$web_test_root/toolchain/toolchain_conformance.spec.mjs"
    run_proof_specs toolchain-webkit \
      --project=webkit \
      "$web_test_root/toolchain/toolchain_conformance.spec.mjs"
    run_proof_specs project-io-chromium \
      --project=chromium \
      "$web_test_root/project_io/project_io_web_conformance.spec.mjs"
    run_proof_specs project-io-webkit \
      --project=webkit \
      "$web_test_root/project_io/project_io_web_conformance.spec.mjs"
    run_proof_specs audio-chromium \
      --project=chromium \
      "$web_test_root/audio/realtime_audio_worklet.spec.mjs" \
      "$web_test_root/audio/realtime_failure.spec.mjs"
    cleanup_proof_server
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
