#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
expected_build_root="$repo_root/build/web/creator"
build_root="${LMDJ_CREATOR_WEB_BUILD_ROOT:-$expected_build_root}"
resolved_build_root="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$build_root")"
if [[ "$resolved_build_root" != "$expected_build_root" ]]; then
  echo "Creator Web error: unsafe build root: $resolved_build_root" >&2
  exit 2
fi

cmake_root="$build_root/cmake"
runtime_root="$build_root/runtime"
ui_root="$build_root/ui"
dist_root="$build_root/dist"
identity_path="$repo_root/build/web/toolchain/toolchain-identity.json"
creator_root="$repo_root/apps/creator-web"
web_test_root="$repo_root/tests/platform/web"
required_sample_editor_spec="$repo_root/tests/platform/web/creator/creator_web_sample_editor.spec.mjs"
required_capture_spec="$repo_root/tests/platform/web/creator/creator_web_capture.spec.mjs"
proof_root=""
proof_server_pid=""
proof_server_ready_root=""

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/creator-web.sh configure
  scripts/creator-web.sh build
  scripts/creator-web.sh test
  scripts/creator-web.sh proof
  scripts/creator-web.sh package
  scripts/creator-web.sh serve [--port PORT]
  scripts/creator-web.sh clean
EOF
}

cleanup_server() {
  if [[ -n "$proof_server_pid" ]]; then
    kill "$proof_server_pid" 2>/dev/null || true
    wait "$proof_server_pid" 2>/dev/null || true
    proof_server_pid=""
  fi
  if [[ -n "$proof_server_ready_root" ]]; then
    case "$proof_server_ready_root" in
      "${TMPDIR:-/tmp}"/lmdj-creator-server.*)
        cmake -E remove_directory "$proof_server_ready_root"
        ;;
      *)
        echo "Creator Web error: unsafe server cleanup: $proof_server_ready_root" >&2
        return 2
        ;;
    esac
    proof_server_ready_root=""
  fi
}

cleanup_proof() {
  cleanup_server || true
  if [[ -n "$proof_root" ]]; then
    case "$proof_root" in
      "${TMPDIR:-/tmp}"/lmdj-creator-proof.*)
        cmake -E remove_directory "$proof_root"
        ;;
      *)
        echo "Creator Web error: unsafe proof cleanup: $proof_root" >&2
        return 2
        ;;
    esac
    proof_root=""
  fi
}

trap cleanup_proof EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

activate_toolchain() {
  if [[ -z "${EMSDK:-}" && -f "$repo_root/build/toolchains/emsdk/emsdk_env.sh" ]]; then
    EMSDK="$repo_root/build/toolchains/emsdk"
    export EMSDK
  fi
  if [[ -z "${EMSDK:-}" || ! -f "$EMSDK/emsdk_env.sh" ]]; then
    echo "Creator Web error: EMSDK is not configured" >&2
    exit 2
  fi
  export EMSDK_QUIET=1
  # shellcheck disable=SC1090
  source "$EMSDK/emsdk_env.sh" >/dev/null
  if ! command -v node >/dev/null 2>&1 && [[ -n "${EMSDK_NODE:-}" ]]; then
    PATH="$(dirname "$EMSDK_NODE"):$PATH"
    export PATH
  fi
  for command in cmake emcc emcmake node npm python3; do
    command -v "$command" >/dev/null 2>&1 || {
      echo "Creator Web error: missing command: $command" >&2
      exit 2
    }
  done
  if [[ "$(node -p 'process.versions.node.split(".")[0]')" != "26" ]]; then
    echo "Creator Web error: Node 26 is required, got $(node --version)" >&2
    exit 2
  fi
}

require_dependencies() {
  [[ -f "$creator_root/package-lock.json" ]] || {
    echo "Creator Web error: Creator lockfile is missing" >&2
    exit 2
  }
  [[ -f "$creator_root/node_modules/vite/package.json" ]] || {
    echo "Creator Web error: run npm ci in apps/creator-web" >&2
    exit 2
  }
  [[ -f "$web_test_root/node_modules/@playwright/test/package.json" ]] || {
    echo "Creator Web error: run npm ci in tests/platform/web" >&2
    exit 2
  }
  local playwright_version
  playwright_version="$(node -p "require('$web_test_root/node_modules/@playwright/test/package.json').version")"
  if [[ "$playwright_version" != "1.62.1" ]]; then
    echo "Creator Web error: Playwright 1.62.1 is required, got $playwright_version" >&2
    exit 2
  fi
  npm --prefix "$creator_root" ls --depth=0 >/dev/null
}

run_cmake_build() {
  local parallel_args=(--parallel)
  if [[ -n "${CMAKE_BUILD_PARALLEL_LEVEL:-}" ]]; then
    parallel_args+=("$CMAKE_BUILD_PARALLEL_LEVEL")
  fi
  cmake --build "$cmake_root" --target lmdj_web_runtime_host "${parallel_args[@]}"
}

configure_creator() {
  activate_toolchain
  require_dependencies
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

build_creator() {
  activate_toolchain
  require_dependencies
  if [[ ! -f "$cmake_root/CMakeCache.txt" ]]; then
    configure_creator
  else
    python3 "$repo_root/tools/web-runtime/verify_emscripten.py"
  fi
  run_cmake_build
  npm --prefix "$creator_root" run build -- \
    --outDir "$ui_root" --emptyOutDir
}

package_creator() {
  [[ -f "$ui_root/index.html" && -f "$runtime_root/lmdj-web-runtime.js" ]] || {
    echo "Creator Web error: build Creator before packaging" >&2
    exit 2
  }
  python3 "$creator_root/tools/package.py" \
    --repo-root "$repo_root" \
    --ui-root "$ui_root" \
    --runtime-root "$runtime_root" \
    --identity "$identity_path" \
    --dist-root "$dist_root"
}

test_creator() {
  activate_toolchain
  require_dependencies
  npm --prefix "$creator_root" test -- --run
  python3 "$creator_root/test/package_test.py"
  python3 "$creator_root/test/server_test.py"
  python3 "$creator_root/test/deployment_smoke_test.py"
  # The Creator packager is one of the two producers the manifest asset-role
  # parity gate compares against the shared vocabulary, so the Creator lane
  # runs it too: a Creator-only change selects this lane and not the Runtime
  # Host lane.
  python3 "$repo_root/apps/web-runtime-host/test/manifest_asset_role_parity_test.py"
  node --test "$repo_root"/packages/web-runtime-platform/test/*.test.mjs
  echo "Creator Web tests: PASS"
}

clean_creator() {
  if [[ "$resolved_build_root" != "$expected_build_root" || -z "$resolved_build_root" ]]; then
    echo "Creator Web error: unsafe clean path: $resolved_build_root" >&2
    exit 2
  fi
  cmake -E remove_directory "$resolved_build_root"
}

generate_project_fixture() {
  local output="$1"
  "$repo_root/scripts/core.sh" configure dev
  "$repo_root/scripts/core.sh" build dev
  python3 - \
    "$repo_root/build/core/dev/bin/lmdj-core" \
    "$repo_root/products/lmdj/assembly.json" \
    "$repo_root/tests/fixtures/audio/kick.wav" \
    "$proof_root" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

executable, assembly, audio, root = map(Path, sys.argv[1:])
workspace = root / "workspace"
project = root / "creator-proof.lmdj"
workspace.mkdir()
project_id = "00000000-0000-4000-8000-000000000001"
asset_id = "00000000-0000-4000-8000-000000000101"
pattern_id = "00000000-0000-4000-8000-000000000010"

def invoke(surface, request, revision):
    completed = subprocess.run(
        [str(executable), "--workspace", str(workspace), "--assembly",
         str(assembly), surface, "--request",
         json.dumps(request, sort_keys=True, separators=(",", ":"))],
        check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0 or completed.stderr:
        raise SystemExit(completed.stderr or completed.stdout)
    response = json.loads(completed.stdout)
    if response.get("ok") is not True or response.get("project_revision") != revision:
        raise SystemExit(f"Core fixture request failed: {response!r}")

invoke("command", {
    "operation": "project.create", "project_path": str(project),
    "project_id": project_id, "bpm": 120,
}, 0)
invoke("command", {
    "operation": "asset.import", "project_path": str(project),
    "command_id": "00000000-0000-4000-8000-000000000001",
    "expected_revision": 0, "asset_id": asset_id,
    "source_path": str(audio), "media_type": "audio/wav",
}, 1)
revision = 1
for slot in range(64):
    invoke("command", {
        "operation": "pad.assign", "project_path": str(project),
        "command_id": f"00000000-0000-4000-8000-{slot + 2:012d}",
        "expected_revision": revision,
        "slot": {"bank": slot // 16, "pad": slot % 16},
        "asset_id": asset_id,
    }, revision + 1)
    revision += 1
invoke("command", {
    "operation": "pattern.create", "project_path": str(project),
    "command_id": "00000000-0000-4000-8000-000000000066",
    "expected_revision": revision, "pattern_id": pattern_id, "bars": 1,
}, revision + 1)
PY
  python3 "$repo_root/tools/project-bundle/project_bundle.py" pack \
    --source "$proof_root/creator-proof.lmdj" --output "$proof_root/first.lmdj" >/dev/null
  python3 "$repo_root/tools/project-bundle/project_bundle.py" pack \
    --source "$proof_root/creator-proof.lmdj" --output "$proof_root/second.lmdj" >/dev/null
  cmp "$proof_root/first.lmdj" "$proof_root/second.lmdj"
  cmake -E copy "$proof_root/first.lmdj" "$output"
  echo "Creator Web Project fixture reproducibility: PASS"
}

generate_sample_editor_fixture() {
  local output="$1"
  python3 - \
    "$repo_root/build/core/dev/bin/lmdj-core" \
    "$repo_root/products/lmdj/assembly.json" \
    "$proof_root" <<'PY'
import json
from pathlib import Path
import struct
import subprocess
import sys
import wave

executable, assembly, root = map(Path, sys.argv[1:])
workspace = root / "sample-workspace"
project = root / "creator-sample-proof.lmdj"
audio = root / "near-limit-44k1.wav"
workspace.mkdir()
with wave.open(str(audio), "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(44_100)
    frames = bytearray()
    for frame in range(240_000):
        value = round((((frame % 97) / 96) * 2 - 1) * 24_000)
        frames.extend(struct.pack("<h", value))
    output.writeframes(frames)

project_id = "00000000-0000-4000-8000-000000000002"
asset_id = "00000000-0000-4000-8000-000000000102"
pattern_id = "00000000-0000-4000-8000-000000000020"

def invoke(surface, request, revision):
    completed = subprocess.run(
        [str(executable), "--workspace", str(workspace), "--assembly",
         str(assembly), surface, "--request",
         json.dumps(request, sort_keys=True, separators=(",", ":"))],
        check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0 or completed.stderr:
        raise SystemExit(completed.stderr or completed.stdout)
    response = json.loads(completed.stdout)
    if response.get("ok") is not True or response.get("project_revision") != revision:
        raise SystemExit(f"Core Sample fixture request failed: {response!r}")

invoke("command", {
    "operation": "project.create", "project_path": str(project),
    "project_id": project_id, "bpm": 120,
}, 0)
invoke("command", {
    "operation": "asset.import", "project_path": str(project),
    "command_id": "00000000-0000-4000-8000-000000000301",
    "expected_revision": 0, "asset_id": asset_id,
    "source_path": str(audio), "media_type": "audio/wav",
}, 1)
revision = 1
for slot in range(1, 45):
    invoke("command", {
        "operation": "pad.assign", "project_path": str(project),
        "command_id": f"00000000-0000-4000-8000-{slot + 301:012d}",
        "expected_revision": revision,
        "slot": {"bank": slot // 16, "pad": slot % 16},
        "asset_id": asset_id,
    }, revision + 1)
    revision += 1
invoke("command", {
    "operation": "pattern.create", "project_path": str(project),
    "command_id": "00000000-0000-4000-8000-000000000402",
    "expected_revision": revision, "pattern_id": pattern_id, "bars": 1,
}, revision + 1)
PY
  python3 "$repo_root/tools/project-bundle/project_bundle.py" pack \
    --source "$proof_root/creator-sample-proof.lmdj" \
    --output "$proof_root/sample-first.lmdj" >/dev/null
  python3 "$repo_root/tools/project-bundle/project_bundle.py" pack \
    --source "$proof_root/creator-sample-proof.lmdj" \
    --output "$proof_root/sample-second.lmdj" >/dev/null
  cmp "$proof_root/sample-first.lmdj" "$proof_root/sample-second.lmdj"
  cmake -E copy "$proof_root/sample-first.lmdj" "$output"
  echo "Creator Web Sample Project fixture reproducibility: PASS"
}

run_browser_gate() {
  local bundle="$1"
  local sample_bundle="$2"
  local candidate_bundle="$3"
  export LMDJ_CREATOR_WEB_CANDIDATE_BUNDLE="$candidate_bundle"
  local requested_port="${LMDJ_CREATOR_WEB_PORT:-0}"
  local ready_file ready_nonce port="" status=0
  local specs=()
  local tracked
  local required_relative="${required_sample_editor_spec#"$repo_root/tests/platform/web/"}"
  local capture_relative="${required_capture_spec#"$repo_root/tests/platform/web/"}"
  [[ -f "$required_sample_editor_spec" ]] &&
    git -C "$repo_root" ls-files --error-unmatch \
      "${required_sample_editor_spec#"$repo_root/"}" >/dev/null || {
    echo "Creator Web error: required Sample Editor proof is not tracked" >&2
    return 2
  }
  [[ -f "$required_capture_spec" ]] &&
    git -C "$repo_root" ls-files --error-unmatch \
      "${required_capture_spec#"$repo_root/"}" >/dev/null || {
    echo "Creator Web error: required Pad Capture proof is not tracked" >&2
    return 2
  }
  while IFS= read -r tracked; do
    case "${tracked#tests/platform/web/}" in
      "$required_relative"|"$capture_relative") ;;
      *) specs+=("${tracked#tests/platform/web/}") ;;
    esac
  done < <(git -C "$repo_root" ls-files 'tests/platform/web/creator/*.spec.mjs')
  [[ ${#specs[@]} -gt 0 ]] || {
    echo "Creator Web error: no tracked Creator browser specs" >&2
    return 2
  }
  cleanup_server
  proof_server_ready_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-creator-server.XXXXXX")"
  ready_file="$proof_server_ready_root/ready.json"
  ready_nonce="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  # #901: the Creator reaches its Catalog through a same-origin prefix, so the
  # proof server forwards the way the deployed Worker does. The Sound Set lane
  # owns its Catalog fixture on a kernel-assigned port and stops it mid-run on
  # purpose, so it writes the upstream here after this server is listening
  # rather than the server being told it up front.
  LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE="$proof_server_ready_root/catalog-upstream"
  export LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE
  python3 "$repo_root/tools/web-runtime/serve_distribution.py" \
    --root "$dist_root" \
    --verifier "$creator_root/tools/package.py" \
    --repo-root "$repo_root" \
    --port "$requested_port" \
    --catalog-upstream-file "$LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE" \
    --ready-file "$ready_file" \
    --ready-nonce "$ready_nonce" >"$build_root/proof-server.log" 2>&1 &
  proof_server_pid=$!
  for _ in {1..100}; do
    if [[ -f "$ready_file" ]]; then
      port="$(python3 - "$ready_file" "$proof_server_pid" "$ready_nonce" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if (set(value) != {"host", "nonce", "pid", "port"}
        or value["host"] != "127.0.0.1"
        or value["pid"] != int(sys.argv[2]) or value["nonce"] != sys.argv[3]
        or type(value["port"]) is not int or not 1 <= value["port"] <= 65535):
    raise SystemExit(1)
print(value["port"])
PY
)" && break
    fi
    kill -0 "$proof_server_pid" 2>/dev/null || break
    sleep 0.05
  done
  [[ -n "$port" ]] || {
    sed -n '1,120p' "$build_root/proof-server.log" >&2 || true
    echo "Creator Web error: proof server did not become ready" >&2
    return 2
  }
  LMDJ_WEB_RESULTS_SLOT=chromium \
    LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_FULL_CHROMIUM=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=chromium "${specs[@]}" || status=$?
  LMDJ_WEB_RESULTS_SLOT=sample-chromium \
    LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_FULL_CHROMIUM=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    LMDJ_CREATOR_WEB_SAMPLE_BUNDLE="$sample_bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=creator-sample-chromium "$required_relative" || status=$?
  LMDJ_WEB_RESULTS_SLOT=webkit \
    LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=webkit "${specs[@]}" --grep "capability boundary" || status=$?
  # S8B-D8: the fake-device projects are the automated acceptance gate for Pad
  # Capture. Both must run here, or capture ships with no browser evidence at
  # all: the granted project proves record/trim/commit and the interruption
  # contract, the denied project proves the permission path is explained and
  # retryable rather than a silent no-op.
  LMDJ_WEB_RESULTS_SLOT=capture-chromium \
    LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_FULL_CHROMIUM=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    LMDJ_CREATOR_WEB_SAMPLE_BUNDLE="$sample_bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=creator-capture-chromium "$capture_relative" || status=$?
  LMDJ_WEB_RESULTS_SLOT=capture-denied-chromium \
    LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_FULL_CHROMIUM=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    LMDJ_CREATOR_WEB_SAMPLE_BUNDLE="$sample_bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=creator-capture-denied-chromium "$capture_relative" || status=$?

  LMDJ_WEB_RESULTS_SLOT=sample-webkit \
    LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    LMDJ_CREATOR_WEB_SAMPLE_BUNDLE="$sample_bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=creator-sample-webkit "$required_relative" \
      --grep "capability boundary" || status=$?
  cleanup_server
  return "$status"
}

proof_creator() {
  activate_toolchain
  require_dependencies
  if [[ -n "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)" ]]; then
    echo "Creator Web error: Proof requires a clean Git source tree" >&2
    return 2
  fi
  export npm_config_offline=true
  export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
  export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
  unset NODE_PATH || true
  unset PYTHONPATH || true
  proof_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-creator-proof.XXXXXX")"
  generate_project_fixture "$proof_root/creator-proof-bundle.lmdj"
  generate_sample_editor_fixture "$proof_root/creator-sample-proof-bundle.lmdj"
  python3 "$web_test_root/creator/fixtures/make_candidate_fixture.py" \
    "$repo_root/build/core/dev/bin/lmdj-core" \
    "$repo_root/products/lmdj/assembly.json" \
    "$proof_root/creator-candidate-proof-bundle.lmdj"
  clean_creator
  configure_creator
  build_creator
  package_creator
  cmake -E copy_directory "$dist_root" "$proof_root/first-dist"
  clean_creator
  configure_creator
  build_creator
  package_creator
  diff -qr "$proof_root/first-dist" "$dist_root" || {
    echo "Creator Web error: two clean distributions are not byte reproducible" >&2
    return 2
  }
  echo "Creator Web distribution reproducibility: PASS"
  test_creator
  run_browser_gate \
    "$proof_root/creator-proof-bundle.lmdj" \
    "$proof_root/creator-sample-proof-bundle.lmdj" \
    "$proof_root/creator-candidate-proof-bundle.lmdj"
  echo "Creator Web Proof: PASS"
}

[[ $# -ge 1 ]] || { usage; exit 64; }
command_name="$1"
shift
cd "$repo_root"

case "$command_name" in
  configure)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    configure_creator
    ;;
  build)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    build_creator
    ;;
  test)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    test_creator
    ;;
  proof)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    proof_creator
    ;;
  package)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    package_creator
    ;;
  serve)
    if [[ $# -ne 0 && ( $# -ne 2 || "$1" != "--port" ) ]]; then
      usage
      exit 64
    fi
    [[ -d "$dist_root" ]] || {
      echo "Creator Web error: package Creator before serving" >&2
      exit 2
    }
    exec python3 "$repo_root/tools/web-runtime/serve_distribution.py" \
      --root "$dist_root" --verifier "$creator_root/tools/package.py" \
      --repo-root "$repo_root" "$@"
    ;;
  clean)
    [[ $# -eq 0 ]] || { usage; exit 64; }
    clean_creator
    ;;
  *)
    echo "unknown Creator Web command: $command_name" >&2
    usage
    exit 64
    ;;
esac
