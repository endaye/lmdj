#!/usr/bin/env bash
# Install the pinned Core Clang/LLVM major from apt.llvm.org on Ubuntu 24.04.
#
# One script serves both consumers of the pin so they cannot drift apart: the
# operator runs it once on each self-hosted Linux host (netcup, Contabo), and
# the hosted `core-tsan` lane runs it per job on `ubuntu-24.04`. Ubuntu's own
# archive stops at LLVM 18 for noble, so the pinned major has to come from the
# LLVM project's repository. That is a third-party apt source on a trusted CI
# host, and this script exists so that source is byte-pinned rather than
# pasted: the signing key is verified against a fixed fingerprint before it is
# trusted, the suite is the exact-major `llvm-toolchain-noble-<MAJOR>` (never
# the rolling `llvm-toolchain-noble`, which follows LLVM main), and the origin
# carries an apt pin priority of 100 so it can only ever provide packages the
# distribution does not, and never override one it does.
#
# Idempotent: rerunning verifies the key and source, then lets apt decide that
# nothing needs installing.
#
# Usage: sudo scripts/ci/host/install-llvm-toolchain.sh [MAJOR]
# MAJOR defaults to 22, the Core pin. It must match the `CC=clang-<MAJOR>`
# pins in .github/workflows and the tool list ci-host-inventory.yml probes.
set -euo pipefail

major="${1:-22}"
if [[ ! "$major" =~ ^[0-9]{2}$ ]]; then
  echo "why: MAJOR must be a two-digit LLVM major, got '$major'; remedy: pass e.g. 22" >&2
  exit 64
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "why: apt sources and keyrings are root-owned; remedy: run with sudo" >&2
  exit 77
fi

codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-}")"
if [[ "$codename" != "noble" ]]; then
  echo "why: the pin is verified only for Ubuntu 24.04 (noble), this host reports '$codename'; remedy: extend the pin deliberately rather than by editing this check" >&2
  exit 78
fi

# apt.llvm.org's signing key, "Sylvestre Ledru - Debian LLVM packages".
expected_fingerprint="6084F3CF814B57C1CF12EFD515CF4D18AF4F7421"
keyring="/usr/share/keyrings/apt-llvm-org.gpg"
source_file="/etc/apt/sources.list.d/apt-llvm-org-${major}.sources"
preferences_file="/etc/apt/preferences.d/apt-llvm-org"
suite="llvm-toolchain-noble-${major}"

work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends ca-certificates curl gnupg >/dev/null

curl -fsSL --max-time 60 https://apt.llvm.org/llvm-snapshot.gpg.key -o "$work/key.asc"
gpg --batch --dearmor -o "$work/key.gpg" "$work/key.asc"
actual_fingerprint="$(
  gpg --batch --with-colons --show-keys "$work/key.gpg" \
    | awk -F: '$1 == "fpr" { print $10; exit }'
)"
if [[ "$actual_fingerprint" != "$expected_fingerprint" ]]; then
  echo "why: apt.llvm.org served a key with fingerprint $actual_fingerprint, not the pinned $expected_fingerprint, so the source cannot be trusted; remedy: confirm the key rotation out of band and update expected_fingerprint in this script" >&2
  exit 65
fi
install -m 0644 "$work/key.gpg" "$keyring"

cat >"$source_file" <<SOURCES
# Managed by scripts/ci/host/install-llvm-toolchain.sh. Pinned to one LLVM
# major on purpose; see that script before changing the suite.
Types: deb
URIs: https://apt.llvm.org/noble/
Suites: ${suite}
Components: main
Signed-By: ${keyring}
SOURCES

cat >"$preferences_file" <<PREFERENCES
# Managed by scripts/ci/host/install-llvm-toolchain.sh. apt.llvm.org may only
# provide packages Ubuntu's archive does not carry; it never overrides one.
Package: *
Pin: origin apt.llvm.org
Pin-Priority: 100
PREFERENCES

# Refresh only this source. A full update would also touch every other list,
# and on a host the runner shares that is more than the pin needs.
apt-get update \
  -o Dir::Etc::sourcelist="$source_file" \
  -o Dir::Etc::sourceparts=- \
  -o APT::Get::List-Cleanup=0 >/dev/null

# clang++-<MAJOR> is shipped by clang-<MAJOR>; there is no separate package.
# libclang-rt provides the sanitizer and profile runtimes, llvm provides
# llvm-cov and llvm-profdata for the coverage lane.
apt-get install -y --no-install-recommends \
  "clang-${major}" "llvm-${major}" "libclang-rt-${major}-dev" "lld-${major}"

for tool in "clang-${major}" "clang++-${major}" "llvm-cov-${major}" "llvm-profdata-${major}"; do
  path="$(command -v "$tool")"
  printf '%s\t%s\t%s\n' "$tool" "$path" "$("$tool" --version | head -n1)"
done
