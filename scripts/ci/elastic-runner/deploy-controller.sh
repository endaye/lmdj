#!/usr/bin/env bash
# Install or update the elastic runner controller on a trusted Linux host (#327).
#
# Runs ON the host as root, from a directory holding elastic_runner.py, the
# host's config JSON, and the two controller unit files.
#
# Usage: deploy-controller.sh <config.json>
set -euo pipefail

config="${1:?usage: deploy-controller.sh <config.json>}"
here="$(cd "$(dirname "$0")" && pwd)"

python3 - "$config" <<'EOF'
import json, sys
json.load(open(sys.argv[1]))
EOF

install -d -o root -g root -m 0755 /usr/local/lib/lmdj /etc/lmdj
install -o root -g root -m 0755 "$here/elastic_runner.py" /usr/local/lib/lmdj/elastic_runner.py
install -o root -g root -m 0644 "$config" /etc/lmdj/elastic-runner.json
install -o root -g root -m 0644 "$here/lmdj-elastic-runner.service" /etc/systemd/system/lmdj-elastic-runner.service
install -o root -g root -m 0644 "$here/lmdj-elastic-runner.timer" /etc/systemd/system/lmdj-elastic-runner.timer

# Baseline services outrank elastic ones under contention: the admission
# guards cannot shed load already admitted, so priority is set at the unit.
baseline_units="$(python3 -c '
import json, sys
for entry in json.load(open(sys.argv[1]))["baseline"]:
    print(entry["service"])
' /etc/lmdj/elastic-runner.json)"
for unit in $baseline_units; do
  install -d -o root -g root -m 0755 "/etc/systemd/system/${unit}.d"
  printf '[Service]\nCPUWeight=300\n' > "/etc/systemd/system/${unit}.d/20-lmdj-priority.conf"
  # set-property applies the weight to the live cgroup immediately, so a busy
  # baseline runner does not need a restart for the drop-in to matter.
  systemctl set-property --runtime "$unit" CPUWeight=300 2>/dev/null || true
  echo "priority drop-in written for ${unit}"
done

systemctl daemon-reload
systemctl enable --now lmdj-elastic-runner.timer

# One dry run proves the controller can observe and decide on this host.
python3 /usr/local/lib/lmdj/elastic_runner.py \
  --config /etc/lmdj/elastic-runner.json \
  --state /var/lib/lmdj-elastic/state.json --dry-run
echo "controller deployed; timer $(systemctl is-enabled lmdj-elastic-runner.timer)/$(systemctl is-active lmdj-elastic-runner.timer)"
