#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_root="$repo_root/build/core"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/core.sh configure [dev|release|asan|tsan]
  scripts/core.sh build [dev|release|asan|tsan]
  scripts/core.sh test [dev|release|asan|tsan] [fast|full|stress]
  scripts/core.sh coverage [report|check]
  scripts/core.sh proof
  scripts/core.sh package
  scripts/core.sh clean
EOF
}

require_preset() {
  case "$1" in
    dev|release|asan|tsan)
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
    [[ $# -ge 1 && $# -le 2 ]] || {
      usage
      exit 64
    }
    test_preset="$1"
    test_mode="${2:-full}"
    require_preset "$test_preset"
    case "$test_mode" in
      fast)
        ctest --preset "$test_preset" -L '^(unit|component)$'
        ;;
      full)
        ctest --preset "$test_preset" -LE '^stress$'
        ;;
      stress)
        ctest --preset "$test_preset" -L '^stress$'
        ;;
      *)
        echo "unsupported Core test mode: $test_mode" >&2
        usage
        exit 64
        ;;
    esac
    ;;
  coverage)
    [[ $# -eq 1 ]] || {
      usage
      exit 64
    }
    exec "$repo_root/scripts/core-coverage.sh" "$1"
    ;;
  proof)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    proof_run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    proof_run_root="$build_root/proof-runs/$proof_run_id"
    proof_e2e_root="$proof_run_root/e2e"
    proof_artifact_root="$proof_run_root/artifacts"
    proof_log="$proof_run_root/proof.log"
    proof_failure_root="$build_root/proof-failures"
    release_root="$build_root/release"
    published_output_root="$release_root/proof-output"
    published_output_wav="$published_output_root/beat.wav"
    published_manifest="$release_root/build-manifest.json"
    proof_output_wav="$proof_artifact_root/beat.wav"
    proof_manifest="$proof_artifact_root/build-manifest.json"
    assembly_path="$repo_root/products/lmdj/assembly.json"
    assembly_lock_path="$repo_root/products/lmdj/assembly.lock.json"

    mkdir -p "$proof_run_root"
    exec > >(tee "$proof_log") 2>&1
    preserve_failed_proof() {
      proof_status=$?
      if [[ $proof_status -ne 0 && -d "$proof_run_root" ]]; then
        set +e
        mkdir -p "$proof_failure_root"
        proof_failure_path="$proof_failure_root/$proof_run_id"
        mv "$proof_run_root" "$proof_failure_path"
        echo "Headless Core Proof artifacts: $proof_failure_path" >&2
      fi
      exit "$proof_status"
    }
    trap preserve_failed_proof EXIT

    bash tests/build/test_active_tree.sh
    python3 tests/build/version_test.py
    python3 tests/conformance/version_lock_test.py
    python3 scripts/version.py verify \
      --version-file products/lmdj/version.json \
      --assembly "$assembly_path" \
      --lock "$assembly_lock_path"

    cmake --preset release
    cmake --build --preset release
    core_c_library="$release_root/lib/liblmdj_core_c.dylib"
    if [[ ! -f "$core_c_library" ]]; then
      core_c_library="$release_root/lib/liblmdj_core_c.so"
    fi
    if [[ ! -f "$core_c_library" ]]; then
      echo "Core C ABI library is missing from the Release build" >&2
      exit 2
    fi
    ctest \
      --test-dir "$release_root" \
      --output-on-failure \
      -E '^(build\.active_tree|build\.version|contract\.schemas|conformance\.|host\.|e2e\.)' \
      -LE '^stress$'

    python3 tests/conformance/schema_contract_test.py
    python3 tests/conformance/module_graph_test.py
    python3 tests/e2e/proof_path_safety_test.py
    python3 tests/host/cli_test.py \
      "$release_root/bin/lmdj-core"
    PYTHONPATH="$repo_root/apps/core-mcp" \
      python3 tests/host/mcp_stdio_test.py \
      "$core_c_library"
    PYTHONPATH="$repo_root/apps/core-mcp" \
      python3 tests/host/mcp_facade_parity_test.py \
      "$release_root/bin/lmdj-core" \
      "$core_c_library"
    PYTHONPATH="$repo_root/apps/core-mcp" \
      python3 tests/e2e/headless_core_proof.py \
      "$release_root/bin/lmdj-core" \
      "$core_c_library" \
      "$assembly_path" \
      "$proof_e2e_root" \
      "$proof_output_wav"

    python3 tests/distribution/package_acceptance_test.py \
      --build-root "$release_root"

    python3 scripts/version.py manifest \
      --version-file products/lmdj/version.json \
      --assembly "$assembly_path" \
      --lock "$assembly_lock_path" \
      --channel canary \
      --artifacts-root "$release_root" \
      --output "$proof_manifest" \
      --overlay-artifact "$proof_output_wav=proof-output/beat.wav"
    git diff --check

    cmake -E make_directory "$published_output_root"
    cmake -E copy_if_different "$proof_output_wav" "$published_output_wav"
    cmake -E copy_if_different "$proof_manifest" "$published_manifest"

    cmake -E remove_directory "$proof_run_root"
    trap - EXIT
    echo "Headless Core Proof: PASS"
    echo "Product Build: 1.0.9.0"
    echo "Channel: canary"
    echo "Assembly lock: MATCH"
    ;;
  package)
    [[ $# -eq 0 ]] || {
      usage
      exit 64
    }
    cmake --preset release
    cmake --build --preset release
    python3 scripts/package-core.py \
      --build-root "$build_root/release" \
      --output-dir "$build_root/dist"
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
