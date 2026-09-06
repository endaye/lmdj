#!/usr/bin/env bash
# Cap the kernel's mmap ASLR entropy at 28 bits on a self-hosted Core host.
#
# Why this exists. Ubuntu 24.04's 6.8 kernel defaults `vm.mmap_rnd_bits` to
# 32 on x86_64. ThreadSanitizer's address-space layout cannot accommodate
# that much randomisation (google/sanitizers#1716): GCC 13's libtsan dies
# with `FATAL: ThreadSanitizer: unexpected memory mapping`, and LLVM 22's
# runtime detects the incompatible layout and re-execs itself with ASLR
# disabled -- which the runner units forbid with `LockPersonality=true`, so
# it dies instead with `unable to disable ASLR (perhaps sandboxing is
# enabled?)`. No compiler major avoids this; the runtime's own advice is
# "rerun with lower ASLR entropy". GitHub's hosted Ubuntu images set 28 for
# exactly this reason, which is why `core-tsan` was hosted until #693.
#
# 28 bits is the pre-6.6 default on this architecture and keeps ASLR on;
# the alternative, `LockPersonality=false` on the runner units, would turn
# ASLR off entirely for every CI process and remove a hardening line. The
# Owner chose the sysctl on 2026-09-06 (#693).
#
# Idempotent. Usage: sudo scripts/ci/host/configure-sanitizer-aslr.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "why: sysctl.d is root-owned; remedy: run with sudo" >&2
  exit 77
fi

conf=/etc/sysctl.d/60-lmdj-ci-sanitizer-aslr.conf
cat >"$conf" <<CONF
# Managed by scripts/ci/host/configure-sanitizer-aslr.sh (#693).
# ThreadSanitizer cannot start under 32-bit mmap ASLR entropy and the runner
# units lock personality(), so it cannot re-exec with ASLR off either.
# 28 matches GitHub's hosted Ubuntu images.
vm.mmap_rnd_bits = 28
CONF

sysctl --quiet --load="$conf"
current="$(sysctl -n vm.mmap_rnd_bits)"
if [[ "$current" != "28" ]]; then
  echo "why: vm.mmap_rnd_bits is $current after loading $conf, so TSan will still refuse to start; remedy: check for a later sysctl.d file overriding it (sysctl --system lists load order)" >&2
  exit 70
fi
printf 'vm.mmap_rnd_bits\t%s\t%s\n' "$current" "$conf"
