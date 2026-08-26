#!/usr/bin/env bash
# Read-only verification of the elastic runner topology on this host (#327).
# Prints inventory, enablement, hardening, priorities, slice bounds, and one
# controller dry-run decision. Mutates nothing.
set -euo pipefail

config="${1:-/etc/lmdj/elastic-runner.json}"

echo "== host"
hostname; nproc; free -h | head -2; swapon --show || true

echo "== slice"
systemctl show lmdj-ci.slice -p CPUQuotaPerSecUSec -p MemoryMax --no-pager

echo "== services"
python3 -c '
import json, sys
cfg = json.load(open(sys.argv[1]))
for kind in ("baseline", "elastic"):
    for e in cfg[kind]:
        print(kind, e["service"], e["user"], ",".join(e["roles"]))
' "$config" | while read -r kind unit user roles; do
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  active="$(systemctl is-active "$unit" 2>/dev/null || true)"
  weight="$(systemctl show "$unit" -p CPUWeight --value 2>/dev/null || true)"
  hardened="$(systemctl show "$unit" -p NoNewPrivileges --value 2>/dev/null || true)"
  slice="$(systemctl show "$unit" -p Slice --value 2>/dev/null || true)"
  workdir="$(systemctl show "$unit" -p WorkingDirectory --value 2>/dev/null || true)"
  echo "$kind $unit user=$user roles=$roles enabled=$enabled active=$active cpu_weight=$weight no_new_privs=$hardened slice=$slice workdir=$workdir"
done

echo "== runner users"
grep "^lmdj-runner-" /etc/passwd || true
for user in $(grep -o "^lmdj-runner-[0-9]*" /etc/passwd); do
  echo "$user groups: $(id -nG "$user")"
done

echo "== controller"
systemctl is-enabled lmdj-elastic-runner.timer || true
systemctl is-active lmdj-elastic-runner.timer || true
python3 /usr/local/lib/lmdj/elastic_runner.py --config "$config" \
  --state /var/lib/lmdj-elastic/state.json --dry-run
echo "== controller state"
cat /var/lib/lmdj-elastic/state.json 2>/dev/null || echo "(no state yet)"
