#!/usr/bin/env bash
set -euo pipefail

# Verifies the vendored third-party build dependencies offline. Provenance,
# upstream URLs, and the update procedure are recorded in third_party/README.md.
# This gate fails closed on any mismatch and never reaches the network, so a
# throttled or unreachable upstream cannot turn it red.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
third_party="$repo_root/third_party"

json_archive="$third_party/nlohmann-json/json-v3.12.0.tar.xz"
json_sha="42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa"
pico_root="$third_party/picosha2"
pico_upstream_commit="161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29"
pico_header_sha="b13c180161ffac8d0adc81e033e493c409457c4d1258ab9781ac80579ba3bdd8"
pico_cmake_sha="bf1de9a64c3f3bcc8bc338cc99158f74803af865e03fd13c960949c848a1bf19"

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

expect_sha() {
  local path="$1" expected="$2" actual
  if [[ ! -f "$path" ]]; then
    echo "vendored dependency is missing: ${path#"$repo_root"/}" >&2
    exit 1
  fi
  actual="$(sha256_of "$path")"
  if [[ "$actual" != "$expected" ]]; then
    echo "vendored dependency hash mismatch: ${path#"$repo_root"/}" >&2
    echo "  expected $expected" >&2
    echo "  actual   $actual" >&2
    exit 1
  fi
}

expect_sha "$json_archive" "$json_sha"
expect_sha "$pico_root/picosha2.h" "$pico_header_sha"
expect_sha "$pico_root/CMakeLists.txt" "$pico_cmake_sha"

test -f "$pico_root/LICENSE"
grep -Eq '^project\(picosha2\)' "$pico_root/CMakeLists.txt"
grep -Eq '^add_library\(\$\{PROJECT_NAME\} INTERFACE\)' \
  "$pico_root/CMakeLists.txt"
grep -q "$pico_upstream_commit" "$third_party/README.md"

# Prove the vendored archive is a readable xz archive carrying its license, and
# that the vendored PicoSHA2 still configures as an interface library.
verify_root="$(mktemp -d)"
trap 'rm -rf "$verify_root"' EXIT

tar -tJf "$json_archive" | grep -q '^json/LICENSE.MIT$'
tar -tJf "$json_archive" | grep -q '^json/single_include/nlohmann/json.hpp$'
cmake -S "$pico_root" -B "$verify_root/pico-build" \
  -DPICOSHA2_TEST=OFF -DPICOSHA2_EXAMPLE=OFF >/dev/null

echo "core dependency verification: PASS (vendored, offline)"
