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
fixture_source_root="$repo_root/tests/fixtures/audio"
proof_root=""
proof_server_pid=""
proof_server_ready_root=""

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

cleanup_proof_server() {
  if [[ -n "$proof_server_pid" ]]; then
    kill "$proof_server_pid" 2>/dev/null || true
    wait "$proof_server_pid" 2>/dev/null || true
    proof_server_pid=""
  fi
  if [[ -n "$proof_server_ready_root" ]]; then
    case "$proof_server_ready_root" in
      "${TMPDIR:-/tmp}"/lmdj-web-host-server.*)
        cmake -E remove_directory "$proof_server_ready_root"
        ;;
      *)
        echo "Web Runtime Host error: unsafe server cleanup path: $proof_server_ready_root" >&2
        return 2
        ;;
    esac
    proof_server_ready_root=""
  fi
}

cleanup_all() {
  local status=$?
  cleanup_proof_server || true
  cleanup_proof_root || true
  return "$status"
}

trap cleanup_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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

run_cmake_build() {
  local build_directory="$1"
  shift
  local parallel_args=(--parallel)
  if [[ -n "${CMAKE_BUILD_PARALLEL_LEVEL:-}" ]]; then
    parallel_args+=("$CMAKE_BUILD_PARALLEL_LEVEL")
  fi
  cmake --build "$build_directory" "$@" "${parallel_args[@]}"
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

verify_clean_room_playwright_config() {
  local selected_base_url="$1"
  LMDJ_WEB_HOST_CLEAN_ROOM=1 \
    LMDJ_WEB_HOST_BASE_URL="$selected_base_url" \
    node --input-type=module - \
      "$web_test_root/playwright.config.mjs" \
      "$repo_root" \
      "$selected_base_url" <<'JS'
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const configPath = process.argv[2];
const repoRoot = process.argv[3];
const expectedBaseURL = process.argv[4];
const config = (await import(
  `${pathToFileURL(configPath).href}?clean-room=${crypto.randomUUID()}`
)).default;
assert.equal(config.webServer, undefined);
assert.equal(config.use.baseURL, expectedBaseURL);
const serialized = JSON.stringify(config);
for (const forbidden of [
  `${repoRoot}/tests/platform/web/toolchain/server.py`,
  `${repoRoot}/build/web/toolchain`,
]) {
  assert.equal(serialized.includes(forbidden), false, forbidden);
}
JS
  echo "Web Runtime Host clean-room Playwright config: PASS"
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
  run_cmake_build "$cmake_root" --target lmdj_web_runtime_host
  package_host
}

run_browser_gate() {
  local selected_dist="$1"
  local selected_fixture_root="${2:-$fixture_source_root}"
  local clean_room_mode="${3:-0}"
  local requested_port="${LMDJ_WEB_HOST_PORT:-0}"
  local log_path="$build_root/proof-server.log"
  local ready_file
  local ready_nonce
  local port=""
  local formal_host_specs=()
  local tracked_spec
  while IFS= read -r tracked_spec; do
    formal_host_specs+=("${tracked_spec#tests/platform/web/}")
  done < <(
    git -C "$repo_root" ls-files 'tests/platform/web/host/web_runtime_host_*.spec.mjs'
  )
  if [[ ${#formal_host_specs[@]} -eq 0 ]]; then
    echo "Web Runtime Host error: no tracked Formal Host specs" >&2
    return 2
  fi
  require_playwright
  verify_clean_room_playwright_config "http://127.0.0.1:9"
  cleanup_proof_server
  proof_server_ready_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-web-host-server.XXXXXX")"
  ready_file="$proof_server_ready_root/ready.json"
  ready_nonce="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  python3 "$repo_root/apps/web-runtime-host/tools/server.py" \
    --root "$selected_dist" \
    --port "$requested_port" \
    --ready-file "$ready_file" \
    --ready-nonce "$ready_nonce" >"$log_path" 2>&1 &
  proof_server_pid=$!
  for _ in {1..100}; do
    if ! kill -0 "$proof_server_pid" 2>/dev/null; then
      break
    fi
    if [[ -f "$ready_file" ]] && port="$(python3 - "$ready_file" "$proof_server_pid" "$ready_nonce" <<'PY'
import json
import pathlib
import sys

try:
    value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit(1)
if (
    set(value) != {"host", "nonce", "pid", "port"}
    or value["host"] != "127.0.0.1"
    or value["nonce"] != sys.argv[3]
    or value["pid"] != int(sys.argv[2])
    or type(value["port"]) is not int
    or value["port"] < 1
    or value["port"] > 65_535
):
    raise SystemExit(1)
print(value["port"])
PY
)"; then
      break
    fi
    sleep 0.05
  done
  if [[ -z "$port" ]] || ! kill -0 "$proof_server_pid" 2>/dev/null; then
    cleanup_proof_server
    echo "Web Runtime Host error: proof server did not become ready" >&2
    sed -n '1,120p' "$log_path" >&2 || true
    return 2
  fi
  if ! python3 -c \
    'import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=0.5).read()' \
    "http://127.0.0.1:$port/index.html" >/dev/null 2>&1; then
    cleanup_proof_server
    echo "Web Runtime Host error: owned proof server is unreachable" >&2
    return 2
  fi
  local status=0
  LMDJ_WEB_HOST_FULL_CHROMIUM=1 \
    LMDJ_WEB_HOST_CLEAN_ROOM="$clean_room_mode" \
    LMDJ_WEB_HOST_EXTERNAL_SERVER=1 \
    LMDJ_WEB_HOST_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_WEB_HOST_FIXTURE_ROOT="$selected_fixture_root" \
    npm --prefix "$web_test_root" test -- \
      --project=chromium \
      "${formal_host_specs[@]}" || status=$?
  LMDJ_WEB_HOST_CLEAN_ROOM="$clean_room_mode" \
    LMDJ_WEB_HOST_EXTERNAL_SERVER=1 \
    LMDJ_WEB_HOST_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_WEB_HOST_FIXTURE_ROOT="$selected_fixture_root" \
    npm --prefix "$web_test_root" test -- \
      --project=webkit \
      host/web_runtime_host_browser.spec.mjs || status=$?
  cleanup_proof_server
  return "$status"
}

run_nonbrowser_tests() {
  activate_toolchain
  python3 "$repo_root/apps/web-runtime-host/test/package_test.py"
  python3 "$repo_root/apps/web-runtime-host/test/release_bundle_test.py"
  python3 "$repo_root/apps/web-runtime-host/test/netlify_api_test.py"
  python3 "$repo_root/apps/web-runtime-host/test/deployment_smoke_test.py"
  python3 "$repo_root/apps/web-runtime-host/test/server_test.py"
  node --test "$repo_root"/apps/web-runtime-host/test/*.test.mjs
  "$repo_root/scripts/core.sh" configure dev
  "$repo_root/scripts/core.sh" build dev
  ctest \
    --test-dir "$repo_root/build/core/dev" \
    --output-on-failure \
    -R '^host\.web_(control_runtime|realtime_session|manifest_gate)$'
}

generate_browser_fixtures() {
  python3 "$repo_root/tests/fixtures/audio/make_fixtures.py"
  echo "Web Runtime Host browser fixtures: PASS"
}

verify_browser_fixture_generator() {
  python3 - "$repo_root/tests/fixtures/audio/make_fixtures.py" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

generator = Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix="lmdj-web-fixture-generator-") as root:
    test_root = Path(root)
    header = test_root / "realtime_engine.hpp"
    output = test_root / "fixtures"
    header.write_text(
        """#pragma once
#include <cstddef>
namespace lmdj::audio {
inline constexpr std::size_t kRealtimeQueueCapacity = (1u << 10);
inline constexpr std::size_t kRealtimeTriggerOutcomeCapacity = 2u * 2'048u;
inline constexpr std::size_t kRealtimeVoiceCapacity = 256u / 2u;
}
""",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["LMDJ_REALTIME_CAPACITY_HEADER"] = str(header)
    environment["LMDJ_AUDIO_FIXTURE_OUTPUT_DIRECTORY"] = str(output)
    completed = subprocess.run(
        [sys.executable, str(generator)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "pre-build fixture generator failed:\n"
            + completed.stdout
            + completed.stderr
        )
    metadata = json.loads(
        (output / "web-runtime-host-fixture.json").read_text(encoding="utf-8")
    )
    capacities = metadata["trigger_proof"]["capacities"]
    if capacities != {"queue": 1024, "trigger_outcome": 4096, "voice": 128}:
        raise SystemExit(f"compiler-evaluated capacities are invalid: {capacities!r}")
PY
  echo "Web Runtime Host fixture generator pre-build regression: PASS"
}

verify_proof_fixture_inventory() {
  local selected_fixture_root="$1"
  python3 - "$selected_fixture_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
actual = sorted(
    path.relative_to(root).as_posix()
    for path in root.rglob("*")
    if path.is_file()
)
expected = ["web-runtime-host-fixture.json", "web-runtime-host-short.wav"]
if actual != expected:
    raise SystemExit(
        f"clean-room fixture inventory mismatch: expected={expected!r} actual={actual!r}"
    )
PY
  echo "Web Runtime Host clean-room fixture inventory: PASS"
}

run_audio_worklet_conformance() {
  "$repo_root/scripts/web-toolchain-conformance.sh" build-audio-runtime
  npm --prefix "$web_test_root" test -- \
    --project=chromium \
    audio/realtime_audio_worklet.spec.mjs \
    audio/realtime_failure.spec.mjs
  echo "Web Runtime Host stable AudioWorklet and failure conformance: PASS"
}

test_host() {
  if [[ ! -d "$dist_root" ]]; then
    echo "Web Runtime Host error: build the Host before testing" >&2
    exit 2
  fi
  run_nonbrowser_tests
  python3 "$repo_root/apps/web-runtime-host/test/distribution_test.py"
  generate_browser_fixtures
  run_browser_gate "$dist_root" "$fixture_source_root"
  echo "Web Runtime Host tests: PASS"
}

proof_host() {
  activate_toolchain
  require_playwright
  verify_browser_fixture_generator
  export npm_config_offline=true
  export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
  export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
  unset NODE_PATH || true
  unset PYTHONPATH || true
  run_audio_worklet_conformance
  proof_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-web-host-proof.XXXXXX")"
  clean_host
  configure_host
  build_host
  cmake -E copy_directory "$dist_root" "$proof_root/first-dist"
  clean_host
  configure_host
  build_host
  if ! diff -qr "$proof_root/first-dist" "$dist_root"; then
    echo "Web Runtime Host error: two clean builds are not byte reproducible" >&2
    return 2
  fi
  echo "Web Runtime Host reproducibility: PASS"
  run_nonbrowser_tests
  cmake -E copy_directory "$dist_root" "$proof_root/dist"
  LMDJ_WEB_HOST_DIST_ROOT="$proof_root/dist" \
    python3 "$repo_root/apps/web-runtime-host/test/distribution_test.py"
  generate_browser_fixtures
  cmake -E make_directory "$proof_root/fixtures"
  cmake -E copy \
    "$fixture_source_root/web-runtime-host-short.wav" \
    "$fixture_source_root/web-runtime-host-fixture.json" \
    "$proof_root/fixtures"
  verify_proof_fixture_inventory "$proof_root/fixtures"
  run_browser_gate "$proof_root/dist" "$proof_root/fixtures" 1
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
