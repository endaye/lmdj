#!/usr/bin/env bash
set -euo pipefail
demo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compiler="${CODEGEN_CXX:-$(command -v xtensa-esp32s3-elf-g++ || true)}"
if [[ ! -x "$compiler" || "${compiler##*/}" != xtensa-esp32s3-elf-g++ ]]; then
  echo 'Need the EIM-managed ESP32-S3 compiler; activate eim shell v6.1 or set CODEGEN_CXX to its xtensa-esp32s3-elf-g++ path.' >&2
  exit 2
fi
prefix="${compiler%g++}"
demo_build="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-observation-codegen.XXXXXX")"
printf 'Retained object evidence: %s\n' "$demo_build"
"$compiler" --version | tee "$demo_build/compiler.txt"
for optimization in O2 Os; do
  flags=(-std=gnu++20 "-$optimization" -Wall -Wextra -Wpedantic -Werror -mlongcalls)
  "$compiler" "${flags[@]}" -c "$demo_root/codegen.cpp" -o "$demo_build/$optimization.o"
  "$compiler" "${flags[@]}" -c "$demo_root/codegen_control.cpp" -o "$demo_build/$optimization-control.o"
  "${prefix}objdump" -dr "$demo_build/$optimization.o" > "$demo_build/$optimization.disassembly.txt"
  "${prefix}nm" -u "$demo_build/$optimization.o" > "$demo_build/$optimization.undefined.txt"
  "${prefix}nm" -u "$demo_build/$optimization-control.o" > "$demo_build/$optimization-control.undefined.txt"
  for symbol in demo_publish demo_exchange demo_claim demo_close demo_check; do
    if ! grep -q "<$symbol>:" "$demo_build/$optimization.disassembly.txt"; then
      echo "Missing $symbol; inspect compile/disassembly output before trusting absence of helpers." >&2
      exit 1
    fi
  done
  if grep -Eq '__atomic_.*_8|mutex|malloc|free' "$demo_build/$optimization.undefined.txt"; then
    echo 'Unexpected atomic64/lock/allocation dependency; inspect the retained undefined-symbol list.' >&2
    exit 1
  fi
  if ! grep -q '__atomic_load_8' "$demo_build/$optimization-control.undefined.txt"; then
    echo 'atomic64 positive control missing; verify compiler/target before trusting the diagnostic.' >&2
    exit 1
  fi
  printf '%s object compilation and symbol checks passed; inspect assembly for progress, not just helper absence.\n' "$optimization"
  "${prefix}size" "$demo_build/$optimization.o"
done
