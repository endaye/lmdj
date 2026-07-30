#!/usr/bin/env bash
set -euo pipefail

json_sha="42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa"
pico_commit="161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29"
verify_root="$(mktemp -d)"
trap 'rm -rf "$verify_root"' EXIT

curl --proto '=https' --tlsv1.2 -fsSL \
  https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz \
  -o "$verify_root/json.tar.xz"

if command -v sha256sum >/dev/null 2>&1; then
  actual_json_sha="$(sha256sum "$verify_root/json.tar.xz" | awk '{print $1}')"
else
  actual_json_sha="$(shasum -a 256 "$verify_root/json.tar.xz" | awk '{print $1}')"
fi
test "$actual_json_sha" = "$json_sha"

mkdir "$verify_root/PicoSHA2"
git -C "$verify_root/PicoSHA2" init --quiet
git -C "$verify_root/PicoSHA2" fetch --quiet --depth 1 \
  https://github.com/okdshin/PicoSHA2.git "$pico_commit"
git -C "$verify_root/PicoSHA2" checkout --quiet FETCH_HEAD
test "$(git -C "$verify_root/PicoSHA2" rev-parse HEAD)" = "$pico_commit"
grep -Eq '^project\(picosha2\)' "$verify_root/PicoSHA2/CMakeLists.txt"
grep -Eq '^add_library\(\$\{PROJECT_NAME\} INTERFACE\)' \
  "$verify_root/PicoSHA2/CMakeLists.txt"
cmake -S "$verify_root/PicoSHA2" -B "$verify_root/pico-build" \
  -DPICOSHA2_TEST=OFF -DPICOSHA2_EXAMPLE=OFF

echo "core dependency verification: PASS"
