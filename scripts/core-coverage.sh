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
coverage_union="$repo_root/tests/quality/coverage_union.py"

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

mkdir -p -- "$coverage_root"
rm -f -- "$merged_profile" "$summary_path" "$report_path"

llvm_profdata="$(resolve_llvm_tool llvm-profdata)"
llvm_cov="$(resolve_llvm_tool llvm-cov)"

cd "$repo_root"
cmake --preset coverage
cmake --build --preset coverage

cmake -E make_directory "$profiles_root"
find "$profiles_root" -maxdepth 1 -type f -name '*.profraw' -delete

# Retain the CTest transcript. Timeout budgets are absolute seconds while
# machine speed is not, so the only way to tell a slower test from a slower
# machine is to keep the run's own timings and compare shares later.
ctest_log="$coverage_root/ctest.log"
cmake -E make_directory "$coverage_root"
set +e
LLVM_PROFILE_FILE="$profiles_root/%p-%m.profraw" ctest --preset coverage \
  2>&1 | tee "$ctest_log"
ctest_status="${PIPESTATUS[0]}"
set -e
if [[ "$ctest_status" -ne 0 ]]; then
  python3 "$repo_root/tests/quality/test_budget_report.py" \
    --ctest-log "$ctest_log" --sanitizer coverage --repo-root "$repo_root" || true
  exit "$ctest_status"
fi

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

if [[ ! -f "$coverage_union" ]]; then
  echo "coverage union helper is missing: $coverage_union" >&2
  exit 1
fi

run_root="$(mktemp -d "$coverage_root/.run.XXXXXX")"
cleanup() {
  rm -rf -- "$run_root"
}
trap cleanup EXIT

tool_stderr="$run_root/tool.stderr"
run_profdata_merge() {
  local output_path="$1"
  shift

  : >"$tool_stderr"
  if ! "$llvm_profdata" merge -sparse "$@" -o "$output_path" \
    2>"$tool_stderr"; then
    cat "$tool_stderr" >&2
    echo "llvm-profdata merge failed" >&2
    return 1
  fi
  if [[ -s "$tool_stderr" ]]; then
    cat "$tool_stderr" >&2
    echo "llvm-profdata merge emitted unexpected diagnostics" >&2
    return 1
  fi
}

run_cov_export() {
  local output_path="$1"
  shift

  : >"$tool_stderr"
  if ! "$llvm_cov" export "$@" >"$output_path" 2>"$tool_stderr"; then
    cat "$tool_stderr" >&2
    echo "llvm-cov export failed" >&2
    return 1
  fi
  if [[ -s "$tool_stderr" ]]; then
    cat "$tool_stderr" >&2
    echo "llvm-cov export emitted unexpected diagnostics" >&2
    return 1
  fi
}

merged_profile_candidate="$run_root/merged.profdata"
run_profdata_merge "$merged_profile_candidate" "${raw_profiles[@]}"

raw_signatures_path="$run_root/raw-signatures.txt"
for profile_path in "${raw_profiles[@]}"; do
  profile_name="$(basename "$profile_path")"
  signature="${profile_name#*-}"
  signature="${signature%.profraw}"
  if [[ ! "$signature" =~ ^[0-9]+_[0-9]+$ ]]; then
    echo "coverage profile has an unexpected module signature: $profile_name" >&2
    exit 1
  fi
  printf '%s\n' "$signature"
done | LC_ALL=C sort -u >"$raw_signatures_path"

signature_count="$(wc -l <"$raw_signatures_path" | tr -d ' ')"
if [[ "$signature_count" -ne "${#objects[@]}" ]]; then
  echo \
    "coverage module signature count does not match object count: " \
    "$signature_count != ${#objects[@]}" \
    >&2
  exit 1
fi

probe_root="$run_root/probes"
cmake -E make_directory "$probe_root"
shared_object_count=0
for ((object_index = 0; object_index < ${#objects[@]}; object_index++)); do
  object_path="${objects[$object_index]}"
  object_number=$((object_index + 1))
  case "$object_path" in
    *.dylib|*.so|*.so.*|*.dll)
      shared_object_count=$((shared_object_count + 1))
      continue
      ;;
  esac

  probe_arguments=()
  case "$(basename "$object_path")" in
    lmdj-native-audio-probe)
      probe_arguments+=(--no-device)
      ;;
  esac

  probe_stdout="$probe_root/$object_number.stdout"
  probe_stderr="$probe_root/$object_number.stderr"
  set +e
  LLVM_PROFILE_FILE="$probe_root/$object_number-%m.profraw" \
    "$object_path" ${probe_arguments[@]+"${probe_arguments[@]}"} \
    >"$probe_stdout" 2>"$probe_stderr" </dev/null
  probe_status=$?
  set -e
  if grep -Eq 'LLVM Profile (Error|Warning)' "$probe_stderr"; then
    cat "$probe_stderr" >&2
    echo "coverage object probe reported a profile diagnostic: $object_path" >&2
    exit 1
  fi

  object_probe_signatures="$probe_root/$object_number.signatures"
  while IFS= read -r probe_profile; do
    probe_name="$(basename "$probe_profile")"
    probe_signature="${probe_name#"$object_number-"}"
    probe_signature="${probe_signature%.profraw}"
    if grep -Fqx "$probe_signature" "$raw_signatures_path"; then
      printf '%s\n' "$probe_signature"
    fi
  done < <(
    find "$probe_root" \
      -maxdepth 1 \
      -type f \
      -name "$object_number-*.profraw" \
      -print |
      LC_ALL=C sort
  ) | LC_ALL=C sort -u >"$object_probe_signatures"
  if [[ ! -s "$object_probe_signatures" ]]; then
    echo \
      "coverage object probe produced no matching module signature " \
      "(status $probe_status): $object_path" \
      >&2
    exit 1
  fi
done

if [[ "$shared_object_count" -ne 1 ]]; then
  echo \
    "coverage signature mapping requires exactly one shared coverage object; " \
    "found $shared_object_count" \
    >&2
  exit 1
fi

signature_occurrences="$probe_root/signature-occurrences.txt"
cat "$probe_root"/*.signatures |
  LC_ALL=C sort |
  uniq -c >"$signature_occurrences"

assigned_signatures="$probe_root/assigned-signatures.txt"
: >"$assigned_signatures"
for ((object_index = 0; object_index < ${#objects[@]}; object_index++)); do
  object_path="${objects[$object_index]}"
  object_number=$((object_index + 1))
  case "$object_path" in
    *.dylib|*.so|*.so.*|*.dll)
      continue
      ;;
  esac

  own_signatures="$probe_root/$object_number.own-signatures"
  while read -r occurrence signature; do
    if [[ "$occurrence" -eq 1 ]] &&
      grep -Fqx "$signature" "$probe_root/$object_number.signatures"; then
      printf '%s\n' "$signature"
    fi
  done <"$signature_occurrences" >"$own_signatures"

  own_signature_count="$(wc -l <"$own_signatures" | tr -d ' ')"
  if [[ "$own_signature_count" -ne 1 ]]; then
    echo \
      "coverage object does not have one unique module signature: " \
      "$object_path (found $own_signature_count)" \
      >&2
    exit 1
  fi
  cat "$own_signatures" >>"$assigned_signatures"
done

shared_signatures="$probe_root/shared-signatures.txt"
grep -Fvx -f "$assigned_signatures" "$raw_signatures_path" >"$shared_signatures" ||
  true
shared_signature_count="$(wc -l <"$shared_signatures" | tr -d ' ')"
if [[ "$shared_signature_count" -ne 1 ]]; then
  echo \
    "coverage shared object does not have one remaining module signature " \
    "(found $shared_signature_count)" \
    >&2
  exit 1
fi
shared_signature="$(cat "$shared_signatures")"

module_profiles_root="$run_root/module-profiles"
fragments_root="$run_root/fragments"
cmake -E make_directory "$module_profiles_root"
cmake -E make_directory "$fragments_root"
for ((object_index = 0; object_index < ${#objects[@]}; object_index++)); do
  object_path="${objects[$object_index]}"
  object_number=$((object_index + 1))
  case "$object_path" in
    *.dylib|*.so|*.so.*|*.dll)
      object_signature="$shared_signature"
      ;;
    *)
      object_signature="$(
        cat "$probe_root/$object_number.own-signatures"
      )"
      ;;
  esac

  module_raw_profiles=()
  for profile_path in "${raw_profiles[@]}"; do
    profile_name="$(basename "$profile_path")"
    profile_signature="${profile_name#*-}"
    profile_signature="${profile_signature%.profraw}"
    if [[ "$profile_signature" == "$object_signature" ]]; then
      module_raw_profiles+=("$profile_path")
    fi
  done
  if [[ ${#module_raw_profiles[@]} -eq 0 ]]; then
    echo "coverage object has no raw module profiles: $object_path" >&2
    exit 1
  fi

  module_profile="$module_profiles_root/$object_number.profdata"
  run_profdata_merge "$module_profile" "${module_raw_profiles[@]}"
  run_cov_export \
    "$fragments_root/$object_number.lcov" \
    -format=lcov \
    -instr-profile="$module_profile" \
    "$object_path"
done

summary_candidate="$run_root/summary.json"
report_candidate="$run_root/report.txt"
union_args=(
  --repo-root "$repo_root"
)
topologies_root="$run_root/topologies"
cmake -E make_directory "$topologies_root"
for ((object_index = 0; object_index < ${#objects[@]}; object_index++)); do
  object_path="${objects[$object_index]}"
  object_number=$((object_index + 1))
  topology_path="$topologies_root/$object_number.lcov"
  run_cov_export \
    "$topology_path" \
    -format=lcov \
    -instr-profile="$module_profiles_root/$object_number.profdata" \
    "$object_path"
  union_args+=(--topology "$topology_path")
done
for fragment_path in "$fragments_root"/*.lcov; do
  union_args+=(--fragment "$fragment_path")
done
python3 "$coverage_union" \
  "${union_args[@]}" \
  --summary "$summary_candidate" \
  --report "$report_candidate"

mv -f -- "$merged_profile_candidate" "$merged_profile"
mv -f -- "$summary_candidate" "$summary_path"
mv -f -- "$report_candidate" "$report_path"

if [[ "$mode" == "check" ]]; then
  python3 tests/quality/coverage_gate.py \
    --summary "$summary_path" \
    --thresholds tests/quality/core-coverage-thresholds.json
fi

echo "Core coverage report: $report_path"
