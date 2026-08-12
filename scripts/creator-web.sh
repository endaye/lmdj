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
  if [[ -n "${EMSDK_NODE:-}" ]]; then
    PATH="$(dirname "$EMSDK_NODE"):$PATH"
    export PATH
  fi
  for command in cmake emcc emcmake node npm python3; do
    command -v "$command" >/dev/null 2>&1 || {
      echo "Creator Web error: missing command: $command" >&2
      exit 2
    }
  done
  if [[ "$(node -p 'process.versions.node.split(".")[0]')" != "22" ]]; then
    echo "Creator Web error: Node 22 is required, got $(node --version)" >&2
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
take_id = "00000000-0000-4000-8000-000000000201"
invoke("command", {
    "operation": "take.begin", "project_path": str(project),
    "take_id": take_id, "expected_revision": revision, "sample_rate": 48000,
}, revision)
invoke("command", {
    "operation": "take.append", "project_path": str(project),
    "take_id": take_id,
    "event": {"slot": {"bank": 0, "pad": 0}, "frame_offset": 0, "velocity": 100},
}, revision)
invoke("command", {
    "operation": "take.commit", "project_path": str(project),
    "command_id": "00000000-0000-4000-8000-000000000066",
    "expected_revision": revision, "take_id": take_id,
    "pattern": {"pattern_id": pattern_id, "bars": 1, "events": [{
        "slot": {"bank": 0, "pad": 0}, "step": 0, "velocity": 100,
    }]},
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

run_browser_gate() {
  local bundle="$1"
  local requested_port="${LMDJ_CREATOR_WEB_PORT:-0}"
  local ready_file ready_nonce port="" status=0
  local specs=()
  local tracked
  while IFS= read -r tracked; do
    specs+=("${tracked#tests/platform/web/}")
  done < <(git -C "$repo_root" ls-files \
    'tests/platform/web/creator/creator_web_*.spec.mjs')
  [[ ${#specs[@]} -gt 0 ]] || {
    echo "Creator Web error: no tracked Creator browser specs" >&2
    return 2
  }
  cleanup_server
  proof_server_ready_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-creator-server.XXXXXX")"
  ready_file="$proof_server_ready_root/ready.json"
  ready_nonce="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  python3 "$repo_root/tools/web-runtime/serve_distribution.py" \
    --root "$dist_root" \
    --verifier "$creator_root/tools/package.py" \
    --repo-root "$repo_root" \
    --port "$requested_port" \
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
  LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_FULL_CHROMIUM=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=chromium "${specs[@]}" || status=$?
  LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
    LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
    LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
    npm --prefix "$web_test_root" test -- \
      --project=webkit "${specs[@]}" --grep "capability boundary" || status=$?
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
  run_browser_gate "$proof_root/creator-proof-bundle.lmdj"
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
