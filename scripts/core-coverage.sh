#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_root="$repo_root/build/core/coverage"
profiles_root="$build_root/profiles"
coverage_root="$build_root/coverage"
objects_path="$build_root/coverage-objects.txt"
merged_profile="$coverage_root/merged.profdata"
summary_path="$coverage_root/summary.json"
report_path="$coverage_root/report.txt"

usage() {
  echo "usage: scripts/core-coverage.sh [report|check]" >&2
}

resolve_llvm_tool() {
  local tool_name="$1"
  local resolved

  resolved="$(command -v "$tool_name" || true)"
  if [[ -n "$resolved" ]]; then
    printf '%s\n' "$resolved"
    return
  fi

  if [[ "$(uname -s)" == "Darwin" ]] && command -v xcrun >/dev/null 2>&1; then
    resolved="$(xcrun --find "$tool_name" 2>/dev/null || true)"
    if [[ -n "$resolved" ]]; then
      printf '%s\n' "$resolved"
      return
    fi
  fi

  echo "unable to locate $tool_name" >&2
  return 1
}

if [[ $# -ne 1 ]]; then
  usage
  exit 64
fi

mode="$1"
case "$mode" in
  report|check)
    ;;
  *)
    usage
    exit 64
    ;;
esac

llvm_profdata="$(resolve_llvm_tool llvm-profdata)"
llvm_cov="$(resolve_llvm_tool llvm-cov)"

cd "$repo_root"
cmake --preset coverage
cmake --build --preset coverage

cmake -E make_directory "$profiles_root"
cmake -E make_directory "$coverage_root"
find "$profiles_root" -maxdepth 1 -type f -name '*.profraw' -delete

LLVM_PROFILE_FILE="$profiles_root/%p-%m.profraw" ctest --preset coverage

raw_profiles=()
while IFS= read -r profile_path; do
  raw_profiles+=("$profile_path")
done < <(
  find "$profiles_root" -maxdepth 1 -type f -name '*.profraw' -print |
    LC_ALL=C sort
)
if [[ ${#raw_profiles[@]} -eq 0 ]]; then
  echo "coverage run produced no raw profiles" >&2
  exit 1
fi

"$llvm_profdata" merge -sparse "${raw_profiles[@]}" -o "$merged_profile"

if [[ ! -f "$objects_path" ]]; then
  echo "coverage object list is missing: $objects_path" >&2
  exit 1
fi

objects=()
while IFS= read -r object_path; do
  [[ -n "$object_path" ]] || continue
  if [[ ! -f "$object_path" ]]; then
    echo "coverage object is missing: $object_path" >&2
    exit 1
  fi
  objects+=("$object_path")
done < "$objects_path"
if [[ ${#objects[@]} -eq 0 ]]; then
  echo "coverage object list is empty: $objects_path" >&2
  exit 1
fi

source_roots=(
  "$repo_root/packages"
  "$repo_root/providers"
  "$repo_root/products/lmdj"
  "$repo_root/apps/core-cli"
)
source_args=()
while IFS= read -r source_path; do
  source_args+=(--sources "$source_path")
done < <(
  find "${source_roots[@]}" \
    -type f \
    \( -name '*.cpp' -o \( -name '*.hpp' -path '*/include/*' \) \) \
    -print |
    LC_ALL=C sort
)
if [[ ${#source_args[@]} -eq 0 ]]; then
  echo "no first-party coverage source is present" >&2
  exit 1
fi

coverage_objects=("${objects[0]}")
for ((object_index = 1; object_index < ${#objects[@]}; object_index++)); do
  coverage_objects+=(--object "${objects[$object_index]}")
done

"$llvm_cov" export \
  -instr-profile="$merged_profile" \
  --summary-only \
  "${coverage_objects[@]}" \
  "${source_args[@]}" >"$summary_path"

python3 - "$summary_path" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
files = [
    file_
    for data in summary.get("data", [])
    for file_ in data.get("files", [])
]
if not files:
    raise SystemExit("coverage export contains no first-party source")
PY

"$llvm_cov" report \
  -instr-profile="$merged_profile" \
  -show-branch-summary \
  "${coverage_objects[@]}" \
  "${source_args[@]}" >"$report_path"

if [[ "$mode" == "check" ]]; then
  python3 tests/quality/coverage_gate.py \
    --summary "$summary_path" \
    --thresholds tests/quality/core-coverage-thresholds.json
fi

echo "Core coverage report: $report_path"
